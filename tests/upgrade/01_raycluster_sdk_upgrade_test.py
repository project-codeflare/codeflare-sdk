import os
import pytest
import requests
from time import sleep

from codeflare_sdk import Cluster, ClusterConfiguration
from codeflare_sdk.ray.client import RayJobClient

from tests.e2e.support import *
from codeflare_sdk.ray.cluster.cluster import get_cluster

from codeflare_sdk.common import _kube_api_error_handling

from tests.upgrade.constants import (
    CLUSTER_QUEUE as cluster_queue,
    LOCAL_QUEUE as local_queue,
    NAMESPACE as namespace,
    RESOURCE_FLAVOR as flavor,
)


# Creates a Ray cluster
@pytest.mark.pre_upgrade
class TestMNISTRayClusterApply:
    def setup_method(self):
        initialize_kubernetes_client(self)
        create_namespace_with_name(self, namespace)
        try:
            create_cluster_queue(self, cluster_queue, flavor)
            create_resource_flavor(self, flavor)
            create_local_queue(self, cluster_queue, local_queue)
            # Populate plural lists used by delete_kueue_resources
            self.cluster_queues = [cluster_queue]
            self.resource_flavors = [flavor]
        except Exception as e:
            delete_namespace(self)
            delete_kueue_resources(self)
            return _kube_api_error_handling(e)

    @pytest.fixture(autouse=True)
    def cleanup_on_failure(self, request):
        """Fixture to cleanup namespace and resources if pre-upgrade test fails"""
        # This runs after the test
        yield

        # Check if the test failed
        test_failed = (
            request.node.rep_call.failed if hasattr(request.node, "rep_call") else False
        )

        if test_failed:
            print(
                f"\n=== Pre-upgrade test failed, cleaning up namespace: {namespace} ==="
            )
            try:
                delete_namespace(self)
                delete_kueue_resources(self)
                print(f"Successfully cleaned up namespace: {namespace}")
            except Exception as e:
                print(f"Warning: Failed to cleanup namespace {namespace}: {e}")

    def test_mnist_ray_cluster_sdk_auth(self):
        self.run_mnist_raycluster_sdk_oauth()

    def run_mnist_raycluster_sdk_oauth(self):
        ray_image = get_ray_image()

        # Set up authentication based on detected method
        auth_instance = authenticate_for_tests()

        # Store auth instance for cleanup
        self.auth_instance = auth_instance

        cluster = Cluster(
            ClusterConfiguration(
                name="mnist",
                namespace=self.namespace,
                num_workers=1,
                head_cpu_requests=1,
                head_cpu_limits=1,
                head_memory_requests=6,
                head_memory_limits=8,
                worker_cpu_requests=1,
                worker_cpu_limits=1,
                worker_memory_requests=6,
                worker_memory_limits=8,
                image=ray_image,
                local_queue=local_queue,
                write_to_file=True,
                verify_tls=False,
            )
        )

        try:
            cluster.apply()
            cluster.status()
            # wait for raycluster to be Ready
            wait_ready_with_stuck_detection(cluster)
            cluster.status()
            # Check cluster details
            cluster.details()
            # Assert the cluster status is READY
            _, ready = cluster.status()
            assert ready

        except Exception as e:
            print(f"An unexpected error occurred. Error: ", e)
            delete_namespace(self)
            assert False, "Cluster is not ready!"


@pytest.mark.post_upgrade
class TestMnistJobSubmit:
    def setup_method(self):
        initialize_kubernetes_client(self)

        # Set up authentication based on detected method
        auth_instance = authenticate_for_tests()

        # Store auth instance for cleanup
        self.auth_instance = auth_instance

        self.namespace = namespace
        self.cluster = get_cluster("mnist", self.namespace, verify_tls=False)
        if not self.cluster:
            raise RuntimeError("TestRayClusterUp needs to be run before this test")

    def test_mnist_job_submission(self):
        self.assert_jobsubmit_withoutLogin(self.cluster)
        self.assert_jobsubmit_withlogin(self.cluster)

    # Assertions
    def assert_jobsubmit_withoutLogin(self, cluster):
        dashboard_url = cluster.cluster_dashboard_uri()

        # Check if this is a BYOIDC cluster
        is_byoidc_cluster = is_byoidc_cluster_detected()

        # For BYOIDC clusters, authentication is enforced at the gateway level
        if is_byoidc_cluster:
            print("Skipping unauthenticated job submission test for BYOIDC cluster")
            print("BYOIDC authentication is enforced at the gateway level")
            print("Verifying that dashboard requires authentication...")

            try:
                response = requests.get(
                    dashboard_url, verify=False, allow_redirects=False
                )
                if response.status_code in [302, 401, 403]:
                    print(
                        f"✓ Dashboard properly redirects unauthenticated access (status: {response.status_code})"
                    )
                    print("✓ BYOIDC authentication enforcement verified")
                    return
                else:
                    print(
                        f"Warning: Dashboard returned unexpected status {response.status_code} for unauthenticated access"
                    )
            except Exception as e:
                print(f"Error testing dashboard authentication: {e}")
            return

        # For non-BYOIDC clusters, verify that job submission is blocked without auth
        if "/ray/" in dashboard_url:
            api_url = dashboard_url + "/api/jobs/"
        else:
            api_url = dashboard_url + "/api/jobs/"

        job_spec = get_upgrade_job_submission_spec()
        jobdata = {
            "entrypoint": job_spec["entrypoint"],
            "runtime_env": job_spec["runtime_env"],
        }

        response = requests.post(
            api_url, verify=False, json=jobdata, allow_redirects=True
        )

        submission_blocked = False

        if response.status_code == 403:
            submission_blocked = True
        elif response.status_code == 401:
            submission_blocked = True
        elif response.status_code == 302:
            submission_blocked = True
        elif response.status_code == 200:
            content_type = response.headers.get("Content-Type", "")
            if "text/html" in content_type or "application/json" not in content_type:
                submission_blocked = True
            else:
                try:
                    json_response = response.json()
                    if "job_id" in json_response or "submission_id" in json_response:
                        submission_blocked = False
                    else:
                        submission_blocked = True
                except ValueError:
                    submission_blocked = True

        if not submission_blocked:
            assert (
                False
            ), f"Job submission succeeded without authentication! Status: {response.status_code}, Response: {response.text[:200]}"

        try:
            client = RayJobClient(address=dashboard_url, verify=False)
            client.list_jobs()
            assert (
                False
            ), "RayJobClient succeeded without authentication - this should not be possible"
        except (
            requests.exceptions.JSONDecodeError,
            requests.exceptions.HTTPError,
            Exception,
        ):
            pass

        assert True, "Job submission without authentication was correctly blocked"

    def assert_jobsubmit_withlogin(self, cluster):
        ray_dashboard = cluster.cluster_dashboard_uri()

        is_byoidc_cluster = is_byoidc_cluster_detected()

        if is_byoidc_cluster:
            # On BYOIDC clusters oc whoami --show-token=true is unavailable.
            # Obtain an OIDC id_token via Keycloak password grant (same approach
            # as Jenkins loginByoidcUser / opendatahub-tests get_oidc_tokens).
            username = os.environ.get("OCP_ADMIN_USER_USERNAME", "")
            password = os.environ.get("OCP_ADMIN_USER_PASSWORD", "")
            if not username or not password:
                raise RuntimeError(
                    "OCP_ADMIN_USER_USERNAME and OCP_ADMIN_USER_PASSWORD must be set "
                    "for BYOIDC job submission"
                )
            issuer_url = get_byoidc_issuer_url()
            id_token, _ = get_oidc_tokens(username, password, issuer_url)
            if not id_token:
                raise RuntimeError(
                    "Failed to obtain OIDC token for Ray Dashboard authentication. "
                    "Check OCP_ADMIN_USER_PASSWORD."
                )
            auth_token = id_token
        else:
            # For non-BYOIDC clusters use the OpenShift OAuth token
            auth_token = run_oc_command(["whoami", "--show-token=true"])
        header = {"Authorization": f"Bearer {auth_token}"}
        client = RayJobClient(address=ray_dashboard, headers=header, verify=False)

        job_spec = get_upgrade_job_submission_spec()
        print(f"Submitting job: {job_spec['entrypoint']}")

        # Submit the job
        submission_id = client.submit_job(
            entrypoint=job_spec["entrypoint"],
            runtime_env=job_spec["runtime_env"],
        )
        print(f"Submitted job with ID: {submission_id}")
        done = False
        time = 0
        timeout = 900
        while not done:
            status = client.get_job_status(submission_id)
            if status.is_terminal():
                break
            if not done:
                print(status)
                if timeout and time >= timeout:
                    raise TimeoutError(f"job has timed out after waiting {timeout}s")
                sleep(5)
                time += 5

        logs = client.get_job_logs(submission_id)
        print(logs)

        self.assert_job_completion(status)

        client.delete_job(submission_id)

    def assert_job_completion(self, status):
        status_value = getattr(status, "value", status)
        if status_value == "SUCCEEDED":
            print(f"Job has completed: '{status_value}'")
            assert True
        else:
            print(f"Job has completed: '{status_value}'")
            assert False

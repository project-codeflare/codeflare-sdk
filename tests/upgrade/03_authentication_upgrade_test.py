# Copyright 2024 IBM, Red Hat
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import pytest
import requests
from time import sleep

from codeflare_sdk import Cluster, ClusterConfiguration, TokenAuthentication
from codeflare_sdk.ray.client import RayJobClient

from tests.e2e.support import *
from codeflare_sdk.ray.cluster.cluster import get_cluster

from codeflare_sdk.common import _kube_api_error_handling

namespace = "test-ns-auth-upgrade"
cluster_name = "auth-test-cluster"
cluster_queue = "auth-cluster-queue"
flavor = "auth-flavor"
local_queue = "auth-local-queue"


def validate_unauthenticated_request_blocked(cluster, context=""):
    """
    Validate that job submission without authentication is blocked.

    Args:
        cluster: The Ray cluster to test against
        context: Optional context string for error messages
    """
    dashboard_url = cluster.cluster_dashboard_uri()
    api_url = dashboard_url + "/api/jobs/"

    jobdata = {
        "entrypoint": "python -c 'print(\"Authentication test job\")'",
        "runtime_env": {
            "working_dir": "./tests/e2e/",
            "env_vars": get_setup_env_variables(),
        },
    }

    response = requests.post(api_url, verify=False, json=jobdata, allow_redirects=True)

    submission_blocked = False
    if response.status_code in (403, 401, 302):
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
        context_msg = f" {context}" if context else ""
        assert (
            False
        ), f"Job submission succeeded without authentication{context_msg}! Status: {response.status_code}, Response: {response.text[:200]}"

    try:
        client = RayJobClient(address=dashboard_url, verify=False)
        client.list_jobs()
        context_msg = f" {context}" if context else ""
        assert (
            False
        ), f"RayJobClient succeeded without authentication{context_msg} - this should not be possible"
    except (
        requests.exceptions.JSONDecodeError,
        requests.exceptions.HTTPError,
        Exception,
    ):
        pass

    context_msg = f" {context}" if context else ""
    assert (
        True
    ), f"Job submission without authentication was correctly blocked{context_msg}"


def validate_authenticated_request_succeeds(cluster, context=""):
    """
    Validate that job submission with authentication succeeds.

    Args:
        cluster: The Ray cluster to test against
        context: Optional context string for error messages
    """
    auth_token = run_oc_command(["whoami", "--show-token=true"])
    ray_dashboard = cluster.cluster_dashboard_uri()
    header = {"Authorization": f"Bearer {auth_token}"}
    client = RayJobClient(address=ray_dashboard, headers=header, verify=False)

    existing_jobs = client.list_jobs()
    if existing_jobs:
        job_ids = [
            job.job_id if hasattr(job, "job_id") else str(job) for job in existing_jobs
        ]
        assert False, (
            f"Found {len(existing_jobs)} existing job(s) before authenticated submission: {job_ids}. "
            "This indicates that the unauthenticated job submission test failed to properly block submission."
        )
    else:
        print(
            "Verified: No jobs exist from the previous unauthenticated submission attempt."
        )

    context_msg = f" {context}" if context else ""
    submission_id = client.submit_job(
        entrypoint=f"python -c 'print(\"Authentication test job completed successfully{context_msg}\")'",
        runtime_env={
            "working_dir": "./tests/e2e/",
            "env_vars": get_setup_env_variables(),
        },
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

    assert_job_completion(status, context)

    client.delete_job(submission_id)


def assert_job_completion(status, context=""):
    """Assert that the job completed successfully."""
    context_msg = f" {context}" if context else ""
    if status == "SUCCEEDED":
        print(f"Job has completed: '{status}'{context_msg}")
        assert True
    else:
        print(f"Job has completed: '{status}'{context_msg}")
        assert False, f"Job did not succeed{context_msg}, status: {status}"


def validate_authentication(cluster, context=""):
    """
    Complete authentication validation: both unauthenticated blocking and authenticated success.

    Args:
        cluster: The Ray cluster to test against
        context: Optional context string for error messages
    """
    print(f"\n=== Validating authentication{(' ' + context) if context else ''} ===")
    validate_unauthenticated_request_blocked(cluster, context)
    validate_authenticated_request_succeeds(cluster, context)


@pytest.mark.smoke
@pytest.mark.openshift
@pytest.mark.pre_upgrade
class TestAuthenticationPreUpgrade:
    """
    Pre-upgrade test: Create Ray cluster with authentication enabled.

    codeflare-operator handles authentication automatically. The cluster persists
    through the upgrade process.
    """

    def setup_method(self):
        """Initialize Kubernetes client and create test resources."""
        initialize_kubernetes_client(self)
        create_namespace_with_name(self, namespace)
        try:
            create_cluster_queue(self, cluster_queue, flavor)
            create_resource_flavor(self, flavor)
            create_local_queue(self, cluster_queue, local_queue)
        except Exception as e:
            delete_namespace(self)
            delete_kueue_resources(self)
            return _kube_api_error_handling(e)

    @pytest.fixture(autouse=True)
    def cleanup_on_failure(self, request):
        """Fixture to cleanup namespace and resources if pre-upgrade test fails."""
        yield

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

    def test_authentication_pre_upgrade(self):
        """Test that creates cluster with authentication and validates it works."""
        self.run_authentication_test()

    def run_authentication_test(self):
        """Create Ray cluster with authentication and validate authentication works."""
        ray_image = get_ray_image()

        auth = TokenAuthentication(
            token=run_oc_command(["whoami", "--show-token=true"]),
            server=run_oc_command(["whoami", "--show-server=true"]),
            skip_tls=True,
        )
        auth.login()

        cluster = Cluster(
            ClusterConfiguration(
                name=cluster_name,
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
                write_to_file=True,
                verify_tls=False,
                annotations={"odh.ray.io/secure-trusted-network": "true"},
            )
        )

        try:
            cluster.apply()
            cluster.status()
            cluster.wait_ready()
            cluster.status()
            cluster.details()
            _, ready = cluster.status()
            assert ready, "Cluster should be ready before upgrade"

            validate_authentication(cluster, context="pre-upgrade")

        except Exception as e:
            print(f"An unexpected error occurred. Error: {e}")
            delete_namespace(self)
            assert False, f"Pre-upgrade test failed: {e}"


@pytest.mark.smoke
@pytest.mark.openshift
@pytest.mark.post_upgrade
class TestAuthenticationPostUpgrade:
    """
    Post-upgrade test: Validate authentication still works after upgrade.

    Retrieves the cluster created in pre-upgrade and validates that authentication
    continues to work correctly after kuberay takes over authentication responsibility.
    """

    def setup_method(self):
        """Initialize Kubernetes client and retrieve existing cluster."""
        initialize_kubernetes_client(self)
        auth = TokenAuthentication(
            token=run_oc_command(["whoami", "--show-token=true"]),
            server=run_oc_command(["whoami", "--show-server=true"]),
            skip_tls=True,
        )
        auth.login()
        self.namespace = namespace
        self.cluster = get_cluster(cluster_name, self.namespace)
        if not self.cluster:
            raise RuntimeError(
                "TestAuthenticationPreUpgrade needs to be run before this test"
            )

    def test_authentication_post_upgrade(self):
        """Test that authentication still works correctly after upgrade."""
        validate_authentication(self.cluster, context="post-upgrade")

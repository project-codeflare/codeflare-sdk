import pytest
import requests
from time import sleep

from codeflare_sdk import Cluster, ClusterConfiguration, TokenAuthentication
from codeflare_sdk.ray.client import RayJobClient

from tests.e2e.support import *
from codeflare_sdk.ray.cluster.cluster import get_cluster

from codeflare_sdk.common import _kube_api_error_handling

namespace = "test-ns-rayupgrade"
cluster_queue = "cluster-queue-mnist"
flavor = "default-flavor-mnist"
local_queue = "local-queue-mnist"


@pytest.mark.pre_upgrade
class TestMNISTRayClusterApply:
    def setup_method(self):
        initialize_kubernetes_client(self)
        create_namespace_with_name(self, namespace)
        try:
            create_cluster_queue(self, cluster_queue, flavor)
            create_resource_flavor(self, flavor)
            create_local_queue(self, cluster_queue, local_queue)
            self.cluster_queues = [cluster_queue]
            self.resource_flavors = [flavor]
        except Exception as e:
            delete_namespace(self)
            delete_kueue_resources(self)
            return _kube_api_error_handling(e)

    @pytest.fixture(autouse=True)
    def cleanup_on_failure(self, request):
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
            except Exception as e:
                print(f"Warning: Failed to cleanup namespace {namespace}: {e}")

    def test_mnist_ray_cluster_sdk_auth(self):
        self.run_mnist_raycluster_sdk_oauth()

    def run_mnist_raycluster_sdk_oauth(self):
        ray_image = get_ray_image()

        auth = TokenAuthentication(
            token=run_oc_command(["whoami", "--show-token=true"]),
            server=run_oc_command(["whoami", "--show-server=true"]),
            skip_tls=True,
        )
        auth.login()

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
                write_to_file=True,
                verify_tls=False,
            )
        )

        try:
            cluster.up()
            cluster.status()
            cluster.wait_ready()
            cluster.status()
            cluster.details()
            _, ready = cluster.status()
            assert ready

        except Exception as e:
            print("An unexpected error occurred. Error: ", e)
            delete_namespace(self)
            assert False, "Cluster is not ready!"


@pytest.mark.post_upgrade
class TestMnistJobSubmit:
    def setup_method(self):
        initialize_kubernetes_client(self)
        auth = TokenAuthentication(
            token=run_oc_command(["whoami", "--show-token=true"]),
            server=run_oc_command(["whoami", "--show-server=true"]),
            skip_tls=True,
        )
        auth.login()
        self.namespace = namespace
        self.cluster = get_cluster("mnist", self.namespace)
        if not self.cluster:
            raise RuntimeError("TestMNISTRayClusterApply needs to be run before this test")

    def test_mnist_job_submission(self):
        self.assert_jobsubmit_withoutLogin(self.cluster)
        self.assert_jobsubmit_withlogin(self.cluster)

    def assert_jobsubmit_withoutLogin(self, cluster):
        dashboard_url = cluster.cluster_dashboard_uri()
        try:
            RayJobClient(address=dashboard_url, verify=False)
            assert False
        except Exception as e:
            if hasattr(e, "response") and e.response.status_code == 403:
                assert True
            else:
                print(f"An unexpected error occurred. Error: {e}")
                assert False

    def assert_jobsubmit_withlogin(self, cluster):
        auth_token = run_oc_command(["whoami", "--show-token=true"])
        ray_dashboard = cluster.cluster_dashboard_uri()
        header = {"Authorization": f"Bearer {auth_token}"}
        client = RayJobClient(address=ray_dashboard, headers=header, verify=False)

        submission_id = client.submit_job(
            entrypoint="python mnist.py",
            runtime_env={
                "working_dir": "./tests/e2e/",
                "pip": "./tests/e2e/mnist_pip_requirements.txt",
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

        self.assert_job_completion(status)

        client.delete_job(submission_id)

    def assert_job_completion(self, status):
        if status == "SUCCEEDED":
            print(f"Job has completed: '{status}'")
            assert True
        else:
            print(f"Job has completed: '{status}'")
            assert False

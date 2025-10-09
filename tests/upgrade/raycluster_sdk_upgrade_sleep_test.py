import requests
from time import sleep

from codeflare_sdk import (
    Cluster,
    ClusterConfiguration,
    TokenAuthentication,
    get_cluster,
)
from codeflare_sdk.ray.client import RayJobClient

from tests.e2e.support import *


from codeflare_sdk.common import _kube_api_error_handling

namespace = "test-ns-rayupgrade-sleep"
# Global variables for kueue resources
cluster_queue = "cluster-queue-mnist"
flavor = "default-flavor-mnist"
local_queue = "local-queue-mnist"


# Creates a Ray cluster , submit RayJob mnist script long running
class TestSetupSleepRayJob:
    def setup_method(self):
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
                head_memory_requests=4,
                head_memory_limits=4,
                worker_cpu_requests=1,
                worker_cpu_limits=1,
                worker_memory_requests=4,
                worker_memory_limits=4,
                image=ray_image,
                write_to_file=True,
                verify_tls=False,
            )
        )

        try:
            cluster.apply()
            cluster.status()
            # wait for raycluster to be Ready
            cluster.wait_ready()
            cluster.status()
            # Check cluster details
            cluster.details()
            # Assert the cluster status is READY
            _, ready = cluster.status()
            assert ready
            submission_id = self.assert_jobsubmit()
            print(f"Job submitted successfully, job submission id: ", submission_id)

        except Exception as e:
            print(f"An unexpected error occurred. Error: ", e)
            delete_namespace(self)
            delete_kueue_resources(self)
            assert False, "Cluster is not ready!"

    def assert_jobsubmit(self):
        auth_token = run_oc_command(["whoami", "--show-token=true"])
        cluster = get_cluster("mnist", namespace)
        cluster.details()
        ray_dashboard = cluster.cluster_dashboard_uri()
        header = {"Authorization": f"Bearer {auth_token}"}
        client = RayJobClient(address=ray_dashboard, headers=header, verify=False)

        # Submit the job
        submission_id = client.submit_job(
            entrypoint="python mnist_sleep.py",
            runtime_env={
                "working_dir": "./tests/e2e/",
                "pip": {"packages": ["torchvision==0.12.0"], "pip_check": False},
                "env_vars": get_setup_env_variables(),
            },
        )
        print(f"Submitted job with ID: {submission_id}")
        done = False
        time = 0
        timeout = 180
        while not done:
            status = client.get_job_status(submission_id)
            if status.is_terminal():
                break
            if status == "RUNNING":
                print(f"Job is Running: '{status}'")
                assert True
                break
            if not done:
                print(status)
                if timeout and time >= timeout:
                    raise TimeoutError(f"job has timed out after waiting {timeout}s")
                sleep(5)
                time += 5

        logs = client.get_job_logs(submission_id)
        print(logs)
        return submission_id


class TestVerifySleepRayJobRunning:
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
        self.cluster_queue = cluster_queue
        self.resource_flavor = flavor
        if not self.cluster:
            raise RuntimeError("TestSetupSleepRayJob needs to be run before this test")

    def teardown_method(self):
        delete_namespace(self)
        delete_kueue_resources(self)

    def test_mnist_job_running(self):
        client = self.get_ray_job_client(self.cluster)
        self.assertJobExists(client, 1)
        self.assertJobRunning(client)
        self.cluster.down()

    def get_ray_job_client(self, cluster):
        auth_token = run_oc_command(["whoami", "--show-token=true"])
        ray_dashboard = cluster.cluster_dashboard_uri()
        header = {"Authorization": f"Bearer {auth_token}"}
        return RayJobClient(address=ray_dashboard, headers=header, verify=False)

    # Assertions
    def assertJobExists(self, client, expectedJobsSize):
        job_list = client.list_jobs()
        assert len(job_list) == expectedJobsSize

    def assertJobRunning(self, client):
        job_list = client.list_jobs()
        submission_id = job_list[0].submission_id
        status = client.get_job_status(submission_id)
        if status == "RUNNING":
            print(f"Job is Running: '{status}'")
            assert True
        else:
            print(f"Job is not in Running state: '{status}'")
            assert False

import requests
import subprocess

from time import sleep

from codeflare_sdk import Cluster, ClusterConfiguration
from codeflare_sdk.ray.client import RayJobClient

import pytest

from support import *

# This test creates a Ray Cluster and covers the Ray Job submission functionality on Kind Cluster


@pytest.mark.kind
class TestRayClusterSDKKind:
    def setup_method(self):
        initialize_kubernetes_client(self)
        self.port_forward_process = None

    def cleanup_port_forward(self):
        if self.port_forward_process:
            self.port_forward_process.terminate()
            self.port_forward_process.wait(timeout=10)
            self.port_forward_process = None

    def teardown_method(self):
        self.cleanup_port_forward()
        delete_namespace(self)
        delete_kueue_resources(self)

    def test_mnist_ray_cluster_sdk_kind(self):
        self.setup_method()
        create_namespace(self)
        create_kueue_resources(self)
        self.run_mnist_raycluster_sdk_kind(accelerator="cpu")

    @pytest.mark.nvidia_gpu
    def test_mnist_ray_cluster_sdk_kind_nvidia_gpu(self):
        self.setup_method()
        create_namespace(self)
        create_kueue_resources(self)
        self.run_mnist_raycluster_sdk_kind(accelerator="gpu", number_of_gpus=1)

    def run_mnist_raycluster_sdk_kind(
        self, accelerator, gpu_resource_name="nvidia.com/gpu", number_of_gpus=0
    ):
        cluster = Cluster(
            ClusterConfiguration(
                name="mnist",
                namespace=self.namespace,
                num_workers=1,
                head_cpu_requests="500m",
                head_cpu_limits="500m",
                worker_cpu_requests="500m",
                worker_cpu_limits=1,
                worker_memory_requests=1,
                worker_memory_limits=4,
                worker_extended_resource_requests={gpu_resource_name: number_of_gpus},
                write_to_file=True,
                verify_tls=False,
            )
        )

        cluster.apply()

        cluster.status()

        # Disable dashboard check on KinD as HTTPRoute/Route is not available
        cluster.wait_ready(dashboard_check=False)

        cluster.status()

        cluster.details()

        self.assert_jobsubmit_withoutlogin_kind(cluster, accelerator, number_of_gpus)

        # Note: assert_get_cluster_and_jobsubmit uses cluster.job_client which requires
        # the dashboard URL (HTTPRoute/Route). Since this is not available on KinD,
        # we skip this call. Job submission is already tested above with port-forwarding.
        # This function is tested on OpenShift in mnist_raycluster_sdk_test.py

        cluster.down()

    # Assertions

    def assert_jobsubmit_withoutlogin_kind(self, cluster, accelerator, number_of_gpus):
        # Use port-forwarding to access the dashboard since HTTPRoute/Route is not available on KinD
        local_port = "8265"
        dashboard_port = "8265"
        cluster_name = cluster.config.name

        port_forward_cmd = [
            "kubectl",
            "port-forward",
            "-n",
            self.namespace,
            f"svc/{cluster_name}-head-svc",
            f"{local_port}:{dashboard_port}",
        ]
        self.port_forward_process = subprocess.Popen(
            port_forward_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )

        # Wait for port-forward to be ready
        sleep(5)

        ray_dashboard = f"http://localhost:{local_port}"
        client = RayJobClient(address=ray_dashboard, verify=False)

        try:
            submission_id = client.submit_job(
                entrypoint="python mnist.py",
                runtime_env={
                    "working_dir": "./tests/e2e/",
                    "pip": "./tests/e2e/mnist_pip_requirements.txt",
                    "env_vars": get_setup_env_variables(ACCELERATOR=accelerator),
                },
                entrypoint_num_gpus=number_of_gpus,
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
                        raise TimeoutError(
                            f"job has timed out after waiting {timeout}s"
                        )
                    sleep(5)
                    time += 5

            logs = client.get_job_logs(submission_id)
            print(logs)

            self.assert_job_completion(status)

            client.delete_job(submission_id)
        finally:
            self.cleanup_port_forward()

    def assert_job_completion(self, status):
        if status == "SUCCEEDED":
            print(f"Job has completed: '{status}'")
            assert True
        else:
            print(f"Job has completed: '{status}'")
            assert False

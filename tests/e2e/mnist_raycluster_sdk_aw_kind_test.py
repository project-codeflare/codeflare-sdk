import requests

from time import sleep

from codeflare_sdk import Cluster, ClusterConfiguration, TokenAuthentication
from codeflare_sdk.job import RayJobClient

import pytest

from support import *

# This test creates an AppWrapper containing a Ray Cluster and covers the Ray Job submission functionality on Kind Cluster


@pytest.mark.kind
class TestRayClusterSDKAppWrapperKind:
    def setup_method(self):
        initialize_kubernetes_client(self)

    def teardown_method(self):
        delete_namespace(self)

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
                head_cpus="500m",
                head_memory=2,
                worker_cpu_requests="500m",
                worker_cpu_limits=1,
                worker_memory_requests=1,
                worker_memory_limits=4,
                worker_extended_resource_requests={gpu_resource_name: number_of_gpus},
                write_to_file=True,
                verify_tls=False,
                appwrapper=True,
            )
        )

        cluster.up()

        cluster.status()

        cluster.wait_ready()

        cluster.status()

        cluster.details()

        self.assert_jobsubmit_withoutlogin_kind(cluster, accelerator, number_of_gpus)

    # Assertions

    def assert_jobsubmit_withoutlogin_kind(self, cluster, accelerator, number_of_gpus):
        ray_dashboard = cluster.cluster_dashboard_uri()
        client = RayJobClient(address=ray_dashboard, verify=False)

        submission_id = client.submit_job(
            entrypoint="python mnist.py",
            runtime_env={
                "working_dir": "./tests/e2e/",
                "pip": "./tests/e2e/mnist_pip_requirements.txt",
                "env_vars": {"ACCELERATOR": accelerator},
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
                    raise TimeoutError(f"job has timed out after waiting {timeout}s")
                sleep(5)
                time += 5

        logs = client.get_job_logs(submission_id)
        print(logs)

        self.assert_job_completion(status)

        client.delete_job(submission_id)

        cluster.down()

    def assert_job_completion(self, status):
        if status == "SUCCEEDED":
            print(f"Job has completed: '{status}'")
            assert True
        else:
            print(f"Job has completed: '{status}'")
            assert False

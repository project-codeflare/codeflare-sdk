from time import sleep

from codeflare_sdk import Cluster, ClusterConfiguration
from codeflare_sdk.ray.rayjobs import RayJob
from codeflare_sdk.ray.rayjobs.status import CodeflareRayJobStatus

import pytest

from support import *

# This test creates a Ray Cluster and then submits a RayJob against the existing cluster on Kind Cluster


@pytest.mark.kind
class TestRayJobExistingClusterKind:
    def setup_method(self):
        initialize_kubernetes_client(self)

    def teardown_method(self):
        delete_namespace(self)
        delete_kueue_resources(self)

    def test_rayjob_ray_cluster_sdk_kind(self):
        self.setup_method()
        create_namespace(self)
        create_kueue_resources(self)
        self.run_rayjob_against_existing_cluster_kind(accelerator="cpu")

    @pytest.mark.nvidia_gpu
    def test_rayjob_ray_cluster_sdk_kind_nvidia_gpu(self):
        self.setup_method()
        create_namespace(self)
        create_kueue_resources(self)
        self.run_rayjob_against_existing_cluster_kind(
            accelerator="gpu", number_of_gpus=1
        )

    def run_rayjob_against_existing_cluster_kind(
        self, accelerator, gpu_resource_name="nvidia.com/gpu", number_of_gpus=0
    ):
        cluster_name = "existing-cluster"
        cluster = Cluster(
            ClusterConfiguration(
                name=cluster_name,
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
        cluster.wait_ready()
        cluster.status()
        cluster.details()

        print(f"✅ Ray cluster '{cluster_name}' is ready")

        # test RayJob submission against the existing cluster
        self.assert_rayjob_submit_against_existing_cluster(
            cluster, accelerator, number_of_gpus
        )

        # Cleanup - manually tear down the cluster since job won't do it
        print("🧹 Cleaning up Ray cluster")
        cluster.down()

    def assert_rayjob_submit_against_existing_cluster(
        self, cluster, accelerator, number_of_gpus
    ):
        """
        Test RayJob submission against an existing Ray cluster.
        """
        cluster_name = cluster.config.name
        job_name = f"mnist-rayjob-{accelerator}"

        print(f"🚀 Testing RayJob submission against existing cluster '{cluster_name}'")

        # Create RayJob targeting the existing cluster
        rayjob = RayJob(
            job_name=job_name,
            cluster_name=cluster_name,
            namespace=self.namespace,
            entrypoint="python mnist.py",
            runtime_env={
                "working_dir": "./tests/e2e/",
                "pip": "./tests/e2e/mnist_pip_requirements.txt",
                "env_vars": get_setup_env_variables(ACCELERATOR=accelerator),
            },
            shutdown_after_job_finishes=False,  # Don't shutdown the existing cluster
        )

        # Submit the job
        submission_result = rayjob.submit()
        assert (
            submission_result == job_name
        ), f"Job submission failed, expected {job_name}, got {submission_result}"
        print(f"✅ Successfully submitted RayJob '{job_name}' against existing cluster")

        # Monitor the job status until completion
        self.monitor_rayjob_completion(rayjob, timeout=900)

        print(f"✅ RayJob '{job_name}' completed successfully against existing cluster!")

    def monitor_rayjob_completion(self, rayjob: RayJob, timeout: int = 900):
        """
        Monitor a RayJob until it completes or fails.

        Args:
            rayjob: The RayJob instance to monitor
            timeout: Maximum time to wait in seconds (default: 15 minutes)
        """
        print(f"⏳ Monitoring RayJob '{rayjob.name}' status...")

        elapsed_time = 0
        check_interval = 10  # Check every 10 seconds

        while elapsed_time < timeout:
            status, ready = rayjob.status(print_to_console=True)

            # Check if job has completed (either successfully or failed)
            if status == CodeflareRayJobStatus.COMPLETE:
                print(f"✅ RayJob '{rayjob.name}' completed successfully!")
                return
            elif status == CodeflareRayJobStatus.FAILED:
                raise AssertionError(f"❌ RayJob '{rayjob.name}' failed!")
            elif status == CodeflareRayJobStatus.RUNNING:
                print(f"🏃 RayJob '{rayjob.name}' is still running...")
            elif status == CodeflareRayJobStatus.UNKNOWN:
                print(f"❓ RayJob '{rayjob.name}' status is unknown")

            # Wait before next check
            sleep(check_interval)
            elapsed_time += check_interval

        # If we reach here, the job has timed out
        final_status, _ = rayjob.status(print_to_console=True)
        raise TimeoutError(
            f"⏰ RayJob '{rayjob.name}' did not complete within {timeout} seconds. "
            f"Final status: {final_status}"
        )

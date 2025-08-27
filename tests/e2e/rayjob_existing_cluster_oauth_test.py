import pytest
from time import sleep

from codeflare_sdk import (
    Cluster,
    ClusterConfiguration,
    TokenAuthentication,
)
from codeflare_sdk.ray.rayjobs import RayJob
from codeflare_sdk.ray.rayjobs.status import CodeflareRayJobStatus

from support import *

# This test creates a Ray Cluster and then submits a RayJob against the existing cluster on OpenShift


@pytest.mark.openshift
class TestRayJobExistingClusterOauth:
    def setup_method(self):
        initialize_kubernetes_client(self)

    def teardown_method(self):
        delete_namespace(self)
        delete_kueue_resources(self)

    def test_rayjob_against_existing_cluster_oauth(self):
        self.setup_method()
        create_namespace(self)
        create_kueue_resources(self)
        self.run_rayjob_against_existing_cluster_oauth()

    def run_rayjob_against_existing_cluster_oauth(self):
        ray_image = get_ray_image()

        auth = TokenAuthentication(
            token=run_oc_command(["whoami", "--show-token=true"]),
            server=run_oc_command(["whoami", "--show-server=true"]),
            skip_tls=True,
        )
        auth.login()

        cluster_name = "existing-cluster"

        cluster = Cluster(
            ClusterConfiguration(
                name=cluster_name,
                namespace=self.namespace,
                num_workers=1,
                head_cpu_requests="500m",
                head_cpu_limits="500m",
                worker_cpu_requests=1,
                worker_cpu_limits=1,
                worker_memory_requests=1,
                worker_memory_limits=4,
                image=ray_image,
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

        job_name = "existing-cluster-rayjob"

        rayjob = RayJob(
            job_name=job_name,
            cluster_name=cluster_name,
            namespace=self.namespace,
            entrypoint="python -c \"import ray; ray.init(); print('Hello from RayJob!'); print(f'Ray version: {ray.__version__}'); import time; time.sleep(30); print('RayJob completed successfully!')\"",
            runtime_env={
                "pip": ["torch", "pytorch-lightning", "torchmetrics", "torchvision"],
                "env_vars": get_setup_env_variables(ACCELERATOR="cpu"),
            },
            shutdown_after_job_finishes=False,
        )

        # Submit the job
        print(
            f"🚀 Submitting RayJob '{job_name}' against existing cluster '{cluster_name}'"
        )
        submission_result = rayjob.submit()
        assert (
            submission_result == job_name
        ), f"Job submission failed, expected {job_name}, got {submission_result}"
        print(f"✅ Successfully submitted RayJob '{job_name}'")

        # Monitor the job status until completion
        self.monitor_rayjob_completion(rayjob)

        # Cleanup - manually tear down the cluster since job won't do it
        print("🧹 Cleaning up Ray cluster")
        cluster.down()

    def monitor_rayjob_completion(self, rayjob: RayJob, timeout: int = 300):
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

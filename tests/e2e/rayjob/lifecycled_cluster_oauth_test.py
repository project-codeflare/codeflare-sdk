import pytest
import sys
import os
from time import sleep

# Add the parent directory to the path to import support
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from support import *

from codeflare_sdk import (
    TokenAuthentication,
    RayJob,
    ManagedClusterConfig,
)
from codeflare_sdk.ray.rayjobs.status import CodeflareRayJobStatus

# This test creates a RayJob that will create and lifecycle its own cluster on OpenShift


@pytest.mark.openshift
class TestRayJobLifecycledClusterOauth:
    def setup_method(self):
        initialize_kubernetes_client(self)

    def teardown_method(self):
        delete_namespace(self)
        delete_kueue_resources(self)

    def test_rayjob_with_lifecycled_cluster_oauth(self):
        self.setup_method()
        create_namespace(self)
        create_kueue_resources(self)
        self.run_rayjob_with_lifecycled_cluster_oauth()

    def run_rayjob_with_lifecycled_cluster_oauth(self):
        ray_image = get_ray_image()

        auth = TokenAuthentication(
            token=run_oc_command(["whoami", "--show-token=true"]),
            server=run_oc_command(["whoami", "--show-server=true"]),
            skip_tls=True,
        )
        auth.login()

        job_name = "lifecycled-cluster-rayjob"

        # Create cluster configuration for auto-creation
        cluster_config = ManagedClusterConfig(
            head_cpu_requests="500m",
            head_cpu_limits="500m",
            head_memory_requests=1,
            head_memory_limits=4,
            num_workers=1,
            worker_cpu_requests="500m",
            worker_cpu_limits="500m",
            worker_memory_requests=1,
            worker_memory_limits=4,
            image=ray_image,
        )

        # Create RayJob with embedded cluster - will auto-create and manage cluster lifecycle
        rayjob = RayJob(
            job_name=job_name,
            cluster_config=cluster_config,  # This triggers auto-cluster creation
            namespace=self.namespace,
            entrypoint="python -c \"import ray; ray.init(); print('Hello from auto-created cluster!'); print(f'Ray version: {ray.__version__}'); import time; time.sleep(30); print('RayJob completed successfully!')\"",
            runtime_env={
                "pip": ["torch", "pytorch-lightning", "torchmetrics", "torchvision"],
                "env_vars": get_setup_env_variables(ACCELERATOR="cpu"),
            },
            shutdown_after_job_finishes=True,  # Auto-cleanup cluster after job finishes
            ttl_seconds_after_finished=30,  # Wait 30s after job completion before cleanup
        )

        # Submit the job
        print(
            f"Submitting RayJob '{job_name}' with auto-cluster creation and lifecycle management"
        )
        submission_result = rayjob.submit()
        assert (
            submission_result == job_name
        ), f"Job submission failed, expected {job_name}, got {submission_result}"
        print(
            f"Successfully submitted RayJob '{job_name}' with cluster '{rayjob.cluster_name}'!"
        )

        # Monitor the job status until completion
        self.monitor_rayjob_completion(rayjob)

        # Verify cluster auto-cleanup
        print("🔍 Verifying cluster auto-cleanup after job completion...")
        self.verify_cluster_cleanup(rayjob.cluster_name, timeout=60)

    def monitor_rayjob_completion(self, rayjob: RayJob, timeout: int = 900):
        """
        Monitor a RayJob until it completes or fails.
        Args:
            rayjob: The RayJob instance to monitor
            timeout: Maximum time to wait in seconds (default: 15 minutes)
        """
        print(f"Monitoring RayJob '{rayjob.name}' status...")

        elapsed_time = 0
        check_interval = 10  # Check every 10 seconds

        while elapsed_time < timeout:
            status, ready = rayjob.status(print_to_console=True)

            # Check if job has completed (either successfully or failed)
            if status == CodeflareRayJobStatus.COMPLETE:
                print(f"RayJob '{rayjob.name}' completed successfully!")
                return
            elif status == CodeflareRayJobStatus.FAILED:
                raise AssertionError(f"RayJob '{rayjob.name}' failed!")
            elif status == CodeflareRayJobStatus.RUNNING:
                print(f"RayJob '{rayjob.name}' is still running...")
            elif status == CodeflareRayJobStatus.UNKNOWN:
                print(f"RayJob '{rayjob.name}' status is unknown")

            # Wait before next check
            sleep(check_interval)
            elapsed_time += check_interval

        # If we reach here, the job has timed out
        final_status, _ = rayjob.status(print_to_console=True)
        raise TimeoutError(
            f"RayJob '{rayjob.name}' did not complete within {timeout} seconds. "
            f"Final status: {final_status}"
        )

    def verify_cluster_cleanup(self, cluster_name: str, timeout: int = 60):
        """
        Verify that the cluster created by the RayJob has been cleaned up.
        Args:
            cluster_name: The name of the cluster to check for cleanup
            timeout: Maximum time to wait for cleanup in seconds (default: 1 minute)
        """
        from kubernetes import client
        import kubernetes.client.rest

        elapsed_time = 0
        check_interval = 5  # Check every 5 seconds

        while elapsed_time < timeout:
            try:
                # Try to get the RayCluster resource
                custom_api = client.CustomObjectsApi()
                custom_api.get_namespaced_custom_object(
                    group="ray.io",
                    version="v1",
                    namespace=self.namespace,
                    plural="rayclusters",
                    name=cluster_name,
                )
                print(f"Cluster '{cluster_name}' still exists, waiting for cleanup...")
                sleep(check_interval)
                elapsed_time += check_interval
            except kubernetes.client.rest.ApiException as e:
                if e.status == 404:
                    print(
                        f"✅ Cluster '{cluster_name}' has been successfully cleaned up!"
                    )
                    return
                else:
                    raise e

        # If we reach here, the cluster was not cleaned up in time
        raise TimeoutError(
            f"Cluster '{cluster_name}' was not cleaned up within {timeout} seconds"
        )

import pytest
import sys
import os
from time import sleep

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from support import *

from codeflare_sdk import (
    Cluster,
    ClusterConfiguration,
)
from codeflare_sdk import RayJob
from codeflare_sdk.ray.rayjobs.status import CodeflareRayJobStatus
from codeflare_sdk.vendored.python_client.kuberay_job_api import RayjobApi


@pytest.mark.tier1
class TestRayJobExistingCluster:
    """Test RayJob against existing Kueue-managed clusters."""

    def setup_method(self):
        initialize_kubernetes_client(self)

    def teardown_method(self):
        # Clean up authentication if needed
        if hasattr(self, "auth_instance"):
            cleanup_authentication(self.auth_instance)
        delete_namespace(self)
        delete_kueue_resources(self)

    def test_existing_kueue_cluster(self):
        """Test RayJob against Kueue-managed RayCluster."""
        self.setup_method()
        create_namespace(self)
        create_kueue_resources(self)

        cluster_name = "kueue-cluster"

        if is_openshift():
            # Set up authentication based on detected method
            auth_instance = authenticate_for_tests()

            # Store auth instance for cleanup
            self.auth_instance = auth_instance

        resources = get_platform_appropriate_resources()

        cluster = Cluster(
            ClusterConfiguration(
                name=cluster_name,
                namespace=self.namespace,
                num_workers=1,
                head_cpu_requests=resources["head_cpu_requests"],
                head_cpu_limits=resources["head_cpu_limits"],
                head_memory_requests=resources["head_memory_requests"],
                head_memory_limits=resources["head_memory_limits"],
                worker_cpu_requests=resources["worker_cpu_requests"],
                worker_cpu_limits=resources["worker_cpu_limits"],
                worker_memory_requests=resources["worker_memory_requests"],
                worker_memory_limits=resources["worker_memory_limits"],
                image=constants.CUDA_PY312_RUNTIME_IMAGE,
                local_queue=self.local_queues[0],
                write_to_file=True,
                verify_tls=False,
            )
        )

        cluster.apply()

        # Wait for cluster to be ready (with Kueue admission)
        # On KinD, disable dashboard check as HTTPRoute/Route is not available
        print(f"Waiting for cluster '{cluster_name}' to be ready...")
        wait_ready_with_stuck_detection(
            cluster, timeout=600, dashboard_check=is_openshift()
        )
        print(f"✓ Cluster '{cluster_name}' is ready")

        # RayJob with explicit local_queue (will be ignored for existing clusters)
        # Kueue does not manage RayJobs targeting existing clusters
        rayjob_explicit = RayJob(
            job_name="job-explicit-queue",
            cluster_name=cluster_name,
            namespace=self.namespace,
            entrypoint="python -c \"import ray; ray.init(); print('Job with explicit queue')\"",
            runtime_env={"env_vars": get_setup_env_variables(ACCELERATOR="cpu")},
            local_queue=self.local_queues[0],  # Ignored for existing clusters
        )

        # RayJob without queue (no Kueue labels for existing clusters)
        rayjob_default = RayJob(
            job_name="job-default-queue",
            cluster_name=cluster_name,
            namespace=self.namespace,
            entrypoint="python -c \"import ray; ray.init(); print('Job with default queue')\"",
            runtime_env={"env_vars": get_setup_env_variables(ACCELERATOR="cpu")},
        )

        try:
            # Test RayJob with explicit queue
            assert rayjob_explicit.submit() == "job-explicit-queue"
            self._wait_completion(rayjob_explicit)

            # Test RayJob with default queue
            assert rayjob_default.submit() == "job-default-queue"
            self._wait_completion(rayjob_default)
        finally:
            rayjob_explicit.delete()
            rayjob_default.delete()
            cluster.down()

    def _wait_completion(self, rayjob: RayJob, timeout: int = 600):
        """Wait for RayJob completion."""
        elapsed = 0
        interval = 10

        while elapsed < timeout:
            status, _ = rayjob.status(print_to_console=False)
            if status == CodeflareRayJobStatus.COMPLETE:
                return
            elif status == CodeflareRayJobStatus.FAILED:
                raise AssertionError(f"RayJob '{rayjob.name}' failed")
            sleep(interval)
            elapsed += interval

        raise TimeoutError(f"RayJob '{rayjob.name}' timeout after {timeout}s")

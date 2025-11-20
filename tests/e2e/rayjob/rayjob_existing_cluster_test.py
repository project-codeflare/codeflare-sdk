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
from codeflare_sdk import RayJob, TokenAuthentication
from codeflare_sdk.ray.rayjobs.status import CodeflareRayJobStatus
from codeflare_sdk.vendored.python_client.kuberay_job_api import RayjobApi


@pytest.mark.tier1
class TestRayJobExistingCluster:
    """Test RayJob against existing Kueue-managed clusters."""

    def setup_method(self):
        initialize_kubernetes_client(self)

    def teardown_method(self):
        delete_namespace(self)
        delete_kueue_resources(self)

    def test_existing_kueue_cluster(self):
        """Test RayJob against Kueue-managed RayCluster."""
        self.setup_method()
        create_namespace(self)
        create_kueue_resources(self)

        cluster_name = "kueue-cluster"

        if is_openshift():
            auth = TokenAuthentication(
                token=run_oc_command(["whoami", "--show-token=true"]),
                server=run_oc_command(["whoami", "--show-server=true"]),
                skip_tls=True,
            )
            auth.login()

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
        print(f"Waiting for cluster '{cluster_name}' to be ready...")
        cluster.wait_ready(timeout=600)
        print(f"✓ Cluster '{cluster_name}' is ready")

        # RayJob with explicit local_queue
        rayjob_explicit = RayJob(
            job_name="job-explicit-queue",
            cluster_name=cluster_name,
            namespace=self.namespace,
            entrypoint="python -c \"import ray; ray.init(); print('Job with explicit queue')\"",
            runtime_env={"env_vars": get_setup_env_variables(ACCELERATOR="cpu")},
            local_queue=self.local_queues[0],
        )

        # RayJob using default queue
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

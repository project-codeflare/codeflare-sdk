"""
Test RayJob CR with lifecycled clusters using RayCluster object.

Tests that RayJob can create and manage clusters using the new RayCluster object.
"""

import pytest
from codeflare_sdk import RayCluster, RayJob
from codeflare_sdk.common.kubernetes_cluster.auth import TokenAuthentication
from codeflare_sdk.vendored.python_client.kuberay_cluster_api import RayClusterApi

from ...utils.helpers import (
    wait_for_job_finished,
    get_job_status,
    assert_job_succeeded,
    verify_rayjob_cluster_cleanup,
)
from ...utils.support import run_oc_command


@pytest.mark.tier1
class TestRayJobCRLifecycledCluster:
    """Test RayJob with lifecycled clusters using RayCluster object."""

    CPU_CONFIG = 0
    GPU_CONFIG = pytest.param(1, marks=pytest.mark.gpu)

    @pytest.mark.openshift
    @pytest.mark.parametrize("num_gpus", [CPU_CONFIG, GPU_CONFIG])
    def test_openshift_rayjob_with_raycluster(
        self,
        num_gpus,
        require_gpu_flag,
        test_namespace_with_kueue,
        ray_image,
        platform_resources,
    ):
        auth = TokenAuthentication(
            token=run_oc_command(["whoami", "--show-token=true"]),
            server=run_oc_command(["whoami", "--show-server=true"]),
            skip_tls=True,
        )
        auth.login()

        self._run_rayjob_test(
            num_gpus=num_gpus,
            test_namespace_with_kueue=test_namespace_with_kueue,
            ray_image=ray_image,
            platform_resources=platform_resources,
        )

    @pytest.mark.kind
    @pytest.mark.parametrize("num_gpus", [CPU_CONFIG, GPU_CONFIG])
    def test_kind_rayjob_with_raycluster(
        self,
        num_gpus,
        require_gpu_flag,
        test_namespace_with_kueue,
        ray_image,
        platform_resources,
    ):
        self._run_rayjob_test(
            num_gpus=num_gpus,
            test_namespace_with_kueue=test_namespace_with_kueue,
            ray_image=ray_image,
            platform_resources=platform_resources,
        )

    def _run_rayjob_test(
        self,
        num_gpus,
        test_namespace_with_kueue,
        ray_image,
        platform_resources,
    ):
        test_namespace = test_namespace_with_kueue["namespace"]
        local_queue = test_namespace_with_kueue["local_queues"][0]

        job_name = f"test-rayjob-{test_namespace}"

        head_accelerators = {"nvidia.com/gpu": num_gpus} if num_gpus > 0 else {}
        worker_accelerators = {"nvidia.com/gpu": num_gpus} if num_gpus > 0 else {}

        cluster_config = RayCluster(
            namespace=test_namespace,
            num_workers=1,
            head_cpu_requests=platform_resources["head_cpu_requests"],
            head_cpu_limits=platform_resources["head_cpu_limits"],
            head_memory_requests=platform_resources["head_memory_requests"],
            head_memory_limits=platform_resources["head_memory_limits"],
            head_accelerators=head_accelerators,
            worker_cpu_requests=platform_resources["worker_cpu_requests"],
            worker_cpu_limits=platform_resources["worker_cpu_limits"],
            worker_memory_requests=platform_resources["worker_memory_requests"],
            worker_memory_limits=platform_resources["worker_memory_limits"],
            worker_accelerators=worker_accelerators,
            image=ray_image,
            local_queue=local_queue,
        )

        if num_gpus > 0:
            entrypoint = "python tests/e2e_v2/utils/scripts/gpu_script.py"
        else:
            entrypoint = "python tests/e2e_v2/utils/scripts/cpu_script.py"

        rayjob = RayJob(
            job_name=job_name,
            entrypoint=entrypoint,
            cluster_config=cluster_config,
            namespace=test_namespace,
        )

        cluster_api = RayClusterApi()

        try:
            rayjob.submit()

            assert wait_for_job_finished(
                job_name=job_name, namespace=test_namespace, timeout=600
            ), f"RayJob '{job_name}' did not finish within timeout"

            status = get_job_status(job_name, test_namespace)
            assert_job_succeeded(status, job_name)

        finally:
            try:
                rayjob.delete()
            except Exception:
                pass

            # Verify the lifecycled RayCluster is cleaned up after job deletion
            verify_rayjob_cluster_cleanup(
                cluster_api=cluster_api,
                rayjob_name=job_name,
                namespace=test_namespace,
                timeout=60,
            )

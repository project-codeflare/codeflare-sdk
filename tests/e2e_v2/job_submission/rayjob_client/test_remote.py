import time

import pytest
from codeflare_sdk import RayCluster
from codeflare_sdk.common.kubernetes_cluster.auth import TokenAuthentication
from codeflare_sdk.ray.client import RayJobClient

from ...utils.support import run_oc_command


@pytest.mark.tier1
class TestRayJobClientWithRayCluster:
    """Test RayJobClient with RayCluster object."""

    CPU_CONFIG = 0
    GPU_CONFIG = pytest.param(1, marks=pytest.mark.gpu)

    @pytest.mark.openshift
    @pytest.mark.parametrize("num_gpus", [CPU_CONFIG, GPU_CONFIG])
    def test_openshift_rayjob_client_with_raycluster(
        self,
        num_gpus,
        require_gpu_flag,
        test_namespace,
        ray_image,
        platform_resources,
        auth_token,
    ):
        auth = TokenAuthentication(
            token=run_oc_command(["whoami", "--show-token=true"]),
            server=run_oc_command(["whoami", "--show-server=true"]),
            skip_tls=True,
        )
        auth.login()

        self._run_rayjob_client_test(
            num_gpus=num_gpus,
            test_namespace=test_namespace,
            ray_image=ray_image,
            platform_resources=platform_resources,
            auth_token=auth_token,
        )

    @pytest.mark.kind
    @pytest.mark.parametrize("num_gpus", [CPU_CONFIG, GPU_CONFIG])
    def test_kind_rayjob_client_with_raycluster(
        self,
        num_gpus,
        require_gpu_flag,
        test_namespace,
        ray_image,
        platform_resources,
    ):
        self._run_rayjob_client_test(
            num_gpus=num_gpus,
            test_namespace=test_namespace,
            ray_image=ray_image,
            platform_resources=platform_resources,
            auth_token=None,
        )

    def _run_rayjob_client_test(
        self,
        num_gpus,
        test_namespace,
        ray_image,
        platform_resources,
        auth_token,
    ):
        cluster_name = f"test-client-cluster-{test_namespace}"

        head_accelerators = {"nvidia.com/gpu": num_gpus} if num_gpus > 0 else {}
        worker_accelerators = {"nvidia.com/gpu": num_gpus} if num_gpus > 0 else {}

        cluster = RayCluster(
            name=cluster_name,
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
            verify_tls=False,
        )

        try:
            cluster.apply()
            cluster.wait_ready(timeout=300)

            dashboard_url = cluster.cluster_dashboard_uri()
            assert dashboard_url, "Dashboard URL should be available"

            # Create job client with auth if on OpenShift
            if auth_token:
                headers = {"Authorization": f"Bearer {auth_token}"}
                client = RayJobClient(
                    address=dashboard_url, headers=headers, verify=False
                )
            else:
                client = RayJobClient(address=dashboard_url, verify=False)

            # Submit a job using the appropriate script
            if num_gpus > 0:
                script = "gpu_script.py"
            else:
                script = "cpu_script.py"

            submission_id = client.submit_job(
                entrypoint=f"python {script}",
                runtime_env={"working_dir": "./tests/e2e_v2/utils/scripts/"},
            )

            # Wait for job to complete with exception handling
            timeout = 600
            elapsed = 0
            status = None
            while elapsed < timeout:
                try:
                    status = client.get_job_status(submission_id)
                    if status.is_terminal():
                        break
                except Exception as e:
                    print(f"Error getting job status: {e}")
                time.sleep(5)
                elapsed += 5
            else:
                raise TimeoutError(f"Job timed out after {timeout}s")

            # Get logs before assertion for debugging
            logs = client.get_job_logs(submission_id)
            if status != "SUCCEEDED":
                print(f"Job failed. Logs:\n{logs}")

            assert status == "SUCCEEDED", f"Job should succeed, got status: {status}"
            assert (
                "EXISTING_CLUSTER_JOB_SUCCESS" in logs
            ), "Job should print success marker"

            client.delete_job(submission_id)

        finally:
            cluster.down()

"""
Test RayJob CR submission to existing clusters.
"""

import textwrap

import pytest

from codeflare_sdk import Cluster, ClusterConfiguration, RayJob
from codeflare_sdk.common.kubernetes_cluster.auth import TokenAuthentication

from ...utils.support import (
    create_kueue_resources,
    delete_kueue_resources,
    initialize_kubernetes_client,
    create_namespace,
    delete_namespace,
    get_ray_image,
    run_oc_command,
)
from ...utils.helpers import wait_for_job_finished, get_job_status, assert_job_succeeded
from ...utils.in_cluster import run_code_in_pod


class TestRayJobCRExistingCluster:
    CPU_CONFIG = 0
    GPU_CONFIG = pytest.param(1, marks=pytest.mark.gpu)

    def setup_method(self):
        initialize_kubernetes_client(self)

    def teardown_method(self):
        delete_kueue_resources(self)
        delete_namespace(self)

    @pytest.mark.openshift
    @pytest.mark.parametrize("num_gpus", [CPU_CONFIG, GPU_CONFIG])
    def test_openshift_remote_submission(self, num_gpus, require_gpu_flag):
        auth = TokenAuthentication(
            token=run_oc_command(["whoami", "--show-token=true"]),
            server=run_oc_command(["whoami", "--show-server=true"]),
            skip_tls=True,
        )
        auth.login()

        self.run_remote_submission(num_gpus=num_gpus)

    @pytest.mark.kind
    @pytest.mark.parametrize("num_gpus", [CPU_CONFIG, GPU_CONFIG])
    def test_kind_remote_submission(self, num_gpus, require_gpu_flag):
        self.run_remote_submission(num_gpus=num_gpus)

    @pytest.mark.openshift
    @pytest.mark.parametrize("num_gpus", [CPU_CONFIG, GPU_CONFIG])
    def test_openshift_in_cluster_submission(self, num_gpus, require_gpu_flag):
        auth = TokenAuthentication(
            token=run_oc_command(["whoami", "--show-token=true"]),
            server=run_oc_command(["whoami", "--show-server=true"]),
            skip_tls=True,
        )
        auth.login()

        self.run_in_cluster_submission(num_gpus=num_gpus)

    @pytest.mark.kind
    @pytest.mark.parametrize("num_gpus", [CPU_CONFIG, GPU_CONFIG])
    def test_kind_in_cluster_submission(self, num_gpus, require_gpu_flag):
        self.run_in_cluster_submission(num_gpus=num_gpus)

    def run_remote_submission(self, num_gpus):
        create_namespace(self)
        create_kueue_resources(self)

        cluster_name = "existing-cluster"

        cluster = Cluster(
            ClusterConfiguration(
                name=cluster_name,
                namespace=self.namespace,
                num_workers=1,
                head_extended_resource_requests={"nvidia.com/gpu": num_gpus},
                worker_extended_resource_requests={"nvidia.com/gpu": num_gpus},
                image=get_ray_image(),
                local_queue=self.local_queues[0],
                verify_tls=False,
            )
        )

        if num_gpus > 0:
            entrypoint = "python tests/e2e_v2/utils/scripts/gpu_script.py"
        else:
            entrypoint = "python tests/e2e_v2/utils/scripts/cpu_script.py"

        jobs = []
        try:
            cluster.apply()
            cluster.wait_ready()

            for i in range(3):
                rayjob = RayJob(
                    job_name=f"remote-job-{i}",
                    cluster_name=cluster_name,
                    namespace=self.namespace,
                    entrypoint=entrypoint,
                )
                rayjob.submit()
                jobs.append(rayjob)

            # Wait for all jobs to finish
            for job in jobs:
                assert wait_for_job_finished(
                    job_name=job.name, namespace=self.namespace, timeout=300
                ), f"RayJob '{job.name}' did not finish within timeout"

            # Verify all jobs succeeded
            for job in jobs:
                status = get_job_status(job.name, self.namespace)
                assert_job_succeeded(status, job.name)

        finally:
            for job in jobs:
                try:
                    job.delete()
                except Exception:
                    pass
            cluster.down()

    def run_in_cluster_submission(self, num_gpus):
        create_namespace(self)
        create_kueue_resources(self)

        cluster_name = "rayjob-cr-in-cluster"

        cluster = Cluster(
            ClusterConfiguration(
                name=cluster_name,
                namespace=self.namespace,
                num_workers=1,
                head_extended_resource_requests={"nvidia.com/gpu": num_gpus},
                worker_extended_resource_requests={"nvidia.com/gpu": num_gpus},
                image=get_ray_image(),
                local_queue=self.local_queues[0],
                verify_tls=False,
            )
        )

        try:
            cluster.apply()
            cluster.wait_ready()

            job_name_in_cluster = "in-cluster-rayjob-cr"
            entrypoint_cmd = (
                "python -c \"import ray; ray.init(); print('IN_CLUSTER_CR_SUCCESS')\""
            )

            in_cluster_code = textwrap.dedent(
                f"""
                from codeflare_sdk import RayJob
                from time import sleep

                entrypoint = {entrypoint_cmd!r}
                rayjob = RayJob(
                    job_name="{job_name_in_cluster}",
                    cluster_name="{cluster_name}",
                    namespace="{self.namespace}",
                    entrypoint=entrypoint,
                )

                rayjob.submit()

                timeout, elapsed = 120, 0
                while elapsed < timeout:
                    status, _ = rayjob.status(print_to_console=False)
                    if status.name in ["COMPLETE", "FAILED"]:
                        break
                    sleep(5)
                    elapsed += 5

                final_status, _ = rayjob.status(print_to_console=False)
                rayjob.delete()

                if final_status.name == "COMPLETE":
                    print("IN_CLUSTER_CR_SUBMISSION_PASSED")
            """
            )

            result = run_code_in_pod(
                api_instance=self.api_instance,
                namespace=self.namespace,
                code=in_cluster_code,
                image=get_ray_image(),
                pip_packages=["codeflare-sdk"],
                timeout=300,
                auto_setup_rbac=True,
                custom_api=self.custom_api,
            )

            assert (
                result.succeeded
            ), f"In-cluster submission failed. Logs: {result.logs}"
            assert (
                "IN_CLUSTER_CR_SUBMISSION_PASSED" in result.logs
            ), f"In-cluster submission did not pass. Logs: {result.logs}"

        finally:
            cluster.down()

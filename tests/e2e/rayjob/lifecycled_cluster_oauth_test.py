import pytest
import sys
import os
from time import sleep

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from support import *

from codeflare_sdk import RayJob, ManagedClusterConfig
from codeflare_sdk.ray.rayjobs.status import (
    CodeflareRayJobStatus,
    RayJobDeploymentStatus,
)
import kubernetes.client.rest
from python_client.kuberay_job_api import RayjobApi
from python_client.kuberay_cluster_api import RayClusterApi


@pytest.mark.openshift
class TestRayJobLifecycledClusterOauth:
    """Test RayJob with auto-created cluster lifecycle management on OpenShift."""

    def setup_method(self):
        initialize_kubernetes_client(self)

    def teardown_method(self):
        delete_namespace(self)

    def test_rayjob_with_lifecycled_cluster_oauth(self):
        """
        Test RayJob submission with embedded cluster configuration, including:
        1. Job submission with auto-cluster creation
        2. Job suspension (stop) and verification
        3. Job resumption (resubmit) and verification
        4. Job completion monitoring
        5. Automatic cluster cleanup after job deletion
        """
        self.setup_method()
        create_namespace(self)
        ray_image = get_ray_image()
        self.job_api = RayjobApi()
        job_name = "lifecycled-job"

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

        rayjob = RayJob(
            job_name=job_name,
            namespace=self.namespace,
            cluster_config=cluster_config,
            entrypoint="python -c \"import ray; ray.init(); print('RayJob completed successfully')\"",
            runtime_env={"env_vars": get_setup_env_variables(ACCELERATOR="cpu")},
            shutdown_after_job_finishes=True,
        )

        try:
            # 1. Submit and wait for job to reach running state
            assert rayjob.submit() == job_name
            assert self.job_api.wait_until_job_running(
                name=rayjob.name, k8s_namespace=rayjob.namespace, timeout=300
            ), "Job did not reach running state"

            # 2. Stop (suspend) the job and
            assert rayjob.stop(), "Job stop failed"
            job_cr = self.job_api.get_job(
                name=rayjob.name, k8s_namespace=rayjob.namespace
            )
            assert job_cr["spec"]["suspend"] is True, "Job suspend not set to true"

            assert self._wait_for_job_status(
                rayjob, "Suspended", timeout=30
            ), "Job did not reach Suspended state"

            # 3.  Test Job Resubmission
            assert rayjob.resubmit(), "Job resubmit failed"
            job_cr = self.job_api.get_job(
                name=rayjob.name, k8s_namespace=rayjob.namespace
            )
            assert job_cr["spec"]["suspend"] is False, "Job suspend not set to false"

            assert self.job_api.wait_until_job_finished(
                name=rayjob.name, k8s_namespace=rayjob.namespace, timeout=300
            ), "Job did not complete"

        finally:
            # 4. Delete the job and cleanup
            assert rayjob.delete()
            self.verify_cluster_cleanup(rayjob)

    def _wait_for_job_status(
        self,
        rayjob: RayJob,
        expected_status: str,
        timeout: int = 30,
    ) -> bool:
        """Wait for a job to reach a specific deployment status."""
        elapsed_time = 0
        check_interval = 2

        while elapsed_time < timeout:
            status = self.job_api.get_job_status(
                name=rayjob.name, k8s_namespace=rayjob.namespace
            )
            if status and status.get("jobDeploymentStatus") == expected_status:
                return True

            sleep(check_interval)
            elapsed_time += check_interval

        return False

    def verify_cluster_cleanup(self, rayjob: RayJob, timeout: int = 60):
        """Verify that the cluster created by the RayJob has been cleaned up."""
        elapsed_time = 0
        check_interval = 5
        cluster_api = RayClusterApi()

        while elapsed_time < timeout:
            try:
                cluster_info = cluster_api.get_ray_cluster(
                    name=rayjob.cluster_name, k8s_namespace=rayjob.namespace
                )
                # Cluster doesn't exist
                if cluster_info is None:
                    return

                sleep(check_interval)
                elapsed_time += check_interval

            except kubernetes.client.rest.ApiException as e:
                if e.status == 404:
                    return
                else:
                    raise e

        raise TimeoutError(
            f"Cluster '{rayjob.cluster_name}' was not cleaned up within {timeout} seconds"
        )

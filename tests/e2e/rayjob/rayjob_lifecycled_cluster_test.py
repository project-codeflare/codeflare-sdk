import pytest
import sys
import os
from time import sleep

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from support import *

from codeflare_sdk import RayJob, ManagedClusterConfig
import kubernetes.client.rest
from python_client.kuberay_job_api import RayjobApi
from python_client.kuberay_cluster_api import RayClusterApi


class TestRayJobLifecycledCluster:
    """Test RayJob with auto-created cluster lifecycle management."""

    def setup_method(self):
        initialize_kubernetes_client(self)

    def teardown_method(self):
        delete_namespace(self)
        delete_kueue_resources(self)

    def test_lifecycled_kueue_managed(self):
        """Test RayJob with Kueue-managed lifecycled cluster."""
        self.setup_method()
        create_namespace(self)
        create_kueue_resources(self)

        self.job_api = RayjobApi()
        cluster_api = RayClusterApi()
        job_name = "kueue-lifecycled"

        # Get platform-appropriate resource configurations
        resources = get_platform_appropriate_resources()

        cluster_config = ManagedClusterConfig(
            head_cpu_requests=resources["head_cpu_requests"],
            head_cpu_limits=resources["head_cpu_limits"],
            head_memory_requests=resources["head_memory_requests"],
            head_memory_limits=resources["head_memory_limits"],
            num_workers=1,
            worker_cpu_requests=resources["worker_cpu_requests"],
            worker_cpu_limits=resources["worker_cpu_limits"],
            worker_memory_requests=resources["worker_memory_requests"],
            worker_memory_limits=resources["worker_memory_limits"],
            image=get_ray_image(),
        )

        rayjob = RayJob(
            job_name=job_name,
            namespace=self.namespace,
            cluster_config=cluster_config,
            entrypoint="python -c \"import ray; ray.init(); print('Kueue job done')\"",
            runtime_env={"env_vars": get_setup_env_variables(ACCELERATOR="cpu")},
            local_queue=self.local_queues[0],
        )

        try:
            assert rayjob.submit() == job_name
            assert self.job_api.wait_until_job_running(
                name=rayjob.name, k8s_namespace=rayjob.namespace, timeout=600
            )

            assert self.job_api.wait_until_job_finished(
                name=rayjob.name, k8s_namespace=rayjob.namespace, timeout=300
            )
        finally:
            try:
                rayjob.delete()
            except Exception:
                pass  # Job might already be deleted
            verify_rayjob_cluster_cleanup(cluster_api, rayjob.name, rayjob.namespace)

    def test_lifecycled_kueue_resource_queueing(self):
        """Test Kueue resource queueing with lifecycled clusters."""
        self.setup_method()
        create_namespace(self)
        create_limited_kueue_resources(self)

        self.job_api = RayjobApi()
        cluster_api = RayClusterApi()

        # Get platform-appropriate resource configurations
        resources = get_platform_appropriate_resources()

        cluster_config = ManagedClusterConfig(
            head_cpu_requests=resources["head_cpu_requests"],
            head_cpu_limits=resources["head_cpu_limits"],
            head_memory_requests=resources["head_memory_requests"],
            head_memory_limits=resources["head_memory_limits"],
            num_workers=0,
            image=get_ray_image(),
        )

        job1 = None
        job2 = None
        try:
            job1 = RayJob(
                job_name="holder",
                namespace=self.namespace,
                cluster_config=cluster_config,
                entrypoint='python -c "import ray; import time; ray.init(); time.sleep(15)"',
                runtime_env={"env_vars": get_setup_env_variables(ACCELERATOR="cpu")},
                local_queue=self.local_queues[0],
            )
            assert job1.submit() == "holder"
            assert self.job_api.wait_until_job_running(
                name=job1.name, k8s_namespace=job1.namespace, timeout=60
            )

            job2 = RayJob(
                job_name="waiter",
                namespace=self.namespace,
                cluster_config=cluster_config,
                entrypoint='python -c "import ray; ray.init()"',
                runtime_env={"env_vars": get_setup_env_variables(ACCELERATOR="cpu")},
                local_queue=self.local_queues[0],
            )
            assert job2.submit() == "waiter"

            # Wait for Kueue to process the job
            sleep(5)
            job2_cr = self.job_api.get_job(name=job2.name, k8s_namespace=job2.namespace)

            # For RayJobs with managed clusters, check if Kueue is holding resources
            job2_status = job2_cr.get("status", {})
            ray_cluster_name = job2_status.get("rayClusterName", "")

            # If RayCluster is not created yet, it means Kueue is holding the job
            if not ray_cluster_name:
                # This is the expected behavior
                job_is_queued = True
            else:
                # Check RayCluster resources - if all are 0, it's queued
                ray_cluster_status = job2_status.get("rayClusterStatus", {})
                desired_cpu = ray_cluster_status.get("desiredCPU", "0")
                desired_memory = ray_cluster_status.get("desiredMemory", "0")

                # Kueue creates the RayCluster but with 0 resources when queued
                job_is_queued = desired_cpu == "0" and desired_memory == "0"

            assert job_is_queued, "Job2 should be queued by Kueue while Job1 is running"

            assert self.job_api.wait_until_job_finished(
                name=job1.name, k8s_namespace=job1.namespace, timeout=60
            )

            assert wait_for_kueue_admission(
                self, self.job_api, job2.name, job2.namespace, timeout=30
            )

            assert self.job_api.wait_until_job_finished(
                name=job2.name, k8s_namespace=job2.namespace, timeout=60
            )
        finally:
            for job in [job1, job2]:
                if job:
                    try:
                        job.delete()
                        verify_rayjob_cluster_cleanup(
                            cluster_api, job.name, job.namespace
                        )
                    except:
                        pass

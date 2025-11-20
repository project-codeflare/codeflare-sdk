import pytest
import sys
import os
from time import sleep
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from support import *

from codeflare_sdk import RayJob, ManagedClusterConfig

from kubernetes import client
from codeflare_sdk.vendored.python_client.kuberay_job_api import RayjobApi
from codeflare_sdk.vendored.python_client.kuberay_cluster_api import RayClusterApi


@pytest.mark.tier1
class TestRayJobLifecycledCluster:
    """Test RayJob with auto-created cluster lifecycle management."""

    def setup_method(self):
        initialize_kubernetes_client(self)

    def teardown_method(self):
        delete_namespace(self)
        delete_kueue_resources(self)

    def test_lifecycled_kueue_managed(self):
        """Test RayJob with Kueue-managed lifecycled cluster with Secret validation."""
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
        )

        # Create a temporary script file to test Secret functionality
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, dir=os.getcwd()
        ) as script_file:
            script_file.write(
                """
                import ray
                ray.init()
                print('Kueue job with Secret done')
                ray.shutdown()
                """
            )
            script_file.flush()
            script_filename = os.path.basename(script_file.name)

        try:
            rayjob = RayJob(
                job_name=job_name,
                namespace=self.namespace,
                cluster_config=cluster_config,
                entrypoint=f"python {script_filename}",
                runtime_env={"env_vars": get_setup_env_variables(ACCELERATOR="cpu")},
                local_queue=self.local_queues[0],
            )

            assert rayjob.submit() == job_name

            # Verify Secret was created with owner reference
            self.verify_secret_with_owner_reference(rayjob)

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
            # Clean up the temporary script file
            if "script_filename" in locals():
                try:
                    os.remove(script_filename)
                except:
                    pass

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

    def verify_secret_with_owner_reference(self, rayjob: RayJob):
        """Verify that the Secret was created with proper owner reference to the RayJob."""
        v1 = client.CoreV1Api()
        secret_name = f"{rayjob.name}-files"

        try:
            # Get the Secret
            secret = v1.read_namespaced_secret(
                name=secret_name, namespace=rayjob.namespace
            )

            # Verify Secret exists
            assert secret is not None, f"Secret {secret_name} not found"

            # Verify it contains the script
            assert secret.data is not None, "Secret has no data"
            assert len(secret.data) > 0, "Secret data is empty"

            # Verify owner reference
            assert (
                secret.metadata.owner_references is not None
            ), "Secret has no owner references"
            assert (
                len(secret.metadata.owner_references) > 0
            ), "Secret owner references list is empty"

            owner_ref = secret.metadata.owner_references[0]
            assert (
                owner_ref.api_version == "ray.io/v1"
            ), f"Wrong API version: {owner_ref.api_version}"
            assert owner_ref.kind == "RayJob", f"Wrong kind: {owner_ref.kind}"
            assert owner_ref.name == rayjob.name, f"Wrong owner name: {owner_ref.name}"
            assert (
                owner_ref.controller is True
            ), "Owner reference controller not set to true"
            assert (
                owner_ref.block_owner_deletion is True
            ), "Owner reference blockOwnerDeletion not set to true"

            # Verify labels
            assert secret.metadata.labels.get("ray.io/job-name") == rayjob.name
            assert (
                secret.metadata.labels.get("app.kubernetes.io/managed-by")
                == "codeflare-sdk"
            )
            assert (
                secret.metadata.labels.get("app.kubernetes.io/component")
                == "rayjob-files"
            )

            print(f"✓ Secret {secret_name} verified with proper owner reference")

        except client.rest.ApiException as e:
            if e.status == 404:
                raise AssertionError(f"Secret {secret_name} not found")
            else:
                raise e

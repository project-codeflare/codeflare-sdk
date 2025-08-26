from time import sleep

from codeflare_sdk import Cluster, ClusterConfiguration
from codeflare_sdk.ray.rayjobs import RayJob
from codeflare_sdk.ray.rayjobs.status import CodeflareRayJobStatus

import pytest

from support import *

# This test creates a Ray Cluster and then submits a RayJob against the existing cluster on Kind Cluster


@pytest.mark.kind
class TestRayJobExistingClusterKind:
    def setup_method(self):
        initialize_kubernetes_client(self)

    def teardown_method(self):
        delete_namespace(self)
        delete_kueue_resources(self)

    def test_rayjob_ray_cluster_sdk_kind(self):
        self.setup_method()
        create_namespace(self)
        create_kueue_resources(self)
        self.run_rayjob_against_existing_cluster_kind(accelerator="cpu")

    @pytest.mark.nvidia_gpu
    def test_rayjob_ray_cluster_sdk_kind_nvidia_gpu(self):
        self.setup_method()
        create_namespace(self)
        create_kueue_resources(self)
        self.run_rayjob_against_existing_cluster_kind(
            accelerator="gpu", number_of_gpus=1
        )

    def run_rayjob_against_existing_cluster_kind(
        self, accelerator, gpu_resource_name="nvidia.com/gpu", number_of_gpus=0
    ):
        cluster_name = "existing-cluster"
        cluster = Cluster(
            ClusterConfiguration(
                name=cluster_name,
                namespace=self.namespace,
                num_workers=1,
                head_cpu_requests="500m",
                head_cpu_limits="500m",
                worker_cpu_requests=2,
                worker_cpu_limits=4,
                worker_memory_requests=4,
                worker_memory_limits=8,
                worker_extended_resource_requests={gpu_resource_name: number_of_gpus},
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

        # test RayJob submission against the existing cluster
        self.assert_rayjob_submit_against_existing_cluster(
            cluster, accelerator, number_of_gpus
        )

        # Cleanup - manually tear down the cluster since job won't do it
        print("🧹 Cleaning up Ray cluster")
        cluster.down()

    def assert_rayjob_submit_against_existing_cluster(
        self, cluster, accelerator, number_of_gpus
    ):
        """
        Test RayJob submission against an existing Ray cluster.
        """
        cluster_name = cluster.config.name
        job_name = f"mnist-rayjob-{accelerator}"

        print(f"🚀 Testing RayJob submission against existing cluster '{cluster_name}'")

        # Create RayJob targeting the existing cluster
        rayjob = RayJob(
            job_name=job_name,
            cluster_name=cluster_name,
            namespace=self.namespace,
            entrypoint="python mnist.py",
            runtime_env={
                "working_dir": "./tests/e2e/",
                "pip": "./tests/e2e/mnist_pip_requirements.txt",
                "env_vars": get_setup_env_variables(ACCELERATOR=accelerator),
            },
            shutdown_after_job_finishes=False,
            entrypoint_num_gpus=number_of_gpus if number_of_gpus > 0 else None,
        )

        # Submit the job
        submission_result = rayjob.submit()
        assert (
            submission_result == job_name
        ), f"Job submission failed, expected {job_name}, got {submission_result}"
        print(f"✅ Successfully submitted RayJob '{job_name}' against existing cluster")

        # Monitor the job status until completion
        self.monitor_rayjob_completion(
            rayjob, timeout=360
        )  # 6 minutes for faster debugging

        print(f"✅ RayJob '{job_name}' completed successfully against existing cluster!")

    def monitor_rayjob_completion(self, rayjob: RayJob, timeout: int = 360):
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
                # Get more details about the failure
                print(f"❌ RayJob '{rayjob.name}' failed! Investigating...")

                # Try to get failure details using kubectl
                import subprocess

                try:
                    result = subprocess.run(
                        [
                            "kubectl",
                            "get",
                            "rayjobs",
                            "-n",
                            self.namespace,
                            rayjob.name,
                            "-o",
                            "yaml",
                        ],
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    if result.returncode == 0:
                        print(f"📋 RayJob YAML details:\n{result.stdout}")

                    # Try to get job submitter pod logs (these pods may be cleaned up quickly)
                    pod_result = subprocess.run(
                        [
                            "kubectl",
                            "get",
                            "pods",
                            "-n",
                            self.namespace,
                            "-l",
                            f"ray.io/rayjob={rayjob.name}",
                            "-o",
                            "name",
                            "--sort-by=.metadata.creationTimestamp",
                        ],
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    if pod_result.returncode == 0 and pod_result.stdout.strip():
                        pod_name = pod_result.stdout.strip().split("/")[-1]
                        log_result = subprocess.run(
                            [
                                "kubectl",
                                "logs",
                                "-n",
                                self.namespace,
                                pod_name,
                                "--tail=50",
                            ],
                            capture_output=True,
                            text=True,
                            timeout=10,
                        )
                        if log_result.returncode == 0:
                            print(f"📝 Pod logs for {pod_name}:\n{log_result.stdout}")
                        else:
                            print(f"❌ Could not get pod logs: {log_result.stderr}")
                    else:
                        print(f"❌ Could not find pods for RayJob: {pod_result.stderr}")

                    # Also try to get events related to the RayJob
                    events_result = subprocess.run(
                        [
                            "kubectl",
                            "get",
                            "events",
                            "-n",
                            self.namespace,
                            "--field-selector",
                            f"involvedObject.name={rayjob.name}",
                            "-o",
                            "wide",
                        ],
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    if events_result.returncode == 0 and events_result.stdout.strip():
                        print(f"📅 Events for RayJob:\n{events_result.stdout}")

                except Exception as e:
                    print(f"❌ Error getting failure details: {e}")

                raise AssertionError(f"❌ RayJob '{rayjob.name}' failed!")
            elif status == CodeflareRayJobStatus.RUNNING:
                print(f"🏃 RayJob '{rayjob.name}' is still running...")
            elif status == CodeflareRayJobStatus.UNKNOWN:
                print(f"❓ RayJob '{rayjob.name}' status is unknown - investigating...")

                # If we've been in Unknown status for too long, get debug info
                if elapsed_time > 120:  # After 2 minutes of Unknown status
                    print(
                        f"⚠️ Job has been in Unknown status for {elapsed_time}s - getting debug info..."
                    )

                    # Get detailed YAML to understand why status is Unknown
                    import subprocess

                    try:
                        result = subprocess.run(
                            [
                                "kubectl",
                                "get",
                                "rayjobs",
                                "-n",
                                self.namespace,
                                rayjob.name,
                                "-o",
                                "yaml",
                            ],
                            capture_output=True,
                            text=True,
                            timeout=10,
                        )
                        if result.returncode == 0:
                            print(
                                f"📋 RayJob YAML (Unknown status debug):\n{result.stdout}"
                            )
                    except Exception as e:
                        print(f"❌ Error getting debug info: {e}")

                    # Break out of Unknown status loop after 4 minutes
                    if elapsed_time > 240:
                        print(
                            f"⏰ Breaking out of Unknown status loop after {elapsed_time}s"
                        )
                        raise AssertionError(
                            f"❌ RayJob '{rayjob.name}' stuck in Unknown status for too long"
                        )

            # Wait before next check
            sleep(check_interval)
            elapsed_time += check_interval

        # If we reach here, the job has timed out
        final_status, _ = rayjob.status(print_to_console=True)
        raise TimeoutError(
            f"⏰ RayJob '{rayjob.name}' did not complete within {timeout} seconds. "
            f"Final status: {final_status}"
        )

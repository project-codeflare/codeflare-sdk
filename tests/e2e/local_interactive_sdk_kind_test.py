from codeflare_sdk import (
    Cluster,
    ClusterConfiguration,
    TokenAuthentication,
    generate_cert,
)

import pytest
import ray
import math
import logging
import time
import os
import subprocess
import signal  # For explicit signal sending

from support import *

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


@pytest.mark.kind
class TestRayLocalInteractiveOauth:
    def setup_method(self):
        initialize_kubernetes_client(self)
        logger.info("Kubernetes client initalized")
        self.port_forward_process = None  # Initialize port_forward_process

    def teardown_method(self):
        if self.port_forward_process:
            logger.info(
                f"Terminating port-forward process (PID: {self.port_forward_process.pid})..."
            )
            self.port_forward_process.terminate()  # Send SIGTERM
            try:
                self.port_forward_process.wait(timeout=10)  # Wait for termination
                logger.info(
                    f"Port-forward process (PID: {self.port_forward_process.pid}) terminated gracefully."
                )
            except subprocess.TimeoutExpired:
                logger.warning(
                    f"Port-forward process (PID: {self.port_forward_process.pid}) did not terminate in time, killing..."
                )
                self.port_forward_process.kill()  # Send SIGKILL if terminate fails
                self.port_forward_process.wait()  # Ensure it's dead
                logger.info(
                    f"Port-forward process (PID: {self.port_forward_process.pid}) killed."
                )
            self.port_forward_process = None
        delete_namespace(self)
        delete_kueue_resources(self)

    def test_local_interactives(self):
        self.setup_method()
        create_namespace(self)
        create_kueue_resources(self)
        self.run_local_interactives()

    @pytest.mark.nvidia_gpu
    def test_local_interactives_nvidia_gpu(self):
        self.setup_method()
        create_namespace(self)
        create_kueue_resources(self)
        self.run_local_interactives(number_of_gpus=1)

    def run_local_interactives(
        self, gpu_resource_name="nvidia.com/gpu", number_of_gpus=0
    ):
        cluster_name = "test-ray-cluster-li"
        logger.info(f"Starting run_local_interactives with {number_of_gpus} GPUs")

        ray.shutdown()

        cluster = Cluster(
            ClusterConfiguration(
                name=cluster_name,
                namespace=self.namespace,
                num_workers=1,
                head_cpu_requests="500m",
                head_cpu_limits="500m",
                head_memory_requests=2,
                head_memory_limits=2,
                worker_cpu_requests="500m",
                worker_cpu_limits="500m",
                worker_memory_requests=1,
                worker_memory_limits=4,
                worker_extended_resource_requests={gpu_resource_name: number_of_gpus},
                write_to_file=True,
                verify_tls=False,  # This is for SDK's JobSubmissionClient, not ray.init directly
            )
        )

        try:  # Wrap main logic in try-finally to ensure port-forward cleanup
            cluster.up()
            logger.info("Cluster deployment initiated")

            cluster.wait_ready()
            cluster.status()
            logger.info("Cluster is ready")

            TIMEOUT = 300  # 5 minutes timeout
            END = time.time() + TIMEOUT

            head_pod_name = None
            worker_pod_name = None

            while time.time() < END:
                # Dynamically find pod names using substrings
                if not head_pod_name:
                    head_pod_name = kubectl_get_pod_name_by_substring(
                        self.namespace, cluster_name, "head"
                    )
                    if head_pod_name:
                        logger.info(
                            f"Discovered head pod by substring: {head_pod_name}"
                        )
                    else:
                        logger.info(
                            f"Head pod not yet found by searching for '{cluster_name}' and 'head' in pod names. Retrying..."
                        )

                if not worker_pod_name:
                    worker_pod_name = kubectl_get_pod_name_by_substring(
                        self.namespace, cluster_name, "worker"
                    )
                    if worker_pod_name:
                        logger.info(
                            f"Discovered worker pod by substring: {worker_pod_name}"
                        )
                    else:
                        logger.info(
                            f"Worker pod not yet found by searching for '{cluster_name}' and 'worker' in pod names. Retrying..."
                        )

                head_status = "NotFound"
                worker_status = "NotFound"

                if head_pod_name:
                    head_status = kubectl_get_pod_status(self.namespace, head_pod_name)
                if worker_pod_name:
                    worker_status = kubectl_get_pod_status(
                        self.namespace, worker_pod_name
                    )

                if (
                    head_pod_name
                    and worker_pod_name
                    and "Running" in head_status
                    and "Running" in worker_status
                ):
                    head_ready = kubectl_get_pod_ready(self.namespace, head_pod_name)
                    worker_ready = kubectl_get_pod_ready(
                        self.namespace, worker_pod_name
                    )

                    if head_ready and worker_ready:
                        logger.info("All discovered pods and containers are ready!")
                        break
                    else:
                        logger.info(
                            "Discovered pods are running but containers are not all ready yet..."
                        )
                        if not head_ready and head_pod_name:
                            head_container_status = kubectl_get_pod_container_status(
                                self.namespace, head_pod_name
                            )
                            logger.info(
                                f"Head pod ({head_pod_name}) container status: {head_container_status}"
                            )
                        if not worker_ready and worker_pod_name:
                            worker_container_status = kubectl_get_pod_container_status(
                                self.namespace, worker_pod_name
                            )
                            logger.info(
                                f"Worker pod ({worker_pod_name}) container status: {worker_container_status}"
                            )
                elif (head_pod_name and "Error" in head_status) or (
                    worker_pod_name and "Error" in worker_status
                ):
                    logger.error(
                        "Error getting pod status for one or more pods, retrying..."
                    )
                else:
                    logger.info(
                        f"Waiting for pods to be discovered and running... Current status - Head ({head_pod_name or 'N/A'}): {head_status}, Worker ({worker_pod_name or 'N/A'}): {worker_status}"
                    )

                time.sleep(10)

            if time.time() >= END:
                logger.error("Timeout waiting for pods to be ready or discovered")
                if not head_pod_name or not worker_pod_name:
                    logger.error(
                        "Could not discover head and/or worker pods by name substring. Listing all pods in namespace for debugging:"
                    )
                    try:
                        all_pods_result = subprocess.run(
                            [
                                "kubectl",
                                "get",
                                "pods",
                                "-n",
                                self.namespace,
                                "-o",
                                "wide",
                            ],
                            capture_output=True,
                            text=True,
                            check=False,
                        )
                        logger.error(
                            f"Pods in namespace '{self.namespace}':\\n{all_pods_result.stdout}"
                        )
                        if all_pods_result.stderr:
                            logger.error(
                                f"Error listing pods: {all_pods_result.stderr}"
                            )
                    except Exception as e_pods:
                        logger.error(
                            f"Exception while trying to list all pods: {e_pods}"
                        )

                if head_pod_name:
                    logger.error(
                        f"Final head pod ({head_pod_name}) status: {kubectl_get_pod_container_status(self.namespace, head_pod_name)}"
                    )
                else:
                    logger.error(
                        f"Final head pod status: Not Discovered by searching for '{cluster_name}' and 'head' in pod names."
                    )

                if worker_pod_name:
                    logger.error(
                        f"Final worker pod ({worker_pod_name}) status: {kubectl_get_pod_container_status(self.namespace, worker_pod_name)}"
                    )
                else:
                    logger.error(
                        f"Final worker pod status: Not Discovered by searching for '{cluster_name}' and 'worker' in pod names."
                    )
                raise TimeoutError(
                    "Pods did not become ready (or were not discovered by name substring) within the timeout period"
                )

            generate_cert.generate_tls_cert(cluster_name, self.namespace)
            generate_cert.export_env(cluster_name, self.namespace)

            # Unset server cert/key for client mode if skip_verify is true, to avoid client trying to use them as its own identity.
            if os.environ.get("RAY_CLIENT_SKIP_TLS_VERIFY") == "1":
                if "RAY_TLS_SERVER_CERT" in os.environ:
                    del os.environ["RAY_TLS_SERVER_CERT"]
                    logger.info(
                        "Removed RAY_TLS_SERVER_CERT from env for client connection"
                    )
                if "RAY_TLS_SERVER_KEY" in os.environ:
                    del os.environ["RAY_TLS_SERVER_KEY"]
                    logger.info(
                        "Removed RAY_TLS_SERVER_KEY from env for client connection"
                    )

            # Start port forwarding
            local_port = "20001"
            ray_client_port = "10001"
            head_service_name = f"{cluster_name}-head-svc"

            port_forward_cmd = [
                "kubectl",
                "port-forward",
                "-n",
                self.namespace,
                f"svc/{head_service_name}",
                f"{local_port}:{ray_client_port}",
            ]
            logger.info(f"Starting port-forward: {' '.join(port_forward_cmd)}")
            # Using preexec_fn=os.setsid to create a new session, so we can kill the whole process group later if needed.
            # However, os.setsid is not available on Windows. For simplicity in a test, direct Popen is used.
            # Proper cross-platform process group management can be more complex.
            self.port_forward_process = subprocess.Popen(
                port_forward_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            logger.info(
                f"Port-forward process started with PID: {self.port_forward_process.pid}"
            )
            time.sleep(5)  # Give port-forward a few seconds to establish

            client_url = f"ray://localhost:{local_port}"
            # client_url = cluster.local_client_url() # Original line, now replaced
            cluster.status()

            logger.info(f"Attempting to connect to Ray client at: {client_url}")
            logger.info("Initializing Ray connection...")
            try:
                ray.init(
                    address=client_url, logging_level="INFO"
                )  # Removed local_mode=True
                logger.info("Ray initialization successful")
            except Exception as e:
                logger.error(f"Ray initialization failed: {str(e)}")
                logger.error(f"Error type: {type(e)}")
                # Log port-forward stdout/stderr if connection fails
                if self.port_forward_process:
                    stdout, stderr = self.port_forward_process.communicate(
                        timeout=5
                    )  # attempt to read
                    logger.error(
                        f"Port-forward stdout: {stdout.decode(errors='ignore')}"
                    )
                    logger.error(
                        f"Port-forward stderr: {stderr.decode(errors='ignore')}"
                    )
                raise

            @ray.remote(num_gpus=number_of_gpus / 2)
            def heavy_calculation_part(num_iterations):
                result = 0.0
                for i in range(num_iterations):
                    for j in range(num_iterations):
                        for k in range(num_iterations):
                            result += math.sin(i) * math.cos(j) * math.tan(k)
                return result

            @ray.remote(num_gpus=number_of_gpus / 2)
            def heavy_calculation(num_iterations):
                results = ray.get(
                    [
                        heavy_calculation_part.remote(num_iterations // 30)
                        for _ in range(30)
                    ]
                )
                return sum(results)

            ref = heavy_calculation.remote(3000)

            try:
                result = ray.get(ref)
                logger.info(f"Calculation completed with result: {result}")
                assert result == 1789.4644387076714
                logger.info("Result assertion passed")
            except Exception as e:
                logger.error(f"Error during calculation: {str(e)}")
                raise
            finally:
                logger.info("Cancelling task reference...")
                ray.cancel(ref)
                logger.info("Task cancelled")

            ray.shutdown()
            # Port-forward process is stopped in finally block or teardown_method

        finally:
            if self.port_forward_process:
                logger.info(
                    f"Stopping port-forward process (PID: {self.port_forward_process.pid}) in finally block..."
                )
                self.port_forward_process.terminate()
                try:
                    self.port_forward_process.wait(timeout=10)
                    logger.info(
                        f"Port-forward process (PID: {self.port_forward_process.pid}) terminated from finally."
                    )
                except subprocess.TimeoutExpired:
                    logger.warning(
                        f"Port-forward process (PID: {self.port_forward_process.pid}) did not terminate in time from finally, killing..."
                    )
                    self.port_forward_process.kill()
                    self.port_forward_process.wait()
                    logger.info(
                        f"Port-forward process (PID: {self.port_forward_process.pid}) killed from finally."
                    )
                self.port_forward_process = None
            cluster.down()

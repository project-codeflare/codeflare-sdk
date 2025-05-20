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

from support import *

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


@pytest.mark.kind
class TestRayLocalInteractiveOauth:
    def setup_method(self):
        logger.info("Setting up test environment...")
        initialize_kubernetes_client(self)
        logger.info("Kubernetes client initialized")

    def teardown_method(self):
        logger.info("Cleaning up test environment...")
        delete_namespace(self)
        delete_kueue_resources(self)
        logger.info("Cleanup completed")

    def test_local_interactives(self):
        logger.info("Starting test_local_interactives...")
        self.setup_method()
        create_namespace(self)
        create_kueue_resources(self)
        self.run_local_interactives()
        logger.info("test_local_interactives completed")

    @pytest.mark.nvidia_gpu
    def test_local_interactives_nvidia_gpu(self):
        logger.info("Starting test_local_interactives_nvidia_gpu...")
        self.setup_method()
        create_namespace(self)
        create_kueue_resources(self)
        self.run_local_interactives(number_of_gpus=1)
        logger.info("test_local_interactives_nvidia_gpu completed")

    def run_local_interactives(
        self, gpu_resource_name="nvidia.com/gpu", number_of_gpus=0
    ):
        cluster_name = "test-ray-cluster-li"
        logger.info(f"Starting run_local_interactives with {number_of_gpus} GPUs")

        logger.info("Creating cluster configuration...")
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
                worker_cpu_limits=1,
                worker_memory_requests=1,
                worker_memory_limits=4,
                worker_extended_resource_requests={gpu_resource_name: number_of_gpus},
                write_to_file=True,
                verify_tls=False,
            )
        )
        logger.info("Cluster configuration created")

        logger.info("Starting cluster deployment...")
        cluster.up()
        logger.info("Cluster deployment initiated")

        logger.info("Waiting for cluster to be ready...")
        cluster.wait_ready()
        logger.info("Cluster is ready")

        logger.info("Generating TLS certificates...")
        generate_cert.generate_tls_cert(cluster_name, self.namespace)
        logger.info("TLS certificates generated")

        logger.info("Exporting environment variables...")
        generate_cert.export_env(cluster_name, self.namespace)
        logger.info("Environment variables exported")

        client_url = cluster.local_client_url()
        logger.info(f"Ray client URL: {client_url}")

        logger.info("Checking cluster status...")
        status = cluster.status()
        logger.info(f"Cluster status: {status}")

        logger.info("Checking cluster dashboard URI...")
        dashboard_uri = cluster.cluster_dashboard_uri()
        logger.info(f"Dashboard URI: {dashboard_uri}")

        logger.info("Checking cluster URI...")
        cluster_uri = cluster.cluster_uri()
        logger.info(f"Cluster URI: {cluster_uri}")

        logger.info("Shutting down any existing Ray connections...")
        ray.shutdown()
        logger.info("Ray shutdown completed")

        logger.info("Initializing Ray connection...")
        try:
            ray.init(address=client_url, logging_level="DEBUG")
            logger.info("Ray initialization successful")
        except Exception as e:
            logger.error(f"Ray initialization failed: {str(e)}")
            logger.error(f"Error type: {type(e)}")
            raise

        logger.info("Defining Ray remote functions...")

        @ray.remote(num_gpus=number_of_gpus / 2)
        def heavy_calculation_part(num_iterations):
            logger.info(
                f"Starting heavy_calculation_part with {num_iterations} iterations"
            )
            result = 0.0
            for i in range(num_iterations):
                for j in range(num_iterations):
                    for k in range(num_iterations):
                        result += math.sin(i) * math.cos(j) * math.tan(k)
            logger.info("heavy_calculation_part completed")
            return result

        @ray.remote(num_gpus=number_of_gpus / 2)
        def heavy_calculation(num_iterations):
            logger.info(f"Starting heavy_calculation with {num_iterations} iterations")
            results = ray.get(
                [heavy_calculation_part.remote(num_iterations // 30) for _ in range(30)]
            )
            logger.info("heavy_calculation completed")
            return sum(results)

        logger.info("Submitting calculation task...")
        ref = heavy_calculation.remote(3000)
        logger.info("Task submitted, waiting for result...")

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

        logger.info("Shutting down Ray...")
        ray.shutdown()
        logger.info("Ray shutdown completed")

        logger.info("Tearing down cluster...")
        cluster.down()
        logger.info("Cluster teardown completed")

from codeflare_sdk import (
    Cluster,
    ClusterConfiguration,
    generate_cert,
)

import pytest
import ray
import math
import subprocess

from support import *


@pytest.mark.kind
class TestRayLocalInteractiveKind:
    def setup_method(self):
        initialize_kubernetes_client(self)
        self.port_forward_process = None

    def cleanup_port_forward(self):
        if self.port_forward_process:
            self.port_forward_process.terminate()
            self.port_forward_process.wait(timeout=10)
            self.port_forward_process = None

    def teardown_method(self):
        self.cleanup_port_forward()
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

        ray.shutdown()

        cluster = Cluster(
            ClusterConfiguration(
                name=cluster_name,
                namespace=self.namespace,
                num_workers=1,
                head_cpu_requests="500m",
                head_cpu_limits="500m",
                worker_cpu_requests="500m",
                worker_cpu_limits=1,
                worker_memory_requests=1,
                worker_memory_limits=4,
                worker_extended_resource_requests={gpu_resource_name: number_of_gpus},
                verify_tls=False,
            )
        )

        cluster.apply()

        # Disable dashboard check on KinD as HTTPRoute/Route is not available
        cluster.wait_ready(dashboard_check=False)
        cluster.status()

        # Try to generate TLS certs, but don't fail if CA secret is not available
        # (CA secret is created by codeflare-operator which is not deployed on KinD)
        try:
            generate_cert.generate_tls_cert(cluster_name, self.namespace)
            generate_cert.export_env(cluster_name, self.namespace)
        except Exception as e:
            print(f"Warning: Could not generate TLS certificates: {e}")
            print("Continuing without TLS - using port-forwarding for local connection")

        print(cluster.local_client_url())

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
                [heavy_calculation_part.remote(num_iterations // 30) for _ in range(30)]
            )
            return sum(results)

        # Attempt to port forward
        try:
            local_port = "20001"
            ray_client_port = "10001"

            port_forward_cmd = [
                "kubectl",
                "port-forward",
                "-n",
                self.namespace,
                f"svc/{cluster_name}-head-svc",
                f"{local_port}:{ray_client_port}",
            ]
            self.port_forward_process = subprocess.Popen(
                port_forward_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )

            client_url = f"ray://localhost:{local_port}"
            cluster.status()

            ray.init(address=client_url, logging_level="INFO")

            ref = heavy_calculation.remote(3000)
            result = ray.get(ref)
            assert (
                result == 1789.4644387076728
            )  # Updated result after moving to Python 3.12 (0.0000000000008% difference to old assertion)
            ray.cancel(ref)
            ray.shutdown()

            cluster.down()
        finally:
            self.cleanup_port_forward()

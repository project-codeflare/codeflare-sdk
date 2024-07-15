from codeflare_sdk import (
    Cluster,
    ClusterConfiguration,
    TokenAuthentication,
    generate_cert,
)

import pytest
import ray
import math

from support import *


@pytest.mark.kind
class TestRayLocalInteractiveOauth:
    def setup_method(self):
        initialize_kubernetes_client(self)

    def teardown_method(self):
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

        cluster = Cluster(
            ClusterConfiguration(
                name=cluster_name,
                namespace=self.namespace,
                num_workers=1,
                head_cpus="500m",
                head_memory=2,
                worker_cpu_requests="500m",
                worker_cpu_limits=1,
                worker_memory_requests=1,
                worker_memory_limits=4,
                worker_extended_resource_requests={gpu_resource_name: number_of_gpus},
                write_to_file=True,
                verify_tls=False,
            )
        )
        cluster.up()
        cluster.wait_ready()

        generate_cert.generate_tls_cert(cluster_name, self.namespace)
        generate_cert.export_env(cluster_name, self.namespace)

        print(cluster.local_client_url())

        ray.shutdown()
        ray.init(address=cluster.local_client_url(), logging_level="DEBUG")

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

        ref = heavy_calculation.remote(3000)
        result = ray.get(ref)
        assert result == 1789.4644387076714
        ray.cancel(ref)
        ray.shutdown()

        cluster.down()

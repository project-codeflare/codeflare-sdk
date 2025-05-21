from codeflare_sdk import (
    Cluster,
    ClusterConfiguration,
    TokenAuthentication,
    generate_cert,
)
import subprocess
import json
import pytest
import ray
import math
import time
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
        cluster.up()
        cluster.wait_ready()

        generate_cert.generate_tls_cert(cluster_name, self.namespace)
        generate_cert.export_env(cluster_name, self.namespace)

        print(cluster.local_client_url())

        ray.shutdown()

        print("RAY DEBUGGING")
        print("\n========== PYTHON DEBUG INFO ==========")
        print(f"Ray local cluster client URL: {cluster.local_client_url()}")
        print(f"Ray cluster client URL: {cluster.cluster_uri()}")
        print(f"Cluster name: {cluster_name}")
        print(f"Current working directory: {os.getcwd()}")
        print(f"Cluster: {cluster}")
        print(f"Cluster namespace: {self.namespace}")
        print(f"Cluster name: {cluster_name}")
        print(f"Cluster config: {cluster.config}")
        print(f"Cluster config namespace: {cluster.config.namespace}")
        print(f"Cluster config name: {cluster.config.name}")
        print(f"Cluster config num_workers: {cluster.config.num_workers}")
        print(f"Cluster config num_workers: {cluster.config.num_workers}")
        print("END OF RAY DEBUGGING")

        # print("Sleeping for 15 minutes before ray.init for debugging...")
        # time.sleep(900)

        svc_json = subprocess.check_output(
            f"kubectl get svc -n {self.namespace} {cluster_name}-head-svc -o json",
            shell=True,
        )
        svc = json.loads(svc_json)
        node_port = None
        for port in svc["spec"]["ports"]:
            if port["port"] == 10001:
                node_port = port["nodePort"]
                break

        ray_url = f"ray://127.0.0.1:{node_port}"
        print(f"Connecting to Ray at: {ray_url}")
        ray.init(address=ray_url, logging_level="DEBUG")

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

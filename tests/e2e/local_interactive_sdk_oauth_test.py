from codeflare_sdk import (
    Cluster,
    ClusterConfiguration,
    TokenAuthentication,
    generate_cert,
)

import math
import pytest
import ray

from support import *


@pytest.mark.openshift
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

    def run_local_interactives(self):
        auth = TokenAuthentication(
            token=run_oc_command(["whoami", "--show-token=true"]),
            server=run_oc_command(["whoami", "--show-server=true"]),
            skip_tls=True,
        )
        auth.login()

        cluster_name = "test-ray-cluster-li"

        cluster = Cluster(
            ClusterConfiguration(
                namespace=self.namespace,
                name=cluster_name,
                num_workers=1,
                worker_cpu_requests=1,
                worker_cpu_limits=1,
                worker_memory_requests=1,
                worker_memory_limits=4,
                verify_tls=False,
            )
        )
        cluster.up()
        cluster.wait_ready()

        generate_cert.generate_tls_cert(cluster_name, self.namespace)
        generate_cert.export_env(cluster_name, self.namespace)

        ray.shutdown()
        ray.init(address=cluster.local_client_url(), logging_level="DEBUG")

        @ray.remote
        def heavy_calculation_part(num_iterations):
            result = 0.0
            for i in range(num_iterations):
                for j in range(num_iterations):
                    for k in range(num_iterations):
                        result += math.sin(i) * math.cos(j) * math.tan(k)
            return result

        @ray.remote
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

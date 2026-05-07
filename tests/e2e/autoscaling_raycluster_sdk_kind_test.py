from time import sleep

import pytest

from codeflare_sdk import Cluster, ClusterConfiguration

from support import *


@pytest.mark.kind
class TestRayClusterAutoscalingSDKKind:
    def setup_method(self):
        initialize_kubernetes_client(self)

    def teardown_method(self):
        delete_namespace(self)

    def test_autoscaling_scale_up_and_down_kind(self):
        self.setup_method()
        create_namespace(self)

        cluster_name = f"autoscale-{random_choice()}"
        ray_image = get_ray_image()

        cluster = Cluster(
            ClusterConfiguration(
                name=cluster_name,
                namespace=self.namespace,
                enable_autoscaling=True,
                min_workers=1,
                max_workers=4,
                head_cpu_requests="500m",
                head_cpu_limits="500m",
                worker_cpu_requests="500m",
                worker_cpu_limits=1,
                worker_memory_requests=1,
                worker_memory_limits=4,
                image=ray_image,
                write_to_file=True,
                verify_tls=False,
            )
        )

        cluster.apply()
        cluster.wait_ready(timeout=600, dashboard_check=False)

        # Verify initial state: 1 worker (min_workers)
        wait_for_worker_count(self, cluster_name, lambda n: n == 1, timeout_s=300)

        # Trigger scale-up via load script in head pod
        run_autoscaling_load_in_head_pod(self, cluster_name)

        # Verify scale-up
        wait_for_worker_count(self, cluster_name, lambda n: n >= 2, timeout_s=600)

        # Wait for idle timeout + verify scale-down back to min_workers
        sleep(90)
        wait_for_worker_count(self, cluster_name, lambda n: n == 1, timeout_s=600)

        cluster.down()

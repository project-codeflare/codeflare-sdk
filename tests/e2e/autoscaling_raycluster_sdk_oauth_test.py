import pytest

from codeflare_sdk import Cluster, ClusterConfiguration

from support import *


@pytest.mark.openshift
@pytest.mark.tier1
class TestRayClusterAutoscalingSDKOauth:
    def setup_method(self):
        initialize_kubernetes_client(self)

    def teardown_method(self):
        if hasattr(self, "auth_instance"):
            cleanup_authentication(self.auth_instance)
        delete_namespace(self)

    @pytest.mark.timeout(1800)
    def test_autoscaling_scale_up_and_down_openshift_oauth(self):
        self.setup_method()

        create_namespace(self)

        ray_image = get_ray_image()
        resources = get_platform_appropriate_resources()
        self.auth_instance = authenticate_for_tests()

        cluster_name = f"autoscale-{random_choice()}"

        cluster = Cluster(
            ClusterConfiguration(
                name=cluster_name,
                namespace=self.namespace,
                enable_autoscaling=True,
                min_workers=1,
                max_workers=2,
                image=ray_image,
                write_to_file=True,
                verify_tls=False,
                **resources,
            )
        )

        cluster.apply()
        wait_ready_with_stuck_detection(cluster, timeout=900, dashboard_check=False)

        # Verify initial state: 1 worker (min_workers)
        wait_for_worker_count(self, cluster_name, lambda n: n == 1, timeout_s=600)

        # Trigger scale-up via load script in head pod (async)
        load_proc = run_autoscaling_load_in_head_pod(
            self, cluster_name, tasks=2, sleep_s=180
        )

        # Verify scale-up while load is still running
        wait_for_worker_count(self, cluster_name, lambda n: n >= 2, timeout_s=900)

        # Wait for load to finish, then verify scale-down back to min_workers
        load_proc.wait(timeout=600)
        assert load_proc.returncode == 0, "Load script failed"

        wait_for_worker_count(self, cluster_name, lambda n: n == 1, timeout_s=900)

        cluster.down()

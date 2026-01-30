from codeflare_sdk import (
    Cluster,
    ClusterConfiguration,
)

from codeflare_sdk.common.kueue.kueue import list_local_queues

import pytest

from support import *


@pytest.mark.skip(reason="Temporarily skipped due to needed investigation")
@pytest.mark.openshift
@pytest.mark.tier1
class TestHeterogeneousClustersOauth:
    def setup_method(self):
        initialize_kubernetes_client(self)

    def teardown_method(self):
        # Clean up authentication if needed
        if hasattr(self, "auth_instance"):
            cleanup_authentication(self.auth_instance)
        delete_namespace(self)
        delete_kueue_resources(self)

    def test_heterogeneous_clusters(self):
        create_namespace(self)
        create_kueue_resources(self, 2, with_labels=True, with_tolerations=True)
        self.run_heterogeneous_clusters()

    def run_heterogeneous_clusters(
        self, gpu_resource_name="nvidia.com/gpu", number_of_gpus=0
    ):
        ray_image = get_ray_image()

        # Set up authentication based on detected method
        auth_instance = authenticate_for_tests()

        # Store auth instance for cleanup
        self.auth_instance = auth_instance

        for flavor in self.resource_flavors:
            node_labels = (
                get_flavor_spec(self, flavor).get("spec", {}).get("nodeLabels", {})
            )
            expected_nodes = get_nodes_by_label(self, node_labels)

            print(f"Expected nodes: {expected_nodes}")
            cluster_name = f"test-ray-cluster-li-{flavor[-5:]}"
            queues = list_local_queues(namespace=self.namespace, flavors=[flavor])
            queue_name = queues[0]["name"] if queues else None
            print(f"Using flavor: {flavor}, Queue: {queue_name}")
            cluster = Cluster(
                ClusterConfiguration(
                    namespace=self.namespace,
                    name=cluster_name,
                    num_workers=1,
                    head_cpu_requests="500m",
                    head_cpu_limits="500m",
                    head_memory_requests=2,
                    head_memory_limits=4,
                    worker_cpu_requests="500m",
                    worker_cpu_limits=1,
                    worker_memory_requests=2,
                    worker_memory_limits=4,
                    image=ray_image,
                    verify_tls=False,
                    local_queue=queue_name,
                )
            )
            cluster.apply()
            # Wait for the cluster to be scheduled and ready, we don't need the dashboard for this check
            wait_ready_with_stuck_detection(cluster, dashboard_check=False)
            node_name = get_pod_node(self, self.namespace, cluster_name)
            print(f"Cluster {cluster_name}-{flavor} is running on node: {node_name}")
            assert (
                node_name in expected_nodes
            ), f"Node {node_name} is not in the expected nodes for flavor {flavor}."
            cluster.down()

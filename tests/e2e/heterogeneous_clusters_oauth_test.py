from time import sleep
import time
from codeflare_sdk import (
    Cluster,
    ClusterConfiguration,
    TokenAuthentication,
)

from codeflare_sdk.common.kueue.kueue import list_local_queues

import pytest

from support import *


@pytest.mark.openshift
class TestHeterogenousClustersOauth:
    def setup_method(self):
        initialize_kubernetes_client(self)

    def teardown_method(self):
        delete_namespace(self)
        delete_kueue_resources(self)

    def test_heterogeneous_clusters(self):
        create_namespace(self)
        create_kueue_resources(self, 2)
        self.run_heterogeneous_clusters()

    def run_heterogeneous_clusters(
        self, gpu_resource_name="nvidia.com/gpu", number_of_gpus=0
    ):
        ray_image = get_ray_image()

        auth = TokenAuthentication(
            token=run_oc_command(["whoami", "--show-token=true"]),
            server=run_oc_command(["whoami", "--show-server=true"]),
            skip_tls=True,
        )
        auth.login()

        used_nodes = []

        for flavor in self.resource_flavors:
            cluster_name = f"test-ray-cluster-li-{flavor[-5:]}"
            queues = list_local_queues(namespace=self.namespace, flavors=[flavor])
            queue_name = queues[0]["name"] if queues else None
            print(f"Using flavor: {flavor}, Queue: {queue_name}")
            cluster = Cluster(
                ClusterConfiguration(
                    namespace=self.namespace,
                    name=cluster_name,
                    num_workers=1,
                    worker_cpu_requests=1,
                    worker_cpu_limits=1,
                    worker_memory_requests=1,
                    worker_memory_limits=4,
                    image=ray_image,
                    verify_tls=False,
                    local_queue=queue_name,
                )
            )
            cluster.up()
            time.sleep(5)
            node_name = get_pod_node(self, self.namespace, cluster_name)
            print(f"Cluster {cluster_name}-{flavor} is running on node: {node_name}")
            time.sleep(5)
            assert (
                node_name not in used_nodes
            ), f"Node {node_name} was already used by another flavor."
            used_nodes.append(node_name)
            cluster.down()

from time import sleep
import time
from codeflare_sdk import (
    Cluster,
    ClusterConfiguration,
    TokenAuthentication,
    generate_cert,
)

from codeflare_sdk.common.kueue.kueue import list_local_queues

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

    def test_heterogeneous_clusters(self):
        create_namespace(self)
        create_kueue_resources(self)
        self.run_heterogeneous_clusters()

    def run_heterogeneous_clusters(
        self, gpu_resource_name="nvidia.com/gpu", number_of_gpus=0
    ):
        cluster_name = "test-ray-cluster-li"

        used_nodes = []

        for flavor in self.resource_flavors:
            queues = list_local_queues(namespace=self.namespace, flavors=[flavor])
            print(queues)
            queue_name = queues[0]["name"] if queues else None
            print(f"Using flavor: {flavor}, Queue: {queue_name}")
            cluster = Cluster(
                ClusterConfiguration(
                    name=f"{cluster_name}-{flavor}",
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
                    worker_extended_resource_requests={
                        gpu_resource_name: number_of_gpus
                    },
                    write_to_file=True,
                    verify_tls=False,
                    local_queue=queue_name,
                )
            )
            cluster.up()
            time.sleep(2)
            pod_name = f"{cluster_name}-{flavor}"
            node_name = get_pod_node(self.namespace, pod_name)
            print(f"Cluster {cluster_name}-{flavor} is running on node: {node_name}")
            time.sleep(2)
            assert (
                node_name not in used_nodes
            ), f"Node {node_name} was already used by another flavor."
            used_nodes.append(node_name)
            cluster.down()

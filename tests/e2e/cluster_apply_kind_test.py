from codeflare_sdk import Cluster, ClusterConfiguration
import pytest
from kubernetes import client

from support import (
    initialize_kubernetes_client,
    create_namespace,
    delete_namespace,
    get_ray_cluster,
)


@pytest.mark.kind
class TestRayClusterApply:
    def setup_method(self):
        initialize_kubernetes_client(self)

    def teardown_method(self):
        delete_namespace(self)

    def test_cluster_apply(self):
        self.setup_method()
        create_namespace(self)

        cluster_name = "test-cluster-apply"
        namespace = self.namespace

        # Initial configuration with 1 worker
        initial_config = ClusterConfiguration(
            name=cluster_name,
            namespace=namespace,
            num_workers=1,
            head_cpu_requests="500m",
            head_cpu_limits="1",
            head_memory_requests="1Gi",
            head_memory_limits="2Gi",
            worker_cpu_requests="500m",
            worker_cpu_limits="1",
            worker_memory_requests="1Gi",
            worker_memory_limits="2Gi",
            write_to_file=True,
            verify_tls=False,
        )

        # Create the cluster
        cluster = Cluster(initial_config)
        cluster.apply()

        # Wait for the cluster to be ready
        cluster.wait_ready()
        status = cluster.status()
        assert status["ready"], f"Cluster {cluster_name} is not ready: {status}"

        # Verify the cluster is created
        ray_cluster = get_ray_cluster(cluster_name, namespace)
        assert ray_cluster is not None, "Cluster was not created successfully"
        assert (
            ray_cluster["spec"]["workerGroupSpecs"][0]["replicas"] == 1
        ), "Initial worker count does not match"

        # Update configuration with 3 workers
        updated_config = ClusterConfiguration(
            name=cluster_name,
            namespace=namespace,
            num_workers=2,
            head_cpu_requests="500m",
            head_cpu_limits="1",
            head_memory_requests="1Gi",
            head_memory_limits="2Gi",
            worker_cpu_requests="500m",
            worker_cpu_limits="1",
            worker_memory_requests="1Gi",
            worker_memory_limits="2Gi",
            write_to_file=True,
            verify_tls=False,
        )

        # Apply the updated configuration
        cluster.config = updated_config
        cluster.apply()

        # Wait for the updated cluster to be ready
        cluster.wait_ready()
        updated_status = cluster.status()
        assert updated_status[
            "ready"
        ], f"Cluster {cluster_name} is not ready after update: {updated_status}"

        # Verify the cluster is updated
        updated_ray_cluster = get_ray_cluster(cluster_name, namespace)
        assert (
            updated_ray_cluster["spec"]["workerGroupSpecs"][0]["replicas"] == 2
        ), "Worker count was not updated"

        # Clean up
        cluster.down()
        ray_cluster = get_ray_cluster(cluster_name, namespace)
        assert ray_cluster is None, "Cluster was not deleted successfully"

    def test_apply_invalid_update(self):
        self.setup_method()
        create_namespace(self)

        cluster_name = "test-cluster-apply-invalid"
        namespace = self.namespace

        # Initial configuration
        initial_config = ClusterConfiguration(
            name=cluster_name,
            namespace=namespace,
            num_workers=1,
            head_cpu_requests="500m",
            head_cpu_limits="1",
            head_memory_requests="1Gi",
            head_memory_limits="2Gi",
            worker_cpu_requests="500m",
            worker_cpu_limits="1",
            worker_memory_requests="1Gi",
            worker_memory_limits="2Gi",
            write_to_file=True,
            verify_tls=False,
        )

        # Create the cluster
        cluster = Cluster(initial_config)
        cluster.apply()

        # Wait for the cluster to be ready
        cluster.wait_ready()
        status = cluster.status()
        assert status["ready"], f"Cluster {cluster_name} is not ready: {status}"

        # Update with an invalid configuration (e.g., immutable field change)
        invalid_config = ClusterConfiguration(
            name=cluster_name,
            namespace=namespace,
            num_workers=2,
            head_cpu_requests="1",
            head_cpu_limits="2",  # Changing CPU limits (immutable)
            head_memory_requests="1Gi",
            head_memory_limits="2Gi",
            worker_cpu_requests="500m",
            worker_cpu_limits="1",
            worker_memory_requests="1Gi",
            worker_memory_limits="2Gi",
            write_to_file=True,
            verify_tls=False,
        )

        # Try to apply the invalid configuration and expect failure
        cluster.config = invalid_config
        with pytest.raises(RuntimeError, match="Immutable fields detected"):
            cluster.apply()

        # Clean up
        cluster.down()

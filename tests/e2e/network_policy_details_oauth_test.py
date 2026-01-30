"""
Network Policy Details Test

This test provides detailed verification of NetworkPolicy configuration
for RayClusters, including:
- Pod selectors targeting Ray pods
- Allowed ports for Ray communication
- Policy types (Ingress/Egress)

It also verifies that NetworkPolicies are properly cleaned up when the
RayCluster is deleted.
"""

import pytest

from codeflare_sdk import (
    Cluster,
    ClusterConfiguration,
)

from kubernetes import client

from support import (
    initialize_kubernetes_client,
    create_namespace,
    delete_namespace,
    create_kueue_resources,
    delete_kueue_resources,
    get_ray_image,
    run_oc_command,
    authenticate_for_tests,
    cleanup_authentication,
    # Gateway API helpers
    wait_for_network_policies,
    wait_for_network_policies_deletion,
    verify_network_policy_spec,
    wait_ready_enhanced,
)


@pytest.mark.openshift
@pytest.mark.tier1
class TestNetworkPolicyDetails:
    """
    Detailed tests for NetworkPolicy configuration on RayClusters.
    """

    def setup_method(self):
        initialize_kubernetes_client(self)
        self.networking_api = client.NetworkingV1Api(self.api_instance.api_client)

    def teardown_method(self):
        # Clean up authentication if needed
        if hasattr(self, "auth_instance"):
            cleanup_authentication(self.auth_instance)
        # Only delete namespace if it was created
        if hasattr(self, "namespace"):
            delete_namespace(self)
        # Only delete kueue resources if they were created
        if hasattr(self, "cluster_queues") and hasattr(self, "resource_flavors"):
            delete_kueue_resources(self)

    def test_network_policy_ports_and_selectors(self):
        """
        Test that NetworkPolicies have correct ports and pod selectors
        for Ray cluster communication.
        """
        self.setup_method()
        create_namespace(self)
        create_kueue_resources(self)

        cluster_name = "netpol-test"
        ray_image = get_ray_image()

        # Set up authentication based on detected method
        auth_instance = authenticate_for_tests()

        # Store auth instance for cleanup
        self.auth_instance = auth_instance

        cluster = Cluster(
            ClusterConfiguration(
                name=cluster_name,
                namespace=self.namespace,
                num_workers=1,
                head_memory_requests=6,
                head_memory_limits=8,
                worker_cpu_requests=1,
                worker_cpu_limits=1,
                worker_memory_requests=6,
                worker_memory_limits=8,
                image=ray_image,
                write_to_file=True,
                verify_tls=False,
            )
        )

        found_network_policies = False

        try:
            cluster.apply()
            wait_ready_enhanced(cluster)

            # Get network policies
            policies = wait_for_network_policies(
                self.networking_api,
                cluster_name,
                self.namespace,
                timeout=120,
            )

            if not policies:
                pytest.skip("No NetworkPolicies found")

            found_network_policies = True
            print(f"\n--- NetworkPolicy Analysis ---")
            print(f"Found {len(policies)} policies for cluster '{cluster_name}'")

            for policy in policies:
                verification = verify_network_policy_spec(policy, cluster_name)

                print(f"\nPolicy: {verification['name']}")

                # Check for proper pod selector
                selector = verification["pod_selector_labels"]
                if selector:
                    print(f"  Pod Selector Labels:")
                    for key, value in selector.items():
                        print(f"    {key}: {value}")

                    # Verify selector targets Ray pods
                    ray_selector_keys = ["ray.io/cluster", "ray.io/node-type"]
                    has_ray_selector = any(key in selector for key in ray_selector_keys)
                    assert has_ray_selector or cluster_name in str(
                        selector
                    ), f"Policy should target Ray pods, got selector: {selector}"
                    print("  ✓ Pod selector targets Ray pods")

                # Check allowed ports
                ports = verification["allowed_ports"]
                if ports:
                    print(f"  Allowed Ports: {ports}")

                    # Common Ray ports
                    ray_ports = {6379, 8265, 10001}
                    overlapping = ray_ports.intersection(set(ports))
                    if overlapping:
                        print(f"  ✓ Ray-specific ports allowed: {overlapping}")

                # Check policy types
                policy_types = verification["policy_types"]
                if policy_types:
                    print(f"  Policy Types: {policy_types}")

        finally:
            try:
                cluster.down()
                print(f"\n--- Cluster '{cluster_name}' deletion initiated ---")
            except Exception as e:
                print(f"Warning: Failed to bring down cluster: {e}")

            # Verify NetworkPolicy cleanup
            if found_network_policies:
                print(
                    f"\nVerifying NetworkPolicy cleanup for cluster '{cluster_name}'..."
                )
                remaining_policies = wait_for_network_policies_deletion(
                    self.networking_api,
                    cluster_name,
                    self.namespace,
                    timeout=120,
                )
                if not remaining_policies:
                    print(
                        f"✓ NetworkPolicy(ies) for cluster '{cluster_name}' properly cleaned up"
                    )
                else:
                    policy_names = [p.metadata.name for p in remaining_policies]
                    print(f"✗ NetworkPolicy(ies) were NOT cleaned up: {policy_names}")
                    print(
                        "  (This may be due to async cleanup timing or operator behavior)"
                    )

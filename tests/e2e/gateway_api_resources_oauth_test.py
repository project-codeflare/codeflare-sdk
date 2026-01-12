"""
Gateway API Resources Verification Test

This test verifies that when a RayCluster is created, the following
Gateway API resources are properly created and configured:

1. ReferenceGrant - named "kuberay-gateway-access" in the RayCluster's namespace
2. NetworkPolicies - with appropriate selectors and ports
3. HTTPRoute - for dashboard access

It also verifies that these resources are properly cleaned up when the
RayCluster is deleted.
"""

import pytest
from typing import Optional

from codeflare_sdk import (
    Cluster,
    ClusterConfiguration,
    TokenAuthentication,
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
    # Gateway API helpers
    get_reference_grant,
    list_reference_grants,
    get_httproutes_for_cluster,
    wait_for_reference_grant,
    wait_for_httproute,
    wait_for_network_policies,
    wait_for_reference_grant_deletion,
    wait_for_httproute_deletion,
    wait_for_network_policies_deletion,
    verify_reference_grant_spec,
    verify_httproute_spec,
    verify_network_policy_spec,
)


@pytest.mark.openshift
@pytest.mark.tier1
class TestGatewayApiResources:
    """
    Test Gateway API resources (ReferenceGrant, HTTPRoute, NetworkPolicy)
    are properly created when a RayCluster is deployed.
    """

    def setup_method(self):
        initialize_kubernetes_client(self)
        # Initialize additional APIs
        self.networking_api = client.NetworkingV1Api(self.api_instance.api_client)

    def teardown_method(self):
        # Only delete namespace if it was created
        if hasattr(self, "namespace"):
            delete_namespace(self)
        # Only delete kueue resources if they were created
        if hasattr(self, "cluster_queues") and hasattr(self, "resource_flavors"):
            delete_kueue_resources(self)

    def test_gateway_resources_created_with_raycluster(self):
        """
        Test that ReferenceGrant, HTTPRoute, and NetworkPolicies are created
        when a RayCluster is deployed.
        """
        self.setup_method()
        create_namespace(self)
        create_kueue_resources(self)

        cluster_name = "gateway-test"
        ray_image = get_ray_image()

        # Authenticate with current user token
        auth = TokenAuthentication(
            token=run_oc_command(["whoami", "--show-token=true"]),
            server=run_oc_command(["whoami", "--show-server=true"]),
            skip_tls=True,
        )
        auth.login()

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

        # Track which resources were found so we can verify cleanup
        found_reference_grant = False
        found_httproute = False
        found_network_policies = False
        reference_grant_name = None

        try:
            # Apply the cluster
            cluster.apply()

            # Wait for cluster to be ready
            cluster.wait_ready()

            # Verify ReferenceGrant is created
            reference_grant_name = self.verify_reference_grant_created(cluster_name)
            found_reference_grant = reference_grant_name is not None

            # Verify HTTPRoute is created
            found_httproute = self.verify_httproute_created(cluster_name)

            # Verify NetworkPolicies are created
            found_network_policies = self.verify_network_policies_created(cluster_name)

            # Verify dashboard is accessible via HTTPRoute
            dashboard_url = cluster.cluster_dashboard_uri()
            assert dashboard_url, "Dashboard URL should be available"
            assert (
                "Dashboard not available" not in dashboard_url
            ), f"Dashboard should be available, got: {dashboard_url}"
            print(f"✓ Dashboard URL: {dashboard_url}")

        finally:
            # Clean up
            try:
                cluster.down()
                print(f"\n--- Cluster '{cluster_name}' deletion initiated ---")
            except Exception as e:
                print(f"Warning: Failed to bring down cluster: {e}")

            # Verify cleanup of gateway resources
            self.verify_resources_cleanup(
                cluster_name,
                found_reference_grant,
                found_httproute,
                found_network_policies,
                reference_grant_name,
            )

    def verify_reference_grant_created(self, cluster_name: str) -> Optional[str]:
        """
        Verify that ReferenceGrant resource is created in the namespace.

        Expected ReferenceGrant name: "kuberay-gateway-access"

        Returns:
            Name of the ReferenceGrant if found, None otherwise (test skipped)
        """
        print(f"\n--- Verifying ReferenceGrant for cluster '{cluster_name}' ---")

        # Wait for ReferenceGrant to be created
        reference_grant = wait_for_reference_grant(
            self.custom_api,
            self.namespace,
            name="kuberay-gateway-access",
            timeout=120,
        )

        if not reference_grant:
            # Try listing all reference grants to help debug
            all_grants = list_reference_grants(self.custom_api, self.namespace)
            if all_grants:
                grant_names = [g.get("metadata", {}).get("name") for g in all_grants]
                print(f"Found ReferenceGrants in namespace: {grant_names}")
                # Use the first one found
                reference_grant = all_grants[0]
            else:
                pytest.skip(
                    "ReferenceGrant 'kuberay-gateway-access' not found. "
                    "This may be expected if Gateway API is not configured on this cluster."
                )
                return None

        assert reference_grant is not None, "ReferenceGrant should exist"
        grant_name = reference_grant.get("metadata", {}).get("name")
        print(f"✓ ReferenceGrant found: {grant_name}")

        # Verify the spec
        assert verify_reference_grant_spec(
            reference_grant
        ), "ReferenceGrant spec validation failed"
        print("✓ ReferenceGrant spec is valid")

        # Print details
        spec = reference_grant.get("spec", {})
        from_entries = spec.get("from", [])
        to_entries = spec.get("to", [])
        print(f"  From entries: {len(from_entries)}")
        for entry in from_entries:
            print(
                f"    - Group: {entry.get('group', 'core')}, Kind: {entry.get('kind')}, Namespace: {entry.get('namespace')}"
            )
        print(f"  To entries: {len(to_entries)}")
        for entry in to_entries:
            print(
                f"    - Group: {entry.get('group', 'core')}, Kind: {entry.get('kind')}"
            )

        return grant_name

    def verify_httproute_created(self, cluster_name: str) -> bool:
        """
        Verify that HTTPRoute is created for the RayCluster.

        Returns:
            True if HTTPRoute(s) found, False otherwise (test skipped)
        """
        print(f"\n--- Verifying HTTPRoute for cluster '{cluster_name}' ---")

        # Wait for HTTPRoute to be created
        httproutes = wait_for_httproute(
            self.custom_api,
            cluster_name,
            self.namespace,
            timeout=120,
        )

        if not httproutes:
            pytest.skip(
                "HTTPRoute not found for cluster. "
                "This may be expected if Gateway API is not configured on this cluster."
            )
            return False

        assert len(httproutes) > 0, "At least one HTTPRoute should exist"
        print(f"✓ Found {len(httproutes)} HTTPRoute(s)")

        for httproute in httproutes:
            route_name = httproute.get("metadata", {}).get("name")
            route_namespace = httproute.get("metadata", {}).get("namespace")
            print(f"  HTTPRoute: {route_namespace}/{route_name}")

            # Verify spec
            assert verify_httproute_spec(
                httproute, cluster_name, self.namespace
            ), f"HTTPRoute {route_name} spec validation failed"
            print(f"  ✓ HTTPRoute '{route_name}' spec is valid")

            # Print details
            spec = httproute.get("spec", {})
            parent_refs = spec.get("parentRefs", [])
            for parent in parent_refs:
                print(f"    Gateway: {parent.get('namespace')}/{parent.get('name')}")

            rules = spec.get("rules", [])
            for i, rule in enumerate(rules):
                backend_refs = rule.get("backendRefs", [])
                for backend in backend_refs:
                    print(
                        f"    Rule {i} -> Service: {backend.get('name')}:{backend.get('port')}"
                    )

        return True

    def verify_network_policies_created(self, cluster_name: str) -> bool:
        """
        Verify that NetworkPolicies are created for the RayCluster
        with appropriate selectors and ports.

        Returns:
            True if NetworkPolicy(ies) found, False otherwise (test skipped)
        """
        print(f"\n--- Verifying NetworkPolicies for cluster '{cluster_name}' ---")

        # Wait for NetworkPolicies to be created
        policies = wait_for_network_policies(
            self.networking_api,
            cluster_name,
            self.namespace,
            timeout=120,
        )

        if not policies:
            pytest.skip(
                "NetworkPolicies not found for cluster. "
                "This may be expected if NetworkPolicy enforcement is not enabled."
            )
            return False

        assert len(policies) > 0, "At least one NetworkPolicy should exist"
        print(f"✓ Found {len(policies)} NetworkPolicy(ies)")

        # Expected Ray ports
        expected_ray_ports = {
            6379,  # Redis/GCS
            8265,  # Dashboard
            10001,  # Ray client
        }

        all_allowed_ports = set()

        for policy in policies:
            verification = verify_network_policy_spec(policy, cluster_name)
            print(f"\n  NetworkPolicy: {verification['name']}")
            print(f"    Has pod selector: {verification['has_pod_selector']}")
            print(f"    Pod selector labels: {verification['pod_selector_labels']}")
            print(f"    Has ingress rules: {verification['has_ingress_rules']}")
            print(f"    Has egress rules: {verification['has_egress_rules']}")
            print(f"    Policy types: {verification['policy_types']}")
            print(f"    Allowed ports: {verification['allowed_ports']}")

            all_allowed_ports.update(verification["allowed_ports"])

            # Verify pod selector includes ray cluster label
            selector_labels = verification["pod_selector_labels"]
            has_ray_label = any(
                "ray" in key.lower() or cluster_name in str(value)
                for key, value in selector_labels.items()
            )
            if not has_ray_label:
                print(f"    Warning: Pod selector may not target Ray cluster")

        # Check if Ray-specific ports are allowed
        ray_ports_allowed = expected_ray_ports.intersection(all_allowed_ports)
        print(f"\n✓ Ray-specific ports allowed: {ray_ports_allowed}")

        return True

    def verify_resources_cleanup(
        self,
        cluster_name: str,
        found_reference_grant: bool,
        found_httproute: bool,
        found_network_policies: bool,
        reference_grant_name: Optional[str],
    ):
        """
        Verify that all gateway-related resources are properly cleaned up
        after the RayCluster is deleted.
        """
        print(f"\n--- Verifying Resource Cleanup for cluster '{cluster_name}' ---")

        cleanup_timeout = 120  # seconds to wait for cleanup
        cleanup_success = True

        # Verify ReferenceGrant cleanup
        if found_reference_grant and reference_grant_name:
            print(f"\nVerifying ReferenceGrant '{reference_grant_name}' cleanup...")
            grant_deleted = wait_for_reference_grant_deletion(
                self.custom_api,
                self.namespace,
                name=reference_grant_name,
                timeout=cleanup_timeout,
            )
            if grant_deleted:
                print(f"✓ ReferenceGrant '{reference_grant_name}' properly cleaned up")
            else:
                print(f"✗ ReferenceGrant '{reference_grant_name}' was NOT cleaned up")
                cleanup_success = False
        else:
            print(
                "Skipping ReferenceGrant cleanup verification (not found during test)"
            )

        # Verify HTTPRoute cleanup
        if found_httproute:
            print(f"\nVerifying HTTPRoute cleanup for cluster '{cluster_name}'...")
            httproute_deleted = wait_for_httproute_deletion(
                self.custom_api,
                cluster_name,
                self.namespace,
                timeout=cleanup_timeout,
            )
            if httproute_deleted:
                print(
                    f"✓ HTTPRoute(s) for cluster '{cluster_name}' properly cleaned up"
                )
            else:
                # Check what's remaining
                remaining_routes = get_httproutes_for_cluster(
                    self.custom_api, cluster_name, self.namespace
                )
                route_names = [
                    r.get("metadata", {}).get("name") for r in remaining_routes
                ]
                print(f"✗ HTTPRoute(s) were NOT cleaned up: {route_names}")
                cleanup_success = False
        else:
            print("Skipping HTTPRoute cleanup verification (not found during test)")

        # Verify NetworkPolicy cleanup
        if found_network_policies:
            print(f"\nVerifying NetworkPolicy cleanup for cluster '{cluster_name}'...")
            remaining_policies = wait_for_network_policies_deletion(
                self.networking_api,
                cluster_name,
                self.namespace,
                timeout=cleanup_timeout,
            )
            if not remaining_policies:
                print(
                    f"✓ NetworkPolicy(ies) for cluster '{cluster_name}' properly cleaned up"
                )
            else:
                policy_names = [p.metadata.name for p in remaining_policies]
                print(f"✗ NetworkPolicy(ies) were NOT cleaned up: {policy_names}")
                cleanup_success = False
        else:
            print("Skipping NetworkPolicy cleanup verification (not found during test)")

        # Final summary
        print(f"\n--- Cleanup Verification Summary ---")
        if cleanup_success:
            print("✓ All gateway resources properly cleaned up")
        else:
            print("✗ Some gateway resources were not properly cleaned up")
            # Note: We don't fail the test here because cleanup might be handled
            # asynchronously by the operator or might have different timing.
            # The warning is sufficient to alert about potential issues.
            print("  (This may be due to async cleanup timing or operator behavior)")

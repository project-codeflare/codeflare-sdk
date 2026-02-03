# Copyright 2024 IBM, Red Hat
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
Kubernetes and accelerator helper methods for RayCluster.

This mixin keeps Kubernetes-specific logic separate from the main class
to improve readability and ease of testing.
"""

from typing import Optional, Tuple

from kubernetes import client
from kubernetes.client.rest import ApiException

from ...common import _kube_api_error_handling
from ...common.kubernetes_cluster.auth import config_check, get_api_client
from .constants import CF_SDK_FIELD_MANAGER, FORBIDDEN_CUSTOM_RESOURCE_TYPES
from ..cluster.status import RayClusterStatus

# Module-level cache for OpenShift cluster detection.
# This avoids repeated API calls since cluster type doesn't change during runtime.
_openshift_cluster_cache: Optional[bool] = None


class RayClusterKubernetesHelpersMixin:
    """
    Mixin that provides Kubernetes API helpers and accelerator utilities.

    This mixin provides:
    - Static utility methods for extracting data from Kubernetes resources
    - Instance methods for cluster-specific operations that may need instance state
    - Accelerator and GPU helper methods that depend on cluster configuration

    Methods are organized by purpose:
    - Static helpers: Pure utility functions that don't need instance state
    - Instance methods: Operations that may access instance attributes or are
      called frequently as instance methods for consistency
    """

    # -------------------------------------------------------------------------
    # Static Utility Methods (Pure Functions)
    # -------------------------------------------------------------------------

    @staticmethod
    def _extract_status_from_rc(rc: dict) -> RayClusterStatus:
        """
        Extract the RayClusterStatus from a RayCluster resource dict.

        This is a pure utility function that doesn't require instance state.
        Can be called as RayCluster._extract_status_from_rc(rc) or
        self._extract_status_from_rc(rc).

        Args:
            rc: The RayCluster resource dictionary from Kubernetes API.

        Returns:
            RayClusterStatus enum value.
        """
        if "status" in rc and "state" in rc["status"]:
            try:
                return RayClusterStatus(rc["status"]["state"].lower())
            except ValueError:
                return RayClusterStatus.UNKNOWN
        return RayClusterStatus.UNKNOWN

    @staticmethod
    def _head_worker_extended_resources_from_rc_dict(rc: dict) -> Tuple[dict, dict]:
        """
        Extract extended resources from RayCluster dict.

        This is a pure utility function that doesn't require instance state.
        Can be called as RayCluster._head_worker_extended_resources_from_rc_dict(rc)
        or self._head_worker_extended_resources_from_rc_dict(rc).

        Args:
            rc: The RayCluster resource dictionary from Kubernetes API.

        Returns:
            Tuple of (head_extended_resources, worker_extended_resources) dictionaries.
        """
        head_extended_resources = {}
        worker_extended_resources = {}

        # Worker resources.
        for resource in rc["spec"]["workerGroupSpecs"][0]["template"]["spec"][
            "containers"
        ][0]["resources"]["limits"].keys():
            if resource in ["memory", "cpu"]:
                continue
            worker_extended_resources[resource] = rc["spec"]["workerGroupSpecs"][0][
                "template"
            ]["spec"]["containers"][0]["resources"]["limits"][resource]

        # Head resources.
        for resource in rc["spec"]["headGroupSpec"]["template"]["spec"]["containers"][
            0
        ]["resources"]["limits"].keys():
            if resource in ["memory", "cpu"]:
                continue
            head_extended_resources[resource] = rc["spec"]["headGroupSpec"]["template"][
                "spec"
            ]["containers"][0]["resources"]["limits"][resource]

        return head_extended_resources, worker_extended_resources

    # -------------------------------------------------------------------------
    # Instance Methods (May Access Instance State)
    # -------------------------------------------------------------------------

    def _is_openshift_cluster(self) -> bool:
        """
        Check if running on OpenShift cluster.

        This method caches its result at module level to avoid repeated API calls,
        since the cluster type doesn't change during runtime.

        This method is an instance method for consistency with how it's called
        throughout the codebase, even though it doesn't currently use instance state.
        This makes the API clearer and allows for future enhancements that might
        need instance-specific configuration.

        Returns:
            True if running on OpenShift, False otherwise.
        """
        global _openshift_cluster_cache

        if _openshift_cluster_cache is not None:
            return _openshift_cluster_cache

        try:
            config_check()
            for api in client.ApisApi(get_api_client()).get_api_versions().groups:
                for v in api.versions:
                    if "route.openshift.io/v1" in v.group_version:
                        _openshift_cluster_cache = True
                        return True
            _openshift_cluster_cache = False
            return False
        except Exception:  # pragma: no cover
            return False

    @staticmethod
    def _get_dashboard_url_from_httproute(
        cluster_name: str, namespace: str
    ) -> Optional[str]:
        """
        Get the Ray dashboard URL from an HTTPRoute (RHOAI v3.0+ Gateway API).

        This is a static utility method that doesn't require instance state.
        Can be called as RayCluster._get_dashboard_url_from_httproute(name, ns)
        or self._get_dashboard_url_from_httproute(name, ns).

        Args:
            cluster_name: Ray cluster name.
            namespace: Ray cluster namespace.

        Returns:
            Dashboard URL if found, else None.
        """
        try:
            config_check()
            api_instance = client.CustomObjectsApi(get_api_client())

            label_selector = (
                f"ray.io/cluster-name={cluster_name},"
                f"ray.io/cluster-namespace={namespace}"
            )

            # Try cluster-wide search first (if permissions allow).
            try:
                httproutes = api_instance.list_cluster_custom_object(
                    group="gateway.networking.k8s.io",
                    version="v1",
                    plural="httproutes",
                    label_selector=label_selector,
                )
                items = httproutes.get("items", [])
                if items:
                    httproute = items[0]
                else:
                    return None
            except Exception:
                # No cluster-wide permissions, try namespace-specific search.
                search_namespaces = [
                    namespace,
                    "redhat-ods-applications",
                    "opendatahub",
                    "default",
                    "ray-system",
                ]

                httproute = None
                for ns in search_namespaces:
                    try:
                        httproutes = api_instance.list_namespaced_custom_object(
                            group="gateway.networking.k8s.io",
                            version="v1",
                            namespace=ns,
                            plural="httproutes",
                            label_selector=label_selector,
                        )
                        items = httproutes.get("items", [])
                        if items:
                            httproute = items[0]
                            break
                    except ApiException:
                        continue

                if not httproute:
                    return None

            # Extract Gateway reference and construct dashboard URL.
            parent_refs = httproute.get("spec", {}).get("parentRefs", [])
            if not parent_refs:
                return None

            gateway_ref = parent_refs[0]
            gateway_name = gateway_ref.get("name")
            gateway_namespace = gateway_ref.get("namespace")

            if not gateway_name or not gateway_namespace:
                return None

            # Get the Gateway to retrieve the hostname.
            gateway = api_instance.get_namespaced_custom_object(
                group="gateway.networking.k8s.io",
                version="v1",
                namespace=gateway_namespace,
                plural="gateways",
                name=gateway_name,
            )

            # Try to get hostname from multiple locations.
            hostname = None

            # First try spec.listeners[].hostname.
            listeners = gateway.get("spec", {}).get("listeners", [])
            if listeners:
                hostname = listeners[0].get("hostname")

            # If no hostname in listeners, try to find OpenShift Route exposing the Gateway.
            if not hostname:
                try:
                    routes = api_instance.list_namespaced_custom_object(
                        group="route.openshift.io",
                        version="v1",
                        namespace=gateway_namespace,
                        plural="routes",
                    )
                    for route in routes.get("items", []):
                        if route["metadata"]["name"] == gateway_name:
                            hostname = route.get("spec", {}).get("host")
                            break
                except Exception:
                    pass

            # If still no hostname, try status.addresses.
            if not hostname:
                addresses = gateway.get("status", {}).get("addresses", [])
                if addresses:
                    addr_value = addresses[0].get("value")
                    if addr_value and not addr_value.endswith(".svc.cluster.local"):
                        hostname = addr_value

            if not hostname:
                return None

            # Construct dashboard URL.
            return f"https://{hostname}/ray/{namespace}/{cluster_name}"

        except Exception:  # pragma: no cover
            return None

    @staticmethod
    def _apply_ray_cluster(yamls, namespace: str, api_instance, force: bool = False):
        """
        Apply RayCluster using server-side apply.

        This is a static utility method for applying RayCluster resources.
        Can be called as RayCluster._apply_ray_cluster(...) or self._apply_ray_cluster(...).

        Args:
            yamls: The RayCluster resource specification.
            namespace: Kubernetes namespace.
            api_instance: Kubernetes API instance.
            force: Whether to force conflicts during server-side apply.
        """
        api_instance.server_side_apply(
            field_manager=CF_SDK_FIELD_MANAGER,
            group="ray.io",
            version="v1",
            namespace=namespace,
            plural="rayclusters",
            body=yamls,
            force_conflicts=force,
        )

    @staticmethod
    def _delete_resources(
        name: str, namespace: str, api_instance: client.CustomObjectsApi
    ):
        """
        Delete a RayCluster resource.

        This is a static utility method for deleting RayCluster resources.
        Can be called as RayCluster._delete_resources(...) or self._delete_resources(...).

        Args:
            name: Name of the RayCluster to delete.
            namespace: Kubernetes namespace.
            api_instance: Kubernetes CustomObjectsApi instance.
        """
        api_instance.delete_namespaced_custom_object(
            group="ray.io",
            version="v1",
            namespace=namespace,
            plural="rayclusters",
            name=name,
        )

    def _ray_cluster_status(
        self, name: str, namespace: str
    ) -> Optional[RayClusterStatus]:
        """
        Get status of a RayCluster from Kubernetes.

        This is an instance method that queries Kubernetes for cluster status.
        Uses the static _extract_status_from_rc utility method internally.

        Args:
            name: The name of the RayCluster.
            namespace: The namespace of the RayCluster.

        Returns:
            RayClusterStatus enum value, or None if cluster not found.
        """
        try:
            config_check()
            api_instance = client.CustomObjectsApi(get_api_client())
            rcs = api_instance.list_namespaced_custom_object(
                group="ray.io",
                version="v1",
                namespace=namespace,
                plural="rayclusters",
            )
        except Exception as e:  # pragma: no cover
            return _kube_api_error_handling(e)

        for rc in rcs["items"]:
            if rc["metadata"]["name"] == name:
                # Call static method - can use self or class name
                return self._extract_status_from_rc(rc)
        return None

    def _throw_for_no_raycluster(self):
        """
        Check if RayCluster CRD is available.

        This instance method uses self.namespace to check for the CRD.
        Raises RuntimeError if the CRD is not available.

        Raises:
            RuntimeError: If RayCluster CRD is not available or access fails.
        """
        api_instance = client.CustomObjectsApi(get_api_client())
        try:
            api_instance.list_namespaced_custom_object(
                group="ray.io",
                version="v1",
                namespace=self.namespace,
                plural="rayclusters",
            )
        except ApiException as e:
            if e.status == 404:
                raise RuntimeError(
                    "RayCluster CustomResourceDefinition unavailable contact your administrator."
                )
            raise RuntimeError(
                "Failed to get RayCluster CustomResourceDefinition: " + str(e)
            )

    # -------------------------------------------------------------------------
    # GPU and Extended Resource Helpers
    # -------------------------------------------------------------------------

    def _head_worker_gpu_count(self) -> Tuple[int, int]:
        """
        Get GPU counts for head and worker nodes.

        This instance method accesses self.head_accelerators, self.worker_accelerators,
        and self.accelerator_configs to calculate GPU counts.

        Returns:
            Tuple of (head_gpu_count, worker_gpu_count).
        """
        head_gpus = 0
        worker_gpus = 0

        for k in self.head_accelerators.keys():
            resource_type = self.accelerator_configs.get(k, "")
            if resource_type == "GPU":
                head_gpus += int(self.head_accelerators[k])

        for k in self.worker_accelerators.keys():
            resource_type = self.accelerator_configs.get(k, "")
            if resource_type == "GPU":
                worker_gpus += int(self.worker_accelerators[k])

        return head_gpus, worker_gpus

    def _head_worker_accelerators(self) -> Tuple[dict, dict]:
        """
        Get accelerator mapping for head and worker nodes.

        This instance method accesses self.head_accelerators, self.worker_accelerators,
        and self.accelerator_configs to build accelerator resource mappings.

        Returns:
            Tuple of (head_accelerator_dict, worker_accelerator_dict).
        """
        head_resources = {}
        worker_resources = {}

        for k in self.head_accelerators.keys():
            resource_type = self.accelerator_configs.get(k, "")
            if resource_type in FORBIDDEN_CUSTOM_RESOURCE_TYPES:
                continue
            head_resources[resource_type] = self.head_accelerators[
                k
            ] + head_resources.get(resource_type, 0)

        for k in self.worker_accelerators.keys():
            resource_type = self.accelerator_configs.get(k, "")
            if resource_type in FORBIDDEN_CUSTOM_RESOURCE_TYPES:
                continue
            worker_resources[resource_type] = self.worker_accelerators[
                k
            ] + worker_resources.get(resource_type, 0)

        return head_resources, worker_resources

    # -------------------------------------------------------------------------
    # Kueue Queue Helpers
    # -------------------------------------------------------------------------

    def _local_queue_exists(self) -> bool:
        """
        Check if the specified local queue exists in Kubernetes.

        This instance method queries the Kubernetes API to check if a Kueue
        LocalQueue resource exists in the cluster's namespace.

        Returns:
            True if the local queue exists, False otherwise.
        """
        try:
            config_check()
            api_instance = client.CustomObjectsApi(get_api_client())
            local_queues = api_instance.list_namespaced_custom_object(
                group="kueue.x-k8s.io",
                version="v1beta1",
                namespace=self.namespace,
                plural="localqueues",
            )
        except Exception as e:  # pragma: no cover
            return _kube_api_error_handling(e)

        for lq in local_queues["items"]:
            if lq["metadata"]["name"] == self.local_queue:
                return True
        return False

    def _get_default_local_queue(self) -> Optional[str]:
        """
        Get the default local queue if one is configured in Kubernetes.

        This instance method queries the Kubernetes API to find a LocalQueue
        resource marked as the default queue in the cluster's namespace.

        Returns:
            Name of the default local queue if found, None otherwise.
        """
        try:
            config_check()
            api_instance = client.CustomObjectsApi(get_api_client())
            local_queues = api_instance.list_namespaced_custom_object(
                group="kueue.x-k8s.io",
                version="v1beta1",
                namespace=self.namespace,
                plural="localqueues",
            )
        except ApiException as e:  # pragma: no cover
            if e.status in (404, 403):
                return None
            return _kube_api_error_handling(e)

        for lq in local_queues["items"]:
            if (
                "annotations" in lq["metadata"]
                and "kueue.x-k8s.io/default-queue" in lq["metadata"]["annotations"]
                and lq["metadata"]["annotations"][
                    "kueue.x-k8s.io/default-queue"
                ].lower()
                == "true"
            ):
                return lq["metadata"]["name"]
        return None

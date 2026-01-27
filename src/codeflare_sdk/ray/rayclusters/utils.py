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
Utility functions for RayCluster operations.

These helpers are module-level to keep the RayCluster class focused on
instance behavior, while still providing a clean public API.
"""

import logging
from typing import List, Optional, TYPE_CHECKING

from kubernetes import client

logger = logging.getLogger(__name__)

from ...common import _kube_api_error_handling
from ...common.kubernetes_cluster.auth import config_check, get_api_client
from ..cluster.status import RayClusterStatus

if TYPE_CHECKING:  # pragma: no cover
    from .raycluster import RayCluster


def list_all_clusters(
    namespace: str, print_to_console: bool = True
) -> List["RayCluster"]:
    """
    Returns (and prints by default) a list of all clusters in a given namespace.

    Args:
        namespace: The Kubernetes namespace to list clusters from.
        print_to_console: Whether to print the clusters to console.

    Returns:
        List of RayCluster objects representing the clusters.
    """
    from ..cluster import pretty_print

    clusters = _get_ray_clusters(namespace)
    if print_to_console:
        pretty_print.print_clusters(clusters)
    return clusters


def list_all_queued(
    namespace: str, print_to_console: bool = True
) -> List["RayCluster"]:
    """
    Returns (and prints by default) a list of Ray Clusters that are READY or SUSPENDED.

    This function returns clusters in READY or SUSPENDED states. SUSPENDED clusters
    are those queued by Kueue waiting for resources to become available.
    READY clusters are included for backward compatibility with existing workflows.

    Note:
        Despite the name suggesting only "queued" clusters, this function includes
        both READY clusters (running) and SUSPENDED clusters (queued by Kueue).

    Args:
        namespace: The Kubernetes namespace to list clusters from.
        print_to_console: Whether to print the clusters to console.

    Returns:
        List of RayCluster objects representing the READY or SUSPENDED clusters.
    """
    from ..cluster import pretty_print

    resources = _get_ray_clusters(
        namespace, filter=[RayClusterStatus.READY, RayClusterStatus.SUSPENDED]
    )
    if print_to_console:
        pretty_print.print_ray_clusters_status(resources)
    return resources


def get_cluster(
    cluster_name: str,
    namespace: str = "default",
    verify_tls: bool = True,
    write_to_file: bool = False,
) -> "RayCluster":
    """
    Retrieves an existing Ray Cluster as a RayCluster object.

    This function fetches an existing Ray Cluster from the Kubernetes cluster and returns
    it as a `RayCluster` object.

    Args:
        cluster_name: The name of the Ray Cluster.
        namespace: The Kubernetes namespace where the Ray Cluster is located.
        verify_tls: Whether to verify TLS when connecting to the cluster.
        write_to_file: If True, writes the resource configuration to a YAML file.

    Returns:
        RayCluster object representing the retrieved Ray Cluster.

    Raises:
        Exception: If the Ray Cluster cannot be found or does not exist.
    """
    config_check()
    api_instance = client.CustomObjectsApi(get_api_client())

    # Get the Ray Cluster.
    try:
        resource = api_instance.get_namespaced_custom_object(
            group="ray.io",
            version="v1",
            namespace=namespace,
            plural="rayclusters",
            name=cluster_name,
        )
    except Exception as e:
        return _kube_api_error_handling(e)

    # Import here to avoid circular imports during module load.
    from .raycluster import RayCluster

    # Extract extended resources from the retrieved cluster.
    (
        head_extended_resources,
        worker_extended_resources,
    ) = RayCluster._head_worker_extended_resources_from_rc_dict(resource)

    # Create a RayCluster with the retrieved parameters.
    cluster = RayCluster(
        name=cluster_name,
        namespace=namespace,
        verify_tls=verify_tls,
        write_to_file=write_to_file,
        head_cpu_limits=resource["spec"]["headGroupSpec"]["template"]["spec"][
            "containers"
        ][0]["resources"]["limits"]["cpu"],
        head_cpu_requests=resource["spec"]["headGroupSpec"]["template"]["spec"][
            "containers"
        ][0]["resources"]["requests"]["cpu"],
        head_memory_limits=resource["spec"]["headGroupSpec"]["template"]["spec"][
            "containers"
        ][0]["resources"]["limits"]["memory"],
        head_memory_requests=resource["spec"]["headGroupSpec"]["template"]["spec"][
            "containers"
        ][0]["resources"]["requests"]["memory"],
        num_workers=resource["spec"]["workerGroupSpecs"][0]["minReplicas"],
        worker_cpu_limits=resource["spec"]["workerGroupSpecs"][0]["template"]["spec"][
            "containers"
        ][0]["resources"]["limits"]["cpu"],
        worker_cpu_requests=resource["spec"]["workerGroupSpecs"][0]["template"]["spec"][
            "containers"
        ][0]["resources"]["requests"]["cpu"],
        worker_memory_limits=resource["spec"]["workerGroupSpecs"][0]["template"][
            "spec"
        ]["containers"][0]["resources"]["limits"]["memory"],
        worker_memory_requests=resource["spec"]["workerGroupSpecs"][0]["template"][
            "spec"
        ]["containers"][0]["resources"]["requests"]["memory"],
        head_accelerators=head_extended_resources,
        worker_accelerators=worker_extended_resources,
    )

    # Remove auto-generated fields like creationTimestamp, uid and etc.
    _remove_autogenerated_fields(resource)

    if write_to_file:
        cluster._resource_yaml = cluster._write_to_file(resource)
    else:
        # Update the Cluster's resource_yaml to reflect the retrieved Ray Cluster.
        cluster._resource_yaml = resource
        print(f"Yaml resources loaded for {cluster.name}")

    return cluster


def _get_ray_clusters(
    namespace: str = "default", filter: Optional[List[RayClusterStatus]] = None
) -> List["RayCluster"]:
    """
    Get a list of RayCluster objects from the Kubernetes cluster.

    Args:
        namespace: The Kubernetes namespace to list clusters from.
        filter: Optional list of RayClusterStatus values to filter by.

    Returns:
        List of RayCluster objects.
    """
    list_of_clusters = []
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

    # Import here to avoid circular imports during module load.
    from .raycluster import RayCluster

    # Get a list of RCs with the filter if it is passed to the function.
    if filter is not None:
        for rc in rcs["items"]:
            ray_cluster = _map_to_ray_cluster(rc)
            if ray_cluster:
                # Get status from the resource and check against filter.
                status = RayCluster._extract_status_from_rc(rc)
                if status in filter:
                    list_of_clusters.append(ray_cluster)
    else:
        for rc in rcs["items"]:
            ray_cluster = _map_to_ray_cluster(rc)
            if ray_cluster:
                list_of_clusters.append(ray_cluster)
    return list_of_clusters


def _map_to_ray_cluster(rc: dict) -> Optional["RayCluster"]:
    """
    Map a RayCluster Kubernetes resource to a RayCluster object.

    Args:
        rc: The RayCluster resource dictionary from Kubernetes API.

    Returns:
        RayCluster object, or None if mapping fails due to malformed spec.
    """
    # Import here to avoid circular imports during module load.
    from .raycluster import RayCluster

    try:
        # Extract extended resources from the RC.
        (
            head_extended_resources,
            worker_extended_resources,
        ) = RayCluster._head_worker_extended_resources_from_rc_dict(rc)

        # Create RayCluster object from the Kubernetes resource.
        return RayCluster(
            name=rc["metadata"]["name"],
            namespace=rc["metadata"]["namespace"],
            num_workers=rc["spec"]["workerGroupSpecs"][0]["replicas"],
            worker_memory_limits=rc["spec"]["workerGroupSpecs"][0]["template"]["spec"][
                "containers"
            ][0]["resources"]["limits"]["memory"],
            worker_memory_requests=rc["spec"]["workerGroupSpecs"][0]["template"][
                "spec"
            ]["containers"][0]["resources"]["requests"]["memory"],
            worker_cpu_requests=rc["spec"]["workerGroupSpecs"][0]["template"]["spec"][
                "containers"
            ][0]["resources"]["requests"]["cpu"],
            worker_cpu_limits=rc["spec"]["workerGroupSpecs"][0]["template"]["spec"][
                "containers"
            ][0]["resources"]["limits"]["cpu"],
            worker_accelerators=worker_extended_resources,
            head_cpu_requests=rc["spec"]["headGroupSpec"]["template"]["spec"][
                "containers"
            ][0]["resources"]["requests"]["cpu"],
            head_cpu_limits=rc["spec"]["headGroupSpec"]["template"]["spec"][
                "containers"
            ][0]["resources"]["limits"]["cpu"],
            head_memory_requests=rc["spec"]["headGroupSpec"]["template"]["spec"][
                "containers"
            ][0]["resources"]["requests"]["memory"],
            head_memory_limits=rc["spec"]["headGroupSpec"]["template"]["spec"][
                "containers"
            ][0]["resources"]["limits"]["memory"],
            head_accelerators=head_extended_resources,
        )
    except (KeyError, IndexError, TypeError) as e:
        cluster_name = rc.get("metadata", {}).get("name", "unknown")
        logger.warning(f"Failed to map RayCluster '{cluster_name}': {e}")
        return None


def _remove_autogenerated_fields(resource):
    """Recursively remove autogenerated fields from a dictionary."""
    if isinstance(resource, dict):
        for key in list(resource.keys()):
            if key in [
                "creationTimestamp",
                "resourceVersion",
                "uid",
                "selfLink",
                "managedFields",
                "finalizers",
                "generation",
                "status",
                "suspend",
            ]:
                del resource[key]
            else:
                _remove_autogenerated_fields(resource[key])

    elif isinstance(resource, list):
        for item in resource:
            _remove_autogenerated_fields(item)

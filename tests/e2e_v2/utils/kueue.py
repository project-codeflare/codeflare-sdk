"""
Kueue-specific utilities for E2E tests.

This module re-exports Kueue functions from the original tests/e2e/support.py
and provides additional wrapper functions with cleaner APIs.
"""

from typing import List, Optional, Dict, Any
from kubernetes import client

# =============================================================================
# Re-export from original e2e/support.py
# =============================================================================

from tests.e2e.support import (
    get_kueue_workload_for_job as _get_kueue_workload_for_job,
    wait_for_kueue_admission as _wait_for_kueue_admission,
    create_limited_kueue_resources as _create_limited_kueue_resources,
)


# =============================================================================
# Wrapper functions with cleaner APIs (no self parameter)
# =============================================================================


def create_resource_flavor(
    custom_api: client.CustomObjectsApi,
    flavor_name: str,
    node_labels: Optional[Dict[str, str]] = None,
    tolerations: Optional[List[Dict[str, Any]]] = None,
) -> None:
    """
    Create a Kueue ResourceFlavor.

    Args:
        custom_api: Kubernetes CustomObjectsApi instance.
        flavor_name: Name of the ResourceFlavor to create.
        node_labels: Optional node labels for the flavor.
        tolerations: Optional tolerations for the flavor.
    """
    resource_flavor_body = {
        "apiVersion": "kueue.x-k8s.io/v1beta1",
        "kind": "ResourceFlavor",
        "metadata": {"name": flavor_name},
        "spec": {
            "nodeLabels": node_labels or {},
        },
    }

    if tolerations:
        resource_flavor_body["spec"]["tolerations"] = tolerations

    try:
        custom_api.get_cluster_custom_object(
            group="kueue.x-k8s.io",
            plural="resourceflavors",
            version="v1beta1",
            name=flavor_name,
        )
        print(f"ResourceFlavor '{flavor_name}' already exists")
    except client.exceptions.ApiException as e:
        if e.status == 404:
            custom_api.create_cluster_custom_object(
                group="kueue.x-k8s.io",
                plural="resourceflavors",
                version="v1beta1",
                body=resource_flavor_body,
            )
            print(f"ResourceFlavor '{flavor_name}' created")
        else:
            raise


def get_resource_flavor(
    custom_api: client.CustomObjectsApi,
    flavor_name: str,
) -> Optional[Dict[str, Any]]:
    """
    Get a ResourceFlavor by name.

    Args:
        custom_api: Kubernetes CustomObjectsApi instance.
        flavor_name: Name of the ResourceFlavor.

    Returns:
        The ResourceFlavor object or None if not found.
    """
    try:
        return custom_api.get_cluster_custom_object(
            group="kueue.x-k8s.io",
            version="v1beta1",
            plural="resourceflavors",
            name=flavor_name,
        )
    except client.exceptions.ApiException as e:
        if e.status == 404:
            return None
        raise


def create_cluster_queue(
    custom_api: client.CustomObjectsApi,
    queue_name: str,
    flavor_name: str,
    cpu_quota: int = 20,
    memory_quota: str = "80Gi",
    gpu_quota: int = 2,
) -> None:
    """
    Create a Kueue ClusterQueue.

    Args:
        custom_api: Kubernetes CustomObjectsApi instance.
        queue_name: Name of the ClusterQueue to create.
        flavor_name: Name of the ResourceFlavor to use.
        cpu_quota: CPU quota for the queue.
        memory_quota: Memory quota for the queue.
        gpu_quota: GPU quota for the queue.
    """
    cluster_queue_body = {
        "apiVersion": "kueue.x-k8s.io/v1beta1",
        "kind": "ClusterQueue",
        "metadata": {"name": queue_name},
        "spec": {
            "namespaceSelector": {},
            "resourceGroups": [
                {
                    "coveredResources": ["cpu", "memory", "nvidia.com/gpu"],
                    "flavors": [
                        {
                            "name": flavor_name,
                            "resources": [
                                {"name": "cpu", "nominalQuota": cpu_quota},
                                {"name": "memory", "nominalQuota": memory_quota},
                                {"name": "nvidia.com/gpu", "nominalQuota": gpu_quota},
                            ],
                        },
                    ],
                }
            ],
        },
    }

    try:
        custom_api.get_cluster_custom_object(
            group="kueue.x-k8s.io",
            plural="clusterqueues",
            version="v1beta1",
            name=queue_name,
        )
        print(f"ClusterQueue '{queue_name}' already exists")
    except client.exceptions.ApiException as e:
        if e.status == 404:
            custom_api.create_cluster_custom_object(
                group="kueue.x-k8s.io",
                plural="clusterqueues",
                version="v1beta1",
                body=cluster_queue_body,
            )
            print(f"ClusterQueue '{queue_name}' created")
        else:
            raise


def create_limited_cluster_queue(
    custom_api: client.CustomObjectsApi,
    queue_name: str,
    flavor_name: str,
    is_openshift: bool = False,
) -> None:
    """
    Create a ClusterQueue with limited resources for preemption testing.

    This mirrors the logic from tests/e2e/support.py create_limited_kueue_resources.

    Args:
        custom_api: Kubernetes CustomObjectsApi instance.
        queue_name: Name of the ClusterQueue to create.
        flavor_name: Name of the ResourceFlavor to use.
        is_openshift: Whether running on OpenShift (affects memory quota).
    """
    # Adjust quota based on platform - matching old e2e/support.py logic
    if is_openshift:
        cpu_quota = 3
        memory_quota = "15Gi"
    else:
        cpu_quota = 3
        memory_quota = "10Gi"

    cluster_queue_body = {
        "apiVersion": "kueue.x-k8s.io/v1beta1",
        "kind": "ClusterQueue",
        "metadata": {"name": queue_name},
        "spec": {
            "namespaceSelector": {},
            "resourceGroups": [
                {
                    "coveredResources": ["cpu", "memory"],
                    "flavors": [
                        {
                            "name": flavor_name,
                            "resources": [
                                {"name": "cpu", "nominalQuota": cpu_quota},
                                {"name": "memory", "nominalQuota": memory_quota},
                            ],
                        }
                    ],
                }
            ],
        },
    }

    custom_api.create_cluster_custom_object(
        group="kueue.x-k8s.io",
        plural="clusterqueues",
        version="v1beta1",
        body=cluster_queue_body,
    )
    print(f"Limited ClusterQueue '{queue_name}' created")


def create_local_queue(
    custom_api: client.CustomObjectsApi,
    namespace: str,
    cluster_queue_name: str,
    local_queue_name: str,
    is_default: bool = True,
) -> None:
    """
    Create a Kueue LocalQueue in a namespace.

    Args:
        custom_api: Kubernetes CustomObjectsApi instance.
        namespace: Namespace to create the LocalQueue in.
        cluster_queue_name: Name of the ClusterQueue to reference.
        local_queue_name: Name of the LocalQueue to create.
        is_default: Whether this is the default queue for the namespace.
    """
    local_queue_body = {
        "apiVersion": "kueue.x-k8s.io/v1beta1",
        "kind": "LocalQueue",
        "metadata": {
            "namespace": namespace,
            "name": local_queue_name,
            "annotations": {"kueue.x-k8s.io/default-queue": str(is_default).lower()},
        },
        "spec": {"clusterQueue": cluster_queue_name},
    }

    try:
        custom_api.get_namespaced_custom_object(
            group="kueue.x-k8s.io",
            namespace=namespace,
            plural="localqueues",
            version="v1beta1",
            name=local_queue_name,
        )
        print(f"LocalQueue '{local_queue_name}' already exists in '{namespace}'")
    except client.exceptions.ApiException as e:
        if e.status == 404:
            custom_api.create_namespaced_custom_object(
                group="kueue.x-k8s.io",
                namespace=namespace,
                plural="localqueues",
                version="v1beta1",
                body=local_queue_body,
            )
            print(f"LocalQueue '{local_queue_name}' created in '{namespace}'")
        else:
            raise


def delete_kueue_resources(
    custom_api: client.CustomObjectsApi,
    cluster_queues: Optional[List[str]] = None,
    resource_flavors: Optional[List[str]] = None,
) -> None:
    """
    Delete Kueue resources (ClusterQueues and ResourceFlavors).

    This mirrors the logic from tests/e2e/support.py delete_kueue_resources.

    Args:
        custom_api: Kubernetes CustomObjectsApi instance.
        cluster_queues: List of ClusterQueue names to delete.
        resource_flavors: List of ResourceFlavor names to delete.
    """
    # Delete ClusterQueues first (order matters for cleanup)
    for cq_name in cluster_queues or []:
        try:
            custom_api.delete_cluster_custom_object(
                group="kueue.x-k8s.io",
                plural="clusterqueues",
                version="v1beta1",
                name=cq_name,
            )
            print(f"ClusterQueue '{cq_name}' deleted")
        except client.exceptions.ApiException as e:
            if e.status != 404:
                print(f"Error deleting ClusterQueue '{cq_name}': {e}")

    # Then delete ResourceFlavors
    for flavor_name in resource_flavors or []:
        try:
            custom_api.delete_cluster_custom_object(
                group="kueue.x-k8s.io",
                plural="resourceflavors",
                version="v1beta1",
                name=flavor_name,
            )
            print(f"ResourceFlavor '{flavor_name}' deleted")
        except client.exceptions.ApiException as e:
            if e.status != 404:
                print(f"Error deleting ResourceFlavor '{flavor_name}': {e}")


def get_kueue_workload_for_job(
    custom_api: client.CustomObjectsApi,
    job_name: str,
    namespace: str,
) -> Optional[Dict[str, Any]]:
    """
    Find the Kueue workload associated with a RayJob.

    This wraps the function from tests/e2e/support.py with a cleaner API.

    Args:
        custom_api: Kubernetes CustomObjectsApi instance.
        job_name: Name of the RayJob.
        namespace: Namespace of the RayJob.

    Returns:
        The workload object or None if not found.
    """

    # Create a mock self object with the custom_api attribute
    class MockSelf:
        pass

    mock_self = MockSelf()
    mock_self.custom_api = custom_api

    return _get_kueue_workload_for_job(mock_self, job_name, namespace)


def wait_for_kueue_admission(
    custom_api: client.CustomObjectsApi,
    job_api,
    job_name: str,
    namespace: str,
    timeout: int = 120,
) -> bool:
    """
    Wait for Kueue to admit a job (unsuspend it).

    This wraps the function from tests/e2e/support.py with a cleaner API.

    Args:
        custom_api: Kubernetes CustomObjectsApi instance.
        job_api: RayjobApi instance.
        job_name: Name of the RayJob.
        namespace: Namespace of the RayJob.
        timeout: Maximum time to wait in seconds.

    Returns:
        True if admitted, False if timeout.
    """

    # Create a mock self object with the custom_api attribute
    class MockSelf:
        pass

    mock_self = MockSelf()
    mock_self.custom_api = custom_api

    return _wait_for_kueue_admission(mock_self, job_api, job_name, namespace, timeout)


# =============================================================================
# Export all functions
# =============================================================================

__all__ = [
    "create_resource_flavor",
    "get_resource_flavor",
    "create_cluster_queue",
    "create_limited_cluster_queue",
    "create_local_queue",
    "delete_kueue_resources",
    "get_kueue_workload_for_job",
    "wait_for_kueue_admission",
]

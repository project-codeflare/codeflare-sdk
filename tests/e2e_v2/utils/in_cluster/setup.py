"""
High-level setup and cleanup functions for in-cluster test execution.

This module provides convenient functions that combine service account creation
and RBAC setup for easy use in test setup/teardown methods.
"""

from kubernetes import client
from .rbac import (
    create_test_service_account,
    create_rayjob_rbac,
    delete_test_service_account,
)


def setup_in_cluster_test_environment(
    api_instance: client.CoreV1Api,
    custom_api: client.CustomObjectsApi,
    namespace: str,
    name_prefix: str = "test-pod",
) -> str:
    """
    Set up a complete in-cluster test environment with service account and RBAC.

    This function:
    1. Creates a ServiceAccount
    2. Creates a Role with permissions for RayJob operations
    3. Creates a RoleBinding linking the Role to the ServiceAccount

    Args:
        api_instance: Kubernetes CoreV1Api instance.
        custom_api: CustomObjectsApi instance.
        namespace: Namespace to create resources in.
        name_prefix: Prefix for resource names.

    Returns:
        The service account name to use in pod creation.
    """
    service_account_name = create_test_service_account(
        api_instance=api_instance,
        namespace=namespace,
        name_prefix=name_prefix,
    )

    try:
        create_rayjob_rbac(
            api_instance=api_instance,
            custom_api=custom_api,
            namespace=namespace,
            service_account_name=service_account_name,
        )
    except Exception:
        try:
            api_instance.delete_namespaced_service_account(
                service_account_name, namespace
            )
        except Exception:
            pass
        raise

    return service_account_name


def cleanup_in_cluster_test_environment(
    api_instance: client.CoreV1Api,
    custom_api: client.CustomObjectsApi,
    namespace: str,
    service_account_name: str,
) -> None:
    """
    Clean up in-cluster test environment (ServiceAccount, Role, RoleBinding).

    Args:
        api_instance: Kubernetes CoreV1Api instance.
        custom_api: CustomObjectsApi instance.
        namespace: Namespace where resources exist.
        service_account_name: Name of the service account to clean up.
    """
    delete_test_service_account(
        api_instance=api_instance,
        custom_api=custom_api,
        namespace=namespace,
        service_account_name=service_account_name,
    )

"""
RBAC utilities for in-cluster test execution.

This module provides functions to create and manage service accounts with
proper RBAC permissions for running tests inside Kubernetes pods.
"""

from kubernetes import client
from kubernetes.client import (
    V1ServiceAccount,
    V1Role,
    V1RoleBinding,
    V1ObjectMeta,
    V1PolicyRule,
)
from ..helpers import random_suffix


def create_test_service_account(
    api_instance: client.CoreV1Api,
    namespace: str,
    name_prefix: str = "test-sa",
) -> str:
    """
    Create a ServiceAccount in the specified namespace.

    Args:
        api_instance: Kubernetes CoreV1Api instance.
        namespace: Namespace to create the service account in.
        name_prefix: Prefix for the service account name.

    Returns:
        The service account name.
    """
    service_account_name = f"{name_prefix}-{random_suffix()}"

    service_account = V1ServiceAccount(
        metadata=V1ObjectMeta(
            name=service_account_name,
            namespace=namespace,
            labels={
                "app.kubernetes.io/managed-by": "codeflare-sdk-tests",
                "codeflare-sdk-test/type": "in-cluster-execution",
            },
        )
    )

    api_instance.create_namespaced_service_account(namespace, service_account)
    return service_account_name


def create_rayjob_rbac(
    api_instance: client.CoreV1Api,
    custom_api: client.CustomObjectsApi,
    namespace: str,
    service_account_name: str,
) -> tuple[str, str]:
    """
    Create a Role and RoleBinding with permissions for RayJob operations.

    This creates:
    - A Role with permissions to create/manage RayJobs, RayClusters, and related resources
    - A RoleBinding linking the Role to the ServiceAccount

    Args:
        api_instance: Kubernetes CoreV1Api instance (for Role/RoleBinding).
        custom_api: CustomObjectsApi instance (for custom resources).
        namespace: Namespace to create resources in.
        service_account_name: Name of the service account to bind permissions to.

    Returns:
        Tuple of (role_name, role_binding_name).

    Raises:
        Exception: If creation fails, attempts to clean up created resources.
    """
    rbac_api = client.RbacAuthorizationV1Api()

    role_name = f"{service_account_name}-role"
    role_binding_name = f"{service_account_name}-rolebinding"

    try:
        role = V1Role(
            metadata=V1ObjectMeta(
                name=role_name,
                namespace=namespace,
                labels={
                    "app.kubernetes.io/managed-by": "codeflare-sdk-tests",
                    "codeflare-sdk-test/type": "in-cluster-execution",
                },
            ),
            rules=[
                V1PolicyRule(
                    api_groups=["ray.io"],
                    resources=["rayjobs"],
                    verbs=[
                        "create",
                        "get",
                        "list",
                        "watch",
                        "update",
                        "patch",
                        "delete",
                    ],
                ),
                V1PolicyRule(
                    api_groups=["ray.io"],
                    resources=["rayjobs/status"],
                    verbs=["get", "list", "watch"],
                ),
                V1PolicyRule(
                    api_groups=["ray.io"],
                    resources=["rayclusters"],
                    verbs=["get", "list", "watch"],
                ),
                V1PolicyRule(
                    api_groups=[""],
                    resources=["pods", "configmaps", "secrets"],
                    verbs=["get", "list", "watch"],
                ),
            ],
        )

        rbac_api.create_namespaced_role(namespace, role)

        role_binding = V1RoleBinding(
            metadata=V1ObjectMeta(
                name=role_binding_name,
                namespace=namespace,
                labels={
                    "app.kubernetes.io/managed-by": "codeflare-sdk-tests",
                    "codeflare-sdk-test/type": "in-cluster-execution",
                },
            ),
            subjects=[
                {
                    "kind": "ServiceAccount",
                    "name": service_account_name,
                    "namespace": namespace,
                }
            ],
            role_ref={
                "apiGroup": "rbac.authorization.k8s.io",
                "kind": "Role",
                "name": role_name,
            },
        )

        rbac_api.create_namespaced_role_binding(namespace, role_binding)
        return role_name, role_binding_name

    except Exception as e:
        try:
            delete_test_service_account(
                api_instance, custom_api, namespace, service_account_name
            )
        except Exception:
            pass
        raise


def delete_test_service_account(
    api_instance: client.CoreV1Api,
    custom_api: client.CustomObjectsApi,
    namespace: str,
    service_account_name: str,
) -> None:
    """
    Delete ServiceAccount, Role, and RoleBinding.

    Handles missing resources gracefully (e.g., if already deleted).

    Args:
        api_instance: Kubernetes CoreV1Api instance.
        custom_api: CustomObjectsApi instance (unused but kept for API consistency).
        namespace: Namespace where resources exist.
        service_account_name: Name of the service account to delete.
    """
    rbac_api = client.RbacAuthorizationV1Api()

    role_name = f"{service_account_name}-role"
    role_binding_name = f"{service_account_name}-rolebinding"

    try:
        rbac_api.delete_namespaced_role_binding(role_binding_name, namespace)
    except client.exceptions.ApiException as e:
        if e.status != 404:
            raise

    try:
        rbac_api.delete_namespaced_role(role_name, namespace)
    except client.exceptions.ApiException as e:
        if e.status != 404:
            raise

    try:
        api_instance.delete_namespaced_service_account(service_account_name, namespace)
    except client.exceptions.ApiException as e:
        if e.status != 404:
            raise

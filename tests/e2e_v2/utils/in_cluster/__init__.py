"""
In-cluster test execution utilities.

This package provides functions for setting up and managing test execution
inside Kubernetes pods, including RBAC setup, service account management,
and pod execution.
"""

from .rbac import (
    create_test_service_account,
    create_rayjob_rbac,
    delete_test_service_account,
)
from .setup import (
    setup_in_cluster_test_environment,
    cleanup_in_cluster_test_environment,
)
from .pod_execution import (
    PodExecutionResult,
    create_test_pod,
    create_sdk_test_pod,
    run_code_in_pod,
    wait_for_pod_completion,
    get_pod_logs,
    delete_test_pod,
    cleanup_test_pods,
)

__all__ = [
    "create_test_service_account",
    "create_rayjob_rbac",
    "delete_test_service_account",
    "setup_in_cluster_test_environment",
    "cleanup_in_cluster_test_environment",
    "PodExecutionResult",
    "create_test_pod",
    "create_sdk_test_pod",
    "run_code_in_pod",
    "wait_for_pod_completion",
    "get_pod_logs",
    "delete_test_pod",
    "cleanup_test_pods",
]

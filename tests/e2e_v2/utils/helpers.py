"""
General test helpers for E2E tests.

This module re-exports helper functions from the original tests/e2e/support.py
and provides additional utilities for the e2e_v2 test suite.
"""

import random
import string
from time import sleep
from typing import Optional, Callable
from kubernetes import client

# =============================================================================
# Re-export from original e2e/support.py
# These functions don't use `self` so they can be imported directly
# =============================================================================

from tests.e2e.support import (
    random_choice,
    wait_for_job_status,
    verify_rayjob_cluster_cleanup,
)


# =============================================================================
# Random Generators
# =============================================================================


def random_suffix(length: int = 5) -> str:
    """
    Generate a random alphanumeric suffix.

    This is an alias for random_choice() from e2e/support.py for
    backwards compatibility with code that uses this name.

    Args:
        length: Length of the suffix.

    Returns:
        Random suffix string.
    """
    alphabet = string.ascii_lowercase + string.digits
    return "".join(random.choices(alphabet, k=length))


# =============================================================================
# RayJob Utilities
# =============================================================================


def get_rayjob_api():
    """Get a RayjobApi instance."""
    from codeflare_sdk.vendored.python_client.kuberay_job_api import RayjobApi

    return RayjobApi()


def wait_for_job_finished(
    job_name: str,
    namespace: str,
    timeout: int = 600,
) -> bool:
    """
    Wait for a RayJob to finish (succeed or fail).

    Args:
        job_name: Name of the RayJob.
        namespace: Namespace of the RayJob.
        timeout: Maximum time to wait in seconds.

    Returns:
        True if job finished, False if timeout.
    """
    job_api = get_rayjob_api()
    return job_api.wait_until_job_finished(
        name=job_name,
        k8s_namespace=namespace,
        timeout=timeout,
    )


def get_job_status(job_name: str, namespace: str) -> dict:
    """
    Get the status of a RayJob.

    Args:
        job_name: Name of the RayJob.
        namespace: Namespace of the RayJob.

    Returns:
        Job status dictionary.
    """
    job_api = get_rayjob_api()
    return job_api.get_job_status(
        name=job_name,
        k8s_namespace=namespace,
    )


# =============================================================================
# Wait Functions
# =============================================================================


def wait_for_condition(
    condition_fn: Callable[[], bool],
    timeout: int = 300,
    interval: int = 5,
    message: str = "Waiting for condition",
) -> bool:
    """
    Wait for a condition to become true.

    Args:
        condition_fn: Function that returns True when condition is met.
        timeout: Maximum time to wait in seconds.
        interval: Time between checks in seconds.
        message: Message to print while waiting.

    Returns:
        True if condition met, False if timeout.
    """
    elapsed = 0
    while elapsed < timeout:
        if condition_fn():
            return True
        print(f"{message}... ({elapsed}s/{timeout}s)")
        sleep(interval)
        elapsed += interval
    return False


def wait_for_rayjob_completion(
    job_api,
    job_name: str,
    namespace: str,
    timeout: int = 600,
) -> bool:
    """
    Wait for a RayJob to complete (succeed or fail).

    Args:
        job_api: RayjobApi instance.
        job_name: Name of the RayJob.
        namespace: Namespace of the RayJob.
        timeout: Maximum time to wait in seconds.

    Returns:
        True if completed successfully, False otherwise.
    """
    elapsed = 0
    interval = 10

    while elapsed < timeout:
        try:
            status = job_api.get_job_status(name=job_name, k8s_namespace=namespace)
            if not status:
                sleep(interval)
                elapsed += interval
                continue

            # Check jobDeploymentStatus (the actual field in the status dict)
            deployment_status = status.get("jobDeploymentStatus", "")

            # "Complete" means the job succeeded
            if deployment_status == "Complete":
                return True
            elif deployment_status in ["Failed", "Suspended"]:
                message = status.get("message", "No error message")
                print(
                    f"RayJob '{job_name}' failed with status: {deployment_status}. Message: {message}"
                )
                return False
        except Exception as e:
            print(f"Error checking job status: {e}")

        sleep(interval)
        elapsed += interval

    print(f"Timeout waiting for RayJob '{job_name}' completion")
    return False


# =============================================================================
# Pod Utilities
# =============================================================================


def wait_for_pod_ready(
    api_instance: client.CoreV1Api,
    namespace: str,
    pod_name: str,
    timeout: int = 300,
) -> bool:
    """
    Wait for a pod to be ready.

    Args:
        api_instance: Kubernetes CoreV1Api instance.
        namespace: Namespace of the pod.
        pod_name: Name of the pod.
        timeout: Maximum time to wait in seconds.

    Returns:
        True if pod is ready, False if timeout.
    """
    elapsed = 0
    interval = 5

    while elapsed < timeout:
        try:
            pod = api_instance.read_namespaced_pod(pod_name, namespace)
            if pod.status.phase == "Running":
                # Check all containers are ready
                if pod.status.container_statuses:
                    all_ready = all(cs.ready for cs in pod.status.container_statuses)
                    if all_ready:
                        return True
        except client.exceptions.ApiException:
            pass

        sleep(interval)
        elapsed += interval

    return False


def wait_for_pod_completion_phase(
    api_instance: client.CoreV1Api,
    namespace: str,
    pod_name: str,
    timeout: int = 600,
) -> Optional[str]:
    """
    Wait for a pod to complete and return its phase.

    Note: This is different from pod_execution.wait_for_pod_completion
    which returns a PodExecutionResult. This just returns the phase string.

    Args:
        api_instance: Kubernetes CoreV1Api instance.
        namespace: Namespace of the pod.
        pod_name: Name of the pod.
        timeout: Maximum time to wait in seconds.

    Returns:
        Pod phase ('Succeeded' or 'Failed') or None if timeout.
    """
    elapsed = 0
    interval = 5

    while elapsed < timeout:
        try:
            pod = api_instance.read_namespaced_pod(pod_name, namespace)
            if pod.status.phase in ["Succeeded", "Failed"]:
                return pod.status.phase
        except client.exceptions.ApiException:
            pass

        sleep(interval)
        elapsed += interval

    return None


def get_pod_logs(
    api_instance: client.CoreV1Api,
    namespace: str,
    pod_name: str,
    container: Optional[str] = None,
) -> str:
    """
    Get logs from a pod.

    Args:
        api_instance: Kubernetes CoreV1Api instance.
        namespace: Namespace of the pod.
        pod_name: Name of the pod.
        container: Optional container name.

    Returns:
        Pod logs as string.
    """
    try:
        return api_instance.read_namespaced_pod_log(
            pod_name,
            namespace,
            container=container,
        )
    except client.exceptions.ApiException as e:
        return f"Error getting logs: {e}"


# =============================================================================
# Assertion Helpers
# =============================================================================


def assert_job_succeeded(status: dict, job_name: str = None) -> None:
    """
    Assert that a RayJob succeeded based on its status dict.

    Handles both jobStatus and jobDeploymentStatus fields.

    Args:
        status: Job status dictionary from get_job_status().
        job_name: Optional job name for error messages.

    Raises:
        AssertionError: If job did not succeed.
    """
    job_status = status.get("jobStatus")
    deployment_status = status.get("jobDeploymentStatus")
    name_prefix = f"Job '{job_name}'" if job_name else "Job"

    if job_status:
        assert (
            job_status == "SUCCEEDED"
        ), f"{name_prefix} did not succeed. Status: {job_status}. Full: {status}"
    elif deployment_status:
        assert (
            deployment_status == "Complete"
        ), f"{name_prefix} did not complete. Status: {deployment_status}. Full: {status}"
    else:
        raise AssertionError(f"Could not determine job status. Full: {status}")


def assert_cluster_ready(cluster) -> None:
    """
    Assert that a cluster is ready.

    Args:
        cluster: Cluster object.

    Raises:
        AssertionError: If cluster is not ready.
    """
    status = cluster.status()
    assert status is not None, "Cluster status is None"


# =============================================================================
# Export all functions
# =============================================================================

__all__ = [
    # Random generators
    "random_choice",
    "random_suffix",
    # RayJob utilities
    "get_rayjob_api",
    "wait_for_job_finished",
    "get_job_status",
    # Wait functions (re-exported from e2e/support.py)
    "wait_for_job_status",
    "verify_rayjob_cluster_cleanup",
    # Wait functions (new)
    "wait_for_condition",
    "wait_for_rayjob_completion",
    # Pod utilities
    "wait_for_pod_ready",
    "wait_for_pod_completion_phase",
    "get_pod_logs",
    # Assertion helpers
    "assert_job_succeeded",
    "assert_cluster_ready",
]

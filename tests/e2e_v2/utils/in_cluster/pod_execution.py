"""
Utilities for in-cluster pod execution.

This module provides functions for creating pods and running code inside
the cluster to test in-cluster execution scenarios (like Jupyter notebooks).
"""

from dataclasses import dataclass
from time import sleep
from typing import Optional, Dict, List
from kubernetes import client

from ..helpers import random_suffix


@dataclass
class PodExecutionResult:
    """Result of executing code in a pod."""

    pod_name: str
    namespace: str
    phase: str  # 'Succeeded' or 'Failed'
    logs: str
    exit_code: Optional[int] = None

    @property
    def succeeded(self) -> bool:
        """Check if the pod execution succeeded."""
        return self.phase == "Succeeded"


def _create_script_configmap(
    api_instance: client.CoreV1Api,
    namespace: str,
    configmap_name: str,
    code: str,
) -> None:
    """
    Create a ConfigMap containing the Python script to execute.

    Args:
        api_instance: Kubernetes CoreV1Api instance.
        namespace: Namespace to create the ConfigMap in.
        configmap_name: Name of the ConfigMap.
        code: Python code to store in the ConfigMap.
    """
    configmap = client.V1ConfigMap(
        metadata=client.V1ObjectMeta(
            name=configmap_name,
            namespace=namespace,
            labels={
                "app.kubernetes.io/managed-by": "codeflare-sdk-tests",
                "codeflare-sdk-test/type": "script-configmap",
            },
        ),
        data={"script.py": code},
    )

    api_instance.create_namespaced_config_map(namespace, configmap)


def _delete_script_configmap(
    api_instance: client.CoreV1Api,
    namespace: str,
    configmap_name: str,
) -> None:
    """Delete a script ConfigMap."""
    try:
        api_instance.delete_namespaced_config_map(configmap_name, namespace)
    except client.exceptions.ApiException as e:
        if e.status != 404:
            raise


def create_test_pod(
    api_instance: client.CoreV1Api,
    namespace: str,
    code: str,
    name_prefix: str = "test-pod",
    image: str = "python:3.12-slim",
    env_vars: Optional[Dict[str, str]] = None,
    pip_packages: Optional[List[str]] = None,
    service_account: Optional[str] = None,
    timeout: int = 600,
) -> str:
    """
    Create a pod that runs Python code in the cluster.

    This is used to test in-cluster execution scenarios where code runs
    inside a pod (like a Jupyter notebook) rather than from outside.

    The code is stored in a ConfigMap and mounted into the pod to avoid
    shell escaping issues.

    Args:
        api_instance: Kubernetes CoreV1Api instance.
        namespace: Namespace to create the pod in.
        code: Python code to execute.
        name_prefix: Prefix for the pod name.
        image: Container image to use.
        env_vars: Optional environment variables.
        pip_packages: Optional pip packages to install.
        service_account: Optional service account name.
        timeout: Timeout for the pod in seconds.

    Returns:
        The pod name.
    """
    pod_name = f"{name_prefix}-{random_suffix()}"
    configmap_name = f"{pod_name}-script"

    # Create ConfigMap with the script
    _create_script_configmap(api_instance, namespace, configmap_name, code)

    pip_install = ""
    if pip_packages:
        packages = " ".join(pip_packages)
        pip_install = f'mkdir -p /tmp/pip-packages && export PYTHONPATH=/tmp/pip-packages:$PYTHONPATH && (python3 -m pip install --quiet --target /tmp/pip-packages {packages} 2>&1 | grep -v "WARNING.*dependency conflicts" | grep -v "ERROR: pip.*dependency resolver" || python3 -m pip install --quiet --target /tmp/pip-packages {packages} 2>&1 | grep -v "WARNING.*dependency conflicts" | grep -v "ERROR: pip.*dependency resolver") || (python -m pip install --quiet --target /tmp/pip-packages {packages} 2>&1 | grep -v "WARNING.*dependency conflicts" | grep -v "ERROR: pip.*dependency resolver" || python -m pip install --quiet --target /tmp/pip-packages {packages} 2>&1 | grep -v "WARNING.*dependency conflicts" | grep -v "ERROR: pip.*dependency resolver") && '

    pythonpath_env = ""
    if pip_packages:
        pythonpath_env = "export PYTHONPATH=/tmp/pip-packages:$PYTHONPATH && "

    command = [
        "/bin/sh",
        "-c",
        f"{pip_install}{pythonpath_env}python3 /scripts/script.py 2>/dev/null || {pythonpath_env}python /scripts/script.py",
    ]

    # Build environment variables
    env = []
    for key, value in (env_vars or {}).items():
        env.append(client.V1EnvVar(name=key, value=value))

    # Create volume mount for the script
    volume_mounts = [
        client.V1VolumeMount(
            name="script-volume",
            mount_path="/scripts",
            read_only=True,
        )
    ]

    # Create volume from ConfigMap
    volumes = [
        client.V1Volume(
            name="script-volume",
            config_map=client.V1ConfigMapVolumeSource(
                name=configmap_name,
            ),
        )
    ]

    # Create the pod spec
    pod_body = client.V1Pod(
        metadata=client.V1ObjectMeta(
            name=pod_name,
            namespace=namespace,
            labels={
                "app.kubernetes.io/name": pod_name,
                "app.kubernetes.io/managed-by": "codeflare-sdk-tests",
                "codeflare-sdk-test/type": "in-cluster-execution",
            },
            annotations={
                "codeflare-sdk-test/configmap": configmap_name,
            },
        ),
        spec=client.V1PodSpec(
            containers=[
                client.V1Container(
                    name="test",
                    image=image,
                    command=command,
                    env=env if env else None,
                    volume_mounts=volume_mounts,
                    resources=client.V1ResourceRequirements(
                        requests={"cpu": "100m", "memory": "256Mi"},
                        limits={"cpu": "500m", "memory": "512Mi"},
                    ),
                )
            ],
            volumes=volumes,
            restart_policy="Never",
            service_account_name=service_account,
            active_deadline_seconds=timeout,
        ),
    )

    api_instance.create_namespaced_pod(namespace, pod_body)
    return pod_name


def create_sdk_test_pod(
    api_instance: client.CoreV1Api,
    namespace: str,
    code: str,
    name_prefix: str = "sdk-test",
    ray_image: Optional[str] = None,
    env_vars: Optional[Dict[str, str]] = None,
    service_account: Optional[str] = None,
    timeout: int = 600,
) -> str:
    """
    Create a pod that runs CodeFlare SDK code in the cluster.

    This pod has the SDK and Ray installed, suitable for testing
    ray.init() and other SDK functionality from inside the cluster.

    Args:
        api_instance: Kubernetes CoreV1Api instance.
        namespace: Namespace to create the pod in.
        code: Python code to execute (should import codeflare_sdk/ray).
        name_prefix: Prefix for the pod name.
        ray_image: Ray image to use (defaults to standard Ray image).
        env_vars: Optional environment variables.
        service_account: Optional service account name.
        timeout: Timeout for the pod in seconds.

    Returns:
        The pod name.
    """
    from codeflare_sdk.common.utils import constants

    if ray_image is None:
        ray_image = f"rayproject/ray:{constants.RAY_VERSION}"

    pip_packages = ["codeflare-sdk"]

    return create_test_pod(
        api_instance=api_instance,
        namespace=namespace,
        code=code,
        name_prefix=name_prefix,
        image=ray_image,
        env_vars=env_vars,
        pip_packages=pip_packages,
        service_account=service_account,
        timeout=timeout,
    )


def run_code_in_pod(
    api_instance: client.CoreV1Api,
    namespace: str,
    code: str,
    image: str = "python:3.12-slim",
    env_vars: Optional[Dict[str, str]] = None,
    pip_packages: Optional[List[str]] = None,
    service_account: Optional[str] = None,
    timeout: int = 600,
    cleanup: bool = True,
    auto_setup_rbac: bool = False,
    custom_api: Optional[client.CustomObjectsApi] = None,
) -> PodExecutionResult:
    """
    Run Python code in a pod and wait for completion.

    This is the main function for in-cluster execution testing.
    It creates a pod, runs the code, waits for completion, and returns results.

    Args:
        api_instance: Kubernetes CoreV1Api instance.
        namespace: Namespace to create the pod in.
        code: Python code to execute.
        image: Container image to use.
        env_vars: Optional environment variables.
        pip_packages: Optional pip packages to install.
        service_account: Optional service account name. If not provided and
            auto_setup_rbac=True, a service account with RBAC will be created.
        timeout: Timeout for the pod in seconds.
        cleanup: Whether to delete the pod after completion.
        auto_setup_rbac: If True and no service_account provided, automatically
            create a service account with RBAC permissions for RayJob operations.
        custom_api: CustomObjectsApi instance (required if auto_setup_rbac=True).

    Returns:
        PodExecutionResult with logs and status.
    """
    from .setup import (
        setup_in_cluster_test_environment,
        cleanup_in_cluster_test_environment,
    )

    auto_created_sa = None
    if auto_setup_rbac and not service_account:
        if custom_api is None:
            raise ValueError("custom_api is required when auto_setup_rbac=True")
        auto_created_sa = setup_in_cluster_test_environment(
            api_instance=api_instance,
            custom_api=custom_api,
            namespace=namespace,
            name_prefix="test-pod",
        )
        service_account = auto_created_sa

    try:
        pod_name = create_test_pod(
            api_instance=api_instance,
            namespace=namespace,
            code=code,
            image=image,
            env_vars=env_vars,
            pip_packages=pip_packages,
            service_account=service_account,
            timeout=timeout,
        )

        result = wait_for_pod_completion(api_instance, namespace, pod_name, timeout)

        if cleanup:
            try:
                delete_test_pod(api_instance, namespace, pod_name)
            except Exception:
                pass

        return result
    finally:
        if auto_created_sa and cleanup and custom_api is not None:
            try:
                cleanup_in_cluster_test_environment(
                    api_instance=api_instance,
                    custom_api=custom_api,
                    namespace=namespace,
                    service_account_name=auto_created_sa,
                )
            except Exception:
                pass


def wait_for_pod_completion(
    api_instance: client.CoreV1Api,
    namespace: str,
    pod_name: str,
    timeout: int = 600,
) -> PodExecutionResult:
    """
    Wait for a test pod to complete and return results.

    Args:
        api_instance: Kubernetes CoreV1Api instance.
        namespace: Namespace of the pod.
        pod_name: Name of the pod.
        timeout: Maximum time to wait in seconds.

    Returns:
        PodExecutionResult with logs and status.
    """
    elapsed = 0
    interval = 5

    while elapsed < timeout:
        try:
            pod = api_instance.read_namespaced_pod(pod_name, namespace)
            phase = pod.status.phase

            if phase in ["Succeeded", "Failed"]:
                logs = get_pod_logs(api_instance, namespace, pod_name)
                exit_code = None
                if pod.status.container_statuses:
                    cs = pod.status.container_statuses[0]
                    if cs.state.terminated:
                        exit_code = cs.state.terminated.exit_code

                return PodExecutionResult(
                    pod_name=pod_name,
                    namespace=namespace,
                    phase=phase,
                    logs=logs,
                    exit_code=exit_code,
                )
        except client.exceptions.ApiException:
            pass

        sleep(interval)
        elapsed += interval

    logs = get_pod_logs(api_instance, namespace, pod_name)
    return PodExecutionResult(
        pod_name=pod_name,
        namespace=namespace,
        phase="Timeout",
        logs=logs,
        exit_code=None,
    )


def get_pod_logs(
    api_instance: client.CoreV1Api,
    namespace: str,
    pod_name: str,
    container: Optional[str] = None,
) -> str:
    """
    Get logs from a test pod.

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


def delete_test_pod(
    api_instance: client.CoreV1Api,
    namespace: str,
    pod_name: str,
) -> None:
    """
    Delete a test pod and its associated ConfigMap.

    Args:
        api_instance: Kubernetes CoreV1Api instance.
        namespace: Namespace of the pod.
        pod_name: Name of the pod.
    """
    configmap_name = None
    try:
        pod = api_instance.read_namespaced_pod(pod_name, namespace)
        annotations = pod.metadata.annotations or {}
        configmap_name = annotations.get("codeflare-sdk-test/configmap")
    except client.exceptions.ApiException:
        pass

    try:
        api_instance.delete_namespaced_pod(
            pod_name,
            namespace,
            body=client.V1DeleteOptions(
                grace_period_seconds=0,
                propagation_policy="Background",
            ),
        )
    except client.exceptions.ApiException as e:
        if e.status != 404:
            raise

    if configmap_name:
        _delete_script_configmap(api_instance, namespace, configmap_name)


def cleanup_test_pods(
    api_instance: client.CoreV1Api,
    namespace: str,
) -> None:
    """
    Clean up all test pods and their ConfigMaps in a namespace.

    Args:
        api_instance: Kubernetes CoreV1Api instance.
        namespace: Namespace to clean up.
    """
    try:
        pods = api_instance.list_namespaced_pod(
            namespace,
            label_selector="codeflare-sdk-test/type=in-cluster-execution",
        )

        for pod in pods.items:
            delete_test_pod(api_instance, namespace, pod.metadata.name)

        configmaps = api_instance.list_namespaced_config_map(
            namespace,
            label_selector="codeflare-sdk-test/type=script-configmap",
        )

        for cm in configmaps.items:
            _delete_script_configmap(api_instance, namespace, cm.metadata.name)

    except client.exceptions.ApiException:
        pass

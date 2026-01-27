"""
Pytest configuration and fixtures for E2E v2 tests.

This module provides comprehensive fixtures for:
- Platform detection (OpenShift vs Kind)
- GPU availability detection
- Namespace and Kueue resource setup
- Authentication and credentials
- Ray image selection
- Resource configurations
"""

import os
import pytest
from kubernetes import client, config

from tests.e2e_v2.utils.helpers import random_suffix as _random_suffix


# =============================================================================
# Platform Detection Fixtures
# =============================================================================


@pytest.fixture(scope="session")
def k8s_client():
    """
    Initialize and return the Kubernetes API client.
    Loads kubeconfig from the environment.
    """
    config.load_kube_config()
    return client.CoreV1Api()


@pytest.fixture(scope="session")
def custom_api(k8s_client):
    """Return the CustomObjectsApi for CRD operations."""
    return client.CustomObjectsApi(k8s_client.api_client)


@pytest.fixture(scope="session")
def is_openshift_platform(k8s_client):
    """
    Detect if running on OpenShift by checking for OpenShift-specific API resources.

    Returns:
        bool: True if running on OpenShift, False otherwise.
    """
    try:
        # Use the existing api_client from k8s_client to ensure kubeconfig is loaded
        discovery = client.ApisApi(k8s_client.api_client)
        groups = discovery.get_api_versions().groups
        for group in groups:
            if group.name == "image.openshift.io":
                return True
        return False
    except Exception:
        return False


@pytest.fixture(scope="session")
def is_gpu_available(k8s_client):
    """
    Detect if NVIDIA GPUs are available in the cluster.

    Returns:
        bool: True if GPUs are available, False otherwise.
    """
    try:
        nodes = k8s_client.list_node()
        for node in nodes.items:
            allocatable = node.status.allocatable or {}
            if "nvidia.com/gpu" in allocatable:
                gpu_count = allocatable.get("nvidia.com/gpu", "0")
                if int(gpu_count) > 0:
                    return True
        return False
    except Exception:
        return False


# =============================================================================
# Credential Fixtures
# =============================================================================


@pytest.fixture(scope="session")
def test_user_credentials():
    """
    Get TEST_USER credentials for most tests (ldap-admin1).
    These are injected via environment variables.

    Returns:
        dict: Dictionary with 'username' and 'password' keys.
    """
    return {
        "username": os.environ.get("TEST_USER_USERNAME", ""),
        "password": os.environ.get("TEST_USER_PASSWORD", ""),
    }


@pytest.fixture(scope="session")
def admin_user_credentials():
    """
    Get OCP_ADMIN_USER credentials for admin operations.
    These are injected via environment variables.

    Returns:
        dict: Dictionary with 'username' and 'password' keys.
    """
    return {
        "username": os.environ.get("OCP_ADMIN_USER_USERNAME", ""),
        "password": os.environ.get("OCP_ADMIN_USER_PASSWORD", ""),
    }


@pytest.fixture(scope="function")
def auth_token(is_openshift_platform):
    """
    Get OAuth token for OpenShift authentication.
    Only applicable on OpenShift clusters.

    Returns:
        str or None: The auth token if on OpenShift, None otherwise.
    """
    if not is_openshift_platform:
        return None

    import subprocess

    try:
        result = subprocess.run(
            ["oc", "whoami", "--show-token=true"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return None


# =============================================================================
# Ray Image Fixtures
# =============================================================================


@pytest.fixture(scope="session")
def ray_image(is_openshift_platform):
    """
    Get appropriate Ray image based on platform.

    - OpenShift: Uses the CUDA runtime image (quay.io/modh/ray:...)
    - Kind/K8s: Uses the standard Ray image (rayproject/ray:VERSION)

    Can be overridden via RAY_IMAGE environment variable.

    Returns:
        str: The Ray image to use.
    """
    from codeflare_sdk.common.utils import constants
    from codeflare_sdk.common.utils.utils import get_ray_image_for_python_version

    # Allow explicit override
    if "RAY_IMAGE" in os.environ:
        return os.environ["RAY_IMAGE"]

    if is_openshift_platform:
        return get_ray_image_for_python_version()
    else:
        return f"rayproject/ray:{constants.RAY_VERSION}"


# =============================================================================
# Resource Configuration Fixtures
# =============================================================================


@pytest.fixture(scope="session")
def platform_resources(is_openshift_platform):
    """
    Get appropriate resource configurations based on platform.
    OpenShift with MODH images requires more memory than Kind with standard Ray images.

    Returns:
        dict: Resource configurations with head and worker CPU/memory settings.
    """
    if is_openshift_platform:
        return {
            "head_cpu_requests": "1",
            "head_cpu_limits": "1.5",
            "head_memory_requests": 7,
            "head_memory_limits": 8,
            "worker_cpu_requests": "1",
            "worker_cpu_limits": "1",
            "worker_memory_requests": 5,
            "worker_memory_limits": 6,
        }
    else:
        return {
            "head_cpu_requests": "1",
            "head_cpu_limits": "1.5",
            "head_memory_requests": 7,
            "head_memory_limits": 8,
            "worker_cpu_requests": "1",
            "worker_cpu_limits": "1",
            "worker_memory_requests": 2,
            "worker_memory_limits": 3,
        }


# =============================================================================
# Namespace Fixtures
# =============================================================================


@pytest.fixture(scope="function")
def test_namespace(k8s_client):
    """
    Create a unique test namespace and clean it up after the test.

    Yields:
        str: The namespace name.
    """
    namespace_name = f"test-ns-{_random_suffix()}"

    namespace_body = client.V1Namespace(
        metadata=client.V1ObjectMeta(name=namespace_name)
    )
    k8s_client.create_namespace(namespace_body)

    yield namespace_name

    # Cleanup
    try:
        k8s_client.delete_namespace(namespace_name)
    except Exception:
        pass


@pytest.fixture(scope="function")
def test_namespace_with_kueue(k8s_client, custom_api, test_namespace):
    """
    Create a test namespace with Kueue resources (ResourceFlavor, ClusterQueue, LocalQueue).

    Yields:
        dict: Dictionary with namespace, resource_flavors, cluster_queues, local_queues.
    """
    from tests.e2e_v2.utils.kueue import (
        create_resource_flavor,
        create_cluster_queue,
        create_local_queue,
        delete_kueue_resources,
    )

    resource_flavor_name = f"test-flavor-{_random_suffix()}"
    cluster_queue_name = f"test-cq-{_random_suffix()}"
    local_queue_name = f"test-lq-{_random_suffix()}"

    # Create Kueue resources
    create_resource_flavor(custom_api, resource_flavor_name)
    create_cluster_queue(custom_api, cluster_queue_name, resource_flavor_name)
    create_local_queue(custom_api, test_namespace, cluster_queue_name, local_queue_name)

    result = {
        "namespace": test_namespace,
        "resource_flavors": [resource_flavor_name],
        "cluster_queues": [cluster_queue_name],
        "local_queues": [local_queue_name],
    }

    yield result

    # Cleanup Kueue resources
    delete_kueue_resources(
        custom_api,
        cluster_queues=[cluster_queue_name],
        resource_flavors=[resource_flavor_name],
    )


# =============================================================================
# Environment Variables Fixture
# =============================================================================


@pytest.fixture(scope="function")
def setup_env_variables():
    """
    Get environment variables for test setup (PIP_INDEX_URL, AWS credentials, etc.).

    Returns:
        dict: Environment variables for test setup.
    """
    env_vars = {}

    # PIP configuration
    if os.environ.get("PIP_INDEX_URL"):
        env_vars["PIP_INDEX_URL"] = os.environ.get("PIP_INDEX_URL")
        env_vars["PIP_TRUSTED_HOST"] = os.environ.get("PIP_TRUSTED_HOST", "")
    else:
        env_vars["PIP_INDEX_URL"] = "https://pypi.org/simple/"
        env_vars["PIP_TRUSTED_HOST"] = "pypi.org"

    # AWS/S3 configuration
    if os.environ.get("AWS_DEFAULT_ENDPOINT"):
        env_vars["AWS_DEFAULT_ENDPOINT"] = os.environ.get("AWS_DEFAULT_ENDPOINT")
        env_vars["AWS_ACCESS_KEY_ID"] = os.environ.get("AWS_ACCESS_KEY_ID", "")
        env_vars["AWS_SECRET_ACCESS_KEY"] = os.environ.get("AWS_SECRET_ACCESS_KEY", "")
        env_vars["AWS_STORAGE_BUCKET"] = os.environ.get("AWS_STORAGE_BUCKET", "")
        env_vars["AWS_STORAGE_BUCKET_MNIST_DIR"] = os.environ.get(
            "AWS_STORAGE_BUCKET_MNIST_DIR", ""
        )

    return env_vars


# =============================================================================
# In-Cluster Test Execution Fixtures
# =============================================================================


@pytest.fixture(scope="function")
def in_cluster_service_account(k8s_client, custom_api, test_namespace):
    """
    Create a service account with RBAC permissions for in-cluster test execution.

    This fixture automatically sets up a service account with permissions to
    create/manage RayJobs, RayClusters, and related resources. Useful for tests
    that need to run code inside pods that interact with the Kubernetes API.

    Yields:
        str: The service account name to use in pod creation.

    Example:
        def test_something(in_cluster_service_account):
            result = run_code_in_pod(
                api_instance=k8s_client,
                namespace=test_namespace,
                code="...",
                service_account=in_cluster_service_account,
            )
    """
    from tests.e2e_v2.utils.in_cluster import (
        setup_in_cluster_test_environment,
        cleanup_in_cluster_test_environment,
    )

    service_account_name = setup_in_cluster_test_environment(
        api_instance=k8s_client,
        custom_api=custom_api,
        namespace=test_namespace,
        name_prefix="test-pod",
    )

    yield service_account_name

    # Cleanup
    cleanup_in_cluster_test_environment(
        api_instance=k8s_client,
        custom_api=custom_api,
        namespace=test_namespace,
        service_account_name=service_account_name,
    )


# =============================================================================
# Test Control Fixtures
# =============================================================================


@pytest.fixture
def require_gpu_flag(request, num_gpus):
    """
    Skip GPU tests unless explicitly run with -m "gpu".

    If the current parameter requires GPUs (num_gpus > 0),
    skip the test unless the user explicitly ran with -m "gpu".
    This allows CPU tests to run by default.
    """
    if num_gpus > 0:
        m_flag = str(request.config.getoption("-m"))
        if "gpu" not in m_flag:
            pytest.skip(
                "Skipping GPU config (default is CPU). Run with -m 'gpu' to enable."
            )


# =============================================================================
# Skip Markers
# =============================================================================


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "kind: mark test to run only on Kind clusters")
    config.addinivalue_line(
        "markers", "openshift: mark test to run only on OpenShift clusters"
    )
    config.addinivalue_line("markers", "gpu: mark test to require GPU resources")
    config.addinivalue_line(
        "markers", "tier1: mark test as tier1 (standard test suite)"
    )
    config.addinivalue_line(
        "markers", "smoke: mark test as smoke test (quick validation)"
    )
    config.addinivalue_line("markers", "pre_upgrade: mark test to run before upgrade")
    config.addinivalue_line("markers", "post_upgrade: mark test to run after upgrade")

"""Shared pytest fixtures for rayjobs tests."""

import pytest
from unittest.mock import MagicMock


# Global test setup that runs automatically for ALL tests
@pytest.fixture(autouse=True)
def auto_mock_setup(mocker):
    """Automatically mock common dependencies for all tests."""
    mocker.patch("kubernetes.config.load_kube_config")

    # Always mock get_default_kueue_name to prevent K8s API calls
    mocker.patch(
        "codeflare_sdk.ray.rayjobs.rayjob.get_default_kueue_name",
        return_value="default-queue",
    )

    mock_get_ns = mocker.patch(
        "codeflare_sdk.ray.rayjobs.rayjob.get_current_namespace",
        return_value="test-namespace",
    )

    mock_rayjob_api = mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")
    mock_rayjob_instance = MagicMock()
    mock_rayjob_api.return_value = mock_rayjob_instance

    mock_cluster_api = mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayClusterApi")
    mock_cluster_instance = MagicMock()
    mock_cluster_api.return_value = mock_cluster_instance

    mock_k8s_api = mocker.patch("kubernetes.client.CoreV1Api")
    mock_k8s_instance = MagicMock()
    mock_k8s_api.return_value = mock_k8s_instance

    # Mock get_api_client in runtime_env module where it's actually used
    mocker.patch("codeflare_sdk.ray.rayjobs.runtime_env.get_api_client")

    # Return the mocked instances so tests can configure them as needed
    return {
        "rayjob_api": mock_rayjob_instance,
        "cluster_api": mock_cluster_instance,
        "k8s_api": mock_k8s_instance,
        "get_current_namespace": mock_get_ns,
    }

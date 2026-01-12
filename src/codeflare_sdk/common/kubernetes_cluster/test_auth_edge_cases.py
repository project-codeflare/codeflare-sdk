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
Tests for edge cases and error paths in auth.py to improve coverage.
"""

import pytest
from kubernetes import client
from codeflare_sdk.common.kubernetes_cluster.auth import (
    TokenAuthentication,
    KubeConfigFileAuthentication,
    _client_with_cert,
    _gen_ca_cert_path,
)
import os
from pathlib import Path


def test_kubeconfig_auth_fallback_to_legacy(mocker):
    """Test that KubeConfigFileAuthentication falls back to legacy when kube-authkit fails."""
    # Mock kube-authkit to be available but fail
    mocker.patch(
        "codeflare_sdk.common.kubernetes_cluster.auth.KUBE_AUTHKIT_AVAILABLE", True
    )

    # Make get_k8s_client raise an exception
    mocker.patch(
        "codeflare_sdk.common.kubernetes_cluster.auth.get_k8s_client",
        side_effect=Exception("kube-authkit failed")
    )

    # Mock the legacy config.load_kube_config
    mock_load_config = mocker.patch("kubernetes.config.load_kube_config")

    # Create and use KubeConfigFileAuthentication
    with pytest.warns(DeprecationWarning):
        auth = KubeConfigFileAuthentication(kube_config_path="/fake/path")

    # This should fall back to legacy method
    with mocker.patch("warnings.warn"):  # Suppress the runtime warning
        result = auth.load_kube_config()

    # Verify legacy method was called
    assert mock_load_config.called
    assert "Loaded user config file" in result


def test_gen_ca_cert_path_with_env_var(monkeypatch):
    """Test _gen_ca_cert_path with CF_SDK_CA_CERT_PATH environment variable."""
    monkeypatch.setenv("CF_SDK_CA_CERT_PATH", "/custom/ca/cert.crt")

    result = _gen_ca_cert_path(None)
    assert result == "/custom/ca/cert.crt"


def test_gen_ca_cert_path_with_explicit_path():
    """Test _gen_ca_cert_path with explicit path parameter."""
    result = _gen_ca_cert_path("/explicit/path.crt")
    assert result == "/explicit/path.crt"


def test_gen_ca_cert_path_defaults_to_none(monkeypatch):
    """Test _gen_ca_cert_path returns None when no cert path is configured."""
    # Remove environment variable if it exists
    monkeypatch.delenv("CF_SDK_CA_CERT_PATH", raising=False)

    result = _gen_ca_cert_path(None)
    # Will be None unless WORKBENCH_CA_CERT_PATH exists
    assert result is None or result == "/etc/pki/tls/custom-certs/ca-bundle.crt"


def test_client_with_cert_none(mocker, monkeypatch):
    """Test _client_with_cert when cert_path is None."""
    # Clear env var to ensure we're testing the None case
    monkeypatch.delenv("CF_SDK_CA_CERT_PATH", raising=False)

    mock_client = mocker.MagicMock()
    mock_client.configuration = mocker.MagicMock()

    _client_with_cert(mock_client, None)

    assert mock_client.configuration.verify_ssl is True
    assert mock_client.configuration.ssl_ca_cert is None


def test_client_with_cert_file_not_found(mocker):
    """Test _client_with_cert raises FileNotFoundError for missing cert."""
    mock_client = mocker.MagicMock()
    mock_client.configuration = mocker.MagicMock()

    with pytest.raises(FileNotFoundError, match="Certificate file not found"):
        _client_with_cert(mock_client, "/nonexistent/cert.crt")


def test_token_auth_exception_handling(mocker):
    """Test TokenAuthentication.login() handles ApiException."""
    from kubernetes.client import ApiException

    # Create real instances but mock the method that raises exception
    mock_auth_instance = mocker.MagicMock()
    mock_auth_instance.get_api_group.side_effect = ApiException(
        status=401, reason="Unauthorized"
    )

    # Patch only AuthenticationApi's __init__ to return our mock
    mocker.patch(
        "kubernetes.client.AuthenticationApi",
        return_value=mock_auth_instance
    )

    # Mock error handling
    mock_error_handler = mocker.patch(
        "codeflare_sdk.common.kubernetes_cluster.auth._kube_api_error_handling"
    )

    with pytest.warns(DeprecationWarning):
        auth = TokenAuthentication(token="test", server="https://test:6443")

    # login() should call error handler when ApiException occurs
    auth.login()

    # Verify error handler was called
    assert mock_error_handler.called

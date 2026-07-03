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
    # Make get_k8s_client raise an exception to trigger fallback
    mocker.patch(
        "codeflare_sdk.common.kubernetes_cluster.auth.get_k8s_client",
        side_effect=Exception("kube-authkit failed"),
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
    """Test _client_with_cert when cert_path is None preserves existing ssl_ca_cert."""
    # Clear env var to ensure we're testing the None case
    monkeypatch.delenv("CF_SDK_CA_CERT_PATH", raising=False)

    mock_client = mocker.MagicMock()
    mock_client.configuration = mocker.MagicMock()
    # Set an existing ssl_ca_cert to verify it's preserved
    mock_client.configuration.ssl_ca_cert = "/existing/ca.crt"

    _client_with_cert(mock_client, None)

    assert mock_client.configuration.verify_ssl is True
    # ssl_ca_cert should be preserved (not overwritten to None)
    assert mock_client.configuration.ssl_ca_cert == "/existing/ca.crt"


def test_client_with_cert_file_not_found(mocker):
    """Test _client_with_cert raises FileNotFoundError for missing cert."""
    mock_client = mocker.MagicMock()
    mock_client.configuration = mocker.MagicMock()

    with pytest.raises(FileNotFoundError, match="Certificate file not found"):
        _client_with_cert(mock_client, "/nonexistent/cert.crt")


def test_client_with_cert_valid_file(mocker, tmp_path):
    """Test _client_with_cert sets ssl_ca_cert when valid cert file exists."""
    # Create a temporary cert file
    cert_file = tmp_path / "ca.crt"
    cert_file.write_text("-----BEGIN CERTIFICATE-----\ntest\n-----END CERTIFICATE-----")

    mock_client = mocker.MagicMock()
    mock_client.configuration = mocker.MagicMock()
    mock_client.configuration.ssl_ca_cert = None

    _client_with_cert(mock_client, str(cert_file))

    assert mock_client.configuration.verify_ssl is True
    assert mock_client.configuration.ssl_ca_cert == str(cert_file)


def test_token_auth_exception_handling(mocker):
    """Test TokenAuthentication.login() handles ApiException and re-raises."""
    from kubernetes.client import ApiException

    mock_auth_instance = mocker.MagicMock()
    mock_auth_instance.get_api_group.side_effect = ApiException(
        status=401, reason="Unauthorized"
    )

    mocker.patch("kubernetes.client.AuthenticationApi", return_value=mock_auth_instance)

    mock_error_handler = mocker.patch(
        "codeflare_sdk.common.kubernetes_cluster.auth._kube_api_error_handling"
    )

    with pytest.warns(DeprecationWarning):
        auth = TokenAuthentication(token="test", server="https://test:6443")

    with pytest.raises(ApiException):
        auth.login()

    assert mock_error_handler.called


def test_token_auth_login_uses_bearer_token_key(mocker):
    """Test that login() sets both 'authorization' and 'BearerToken' api_key entries.

    kubernetes client <=35 resolves the prefix via the header name ("authorization"),
    while >=36 uses the security-scheme name ("BearerToken").  Setting both keys
    ensures the Bearer prefix is always applied, regardless of client version.
    """
    captured_configs = []

    original_init = client.ApiClient.__init__

    def capture_config(self, configuration=None, *args, **kwargs):
        if configuration is not None:
            captured_configs.append(configuration)
        return original_init(self, configuration, *args, **kwargs)

    mocker.patch.object(client.ApiClient, "__init__", capture_config)
    mocker.patch.object(client.ApiClient, "call_api", return_value=None)
    mocker.patch("kubernetes.client.AuthenticationApi")

    with pytest.warns(DeprecationWarning):
        auth = TokenAuthentication(
            token="sha256~testtoken",
            server="https://api.test:6443",
            skip_tls=True,
        )

    auth.login()

    assert len(captured_configs) == 1
    config = captured_configs[0]

    for key in ("authorization", "BearerToken"):
        assert key in config.api_key, f"api_key missing '{key}'"
        assert config.api_key[key] == "sha256~testtoken"
        assert key in config.api_key_prefix, f"api_key_prefix missing '{key}'"
        assert config.api_key_prefix[key] == "Bearer"

    auth_settings = config.auth_settings()
    bearer = auth_settings.get("BearerToken", {})
    assert bearer["value"] == "Bearer sha256~testtoken"


def test_token_auth_login_resets_api_client_on_failure(mocker):
    """Test that login() resets the global api_client on auth failure."""
    from kubernetes.client import ApiException
    import codeflare_sdk.common.kubernetes_cluster.auth as auth_module

    mock_auth_instance = mocker.MagicMock()
    mock_auth_instance.get_api_group.side_effect = ApiException(
        status=403, reason="Forbidden"
    )

    mocker.patch("kubernetes.client.AuthenticationApi", return_value=mock_auth_instance)
    mocker.patch(
        "codeflare_sdk.common.kubernetes_cluster.auth._kube_api_error_handling"
    )

    with pytest.warns(DeprecationWarning):
        auth = TokenAuthentication(token="bad-token", server="https://test:6443")

    with pytest.raises(ApiException):
        auth.login()

    assert auth_module.api_client is None

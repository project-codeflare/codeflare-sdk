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

from codeflare_sdk.common.kubernetes_cluster import (
    Authentication,
    KubeConfigFileAuthentication,
    TokenAuthentication,
    config_check,
)
from kubernetes import client, config
import os
from pathlib import Path
import pytest

parent = Path(__file__).resolve().parents[4]  # project directory


def test_token_auth_creation():
    with pytest.warns(DeprecationWarning):
        token_auth = TokenAuthentication(token="token", server="server")
    assert token_auth.token == "token"
    assert token_auth.server == "server"
    assert token_auth.skip_tls == False
    assert token_auth.ca_cert_path == None

    with pytest.warns(DeprecationWarning):
        token_auth = TokenAuthentication(token="token", server="server", skip_tls=True)
    assert token_auth.token == "token"
    assert token_auth.server == "server"
    assert token_auth.skip_tls == True
    assert token_auth.ca_cert_path == None

    os.environ["CF_SDK_CA_CERT_PATH"] = "/etc/pki/tls/custom-certs/ca-bundle.crt"
    with pytest.warns(DeprecationWarning):
        token_auth = TokenAuthentication(token="token", server="server", skip_tls=False)
    assert token_auth.token == "token"
    assert token_auth.server == "server"
    assert token_auth.skip_tls == False
    assert token_auth.ca_cert_path == "/etc/pki/tls/custom-certs/ca-bundle.crt"
    os.environ.pop("CF_SDK_CA_CERT_PATH")

    with pytest.warns(DeprecationWarning):
        token_auth = TokenAuthentication(
            token="token",
            server="server",
            skip_tls=False,
            ca_cert_path=f"{parent}/tests/auth-test.crt",
        )
    assert token_auth.token == "token"
    assert token_auth.server == "server"
    assert token_auth.skip_tls == False
    assert token_auth.ca_cert_path == f"{parent}/tests/auth-test.crt"


def test_token_auth_login_logout(mocker):
    mocker.patch.object(client, "ApiClient")

    with pytest.warns(DeprecationWarning):
        token_auth = TokenAuthentication(
            token="testtoken",
            server="testserver:6443",
            skip_tls=False,
            ca_cert_path=None,
        )
    assert token_auth.login() == ("Logged into testserver:6443")
    assert token_auth.logout() == ("Successfully logged out of testserver:6443")


def test_token_auth_login_tls(mocker):
    mocker.patch.object(client, "ApiClient")

    with pytest.warns(DeprecationWarning):
        token_auth = TokenAuthentication(
            token="testtoken",
            server="testserver:6443",
            skip_tls=True,
            ca_cert_path=None,
        )
    assert token_auth.login() == ("Logged into testserver:6443")

    with pytest.warns(DeprecationWarning):
        token_auth = TokenAuthentication(
            token="testtoken",
            server="testserver:6443",
            skip_tls=False,
            ca_cert_path=None,
        )
    assert token_auth.login() == ("Logged into testserver:6443")

    with pytest.warns(DeprecationWarning):
        token_auth = TokenAuthentication(
            token="testtoken",
            server="testserver:6443",
            skip_tls=False,
            ca_cert_path=f"{parent}/tests/auth-test.crt",
        )
    assert token_auth.login() == ("Logged into testserver:6443")

    os.environ["CF_SDK_CA_CERT_PATH"] = f"{parent}/tests/auth-test.crt"
    with pytest.warns(DeprecationWarning):
        token_auth = TokenAuthentication(
            token="testtoken",
            server="testserver:6443",
            skip_tls=False,
        )
    assert token_auth.login() == ("Logged into testserver:6443")


def test_config_check_no_config_file(mocker):
    mocker.patch("os.path.expanduser", return_value="/mock/home/directory")
    mocker.patch("os.path.isfile", return_value=False)
    mocker.patch("codeflare_sdk.common.kubernetes_cluster.auth.config_path", None)
    mocker.patch("codeflare_sdk.common.kubernetes_cluster.auth.api_client", None)

    with pytest.raises(PermissionError):
        config_check()


def test_config_check_with_incluster_config(mocker):
    mocker.patch("os.path.expanduser", return_value="/mock/home/directory")
    mocker.patch("os.path.isfile", return_value=False)
    mocker.patch.dict(os.environ, {"KUBERNETES_PORT": "number"})
    mocker.patch("kubernetes.config.load_incluster_config", side_effect=None)
    mocker.patch("codeflare_sdk.common.kubernetes_cluster.auth.config_path", None)
    mocker.patch("codeflare_sdk.common.kubernetes_cluster.auth.api_client", None)

    result = config_check()
    assert result == None


def test_config_check_with_existing_config_file(mocker):
    mocker.patch("os.path.expanduser", return_value="/mock/home/directory")
    mocker.patch("os.path.isfile", return_value=True)
    mocker.patch("kubernetes.config.load_kube_config", side_effect=None)
    mocker.patch("codeflare_sdk.common.kubernetes_cluster.auth.config_path", None)
    mocker.patch("codeflare_sdk.common.kubernetes_cluster.auth.api_client", None)

    result = config_check()
    assert result == None


def test_config_check_with_config_path_and_no_api_client(mocker):
    mocker.patch(
        "codeflare_sdk.common.kubernetes_cluster.auth.config_path", "/mock/config/path"
    )
    mocker.patch("codeflare_sdk.common.kubernetes_cluster.auth.api_client", None)
    result = config_check()
    assert result == "/mock/config/path"


def test_load_kube_config(mocker):
    mocker.patch.object(config, "load_kube_config")

    with pytest.warns(DeprecationWarning):
        kube_config_auth = KubeConfigFileAuthentication(
            kube_config_path="/path/to/your/config"
        )
    response = kube_config_auth.load_kube_config()

    assert (
        response
        == "Loaded user config file at path %s" % kube_config_auth.kube_config_path
    )

    with pytest.warns(DeprecationWarning):
        kube_config_auth = KubeConfigFileAuthentication(kube_config_path=None)
    response = kube_config_auth.load_kube_config()
    assert response == "Please specify a config file path"


def test_auth_coverage():
    abstract = Authentication()
    abstract.login()
    abstract.logout()


def test_deprecation_warnings():
    """Test that deprecation warnings are shown for legacy classes."""
    with pytest.warns(DeprecationWarning, match="TokenAuthentication is deprecated"):
        TokenAuthentication(token="test", server="https://test:6443")

    with pytest.warns(
        DeprecationWarning, match="KubeConfigFileAuthentication is deprecated"
    ):
        KubeConfigFileAuthentication(kube_config_path="/path/to/config")


def test_token_auth_uses_legacy_implementation(mocker):
    """Test TokenAuthentication uses legacy implementation (kube-authkit doesn't support direct token auth)."""
    mocker.patch.object(client, "ApiClient")

    # Suppress deprecation warnings in this test
    with pytest.warns(DeprecationWarning):
        auth = TokenAuthentication(token="test", server="https://test:6443")

    result = auth.login()

    # TokenAuthentication always uses legacy implementation
    assert result == "Logged into https://test:6443"


def test_kubeconfig_auth_with_kube_authkit(mocker):
    """Test KubeConfigFileAuthentication uses kube-authkit when available."""
    # Mock kube-authkit to be available
    mocker.patch(
        "codeflare_sdk.common.kubernetes_cluster.auth.KUBE_AUTHKIT_AVAILABLE", True
    )
    mock_get_k8s_client = mocker.patch(
        "codeflare_sdk.common.kubernetes_cluster.auth.get_k8s_client"
    )
    mock_client = mocker.MagicMock()
    mock_get_k8s_client.return_value = mock_client

    # Suppress deprecation warnings
    with pytest.warns(DeprecationWarning):
        auth = KubeConfigFileAuthentication(kube_config_path="/path/to/config")

    result = auth.load_kube_config()

    # Verify kube-authkit was called
    assert mock_get_k8s_client.called
    assert result == "Loaded user config file at path /path/to/config"


def test_config_check_with_kube_authkit(mocker):
    """Test config_check uses kube-authkit auto-detection."""
    # Mock kube-authkit to be available
    mocker.patch(
        "codeflare_sdk.common.kubernetes_cluster.auth.KUBE_AUTHKIT_AVAILABLE", True
    )
    mock_auth_config = mocker.patch(
        "codeflare_sdk.common.kubernetes_cluster.auth.AuthConfig"
    )
    mock_get_k8s_client = mocker.patch(
        "codeflare_sdk.common.kubernetes_cluster.auth.get_k8s_client"
    )
    mock_client = mocker.MagicMock()
    mock_get_k8s_client.return_value = mock_client

    # Mock AuthenticationApi to prevent actual API calls
    mocker.patch.object(client, "AuthenticationApi")

    # Reset global state
    mocker.patch("codeflare_sdk.common.kubernetes_cluster.auth.api_client", None)
    mocker.patch("codeflare_sdk.common.kubernetes_cluster.auth.config_path", None)

    config_check()

    # Should call AuthConfig with method="auto"
    mock_auth_config.assert_called_once_with(method="auto")
    # Should call get_k8s_client
    assert mock_get_k8s_client.called

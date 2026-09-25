# Copyright 2024-2026 IBM, Red Hat
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
    config_check,
    set_api_client,
)
from kubernetes import client, config
import os
import pytest


@pytest.fixture(autouse=True)
def reset_auth_globals(mocker):
    """Reset global auth state before and after each test to ensure test isolation."""
    import codeflare_sdk.common.kubernetes_cluster.auth as auth_module

    original_api_client = auth_module.api_client
    original_config_path = auth_module.config_path

    auth_module.api_client = None
    auth_module.config_path = None

    mocker.patch.object(client.ApiClient, "call_api", return_value=None)

    yield

    auth_module.api_client = original_api_client
    auth_module.config_path = original_config_path


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
    assert result is None


def test_config_check_with_existing_config_file(mocker):
    mocker.patch("os.path.expanduser", return_value="/mock/home/directory")
    mocker.patch("os.path.isfile", return_value=True)
    mocker.patch("kubernetes.config.load_kube_config", side_effect=None)
    mocker.patch("codeflare_sdk.common.kubernetes_cluster.auth.config_path", None)
    mocker.patch("codeflare_sdk.common.kubernetes_cluster.auth.api_client", None)

    result = config_check()
    assert result is None


def test_config_check_with_config_path_and_no_api_client(mocker):
    mocker.patch(
        "codeflare_sdk.common.kubernetes_cluster.auth.config_path", "/mock/config/path"
    )
    mocker.patch("codeflare_sdk.common.kubernetes_cluster.auth.api_client", None)
    result = config_check()
    assert result == "/mock/config/path"


def test_config_check_with_kube_authkit(mocker):
    """Test config_check uses kube-authkit auto-detection."""
    mock_auth_config = mocker.patch(
        "codeflare_sdk.common.kubernetes_cluster.auth.AuthConfig"
    )
    mock_get_k8s_client = mocker.patch(
        "codeflare_sdk.common.kubernetes_cluster.auth.get_k8s_client"
    )
    mock_client = mocker.MagicMock()
    mock_get_k8s_client.return_value = mock_client

    mocker.patch.object(client, "AuthenticationApi")
    mocker.patch("codeflare_sdk.common.kubernetes_cluster.auth.api_client", None)
    mocker.patch("codeflare_sdk.common.kubernetes_cluster.auth.config_path", None)

    config_check()

    mock_auth_config.assert_called_once_with(method="auto")
    assert mock_get_k8s_client.called


def test_set_api_client():
    """Test set_api_client registers a custom API client."""
    import codeflare_sdk.common.kubernetes_cluster.auth as auth_module

    mock_client = client.ApiClient()
    set_api_client(mock_client)

    assert auth_module.api_client is mock_client
    assert auth_module.config_path == "custom"

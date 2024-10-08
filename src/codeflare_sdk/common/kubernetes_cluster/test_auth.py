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
    token_auth = TokenAuthentication(token="token", server="server")
    assert token_auth.token == "token"
    assert token_auth.server == "server"
    assert token_auth.skip_tls == False
    assert token_auth.ca_cert_path == None

    token_auth = TokenAuthentication(token="token", server="server", skip_tls=True)
    assert token_auth.token == "token"
    assert token_auth.server == "server"
    assert token_auth.skip_tls == True
    assert token_auth.ca_cert_path == None

    os.environ["CF_SDK_CA_CERT_PATH"] = "/etc/pki/tls/custom-certs/ca-bundle.crt"
    token_auth = TokenAuthentication(token="token", server="server", skip_tls=False)
    assert token_auth.token == "token"
    assert token_auth.server == "server"
    assert token_auth.skip_tls == False
    assert token_auth.ca_cert_path == "/etc/pki/tls/custom-certs/ca-bundle.crt"
    os.environ.pop("CF_SDK_CA_CERT_PATH")

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

    token_auth = TokenAuthentication(
        token="testtoken", server="testserver:6443", skip_tls=False, ca_cert_path=None
    )
    assert token_auth.login() == ("Logged into testserver:6443")
    assert token_auth.logout() == ("Successfully logged out of testserver:6443")


def test_token_auth_login_tls(mocker):
    mocker.patch.object(client, "ApiClient")

    token_auth = TokenAuthentication(
        token="testtoken", server="testserver:6443", skip_tls=True, ca_cert_path=None
    )
    assert token_auth.login() == ("Logged into testserver:6443")
    token_auth = TokenAuthentication(
        token="testtoken", server="testserver:6443", skip_tls=False, ca_cert_path=None
    )
    assert token_auth.login() == ("Logged into testserver:6443")
    token_auth = TokenAuthentication(
        token="testtoken",
        server="testserver:6443",
        skip_tls=False,
        ca_cert_path=f"{parent}/tests/auth-test.crt",
    )
    assert token_auth.login() == ("Logged into testserver:6443")

    os.environ["CF_SDK_CA_CERT_PATH"] = f"{parent}/tests/auth-test.crt"
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
    kube_config_auth = KubeConfigFileAuthentication(
        kube_config_path="/path/to/your/config"
    )
    response = kube_config_auth.load_kube_config()

    assert (
        response
        == "Loaded user config file at path %s" % kube_config_auth.kube_config_path
    )

    kube_config_auth = KubeConfigFileAuthentication(kube_config_path=None)
    response = kube_config_auth.load_kube_config()
    assert response == "Please specify a config file path"


def test_auth_coverage():
    abstract = Authentication()
    abstract.login()
    abstract.logout()

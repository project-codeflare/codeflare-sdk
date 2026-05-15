# Copyright 2022 IBM, Red Hat
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
The auth sub-module contains Kubernetes authentication utilities.

Authentication is handled exclusively via kube-authkit's AuthConfig.
Use the Codeflare class as the primary entrypoint.
"""

import os
from typing import Optional

from kube_authkit import AuthConfig, get_k8s_client
from kubernetes import client, config

from .kube_api_helpers import _kube_api_error_handling

global api_client
api_client = None
global config_path
config_path = None

WORKBENCH_CA_CERT_PATH = "/etc/pki/tls/custom-certs/ca-bundle.crt"


def config_check() -> str:
    """
    Check and load the Kubernetes config from the default location.

    Uses kube-authkit's auto-detection when available, falls back to legacy method.

    This function checks if a Kubernetes config file exists at the default path
    (`~/.kube/config`). If none is provided, it tries to load in-cluster config.
    If the `config_path` global variable is set by an external module (e.g., `auth.py`),
    this path will be used directly.

    Priority:
    1. Existing global api_client (already authenticated)
    2. kube-authkit auto-detection (kubeconfig, in-cluster, etc.)
    3. Legacy method (kubeconfig or in-cluster)

    Returns:
        str:
            The loaded config path if successful.

    Raises:
        PermissionError:
            If no valid credentials or config file is found.
    """
    global config_path
    global api_client

    # If already configured, return early
    if api_client is not None:
        return config_path

    # Try kube-authkit auto-detection
    if config_path is None:
        try:
            # Auto-detect authentication method (kubeconfig or in-cluster)
            auth_config = AuthConfig(method="auto")
            api_client = get_k8s_client(config=auth_config)
            # Verify connection
            client.AuthenticationApi(api_client).get_api_group()
            return config_path
        except Exception as e:
            # Fall through to legacy method
            api_client = None
            # Don't warn - auto-detection failure is expected when no auth is configured
            pass

    # Legacy implementation
    home_directory = os.path.expanduser("~")
    if config_path is None and api_client is None:
        if os.path.isfile("%s/.kube/config" % home_directory):
            try:
                config.load_kube_config()
            except Exception as e:  # pragma: no cover
                _kube_api_error_handling(e)
        elif "KUBERNETES_PORT" in os.environ:
            try:
                config.load_incluster_config()
            except Exception as e:  # pragma: no cover
                _kube_api_error_handling(e)
        else:
            raise PermissionError(
                "Action not permitted, have you put in correct/up-to-date auth credentials?"
            )

    if config_path is not None and api_client is None:
        return config_path


def _client_with_cert(api_client: client.ApiClient, ca_cert_path: Optional[str] = None):
    """
    Configure SSL certificate verification for a Kubernetes API client.

    If a custom CA cert path is provided or configured via environment variable,
    it will be used. Otherwise, the existing ssl_ca_cert configuration from the
    kubeconfig (which may include embedded certificates) is preserved.

    Args:
        api_client: The Kubernetes API client to configure.
        ca_cert_path: Optional path to a custom CA certificate file.
    """
    api_client.configuration.verify_ssl = True
    cert_path = _gen_ca_cert_path(ca_cert_path)
    if cert_path is not None:
        if os.path.isfile(cert_path):
            api_client.configuration.ssl_ca_cert = cert_path
        else:
            raise FileNotFoundError(f"Certificate file not found at {cert_path}")
    # If cert_path is None, preserve the existing ssl_ca_cert from kubeconfig
    # (which may contain embedded certificate data from certificate-authority-data)


def _gen_ca_cert_path(ca_cert_path: Optional[str]):
    """Gets the path to the default CA certificate file either through env config or default path"""
    if ca_cert_path is not None:
        return ca_cert_path
    elif "CF_SDK_CA_CERT_PATH" in os.environ:
        return os.environ.get("CF_SDK_CA_CERT_PATH")
    elif os.path.exists(WORKBENCH_CA_CERT_PATH):
        return WORKBENCH_CA_CERT_PATH
    else:
        return None


def get_api_client() -> client.ApiClient:
    """
    Retrieve the Kubernetes API client with the default configuration.

    This function returns the current API client instance if already loaded,
    or creates a new API client with the default configuration.

    Returns:
        client.ApiClient:
            The Kubernetes API client object.
    """
    if api_client is not None:
        return api_client
    to_return = client.ApiClient()
    _client_with_cert(to_return)
    return to_return


def set_api_client(new_client: client.ApiClient):
    """
    Set a custom Kubernetes API client for the SDK to use.

    This is useful when you want to use kube-authkit or other authentication
    methods to create an API client and register it with the CodeFlare SDK.

    Example:
        >>> from kube_authkit import get_k8s_client, AuthConfig
        >>> from codeflare_sdk.common.kubernetes_cluster.auth import set_api_client
        >>>
        >>> auth_config = AuthConfig(k8s_api_host="...", token="...")
        >>> api_client = get_k8s_client(config=auth_config)
        >>> set_api_client(api_client)

    Args:
        new_client: The Kubernetes API client instance to use.
    """
    global api_client, config_path
    api_client = new_client
    config_path = "custom"  # Mark as configured with custom client
    # verify the client works by making a simple API call
    client.AuthenticationApi(api_client).get_api_group()
    # print message confirming successful configuration
    print("Custom API client has been set and verified successfully.")

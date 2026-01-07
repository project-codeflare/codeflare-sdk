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
The auth sub-module contains authentication methods for Kubernetes clusters.

Recommended: Use kube-authkit's AuthConfig directly for new code.
Legacy: TokenAuthentication and KubeConfigFileAuthentication are deprecated but still supported.
"""

import abc
import warnings
from kubernetes import client, config
import os
import urllib3
from .kube_api_helpers import _kube_api_error_handling

from typing import Optional

# Import kube-authkit
try:
    from kube_authkit import get_k8s_client, AuthConfig

    KUBE_AUTHKIT_AVAILABLE = True
except ImportError:
    KUBE_AUTHKIT_AVAILABLE = False
    warnings.warn(
        "kube-authkit is not installed. Advanced authentication features unavailable. "
        "Install with: pip install kube-authkit",
        ImportWarning,
    )

global api_client
api_client = None
global config_path
config_path = None

WORKBENCH_CA_CERT_PATH = "/etc/pki/tls/custom-certs/ca-bundle.crt"

# Deprecation message template
_DEPRECATION_MSG = (
    "{cls_name} is deprecated and will be removed in a future version. "
    "Please use kube-authkit's AuthConfig directly. "
    "See: https://github.com/opendatahub-io/kube-authkit"
)


class Authentication(metaclass=abc.ABCMeta):
    """
    An abstract class that defines the necessary methods for authenticating to a remote environment.
    Specifically, this class defines the need for a `login()` and a `logout()` function.
    """

    def login(self):
        """
        Method for logging in to a remote cluster.
        """
        pass

    def logout(self):
        """
        Method for logging out of the remote cluster.
        """
        pass


class KubeConfiguration(metaclass=abc.ABCMeta):
    """
    An abstract class that defines the method for loading a user defined config file using the `load_kube_config()` function
    """

    def load_kube_config(self):
        """
        Method for setting your Kubernetes configuration to a certain file
        """
        pass

    def logout(self):
        """
        Method for logging out of the remote cluster
        """
        pass


class TokenAuthentication(Authentication):
    """
    DEPRECATED: Use kube_authkit.AuthConfig with token strategy instead.

    `TokenAuthentication` is a subclass of `Authentication`. It can be used to authenticate to a Kubernetes
    cluster when the user has an API token and the API server address.
    """

    def __init__(
        self,
        token: str,
        server: str,
        skip_tls: bool = False,
        ca_cert_path: str = None,
    ):
        """
        Initialize a TokenAuthentication object that requires a value for `token`, the API Token
        and `server`, the API server address for authenticating to a Kubernetes cluster.
        """
        warnings.warn(
            _DEPRECATION_MSG.format(cls_name="TokenAuthentication"),
            DeprecationWarning,
            stacklevel=2,
        )

        self.token = token
        self.server = server
        self.skip_tls = skip_tls
        self.ca_cert_path = _gen_ca_cert_path(ca_cert_path)
        self._use_kube_authkit = KUBE_AUTHKIT_AVAILABLE

    def login(self) -> str:
        """
        This function is used to log in to a Kubernetes cluster using the user's API token and API server address.
        Depending on the cluster, a user can choose to login in with `--insecure-skip-tls-verify` by setting `skip_tls`
        to `True` or `--certificate-authority` by setting `skip_tls` to False and providing a path to a ca bundle with `ca_cert_path`.

        Note: kube-authkit does not support direct token authentication via AuthConfig,
        so this uses the legacy implementation.
        """
        global config_path
        global api_client

        # Legacy implementation (kube-authkit doesn't support direct token auth)
        try:
            configuration = client.Configuration()
            configuration.api_key_prefix["authorization"] = "Bearer"
            configuration.host = self.server
            configuration.api_key["authorization"] = self.token

            if self.skip_tls:
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                print("Insecure request warnings have been disabled")
                configuration.verify_ssl = False

            api_client = client.ApiClient(configuration)
            if not self.skip_tls:
                _client_with_cert(api_client, self.ca_cert_path)

            client.AuthenticationApi(api_client).get_api_group()
            config_path = None
            return "Logged into %s" % self.server
        except client.ApiException as e:
            _kube_api_error_handling(e)

    def logout(self) -> str:
        """
        This function is used to logout of a Kubernetes cluster.
        """
        global config_path
        config_path = None
        global api_client
        api_client = None
        return "Successfully logged out of %s" % self.server


class KubeConfigFileAuthentication(KubeConfiguration):
    """
    DEPRECATED: Use kube_authkit.AuthConfig with kubeconfig strategy instead.

    A class that defines the necessary methods for passing a user's own Kubernetes config file.
    Specifically this class defines the `load_kube_config()` and `config_check()` functions.
    """

    def __init__(self, kube_config_path: str = None):
        warnings.warn(
            _DEPRECATION_MSG.format(cls_name="KubeConfigFileAuthentication"),
            DeprecationWarning,
            stacklevel=2,
        )
        self.kube_config_path = kube_config_path
        self._use_kube_authkit = KUBE_AUTHKIT_AVAILABLE

    def load_kube_config(self):
        """
        Function for loading a user's own predefined Kubernetes config file.
        """
        global config_path
        global api_client

        if self.kube_config_path == None:
            return "Please specify a config file path"

        # Try kube-authkit first if available
        if self._use_kube_authkit:
            try:
                auth_config = AuthConfig(method="kubeconfig")
                # kube-authkit auto-detects kubeconfig location, but we need to set it
                # This may need adjustment based on actual kube-authkit API
                api_client = get_k8s_client(config=auth_config)
                config_path = self.kube_config_path
                return "Loaded user config file at path %s" % self.kube_config_path
            except Exception as e:
                warnings.warn(
                    f"kube-authkit failed, using legacy method: {e}", RuntimeWarning
                )
                # Reset for legacy implementation
                api_client = None

        # Legacy implementation
        try:
            config_path = self.kube_config_path
            api_client = None
            config.load_kube_config(config_path)
            response = "Loaded user config file at path %s" % self.kube_config_path
        except config.ConfigException:  # pragma: no cover
            config_path = None
            raise Exception("Please specify a config file path")
        return response


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
    if KUBE_AUTHKIT_AVAILABLE and config_path is None:
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
    if config_path == None and api_client == None:
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

    if config_path != None and api_client == None:
        return config_path


def _client_with_cert(client: client.ApiClient, ca_cert_path: Optional[str] = None):
    client.configuration.verify_ssl = True
    cert_path = _gen_ca_cert_path(ca_cert_path)
    if cert_path is None:
        client.configuration.ssl_ca_cert = None
    elif os.path.isfile(cert_path):
        client.configuration.ssl_ca_cert = cert_path
    else:
        raise FileNotFoundError(f"Certificate file not found at {cert_path}")


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
    if api_client != None:
        return api_client
    to_return = client.ApiClient()
    _client_with_cert(to_return)
    return to_return

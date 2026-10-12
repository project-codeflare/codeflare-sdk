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

import contextlib
import contextvars
import functools
import os
from typing import Optional

from kube_authkit import AuthConfig, get_k8s_client
from kubernetes import client, config

from .kube_api_helpers import _kube_api_error_handling

global api_client
api_client = None
global config_path
config_path = None

# Client bound to the current operation, used in preference to the module-level
# global. This is what keeps objects created through one Codeflare instance from
# being hijacked by a later instance (RHOAIENG-98754). It is a ContextVar rather
# than a plain attribute so that the many helpers which resolve the client
# themselves — build_ray_cluster, the Kueue helpers, cert generation — pick it up
# without each needing to thread a client parameter through.
_active_api_client: contextvars.ContextVar = contextvars.ContextVar(
    "codeflare_active_api_client", default=None
)


@contextlib.contextmanager
def _use_api_client(new_client):
    """Bind ``new_client`` for the duration of the block.

    Passing ``None`` is a no-op, which is what preserves legacy behaviour for
    objects constructed without an explicit client.
    """
    if new_client is None:
        yield
        return
    token = _active_api_client.set(new_client)
    try:
        yield
    finally:
        _active_api_client.reset(token)


def _bound_to_api_client(method):
    """Run a method with ``self._api_client`` bound as the active client."""

    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        with _use_api_client(getattr(self, "_api_client", None)):
            return method(self, *args, **kwargs)

    return wrapper


WORKBENCH_CA_CERT_PATH = "/etc/pki/tls/custom-certs/ca-bundle.crt"


def config_check() -> Optional[str]:
    """
    Check and load the Kubernetes config from the default location.

    Uses kube-authkit's auto-detection when available, falls back to legacy method.

    This function checks if a Kubernetes config file exists at the default path
    (`~/.kube/config`). If none is provided, it tries to load in-cluster config.
    If the `config_path` global variable is set by an external module (e.g., `auth.py`),
    this path will be used directly.

    Priority:
    1. Client bound to the current operation via ``_use_api_client`` (already
       authenticated; auto-detection is skipped so a scoped call cannot
       overwrite the module-level client as a side effect)
    2. Existing global api_client (already authenticated)
    3. kube-authkit auto-detection (kubeconfig, in-cluster, etc.)
    4. Legacy method (kubeconfig or in-cluster)

    Returns:
        str:
            The loaded config path if successful.

    Raises:
        PermissionError:
            If no valid credentials or config file is found.
    """
    global config_path
    global api_client

    # An operation scoped to an explicit client is already configured. Return
    # before the auto-detection below, which would otherwise overwrite the
    # module-level client as a side effect of a scoped call.
    if _active_api_client.get() is not None:
        return config_path

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
        except Exception:
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

    Resolution order:
    1. The client bound to the current operation via ``_use_api_client``.
    2. The module-level client set by ``set_api_client`` (legacy fallback).
    3. A freshly constructed default client.

    Returns:
        client.ApiClient:
            The Kubernetes API client object.
    """
    scoped = _active_api_client.get()
    if scoped is not None:
        return scoped
    if api_client is not None:
        return api_client
    to_return = client.ApiClient()
    _client_with_cert(to_return)
    return to_return


def set_api_client(new_client: client.ApiClient) -> None:
    """
    Set a custom Kubernetes API client for the SDK to use.

    This is an internal function called by Codeflare.__init__().
    Users should use the Codeflare class instead of calling this directly.

    Unlike the previous implementation, this no longer probes the cluster
    with AuthenticationApi.get_api_group() — validation is handled upstream
    by kube-authkit. Misconfigured clients will fail on the first real API
    call rather than at init time.

    Args:
        new_client: The Kubernetes API client instance to use.
    """
    global api_client, config_path
    api_client = new_client
    config_path = "custom"


def _bind_api_client(new_client: client.ApiClient, path: Optional[str]) -> None:
    """Set the module-level client and ``config_path`` together.

    ``set_api_client`` always writes ``config_path = "custom"``, which is wrong
    for the deprecated auth adapters: ``config_check()`` returns ``config_path``
    and ``common/utils/k8s_utils.py`` hands that straight to
    ``list_kube_config_contexts()`` as a kubeconfig path. Token login must
    leave it ``None`` so namespace detection still falls back to the default
    kubeconfig, while ``KubeConfigFileAuthentication`` must set the real path.
    """
    global api_client, config_path
    api_client = new_client
    config_path = path


def _clear_api_client() -> None:
    """Discard the module-level client, so the next call re-resolves one.

    Used by the deprecated ``logout()`` adapters in ``deprecated_auth``.
    """
    global api_client, config_path
    api_client = None
    config_path = None

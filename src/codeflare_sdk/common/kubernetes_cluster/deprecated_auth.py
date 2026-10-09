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

"""Deprecated authentication classes, restored and still working.

RHOAIENG-98947. These shipped through v0.39.x, were deleted by #1091, and are
back by team decision: v0.39.x documentation promised they would survive, and
in the token case actively advised users to stay on ``TokenAuthentication``.

**No removal version is named, deliberately.** The old docs said v1.0.0; that
date is not being renewed, and removal may come sooner. The warnings say "a
future release" and nothing more precise.

Every class here is an adapter. The authentication itself is kube-authkit's —
nothing in this module re-implements a strategy, which is what the original
v0.39.x ``TokenAuthentication.login()`` did. Prefer:

    cf = Codeflare(config=SDKConfig(auth=AuthConfig(...)))

which scopes the client to the clusters and jobs it creates. These classes set
a process-wide global instead, so the last caller wins.
"""

import abc
from typing import Optional

import urllib3
from kubernetes import client
from kube_authkit import AuthConfig, get_k8s_client
from typing_extensions import deprecated

from .auth import (
    _bind_api_client,
    _clear_api_client,
    _gen_ca_cert_path,
)
from .kube_api_helpers import _kube_api_error_handling

# One warning per class, not two. v0.39.x stacked @deprecated on top of a
# warnings.warn() inside __init__, so constructing a TokenAuthentication
# emitted the same notice twice. @deprecated alone covers both the runtime
# DeprecationWarning and static analysis, so the message lives here and is
# handed to the decorator.
_DEPRECATION_MSG = (
    "{cls_name} is deprecated and will be removed in a future release. "
    "Use kube_authkit.AuthConfig with Codeflare, e.g. "
    "Codeflare(config=SDKConfig(auth=AuthConfig(...))). "
    "See: https://github.com/opendatahub-io/kube-authkit"
)


def _apply_bearer_token_compat(api_client: client.ApiClient, token: str) -> None:
    """Set both spellings of the bearer key on an existing client.

    Preserves the fix from 2eedf55: the kubernetes client looks the token up by
    header name ("authorization") in <=35 and by scheme name ("BearerToken") in
    >=36, and ``kubernetes = ">= 27.2.0"`` in pyproject.toml admits both.
    kube-authkit's OpenShift strategy writes only ``api_key["authorization"]``,
    so delegating to it without this would reintroduce the bug on newer
    clients.

    This is not a second auth implementation — the client, its host and its TLS
    settings all come from kube-authkit. Only the key spelling is normalised.
    """
    configuration = api_client.configuration
    for key in ("authorization", "BearerToken"):
        configuration.api_key[key] = token
        configuration.api_key_prefix[key] = "Bearer"


class Authentication(metaclass=abc.ABCMeta):
    """
    An abstract class that defines the necessary methods for authenticating to a remote environment.
    Specifically, this class defines the need for a `login()` and a `logout()` function.

    .. deprecated::
        Use :class:`~codeflare_sdk.Codeflare` with ``kube_authkit.AuthConfig``.
    """

    def login(self) -> None:
        """
        Method for logging in to a remote cluster.
        """
        pass

    def logout(self) -> None:
        """
        Method for logging out of the remote cluster.
        """
        pass


class KubeConfiguration(metaclass=abc.ABCMeta):
    """
    An abstract class that defines the method for loading a user defined config file using the `load_kube_config()` function

    .. deprecated::
        Use :class:`~codeflare_sdk.Codeflare` with ``kube_authkit.AuthConfig``.
    """

    def load_kube_config(self) -> None:
        """
        Method for setting your Kubernetes configuration to a certain file
        """
        pass

    def logout(self) -> None:
        """
        Method for logging out of the remote cluster
        """
        pass


@deprecated(_DEPRECATION_MSG.format(cls_name="TokenAuthentication"))
class TokenAuthentication(Authentication):
    """
    DEPRECATED: Use kube_authkit.AuthConfig with Codeflare instead.

    `TokenAuthentication` is a subclass of `Authentication`. It can be used to authenticate to a Kubernetes
    cluster when the user has an API token and the API server address.
    """

    def __init__(
        self,
        token: str,
        server: str,
        skip_tls: bool = False,
        ca_cert_path: Optional[str] = None,
    ) -> None:
        """
        Initialize a TokenAuthentication object that requires a value for `token`, the API Token
        and `server`, the API server address for authenticating to a Kubernetes cluster.
        """
        self.token = token
        self.server = server
        self.skip_tls = skip_tls
        self.ca_cert_path = _gen_ca_cert_path(ca_cert_path)

    def login(self) -> str:
        """
        This function is used to log in to a Kubernetes cluster using the user's API token and API server address.
        Depending on the cluster, a user can choose to login in with `--insecure-skip-tls-verify` by setting `skip_tls`
        to `True` or `--certificate-authority` by setting `skip_tls` to False and providing a path to a ca bundle with `ca_cert_path`.
        """
        if self.skip_tls:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            print("Insecure request warnings have been disabled")

        try:
            api_client = get_k8s_client(
                config=AuthConfig(
                    method="openshift",
                    k8s_api_host=self.server,
                    token=self.token,
                    verify_ssl=not self.skip_tls,
                    ca_cert=None if self.skip_tls else self.ca_cert_path,
                )
            )
            _apply_bearer_token_compat(api_client, self.token)
            client.AuthenticationApi(api_client).get_api_group()
        except client.ApiException as e:
            _clear_api_client()
            _kube_api_error_handling(e)
            raise

        # config_path stays None, not "custom": config_check() returns it and
        # k8s_utils passes that to list_kube_config_contexts() as a path.
        _bind_api_client(api_client, None)
        return "Logged into %s" % self.server

    def logout(self) -> str:
        """
        This function is used to logout of a Kubernetes cluster.
        """
        _clear_api_client()
        return "Successfully logged out of %s" % self.server


@deprecated(_DEPRECATION_MSG.format(cls_name="KubeConfigFileAuthentication"))
class KubeConfigFileAuthentication(KubeConfiguration):
    """
    DEPRECATED: Use kube_authkit.AuthConfig with Codeflare instead.

    A class that defines the necessary methods for passing a user's own Kubernetes config file.
    Specifically this class defines the `load_kube_config()` and `config_check()` functions.
    """

    def __init__(self, kube_config_path: Optional[str] = None):
        self.kube_config_path = kube_config_path

    def load_kube_config(self) -> str:
        """
        Function for loading a user's own predefined Kubernetes config file.
        """
        if self.kube_config_path is None:
            return "Please specify a config file path"

        # v0.39.x built AuthConfig(method="kubeconfig") with no path, so
        # kube-authkit auto-detected and kube_config_path was ignored whenever
        # that call succeeded. AuthConfig takes kubeconfig_path now, so honour
        # the argument the caller actually passed.
        api_client = get_k8s_client(
            config=AuthConfig(
                method="kubeconfig", kubeconfig_path=self.kube_config_path
            )
        )
        _bind_api_client(api_client, self.kube_config_path)
        return "Loaded user config file at path %s" % self.kube_config_path

    def logout(self) -> str:
        """
        This function is used to logout of a Kubernetes cluster.
        """
        _clear_api_client()
        return "Successfully logged out of %s" % self.kube_config_path

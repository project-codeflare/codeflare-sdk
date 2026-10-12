from .auth import (
    config_check,
    get_api_client,
    set_api_client,
)

from kube_authkit import AuthConfig, get_k8s_client

# Deprecated, kept working. No removal version is promised — see
# deprecated_auth for why the old v1.0.0 date is not being renewed.
from .deprecated_auth import (
    Authentication,
    KubeConfiguration,
    TokenAuthentication,
    KubeConfigFileAuthentication,
)

__all__ = [
    "config_check",
    "get_api_client",
    "set_api_client",
    "AuthConfig",
    "get_k8s_client",
    "Authentication",
    "KubeConfiguration",
    "TokenAuthentication",
    "KubeConfigFileAuthentication",
]

from .kube_api_helpers import _kube_api_error_handling

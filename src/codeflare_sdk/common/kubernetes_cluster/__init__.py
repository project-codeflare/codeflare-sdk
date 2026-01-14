from .auth import (
    Authentication,
    KubeConfiguration,
    TokenAuthentication,
    KubeConfigFileAuthentication,
    config_check,
    get_api_client,
    set_api_client,
)

# Re-export kube-authkit for convenience
try:
    from kube_authkit import AuthConfig, get_k8s_client

    __all__ = [
        # Legacy
        "Authentication",
        "KubeConfiguration",
        "TokenAuthentication",
        "KubeConfigFileAuthentication",
        "config_check",
        "get_api_client",
        "set_api_client",
        # New - kube-authkit
        "AuthConfig",
        "get_k8s_client",
    ]
except ImportError:
    __all__ = [
        # Legacy only
        "Authentication",
        "KubeConfiguration",
        "TokenAuthentication",
        "KubeConfigFileAuthentication",
        "config_check",
        "get_api_client",
        "set_api_client",
    ]

from .kube_api_helpers import _kube_api_error_handling

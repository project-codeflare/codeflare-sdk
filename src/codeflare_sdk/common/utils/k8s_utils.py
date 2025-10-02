"""
Kubernetes utility functions for the CodeFlare SDK.
"""

import os
from kubernetes import config
from ..kubernetes_cluster import config_check, _kube_api_error_handling


def get_current_namespace():  # pragma: no cover
    """
    Retrieves the current Kubernetes namespace.

    Returns:
        str:
            The current namespace or None if not found.
    """
    if os.path.isfile("/var/run/secrets/kubernetes.io/serviceaccount/namespace"):
        try:
            file = open("/var/run/secrets/kubernetes.io/serviceaccount/namespace", "r")
            active_context = file.readline().strip("\n")
            return active_context
        except Exception as e:
            print("Unable to find current namespace")
    print("trying to gather from current context")
    try:
        _, active_context = config.list_kube_config_contexts(config_check())
    except Exception as e:
        return _kube_api_error_handling(e)
    try:
        return active_context["context"]["namespace"]
    except KeyError:
        return None

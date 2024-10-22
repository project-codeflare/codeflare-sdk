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

from typing import Optional, List
from codeflare_sdk.common import _kube_api_error_handling
from codeflare_sdk.common.kubernetes_cluster.auth import config_check, get_api_client
from kubernetes import client
from kubernetes.client.exceptions import ApiException


def get_default_kueue_name(namespace: str) -> Optional[str]:
    """
    Retrieves the default Kueue name from the provided namespace.

    This function attempts to fetch the local queues in the given namespace and checks if any of them is annotated
    as the default queue. If found, the name of the default queue is returned.

    The default queue is marked with the annotation "kueue.x-k8s.io/default-queue" set to "true."

    Args:
        namespace (str):
            The Kubernetes namespace where the local queues are located.

    Returns:
        Optional[str]:
            The name of the default queue if it exists, otherwise None.
    """
    try:
        config_check()
        api_instance = client.CustomObjectsApi(get_api_client())
        local_queues = api_instance.list_namespaced_custom_object(
            group="kueue.x-k8s.io",
            version="v1beta1",
            namespace=namespace,
            plural="localqueues",
        )
    except ApiException as e:  # pragma: no cover
        if e.status == 404 or e.status == 403:
            return
        else:
            return _kube_api_error_handling(e)
    for lq in local_queues["items"]:
        if (
            "annotations" in lq["metadata"]
            and "kueue.x-k8s.io/default-queue" in lq["metadata"]["annotations"]
            and lq["metadata"]["annotations"]["kueue.x-k8s.io/default-queue"].lower()
            == "true"
        ):
            return lq["metadata"]["name"]


def list_local_queues(
    namespace: Optional[str] = None, flavors: Optional[List[str]] = None
) -> List[dict]:
    """
    This function lists all local queues in the namespace provided.

    If no namespace is provided, it will use the current namespace. If flavors is provided, it will only return local
    queues that support all the flavors provided.

    Note:
        Depending on the version of the local queue API, the available flavors may not be present in the response.

    Args:
        namespace (str, optional):
            The namespace to list local queues from. Defaults to None.
        flavors (List[str], optional):
            The flavors to filter local queues by. Defaults to None.
    Returns:
        List[dict]:
            A list of dictionaries containing the name of the local queue and the available flavors
    """
    from ...ray.cluster.cluster import get_current_namespace

    if namespace is None:  # pragma: no cover
        namespace = get_current_namespace()
    try:
        config_check()
        api_instance = client.CustomObjectsApi(get_api_client())
        local_queues = api_instance.list_namespaced_custom_object(
            group="kueue.x-k8s.io",
            version="v1beta1",
            namespace=namespace,
            plural="localqueues",
        )
    except ApiException as e:  # pragma: no cover
        return _kube_api_error_handling(e)
    to_return = []
    for lq in local_queues["items"]:
        item = {"name": lq["metadata"]["name"]}
        if "flavors" in lq["status"]:
            item["flavors"] = [f["name"] for f in lq["status"]["flavors"]]
            if flavors is not None and not set(flavors).issubset(set(item["flavors"])):
                continue
        elif flavors is not None:
            continue  # NOTE: may be indicative old local queue API and might be worth while raising or warning here
        to_return.append(item)
    return to_return


def local_queue_exists(namespace: str, local_queue_name: str) -> bool:
    """
    Checks if a local queue with the provided name exists in the given namespace.

    This function queries the local queues in the specified namespace and verifies if any queue matches the given name.

    Args:
        namespace (str):
            The namespace where the local queues are located.
        local_queue_name (str):
            The name of the local queue to check for existence.

    Returns:
        bool:
            True if the local queue exists, False otherwise.
    """
    try:
        config_check()
        api_instance = client.CustomObjectsApi(get_api_client())
        local_queues = api_instance.list_namespaced_custom_object(
            group="kueue.x-k8s.io",
            version="v1beta1",
            namespace=namespace,
            plural="localqueues",
        )
    except Exception as e:  # pragma: no cover
        return _kube_api_error_handling(e)
    # check if local queue with the name provided in cluster config exists
    for lq in local_queues["items"]:
        if lq["metadata"]["name"] == local_queue_name:
            return True
    return False


def add_queue_label(item: dict, namespace: str, local_queue: Optional[str]):
    """
    Adds a local queue name label to the provided item.

    If the local queue is not provided, the default local queue for the namespace is used. The function validates if the
    local queue exists, and if it does, the local queue name label is added to the resource metadata.

    Args:
        item (dict):
            The resource where the label will be added.
        namespace (str):
            The namespace of the local queue.
        local_queue (str, optional):
            The name of the local queue to use. Defaults to None.

    Raises:
        ValueError:
            If the provided or default local queue does not exist in the namespace.
    """
    lq_name = local_queue or get_default_kueue_name(namespace)
    if lq_name == None:
        return
    elif not local_queue_exists(namespace, lq_name):
        raise ValueError(
            "local_queue provided does not exist or is not in this namespace. Please provide the correct local_queue name in Cluster Configuration"
        )
    if not "labels" in item["metadata"]:
        item["metadata"]["labels"] = {}
    item["metadata"]["labels"].update({"kueue.x-k8s.io/queue-name": lq_name})

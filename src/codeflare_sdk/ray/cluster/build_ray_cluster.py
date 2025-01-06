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

"""
    This sub-module exists primarily to be used internally by the Cluster object
    (in the cluster sub-module) for RayCluster/AppWrapper generation.
"""
from typing import List, Union, Tuple, Dict
from ...common import _kube_api_error_handling
from ...common.kubernetes_cluster import get_api_client, config_check
from kubernetes.client.exceptions import ApiException
import codeflare_sdk
import os

from kubernetes import client
from kubernetes.client import (
    V1ObjectMeta,
    V1KeyToPath,
    V1ConfigMapVolumeSource,
    V1Volume,
    V1VolumeMount,
    V1ResourceRequirements,
    V1Container,
    V1ContainerPort,
    V1Lifecycle,
    V1ExecAction,
    V1LifecycleHandler,
    V1EnvVar,
    V1PodTemplateSpec,
    V1PodSpec,
    V1LocalObjectReference,
    V1Toleration,
)

import yaml
import uuid
import sys
import warnings
import json

FORBIDDEN_CUSTOM_RESOURCE_TYPES = ["GPU", "CPU", "memory"]
VOLUME_MOUNTS = [
    V1VolumeMount(
        mount_path="/etc/pki/tls/certs/odh-trusted-ca-bundle.crt",
        name="odh-trusted-ca-cert",
        sub_path="odh-trusted-ca-bundle.crt",
    ),
    V1VolumeMount(
        mount_path="/etc/ssl/certs/odh-trusted-ca-bundle.crt",
        name="odh-trusted-ca-cert",
        sub_path="odh-trusted-ca-bundle.crt",
    ),
    V1VolumeMount(
        mount_path="/etc/pki/tls/certs/odh-ca-bundle.crt",
        name="odh-ca-cert",
        sub_path="odh-ca-bundle.crt",
    ),
    V1VolumeMount(
        mount_path="/etc/ssl/certs/odh-ca-bundle.crt",
        name="odh-ca-cert",
        sub_path="odh-ca-bundle.crt",
    ),
]

VOLUMES = [
    V1Volume(
        name="odh-trusted-ca-cert",
        config_map=V1ConfigMapVolumeSource(
            name="odh-trusted-ca-bundle",
            items=[V1KeyToPath(key="ca-bundle.crt", path="odh-trusted-ca-bundle.crt")],
            optional=True,
        ),
    ),
    V1Volume(
        name="odh-ca-cert",
        config_map=V1ConfigMapVolumeSource(
            name="odh-trusted-ca-bundle",
            items=[V1KeyToPath(key="odh-ca-bundle.crt", path="odh-ca-bundle.crt")],
            optional=True,
        ),
    ),
]

SUPPORTED_PYTHON_VERSIONS = {
    "3.9": "quay.io/modh/ray@sha256:0d715f92570a2997381b7cafc0e224cfa25323f18b9545acfd23bc2b71576d06",
    "3.11": "quay.io/modh/ray@sha256:db667df1bc437a7b0965e8031e905d3ab04b86390d764d120e05ea5a5c18d1b4",
}


# RayCluster/AppWrapper builder function
def build_ray_cluster(cluster: "codeflare_sdk.ray.cluster.Cluster"):
    """build_ray_cluster is used for creating a Ray Cluster/AppWrapper dict

    The resource is a dict template which uses Kubernetes Objects for creating metadata, resource requests,
    specs and containers. The result is sanitised and returned either as a dict or written as a yaml file.
    """
    ray_version = "2.35.0"

    # GPU related variables
    head_gpu_count, worker_gpu_count = head_worker_gpu_count_from_cluster(cluster)
    head_resources, worker_resources = head_worker_extended_resources_from_cluster(
        cluster
    )
    head_resources = json.dumps(head_resources).replace('"', '\\"')
    head_resources = f'"{head_resources}"'
    worker_resources = json.dumps(worker_resources).replace('"', '\\"')
    worker_resources = f'"{worker_resources}"'

    # Create the Ray Cluster using the V1RayCluster Object
    resource = {
        "apiVersion": "ray.io/v1",
        "kind": "RayCluster",
        "metadata": get_metadata(cluster),
        "spec": {
            "rayVersion": ray_version,
            "enableInTreeAutoscaling": False,
            "autoscalerOptions": {
                "upscalingMode": "Default",
                "idleTimeoutSeconds": 60,
                "resources": get_resources("500m", "500m", "512Mi", "512Mi"),
            },
            "headGroupSpec": {
                "serviceType": "ClusterIP",
                "enableIngress": False,
                "rayStartParams": {
                    "dashboard-host": "0.0.0.0",
                    "block": "true",
                    "num-gpus": str(head_gpu_count),
                    "resources": head_resources,
                },
                "template": {
                    "spec": get_pod_spec(
                        cluster,
                        [get_head_container_spec(cluster)],
                        cluster.config.head_tolerations,
                    )
                },
            },
            "workerGroupSpecs": [
                {
                    "replicas": cluster.config.num_workers,
                    "minReplicas": cluster.config.num_workers,
                    "maxReplicas": cluster.config.num_workers,
                    "groupName": f"small-group-{cluster.config.name}",
                    "rayStartParams": {
                        "block": "true",
                        "num-gpus": str(worker_gpu_count),
                        "resources": worker_resources,
                    },
                    "template": V1PodTemplateSpec(
                        spec=get_pod_spec(
                            cluster,
                            [get_worker_container_spec(cluster)],
                            cluster.config.worker_tolerations,
                        )
                    ),
                }
            ],
        },
    }

    config_check()
    k8s_client = get_api_client() or client.ApiClient()

    if cluster.config.appwrapper:
        # Wrap the Ray Cluster in an AppWrapper
        appwrapper_name, _ = gen_names(cluster.config.name)
        resource = wrap_cluster(cluster, appwrapper_name, resource)

    resource = k8s_client.sanitize_for_serialization(resource)

    # write_to_file functionality
    if cluster.config.write_to_file:
        return write_to_file(cluster, resource)  # Writes the file and returns its name
    else:
        print(f"Yaml resources loaded for {cluster.config.name}")
        return resource  # Returns the Resource as a dict


# Metadata related functions
def get_metadata(cluster: "codeflare_sdk.ray.cluster.Cluster"):
    """
    The get_metadata() function builds and returns a V1ObjectMeta Object using cluster configurtation parameters
    """
    object_meta = V1ObjectMeta(
        name=cluster.config.name,
        namespace=cluster.config.namespace,
        labels=get_labels(cluster),
    )

    # Get the NB annotation if it exists - could be useful in future for a "annotations" parameter.
    annotations = with_nb_annotations(cluster.config.annotations)
    if annotations != {}:
        object_meta.annotations = annotations  # As annotations are not a guarantee they are appended to the metadata after creation.
    return object_meta


def get_labels(cluster: "codeflare_sdk.ray.cluster.Cluster"):
    """
    The get_labels() function generates a dict "labels" which includes the base label, local queue label and user defined labels
    """
    labels = {
        "controller-tools.k8s.io": "1.0",
    }
    if cluster.config.labels != {}:
        labels.update(cluster.config.labels)

    if cluster.config.appwrapper is False:
        add_queue_label(cluster, labels)

    return labels


def with_nb_annotations(annotations: dict):
    """
    The with_nb_annotations() function generates the annotation for NB Prefix if the SDK is running in a notebook and appends any user set annotations
    """

    # Notebook annotation
    nb_prefix = os.environ.get("NB_PREFIX")
    if nb_prefix:
        annotations.update({"app.kubernetes.io/managed-by": nb_prefix})

    return annotations


# Head/Worker container related functions
def update_image(image) -> str:
    """
    The update_image() function automatically sets the image config parameter to a preset image based on Python version if not specified.
    If no Ray image exists for the given Python version a warning is produced.
    """
    if not image:
        python_version = f"{sys.version_info.major}.{sys.version_info.minor}"
        if python_version in SUPPORTED_PYTHON_VERSIONS:
            image = SUPPORTED_PYTHON_VERSIONS[python_version]
        else:
            warnings.warn(
                f"No default Ray image defined for {python_version}. Please provide your own image or use one of the following python versions: {', '.join(SUPPORTED_PYTHON_VERSIONS.keys())}."
            )
    return image


def get_pod_spec(
    cluster: "codeflare_sdk.ray.cluster.Cluster",
    containers: List,
    tolerations: List[V1Toleration],
) -> V1PodSpec:
    """
    The get_pod_spec() function generates a V1PodSpec for the head/worker containers
    """

    pod_spec = V1PodSpec(
        containers=containers,
        volumes=generate_custom_storage(cluster.config.volumes, VOLUMES),
        tolerations=tolerations or None,
    )

    if cluster.config.image_pull_secrets != []:
        pod_spec.image_pull_secrets = generate_image_pull_secrets(cluster)

    return pod_spec


def generate_image_pull_secrets(cluster: "codeflare_sdk.ray.cluster.Cluster"):
    """
    The generate_image_pull_secrets() methods generates a list of V1LocalObjectReference including each of the specified image pull secrets
    """
    pull_secrets = []
    for pull_secret in cluster.config.image_pull_secrets:
        pull_secrets.append(V1LocalObjectReference(name=pull_secret))

    return pull_secrets


def get_head_container_spec(
    cluster: "codeflare_sdk.ray.cluster.Cluster",
):
    """
    The get_head_container_spec() function builds and returns a V1Container object including user defined resource requests/limits
    """
    head_container = V1Container(
        name="ray-head",
        image=update_image(cluster.config.image),
        image_pull_policy="Always",
        ports=[
            V1ContainerPort(name="gcs", container_port=6379),
            V1ContainerPort(name="dashboard", container_port=8265),
            V1ContainerPort(name="client", container_port=10001),
        ],
        lifecycle=V1Lifecycle(
            pre_stop=V1LifecycleHandler(
                _exec=V1ExecAction(["/bin/sh", "-c", "ray stop"])
            )
        ),
        resources=get_resources(
            cluster.config.head_cpu_requests,
            cluster.config.head_cpu_limits,
            cluster.config.head_memory_requests,
            cluster.config.head_memory_limits,
            cluster.config.head_extended_resource_requests,
        ),
        volume_mounts=generate_custom_storage(
            cluster.config.volume_mounts, VOLUME_MOUNTS
        ),
    )
    if cluster.config.envs != {}:
        head_container.env = generate_env_vars(cluster)

    return head_container


def generate_env_vars(cluster: "codeflare_sdk.ray.cluster.Cluster"):
    """
    The generate_env_vars() builds and returns a V1EnvVar object which is populated by user specified environment variables
    """
    envs = []
    for key, value in cluster.config.envs.items():
        env_var = V1EnvVar(name=key, value=value)
        envs.append(env_var)

    return envs


def get_worker_container_spec(
    cluster: "codeflare_sdk.ray.cluster.Cluster",
):
    """
    The get_worker_container_spec() function builds and returns a V1Container object including user defined resource requests/limits
    """
    worker_container = V1Container(
        name="machine-learning",
        image=update_image(cluster.config.image),
        image_pull_policy="Always",
        lifecycle=V1Lifecycle(
            pre_stop=V1LifecycleHandler(
                _exec=V1ExecAction(["/bin/sh", "-c", "ray stop"])
            )
        ),
        resources=get_resources(
            cluster.config.worker_cpu_requests,
            cluster.config.worker_cpu_limits,
            cluster.config.worker_memory_requests,
            cluster.config.worker_memory_limits,
            cluster.config.worker_extended_resource_requests,
        ),
        volume_mounts=generate_custom_storage(
            cluster.config.volume_mounts, VOLUME_MOUNTS
        ),
    )

    if cluster.config.envs != {}:
        worker_container.env = generate_env_vars(cluster)

    return worker_container


def get_resources(
    cpu_requests: Union[int, str],
    cpu_limits: Union[int, str],
    memory_requests: Union[int, str],
    memory_limits: Union[int, str],
    custom_extended_resource_requests: Dict[str, int] = None,
):
    """
    The get_resources() function generates a V1ResourceRequirements object for cpu/memory request/limits and GPU resources
    """
    resource_requirements = V1ResourceRequirements(
        requests={"cpu": cpu_requests, "memory": memory_requests},
        limits={"cpu": cpu_limits, "memory": memory_limits},
    )

    # Append the resource/limit requests with custom extended resources
    if custom_extended_resource_requests is not None:
        for k in custom_extended_resource_requests.keys():
            resource_requirements.limits[k] = custom_extended_resource_requests[k]
            resource_requirements.requests[k] = custom_extended_resource_requests[k]

    return resource_requirements


# GPU related functions
def head_worker_gpu_count_from_cluster(
    cluster: "codeflare_sdk.ray.cluster.Cluster",
) -> Tuple[int, int]:
    """
    The head_worker_gpu_count_from_cluster() function returns the total number of requested GPUs for the head and worker separately
    """
    head_gpus = 0
    worker_gpus = 0
    for k in cluster.config.head_extended_resource_requests.keys():
        resource_type = cluster.config.extended_resource_mapping[k]
        if resource_type == "GPU":
            head_gpus += int(cluster.config.head_extended_resource_requests[k])
    for k in cluster.config.worker_extended_resource_requests.keys():
        resource_type = cluster.config.extended_resource_mapping[k]
        if resource_type == "GPU":
            worker_gpus += int(cluster.config.worker_extended_resource_requests[k])

    return head_gpus, worker_gpus


def head_worker_extended_resources_from_cluster(
    cluster: "codeflare_sdk.ray.cluster.Cluster",
) -> Tuple[dict, dict]:
    """
    The head_worker_extended_resources_from_cluster() function returns 2 dicts for head/worker respectively populated by the GPU type requested by the user
    """
    head_worker_extended_resources = {}, {}
    for k in cluster.config.head_extended_resource_requests.keys():
        resource_type = cluster.config.extended_resource_mapping[k]
        if resource_type in FORBIDDEN_CUSTOM_RESOURCE_TYPES:
            continue
        head_worker_extended_resources[0][
            resource_type
        ] = cluster.config.head_extended_resource_requests[
            k
        ] + head_worker_extended_resources[
            0
        ].get(
            resource_type, 0
        )

    for k in cluster.config.worker_extended_resource_requests.keys():
        resource_type = cluster.config.extended_resource_mapping[k]
        if resource_type in FORBIDDEN_CUSTOM_RESOURCE_TYPES:
            continue
        head_worker_extended_resources[1][
            resource_type
        ] = cluster.config.worker_extended_resource_requests[
            k
        ] + head_worker_extended_resources[
            1
        ].get(
            resource_type, 0
        )
    return head_worker_extended_resources


# Local Queue related functions
def add_queue_label(cluster: "codeflare_sdk.ray.cluster.Cluster", labels: dict):
    """
    The add_queue_label() function updates the given base labels with the local queue label if Kueue exists on the Cluster
    """
    lq_name = cluster.config.local_queue or get_default_local_queue(cluster, labels)
    if lq_name == None:
        return
    elif not local_queue_exists(cluster):
        raise ValueError(
            "local_queue provided does not exist or is not in this namespace. Please provide the correct local_queue name in Cluster Configuration"
        )
    labels.update({"kueue.x-k8s.io/queue-name": lq_name})


def local_queue_exists(cluster: "codeflare_sdk.ray.cluster.Cluster"):
    """
    The local_queue_exists() checks if the user inputted local_queue exists in the given namespace and returns a bool
    """
    # get all local queues in the namespace
    try:
        config_check()
        api_instance = client.CustomObjectsApi(get_api_client())
        local_queues = api_instance.list_namespaced_custom_object(
            group="kueue.x-k8s.io",
            version="v1beta1",
            namespace=cluster.config.namespace,
            plural="localqueues",
        )
    except Exception as e:  # pragma: no cover
        return _kube_api_error_handling(e)
    # check if local queue with the name provided in cluster config exists
    for lq in local_queues["items"]:
        if lq["metadata"]["name"] == cluster.config.local_queue:
            return True
    return False


def get_default_local_queue(cluster: "codeflare_sdk.ray.cluster.Cluster", labels: dict):
    """
    The get_default_local_queue() function attempts to find a local queue with the default label == true, if that is the case the labels variable is updated with that local queue
    """
    try:
        # Try to get the default local queue if it exists and append the label list
        config_check()
        api_instance = client.CustomObjectsApi(get_api_client())
        local_queues = api_instance.list_namespaced_custom_object(
            group="kueue.x-k8s.io",
            version="v1beta1",
            namespace=cluster.config.namespace,
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
            labels.update({"kueue.x-k8s.io/queue-name": lq["metadata"]["name"]})


# AppWrapper related functions
def wrap_cluster(
    cluster: "codeflare_sdk.ray.cluster.Cluster",
    appwrapper_name: str,
    ray_cluster_yaml: dict,
):
    """
    Wraps the pre-built Ray Cluster dict in an AppWrapper
    """
    wrapping = {
        "apiVersion": "workload.codeflare.dev/v1beta2",
        "kind": "AppWrapper",
        "metadata": {"name": appwrapper_name, "namespace": cluster.config.namespace},
        "spec": {"components": [{"template": ray_cluster_yaml}]},
    }
    # Add local queue label if it is necessary
    labels = {}
    add_queue_label(cluster, labels)
    if labels != {}:
        wrapping["metadata"]["labels"] = labels

    return wrapping


# Etc.
def generate_custom_storage(provided_storage: list, default_storage: list):
    """
    The generate_custom_storage function updates the volumes/volume mounts configs with the default volumes/volume mounts.
    """
    storage_list = provided_storage.copy()

    if storage_list == []:
        storage_list = default_storage
    else:
        # We append the list of volumes/volume mounts with the defaults and return the full list
        for storage in default_storage:
            storage_list.append(storage)

    return storage_list


def write_to_file(cluster: "codeflare_sdk.ray.cluster.Cluster", resource: dict):
    """
    The write_to_file function writes the built Ray Cluster/AppWrapper dict as a yaml file in the .codeflare folder
    """
    directory_path = os.path.expanduser("~/.codeflare/resources/")
    output_file_name = os.path.join(directory_path, cluster.config.name + ".yaml")

    directory_path = os.path.dirname(output_file_name)
    if not os.path.exists(directory_path):
        os.makedirs(directory_path)

    with open(output_file_name, "w") as outfile:
        yaml.dump(resource, outfile, default_flow_style=False)

    print(f"Written to: {output_file_name}")
    return output_file_name


def gen_names(name):
    """
    Generates a unique name for the appwrapper and Ray Cluster
    """
    if not name:
        gen_id = str(uuid.uuid4())
        appwrapper_name = "appwrapper-" + gen_id
        cluster_name = "cluster-" + gen_id
        return appwrapper_name, cluster_name
    else:
        return name, name

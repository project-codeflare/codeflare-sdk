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
    (in the cluster sub-module) for RayCluster generation.
"""

from typing import List, Tuple
from ...common import _kube_api_error_handling
from ...common.kubernetes_cluster import get_api_client, config_check
from kubernetes.client.exceptions import ApiException
from ...common.utils.constants import RAY_VERSION
from ...common.utils.utils import update_image
import codeflare_sdk
import os

from kubernetes import client
from kubernetes.client import (
    V1ObjectMeta,
    V1Container,
    V1Lifecycle,
    V1ExecAction,
    V1LifecycleHandler,
    V1EnvVar,
    V1PodTemplateSpec,
    V1PodSpec,
    V1Toleration,
)

import yaml
import uuid
import json

# RHOAIENG-98942: the RayCluster spec is rendered from one place, shared with
# the RayJob-embedded builder. These aliases keep this module's existing call
# sites; the wrappers further down do the same for helpers that take a Cluster
# rather than a ClusterConfiguration.
from . import raycluster_spec as _spec
from .raycluster_spec import (
    FORBIDDEN_CUSTOM_RESOURCE_TYPES,
    ODH_VOLUMES as VOLUMES,
    ODH_VOLUME_MOUNTS as VOLUME_MOUNTS,
    build_resource_requirements as get_resources,
    cpu_limit_to_num_cpus as _cpu_limit_to_num_cpus,
    format_resources_param,
    gcs_fault_tolerance_options,
    merge_storage as generate_custom_storage,
    worker_replica_counts,
)


# RayCluster builder function
def build_ray_cluster(cluster: "codeflare_sdk.ray.cluster.Cluster"):
    """build_ray_cluster is used for creating a Ray Cluster dict

    The resource is a dict template which uses Kubernetes Objects for creating metadata, resource requests,
    specs and containers. The result is sanitised and returned either as a dict or written as a yaml file.
    """

    # GPU related variables
    head_gpu_count, worker_gpu_count = head_worker_gpu_count_from_cluster(cluster)
    head_resources, worker_resources = head_worker_extended_resources_from_cluster(
        cluster
    )
    head_resources = format_resources_param(head_resources)
    worker_resources = format_resources_param(worker_resources)

    # Kueue compatibility is a cluster lookup, so it stays here rather than in
    # the shared renderer, which must remain free of API calls.
    autoscaling_enabled = cluster.config.enable_autoscaling
    if autoscaling_enabled:
        from codeflare_sdk.common.kueue.kueue import validate_autoscaling_with_kueue

        validate_autoscaling_with_kueue(
            cluster.config.namespace, cluster.config.local_queue
        )

    worker_replicas, worker_min_replicas, worker_max_replicas = worker_replica_counts(
        cluster.config
    )

    # Create the Ray Cluster using the V1RayCluster Object
    resource = {
        "apiVersion": "ray.io/v1",
        "kind": "RayCluster",
        "metadata": get_metadata(cluster),
        "spec": {
            "rayVersion": RAY_VERSION,
            "enableInTreeAutoscaling": autoscaling_enabled,
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
                    "num-cpus": _cpu_limit_to_num_cpus(cluster.config.head_cpu_limits),
                    "num-gpus": str(head_gpu_count),
                    "resources": head_resources,
                },
                "template": V1PodTemplateSpec(
                    metadata=(
                        V1ObjectMeta(annotations=cluster.config.annotations)
                        if cluster.config.annotations
                        else None
                    ),
                    spec=get_pod_spec(
                        cluster,
                        [get_head_container_spec(cluster)],
                        cluster.config.head_tolerations,
                    ),
                ),
            },
            "workerGroupSpecs": [
                {
                    "replicas": worker_replicas,
                    "minReplicas": worker_min_replicas,
                    "maxReplicas": worker_max_replicas,
                    "groupName": f"small-group-{cluster.config.name}",
                    "rayStartParams": {
                        "block": "true",
                        "num-cpus": _cpu_limit_to_num_cpus(
                            cluster.config.worker_cpu_limits
                        ),
                        "num-gpus": str(worker_gpu_count),
                        "resources": worker_resources,
                    },
                    "template": V1PodTemplateSpec(
                        metadata=(
                            V1ObjectMeta(annotations=cluster.config.annotations)
                            if cluster.config.annotations
                            else None
                        ),
                        spec=get_pod_spec(
                            cluster,
                            [get_worker_container_spec(cluster)],
                            cluster.config.worker_tolerations,
                        ),
                    ),
                }
            ],
        },
    }

    for wg in cluster.config.additional_worker_groups:
        resource["spec"]["workerGroupSpecs"].append(
            _build_worker_group_spec(cluster, wg)
        )

    gcs_ft_options = gcs_fault_tolerance_options(cluster.config)
    if gcs_ft_options is not None:
        resource["spec"]["gcsFaultToleranceOptions"] = gcs_ft_options

    config_check()
    k8s_client = get_api_client() or client.ApiClient()

    resource = k8s_client.sanitize_for_serialization(resource)

    # write_to_file functionality
    if cluster.config.write_to_file:
        return write_to_file(cluster, resource)  # Writes the file and returns its name
    else:
        return resource  # Returns the Resource as a dict


# Metadata related functions
def get_metadata(cluster: "codeflare_sdk.ray.cluster.Cluster"):
    """
    The get_metadata() function builds and returns a V1ObjectMeta Object using cluster configuration parameters
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
        "ray.io/cluster": cluster.config.name,  # Enforced label always present
    }
    if cluster.config.labels != {}:
        labels.update(cluster.config.labels)

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


# GPU related functions


# Local Queue related functions
def add_queue_label(cluster: "codeflare_sdk.ray.cluster.Cluster", labels: dict):
    """
    The add_queue_label() function updates the given base labels with the local queue label if Kueue exists on the Cluster
    """
    lq_name = cluster.config.local_queue or get_default_local_queue(cluster, labels)
    if lq_name is None:
        return
    elif not local_queue_exists(cluster):
        # ValueError removed to pass validation to validating admission policy
        print(
            "local_queue provided does not exist or is not in this namespace. Please provide the correct local_queue name in Cluster Configuration"
        )
        return
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


# Etc.


def write_to_file(cluster: "codeflare_sdk.ray.cluster.Cluster", resource: dict):
    """
    The write_to_file function writes the built Ray Cluster dict as a yaml file in the .codeflare folder
    """
    directory_path = os.path.expanduser("~/.codeflare/resources/")
    output_file_name = os.path.join(directory_path, cluster.config.name + ".yaml")

    directory_path = os.path.dirname(output_file_name)
    if not os.path.exists(directory_path):
        os.makedirs(directory_path)

    # Convert resource to JSON and back to sanitize Pydantic undefined values
    # This is a workaround for PyYAML not being able to serialize Pydantic v2 models
    # used by Kubernetes client v33+
    try:
        import json

        resource_json = json.dumps(resource, default=str)
        sanitized_resource = json.loads(resource_json)
    except (TypeError, ValueError):
        # If JSON serialization fails, use the resource as-is
        sanitized_resource = resource

    with open(output_file_name, "w") as outfile:
        yaml.dump(sanitized_resource, outfile, default_flow_style=False)

    print(f"Written to: {output_file_name}")
    return output_file_name


def _build_worker_group_spec(
    cluster: "codeflare_sdk.ray.cluster.Cluster",
    wg: "codeflare_sdk.ray.cluster.config.WorkerGroup",
) -> dict:
    """Build a single workerGroupSpec dict from a WorkerGroup."""
    replicas = wg.replicas
    min_replicas = wg.min_replicas if wg.min_replicas is not None else replicas
    max_replicas = wg.max_replicas if wg.max_replicas is not None else replicas

    # GPU handling
    gpu_count = wg.gpu_count or 0
    extended_resources = dict(wg.extended_resource_requests)
    if wg.gpu_type and wg.gpu_count:
        extended_resources[wg.gpu_type] = wg.gpu_count

    # Ray custom resources (non-GPU extended resources)
    ray_resources = {}
    if wg.gpu_type and wg.gpu_count:
        mapping = cluster.config.extended_resource_mapping
        rtype = mapping.get(wg.gpu_type, "GPU")
        if rtype not in FORBIDDEN_CUSTOM_RESOURCE_TYPES:
            ray_resources[rtype] = wg.gpu_count
    ray_resources_str = json.dumps(ray_resources).replace('"', '\\"')
    ray_resources_str = f'"{ray_resources_str}"'

    # Image inheritance
    image = wg.image if wg.image else update_image(cluster.config.image)

    # Env merge: cluster-level defaults, group overrides
    merged_envs = {**cluster.config.envs, **wg.envs}

    # Tolerations inheritance
    tolerations = (
        wg.tolerations
        if wg.tolerations is not None
        else cluster.config.worker_tolerations
    )

    # Build container
    container = V1Container(
        name="machine-learning",
        image=image,
        image_pull_policy="Always",
        lifecycle=V1Lifecycle(
            pre_stop=V1LifecycleHandler(
                _exec=V1ExecAction(command=["/bin/sh", "-c", "ray stop"])
            )
        ),
        resources=get_resources(
            wg.cpu_requests,
            wg.cpu_limits,
            wg.memory_requests,
            wg.memory_limits,
            extended_resources or None,
        ),
        volume_mounts=generate_custom_storage(
            cluster.config.volume_mounts, VOLUME_MOUNTS
        ),
    )

    if merged_envs:
        container.env = [V1EnvVar(name=k, value=v) for k, v in merged_envs.items()]

    # Labels merge: cluster-level defaults, group overrides
    merged_labels = {**cluster.config.labels, **wg.labels}

    pod_spec = V1PodSpec(
        containers=[container],
        volumes=generate_custom_storage(cluster.config.volumes, VOLUMES),
        tolerations=tolerations or None,
    )

    if cluster.config.image_pull_secrets:
        pod_spec.image_pull_secrets = generate_image_pull_secrets(cluster)

    # Pod template metadata with merged annotations and labels
    pod_metadata = None
    if cluster.config.annotations or merged_labels:
        pod_metadata = V1ObjectMeta(
            annotations=cluster.config.annotations
            if cluster.config.annotations
            else None,
            labels=merged_labels if merged_labels else None,
        )

    return {
        "replicas": replicas,
        "minReplicas": min_replicas,
        "maxReplicas": max_replicas,
        "groupName": wg.group_name,
        "rayStartParams": {
            "block": "true",
            "num-cpus": _cpu_limit_to_num_cpus(wg.cpu_limits),
            "num-gpus": str(gpu_count),
            "resources": ray_resources_str,
        },
        "template": V1PodTemplateSpec(
            metadata=pod_metadata,
            spec=pod_spec,
        ),
    }


def gen_names(name):
    """
    Generates a unique name for the Ray Cluster
    """
    if not name:
        gen_id = str(uuid.uuid4())
        cluster_name = "cluster-" + gen_id
        return cluster_name
    else:
        return name


def head_worker_gpu_count_from_cluster(cluster) -> Tuple[int, int]:
    """Total GPUs requested for the head and for a worker, respectively."""
    return _spec.gpu_counts(cluster.config)


def head_worker_extended_resources_from_cluster(cluster) -> Tuple[dict, dict]:
    """Non-GPU/CPU/memory resources for the head and worker rayStartParams."""
    return _spec.extended_resources(cluster.config)


def get_head_container_spec(cluster):
    """The ray-head container."""
    return _spec.build_head_container(cluster.config)


def get_worker_container_spec(cluster):
    """The machine-learning worker container."""
    return _spec.build_worker_container(cluster.config)


def generate_image_pull_secrets(cluster):
    """Secret references for pulling the Ray image."""
    return _spec.image_pull_secrets(cluster.config)


def generate_env_vars(cluster):
    """User-supplied environment variables."""
    return _spec.env_vars(cluster.config)

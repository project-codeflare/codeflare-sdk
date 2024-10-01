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
This sub-module exists primarily to be used internally by the Cluster object
(in the cluster sub-module) for AppWrapper generation.
"""

import json
import typing
import yaml
import os
import uuid
from kubernetes import client
from ...common import _kube_api_error_handling
from ...common.kueue import add_queue_label
from ...common.kubernetes_cluster.auth import (
    get_api_client,
    config_check,
)
import codeflare_sdk


def read_template(template):
    with open(template, "r") as stream:
        try:
            return yaml.safe_load(stream)
        except yaml.YAMLError as exc:
            print(exc)


def gen_names(name):
    if not name:
        gen_id = str(uuid.uuid4())
        appwrapper_name = "appwrapper-" + gen_id
        cluster_name = "cluster-" + gen_id
        return appwrapper_name, cluster_name
    else:
        return name, name


# Check if the routes api exists
def is_openshift_cluster():
    try:
        config_check()
        for api in client.ApisApi(get_api_client()).get_api_versions().groups:
            for v in api.versions:
                if "route.openshift.io/v1" in v.group_version:
                    return True
        else:
            return False
    except Exception as e:  # pragma: no cover
        return _kube_api_error_handling(e)


def is_kind_cluster():
    try:
        config_check()
        v1 = client.CoreV1Api()
        label_selector = "kubernetes.io/hostname=kind-control-plane"
        nodes = v1.list_node(label_selector=label_selector)
        # If we find one or more nodes with the label, assume it's a KinD cluster
        return len(nodes.items) > 0
    except Exception as e:
        print(f"Error checking if cluster is KinD: {e}")
        return False


def update_names(
    cluster_yaml: dict,
    cluster: "codeflare_sdk.ray.cluster.cluster.Cluster",
):
    metadata = cluster_yaml.get("metadata")
    metadata["name"] = cluster.config.name
    metadata["namespace"] = cluster.config.namespace


def update_image(spec, image):
    containers = spec.get("containers")
    if image != "":
        for container in containers:
            container["image"] = image


def update_image_pull_secrets(spec, image_pull_secrets):
    template_secrets = spec.get("imagePullSecrets", [])
    spec["imagePullSecrets"] = template_secrets + [
        {"name": x} for x in image_pull_secrets
    ]


def update_env(spec, env):
    containers = spec.get("containers")
    for container in containers:
        if env:
            if "env" in container:
                container["env"].extend(env)
            else:
                container["env"] = env


def update_resources(
    spec,
    cpu_requests,
    cpu_limits,
    memory_requests,
    memory_limits,
    custom_resources,
):
    container = spec.get("containers")
    for resource in container:
        requests = resource.get("resources").get("requests")
        if requests is not None:
            requests["cpu"] = cpu_requests
            requests["memory"] = memory_requests
        limits = resource.get("resources").get("limits")
        if limits is not None:
            limits["cpu"] = cpu_limits
            limits["memory"] = memory_limits
        for k in custom_resources.keys():
            limits[k] = custom_resources[k]
            requests[k] = custom_resources[k]


def head_worker_gpu_count_from_cluster(
    cluster: "codeflare_sdk.ray.cluster.cluster.Cluster",
) -> typing.Tuple[int, int]:
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


FORBIDDEN_CUSTOM_RESOURCE_TYPES = ["GPU", "CPU", "memory"]


def head_worker_resources_from_cluster(
    cluster: "codeflare_sdk.ray.cluster.cluster.Cluster",
) -> typing.Tuple[dict, dict]:
    to_return = {}, {}
    for k in cluster.config.head_extended_resource_requests.keys():
        resource_type = cluster.config.extended_resource_mapping[k]
        if resource_type in FORBIDDEN_CUSTOM_RESOURCE_TYPES:
            continue
        to_return[0][resource_type] = cluster.config.head_extended_resource_requests[
            k
        ] + to_return[0].get(resource_type, 0)

    for k in cluster.config.worker_extended_resource_requests.keys():
        resource_type = cluster.config.extended_resource_mapping[k]
        if resource_type in FORBIDDEN_CUSTOM_RESOURCE_TYPES:
            continue
        to_return[1][resource_type] = cluster.config.worker_extended_resource_requests[
            k
        ] + to_return[1].get(resource_type, 0)
    return to_return


def update_nodes(
    ray_cluster_dict: dict,
    cluster: "codeflare_sdk.ray.cluster.cluster.Cluster",
):
    head = ray_cluster_dict.get("spec").get("headGroupSpec")
    worker = ray_cluster_dict.get("spec").get("workerGroupSpecs")[0]
    head_gpus, worker_gpus = head_worker_gpu_count_from_cluster(cluster)
    head_resources, worker_resources = head_worker_resources_from_cluster(cluster)
    head_resources = json.dumps(head_resources).replace('"', '\\"')
    head_resources = f'"{head_resources}"'
    worker_resources = json.dumps(worker_resources).replace('"', '\\"')
    worker_resources = f'"{worker_resources}"'
    head["rayStartParams"]["num-gpus"] = str(head_gpus)
    head["rayStartParams"]["resources"] = head_resources

    # Head counts as first worker
    worker["replicas"] = cluster.config.num_workers
    worker["minReplicas"] = cluster.config.num_workers
    worker["maxReplicas"] = cluster.config.num_workers
    worker["groupName"] = "small-group-" + cluster.config.name
    worker["rayStartParams"]["num-gpus"] = str(worker_gpus)
    worker["rayStartParams"]["resources"] = worker_resources

    for comp in [head, worker]:
        spec = comp.get("template").get("spec")
        update_image_pull_secrets(spec, cluster.config.image_pull_secrets)
        update_image(spec, cluster.config.image)
        update_env(spec, cluster.config.envs)
        if comp == head:
            # TODO: Eventually add head node configuration outside of template
            update_resources(
                spec,
                cluster.config.head_cpu_requests,
                cluster.config.head_cpu_limits,
                cluster.config.head_memory_requests,
                cluster.config.head_memory_limits,
                cluster.config.head_extended_resource_requests,
            )
        else:
            update_resources(
                spec,
                cluster.config.worker_cpu_requests,
                cluster.config.worker_cpu_limits,
                cluster.config.worker_memory_requests,
                cluster.config.worker_memory_limits,
                cluster.config.worker_extended_resource_requests,
            )


def del_from_list_by_name(l: list, target: typing.List[str]) -> list:
    return [x for x in l if x["name"] not in target]


def augment_labels(item: dict, labels: dict):
    if not "labels" in item["metadata"]:
        item["metadata"]["labels"] = {}
    item["metadata"]["labels"].update(labels)


def notebook_annotations(item: dict):
    nb_prefix = os.environ.get("NB_PREFIX")
    if nb_prefix:
        if not "annotations" in item["metadata"]:
            item["metadata"]["annotations"] = {}
        item["metadata"]["annotations"].update(
            {"app.kubernetes.io/managed-by": nb_prefix}
        )


def wrap_cluster(cluster_yaml: dict, appwrapper_name: str, namespace: str):
    return {
        "apiVersion": "workload.codeflare.dev/v1beta2",
        "kind": "AppWrapper",
        "metadata": {"name": appwrapper_name, "namespace": namespace},
        "spec": {"components": [{"template": cluster_yaml}]},
    }


def write_user_yaml(user_yaml, output_file_name):
    # Create the directory if it doesn't exist
    directory_path = os.path.dirname(output_file_name)
    if not os.path.exists(directory_path):
        os.makedirs(directory_path)

    with open(output_file_name, "w") as outfile:
        yaml.dump(user_yaml, outfile, default_flow_style=False)

    print(f"Written to: {output_file_name}")


def generate_appwrapper(cluster: "codeflare_sdk.ray.cluster.cluster.Cluster"):
    cluster_yaml = read_template(cluster.config.template)
    appwrapper_name, _ = gen_names(cluster.config.name)
    update_names(
        cluster_yaml,
        cluster,
    )
    update_nodes(cluster_yaml, cluster)
    augment_labels(cluster_yaml, cluster.config.labels)
    notebook_annotations(cluster_yaml)
    user_yaml = (
        wrap_cluster(cluster_yaml, appwrapper_name, cluster.config.namespace)
        if cluster.config.appwrapper
        else cluster_yaml
    )

    add_queue_label(user_yaml, cluster.config.namespace, cluster.config.local_queue)

    if cluster.config.write_to_file:
        directory_path = os.path.expanduser("~/.codeflare/resources/")
        outfile = os.path.join(directory_path, appwrapper_name + ".yaml")
        write_user_yaml(user_yaml, outfile)
        return outfile
    else:
        user_yaml = yaml.dump(user_yaml)
        print(f"Yaml resources loaded for {cluster.config.name}")
        return user_yaml

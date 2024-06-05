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

from typing import Optional
import typing
import yaml
import sys
import os
import argparse
import uuid
from kubernetes import client, config
from .kube_api_helpers import _kube_api_error_handling
from ..cluster.auth import api_config_handler, config_check
from os import urandom
from base64 import b64encode
from urllib3.util import parse_url


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
        for api in client.ApisApi(api_config_handler()).get_api_versions().groups:
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


def update_names(yaml, item, appwrapper_name, cluster_name, namespace):
    metadata = yaml.get("metadata")
    metadata["name"] = appwrapper_name
    metadata["namespace"] = namespace
    lower_meta = item.get("template", {}).get("metadata")
    lower_meta["name"] = cluster_name
    lower_meta["namespace"] = namespace


def update_image(spec, image):
    containers = spec.get("containers")
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


def update_resources(spec, min_cpu, max_cpu, min_memory, max_memory, gpu):
    container = spec.get("containers")
    for resource in container:
        requests = resource.get("resources").get("requests")
        if requests is not None:
            requests["cpu"] = min_cpu
            requests["memory"] = min_memory
            requests["nvidia.com/gpu"] = gpu
        limits = resource.get("resources").get("limits")
        if limits is not None:
            limits["cpu"] = max_cpu
            limits["memory"] = max_memory
            limits["nvidia.com/gpu"] = gpu


def update_nodes(
    item,
    appwrapper_name,
    min_cpu,
    max_cpu,
    min_memory,
    max_memory,
    gpu,
    workers,
    image,
    env,
    image_pull_secrets,
    head_cpus,
    head_memory,
    head_gpus,
):
    if "template" in item.keys():
        head = item.get("template").get("spec").get("headGroupSpec")
        head["rayStartParams"]["num-gpus"] = str(int(head_gpus))

        worker = item.get("template").get("spec").get("workerGroupSpecs")[0]
        # Head counts as first worker
        worker["replicas"] = workers
        worker["minReplicas"] = workers
        worker["maxReplicas"] = workers
        worker["groupName"] = "small-group-" + appwrapper_name
        worker["rayStartParams"]["num-gpus"] = str(int(gpu))

        for comp in [head, worker]:
            spec = comp.get("template").get("spec")
            update_image_pull_secrets(spec, image_pull_secrets)
            update_image(spec, image)
            update_env(spec, env)
            if comp == head:
                # TODO: Eventually add head node configuration outside of template
                update_resources(
                    spec, head_cpus, head_cpus, head_memory, head_memory, head_gpus
                )
            else:
                update_resources(spec, min_cpu, max_cpu, min_memory, max_memory, gpu)


def del_from_list_by_name(l: list, target: typing.List[str]) -> list:
    return [x for x in l if x["name"] not in target]


def write_user_appwrapper(user_yaml, output_file_name):
    # Create the directory if it doesn't exist
    directory_path = os.path.dirname(output_file_name)
    if not os.path.exists(directory_path):
        os.makedirs(directory_path)

    with open(output_file_name, "w") as outfile:
        yaml.dump(user_yaml, outfile, default_flow_style=False)

    print(f"Written to: {output_file_name}")


def get_default_kueue_name(namespace: str):
    # If the local queue is set, use it. Otherwise, try to use the default queue.
    try:
        config_check()
        api_instance = client.CustomObjectsApi(api_config_handler())
        local_queues = api_instance.list_namespaced_custom_object(
            group="kueue.x-k8s.io",
            version="v1beta1",
            namespace=namespace,
            plural="localqueues",
        )
    except Exception as e:  # pragma: no cover
        return _kube_api_error_handling(e)
    for lq in local_queues["items"]:
        if (
            "annotations" in lq["metadata"]
            and "kueue.x-k8s.io/default-queue" in lq["metadata"]["annotations"]
            and lq["metadata"]["annotations"]["kueue.x-k8s.io/default-queue"].lower()
            == "true"
        ):
            return lq["metadata"]["name"]
    raise ValueError(
        "Default Local Queue with kueue.x-k8s.io/default-queue: true annotation not found please create a default Local Queue or provide the local_queue name in Cluster Configuration"
    )


def local_queue_exists(namespace: str, local_queue_name: str):
    # get all local queues in the namespace
    try:
        config_check()
        api_instance = client.CustomObjectsApi(api_config_handler())
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
    lq_name = local_queue or get_default_kueue_name(namespace)
    if not local_queue_exists(namespace, lq_name):
        raise ValueError(
            "local_queue provided does not exist or is not in this namespace. Please provide the correct local_queue name in Cluster Configuration"
        )
    if not "labels" in item["metadata"]:
        item["metadata"]["labels"] = {}
    item["metadata"]["labels"].update({"kueue.x-k8s.io/queue-name": lq_name})


def augment_labels(item: dict, labels: dict):
    if "template" in item:
        if not "labels" in item["template"]["metadata"]:
            item["template"]["metadata"]["labels"] = {}
    item["template"]["metadata"]["labels"].update(labels)


def write_components(
    user_yaml: dict,
    output_file_name: str,
):
    # Create the directory if it doesn't exist
    directory_path = os.path.dirname(output_file_name)
    if not os.path.exists(directory_path):
        os.makedirs(directory_path)

    components = user_yaml.get("spec", "resources").get("components")
    open(output_file_name, "w").close()
    with open(output_file_name, "a") as outfile:
        for component in components:
            if "template" in component:
                outfile.write("---\n")
                yaml.dump(component["template"], outfile, default_flow_style=False)
    print(f"Written to: {output_file_name}")


def load_components(
    user_yaml: dict,
    name: str,
):
    component_list = []
    components = user_yaml.get("spec", "resources").get("components")
    for component in components:
        if "template" in component:
            component_list.append(component["template"])

    resources = "---\n" + "---\n".join(
        [yaml.dump(component) for component in component_list]
    )
    user_yaml = resources
    print(f"Yaml resources loaded for {name}")
    return user_yaml


def load_appwrapper(user_yaml: dict, name: str):
    user_yaml = yaml.dump(user_yaml)
    print(f"Yaml resources loaded for {name}")
    return user_yaml


def generate_appwrapper(
    name: str,
    namespace: str,
    head_cpus: int,
    head_memory: int,
    head_gpus: int,
    min_cpu: int,
    max_cpu: int,
    min_memory: int,
    max_memory: int,
    gpu: int,
    workers: int,
    template: str,
    image: str,
    appwrapper: bool,
    instance_types: list,
    env,
    image_pull_secrets: list,
    write_to_file: bool,
    verify_tls: bool,
    local_queue: Optional[str],
    labels,
):
    user_yaml = read_template(template)
    appwrapper_name, cluster_name = gen_names(name)
    resources = user_yaml.get("spec", "resources")
    item = resources.get("components")[0]
    update_names(
        user_yaml,
        item,
        appwrapper_name,
        cluster_name,
        namespace,
    )
    update_nodes(
        item,
        appwrapper_name,
        min_cpu,
        max_cpu,
        min_memory,
        max_memory,
        gpu,
        workers,
        image,
        env,
        image_pull_secrets,
        head_cpus,
        head_memory,
        head_gpus,
    )

    augment_labels(item, labels)

    if appwrapper:
        add_queue_label(user_yaml, namespace, local_queue)
    else:
        add_queue_label(item["template"], namespace, local_queue)

    directory_path = os.path.expanduser("~/.codeflare/resources/")
    outfile = os.path.join(directory_path, appwrapper_name + ".yaml")

    if write_to_file:
        if appwrapper:
            write_user_appwrapper(user_yaml, outfile)
        else:
            write_components(user_yaml, outfile)
        return outfile
    else:
        if appwrapper:
            user_yaml = load_appwrapper(user_yaml, name)
        else:
            user_yaml = load_components(user_yaml, name)
        return user_yaml

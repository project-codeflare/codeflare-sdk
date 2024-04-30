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
    lower_meta = item.get("generictemplate", {}).get("metadata")
    lower_meta["labels"]["workload.codeflare.dev/appwrapper"] = appwrapper_name
    lower_meta["name"] = cluster_name
    lower_meta["namespace"] = namespace


def update_labels(yaml, instascale, instance_types):
    metadata = yaml.get("metadata")
    if instascale:
        if not len(instance_types) > 0:
            sys.exit(
                "If instascale is set to true, must provide at least one instance type"
            )
        type_str = ""
        for type in instance_types:
            type_str += type + "_"
        type_str = type_str[:-1]
        metadata["labels"]["orderedinstance"] = type_str
    else:
        metadata.pop("labels")


def update_priority(yaml, item, dispatch_priority, priority_val):
    spec = yaml.get("spec")
    if dispatch_priority is not None:
        if priority_val:
            spec["priority"] = priority_val
        else:
            raise ValueError(
                "AW generation error: Priority value is None, while dispatch_priority is defined"
            )
        head = item.get("generictemplate").get("spec").get("headGroupSpec")
        worker = item.get("generictemplate").get("spec").get("workerGroupSpecs")[0]
        head["template"]["spec"]["priorityClassName"] = dispatch_priority
        worker["template"]["spec"]["priorityClassName"] = dispatch_priority
    else:
        spec.pop("priority")


def update_custompodresources(
    item,
    min_cpu,
    max_cpu,
    min_memory,
    max_memory,
    gpu,
    workers,
    head_cpus,
    head_memory,
    head_gpus,
):
    if "custompodresources" in item.keys():
        custompodresources = item.get("custompodresources")
        for i in range(len(custompodresources)):
            resource = custompodresources[i]
            if i == 0:
                # Leave head node resources as template default
                resource["requests"]["cpu"] = head_cpus
                resource["limits"]["cpu"] = head_cpus
                resource["requests"]["memory"] = head_memory
                resource["limits"]["memory"] = head_memory
                resource["requests"]["nvidia.com/gpu"] = head_gpus
                resource["limits"]["nvidia.com/gpu"] = head_gpus

            else:
                for k, v in resource.items():
                    if k == "replicas" and i == 1:
                        resource[k] = workers
                    if k == "requests" or k == "limits":
                        for spec, _ in v.items():
                            if spec == "cpu":
                                if k == "limits":
                                    resource[k][spec] = max_cpu
                                else:
                                    resource[k][spec] = min_cpu
                            if spec == "memory":
                                if k == "limits":
                                    resource[k][spec] = max_memory
                                else:
                                    resource[k][spec] = min_memory
                            if spec == "nvidia.com/gpu":
                                if i == 0:
                                    resource[k][spec] = 0
                                else:
                                    resource[k][spec] = gpu
    else:
        sys.exit("Error: malformed template")


def update_affinity(spec, appwrapper_name, instascale):
    if instascale:
        node_selector_terms = (
            spec.get("affinity")
            .get("nodeAffinity")
            .get("requiredDuringSchedulingIgnoredDuringExecution")
            .get("nodeSelectorTerms")
        )
        node_selector_terms[0]["matchExpressions"][0]["values"][0] = appwrapper_name
        node_selector_terms[0]["matchExpressions"][0]["key"] = appwrapper_name
    else:
        spec.pop("affinity")


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
    instascale,
    env,
    image_pull_secrets,
    head_cpus,
    head_memory,
    head_gpus,
):
    if "generictemplate" in item.keys():
        head = item.get("generictemplate").get("spec").get("headGroupSpec")
        head["rayStartParams"]["num-gpus"] = str(int(head_gpus))

        worker = item.get("generictemplate").get("spec").get("workerGroupSpecs")[0]
        # Head counts as first worker
        worker["replicas"] = workers
        worker["minReplicas"] = workers
        worker["maxReplicas"] = workers
        worker["groupName"] = "small-group-" + appwrapper_name
        worker["rayStartParams"]["num-gpus"] = str(int(gpu))

        for comp in [head, worker]:
            spec = comp.get("template").get("spec")
            update_affinity(spec, appwrapper_name, instascale)
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


def write_components(
    user_yaml: dict, output_file_name: str, namespace: str, local_queue: Optional[str]
):
    # Create the directory if it doesn't exist
    directory_path = os.path.dirname(output_file_name)
    if not os.path.exists(directory_path):
        os.makedirs(directory_path)

    components = user_yaml.get("spec", "resources")["resources"].get("GenericItems")
    open(output_file_name, "w").close()
    lq_name = local_queue or get_default_kueue_name(namespace)
    with open(output_file_name, "a") as outfile:
        for component in components:
            if "generictemplate" in component:
                if (
                    "workload.codeflare.dev/appwrapper"
                    in component["generictemplate"]["metadata"]["labels"]
                ):
                    del component["generictemplate"]["metadata"]["labels"][
                        "workload.codeflare.dev/appwrapper"
                    ]
                    labels = component["generictemplate"]["metadata"]["labels"]
                    labels.update({"kueue.x-k8s.io/queue-name": lq_name})
                outfile.write("---\n")
                yaml.dump(
                    component["generictemplate"], outfile, default_flow_style=False
                )
    print(f"Written to: {output_file_name}")


def load_components(
    user_yaml: dict, name: str, namespace: str, local_queue: Optional[str]
):
    component_list = []
    components = user_yaml.get("spec", "resources")["resources"].get("GenericItems")
    lq_name = local_queue or get_default_kueue_name(namespace)
    for component in components:
        if "generictemplate" in component:
            if (
                "workload.codeflare.dev/appwrapper"
                in component["generictemplate"]["metadata"]["labels"]
            ):
                del component["generictemplate"]["metadata"]["labels"][
                    "workload.codeflare.dev/appwrapper"
                ]
                labels = component["generictemplate"]["metadata"]["labels"]
                labels.update({"kueue.x-k8s.io/queue-name": lq_name})
            component_list.append(component["generictemplate"])

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
    instascale: bool,
    mcad: bool,
    instance_types: list,
    env,
    image_pull_secrets: list,
    dispatch_priority: str,
    priority_val: int,
    write_to_file: bool,
    verify_tls: bool,
    local_queue: Optional[str],
):
    user_yaml = read_template(template)
    appwrapper_name, cluster_name = gen_names(name)
    resources = user_yaml.get("spec", "resources")
    item = resources["resources"].get("GenericItems")[0]
    update_names(
        user_yaml,
        item,
        appwrapper_name,
        cluster_name,
        namespace,
    )
    update_labels(user_yaml, instascale, instance_types)
    update_priority(user_yaml, item, dispatch_priority, priority_val)
    update_custompodresources(
        item,
        min_cpu,
        max_cpu,
        min_memory,
        max_memory,
        gpu,
        workers,
        head_cpus,
        head_memory,
        head_gpus,
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
        instascale,
        env,
        image_pull_secrets,
        head_cpus,
        head_memory,
        head_gpus,
    )

    directory_path = os.path.expanduser("~/.codeflare/resources/")
    outfile = os.path.join(directory_path, appwrapper_name + ".yaml")

    if write_to_file:
        if mcad:
            write_user_appwrapper(user_yaml, outfile)
        else:
            write_components(user_yaml, outfile, namespace, local_queue)
        return outfile
    else:
        if mcad:
            user_yaml = load_appwrapper(user_yaml, name)
        else:
            user_yaml = load_components(user_yaml, name, namespace, local_queue)
        return user_yaml

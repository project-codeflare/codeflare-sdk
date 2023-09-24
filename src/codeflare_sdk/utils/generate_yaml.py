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

import yaml
import sys
import argparse
import uuid
from kubernetes import client, config
from .kube_api_helpers import _kube_api_error_handling
from ..cluster.auth import api_config_handler, config_check


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


def update_dashboard_route(route_item, cluster_name, namespace):
    metadata = route_item.get("generictemplate", {}).get("metadata")
    metadata["name"] = f"ray-dashboard-{cluster_name}"
    metadata["namespace"] = namespace
    metadata["labels"]["odh-ray-cluster-service"] = f"{cluster_name}-head-svc"
    spec = route_item.get("generictemplate", {}).get("spec")
    spec["to"]["name"] = f"{cluster_name}-head-svc"


# ToDo: refactor the update_x_route() functions
def update_rayclient_route(route_item, cluster_name, namespace):
    metadata = route_item.get("generictemplate", {}).get("metadata")
    metadata["name"] = f"rayclient-{cluster_name}"
    metadata["namespace"] = namespace
    metadata["labels"]["odh-ray-cluster-service"] = f"{cluster_name}-head-svc"
    spec = route_item.get("generictemplate", {}).get("spec")
    spec["to"]["name"] = f"{cluster_name}-head-svc"


def update_names(yaml, item, appwrapper_name, cluster_name, namespace):
    metadata = yaml.get("metadata")
    metadata["name"] = appwrapper_name
    metadata["namespace"] = namespace
    lower_meta = item.get("generictemplate", {}).get("metadata")
    lower_meta["labels"]["appwrapper.mcad.ibm.com"] = appwrapper_name
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
                resource["requests"]["memory"] = str(head_memory) + "G"
                resource["limits"]["memory"] = str(head_memory) + "G"
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
                                    resource[k][spec] = str(max_memory) + "G"
                                else:
                                    resource[k][spec] = str(min_memory) + "G"
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
            requests["memory"] = str(min_memory) + "G"
            requests["nvidia.com/gpu"] = gpu
        limits = resource.get("resources").get("limits")
        if limits is not None:
            limits["cpu"] = max_cpu
            limits["memory"] = str(max_memory) + "G"
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


def update_ca_secret(ca_secret_item, cluster_name, namespace):
    from . import generate_cert

    metadata = ca_secret_item.get("generictemplate", {}).get("metadata")
    metadata["name"] = f"ca-secret-{cluster_name}"
    metadata["namespace"] = namespace
    metadata["labels"]["odh-ray-cluster-service"] = f"{cluster_name}-head-svc"
    data = ca_secret_item.get("generictemplate", {}).get("data")
    data["ca.key"], data["ca.crt"] = generate_cert.generate_ca_cert(365)


def enable_local_interactive(resources, cluster_name, namespace):
    rayclient_route_item = resources["resources"].get("GenericItems")[2]
    ca_secret_item = resources["resources"].get("GenericItems")[3]
    item = resources["resources"].get("GenericItems")[0]
    update_rayclient_route(rayclient_route_item, cluster_name, namespace)
    update_ca_secret(ca_secret_item, cluster_name, namespace)
    # update_ca_secret_volumes
    item["generictemplate"]["spec"]["headGroupSpec"]["template"]["spec"]["volumes"][0][
        "secret"
    ]["secretName"] = f"ca-secret-{cluster_name}"
    item["generictemplate"]["spec"]["workerGroupSpecs"][0]["template"]["spec"][
        "volumes"
    ][0]["secret"]["secretName"] = f"ca-secret-{cluster_name}"
    # update_tls_env
    item["generictemplate"]["spec"]["headGroupSpec"]["template"]["spec"]["containers"][
        0
    ]["env"][1]["value"] = "1"
    item["generictemplate"]["spec"]["workerGroupSpecs"][0]["template"]["spec"][
        "containers"
    ][0]["env"][1]["value"] = "1"
    # update_init_container
    command = item["generictemplate"]["spec"]["headGroupSpec"]["template"]["spec"][
        "initContainers"
    ][0].get("command")[2]

    command = command.replace("deployment-name", cluster_name)
    try:
        config_check()
        api_client = client.CustomObjectsApi(api_config_handler())
        ingress = api_client.get_cluster_custom_object(
            "config.openshift.io", "v1", "ingresses", "cluster"
        )
    except Exception as e:  # pragma: no cover
        return _kube_api_error_handling(e)
    domain = ingress["spec"]["domain"]
    command = command.replace("server-name", domain)

    item["generictemplate"]["spec"]["headGroupSpec"]["template"]["spec"][
        "initContainers"
    ][0].get("command")[2] = command


def disable_raycluster_tls(resources):
    generic_template_spec = resources["GenericItems"][0]["generictemplate"]["spec"]

    if "volumes" in generic_template_spec["headGroupSpec"]["template"]["spec"]:
        del generic_template_spec["headGroupSpec"]["template"]["spec"]["volumes"]

    if (
        "volumeMounts"
        in generic_template_spec["headGroupSpec"]["template"]["spec"]["containers"][0]
    ):
        del generic_template_spec["headGroupSpec"]["template"]["spec"]["containers"][0][
            "volumeMounts"
        ]

    if "initContainers" in generic_template_spec["headGroupSpec"]["template"]["spec"]:
        del generic_template_spec["headGroupSpec"]["template"]["spec"]["initContainers"]

    if "volumes" in generic_template_spec["workerGroupSpecs"][0]["template"]["spec"]:
        del generic_template_spec["workerGroupSpecs"][0]["template"]["spec"]["volumes"]

    if (
        "volumeMounts"
        in generic_template_spec["workerGroupSpecs"][0]["template"]["spec"][
            "containers"
        ][0]
    ):
        del generic_template_spec["workerGroupSpecs"][0]["template"]["spec"][
            "containers"
        ][0]["volumeMounts"]

    for i in range(
        len(
            generic_template_spec["workerGroupSpecs"][0]["template"]["spec"][
                "initContainers"
            ]
        )
    ):
        if (
            generic_template_spec["workerGroupSpecs"][0]["template"]["spec"][
                "initContainers"
            ][i]["name"]
            == "create-cert"
        ):
            del generic_template_spec["workerGroupSpecs"][0]["template"]["spec"][
                "initContainers"
            ][i]

    updated_items = []
    for i in resources["GenericItems"][:]:
        if "rayclient-deployment-name" in i["generictemplate"]["metadata"]["name"]:
            continue
        if "ca-secret-deployment-name" in i["generictemplate"]["metadata"]["name"]:
            continue
        updated_items.append(i)

    resources["GenericItems"] = updated_items


def write_user_appwrapper(user_yaml, output_file_name):
    with open(output_file_name, "w") as outfile:
        yaml.dump(user_yaml, outfile, default_flow_style=False)
    print(f"Written to: {output_file_name}")


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
    instance_types: list,
    env,
    local_interactive: bool,
    image_pull_secrets: list,
    dispatch_priority: str,
    priority_val: int,
):
    user_yaml = read_template(template)
    appwrapper_name, cluster_name = gen_names(name)
    resources = user_yaml.get("spec", "resources")
    item = resources["resources"].get("GenericItems")[0]
    route_item = resources["resources"].get("GenericItems")[1]
    update_names(user_yaml, item, appwrapper_name, cluster_name, namespace)
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
    update_dashboard_route(route_item, cluster_name, namespace)
    if local_interactive:
        enable_local_interactive(resources, cluster_name, namespace)
    else:
        disable_raycluster_tls(resources["resources"])
    outfile = appwrapper_name + ".yaml"
    write_user_appwrapper(user_yaml, outfile)
    return outfile

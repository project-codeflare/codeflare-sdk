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


def update_custompodresources(
    item, min_cpu, max_cpu, min_memory, max_memory, gpu, workers
):
    if "custompodresources" in item.keys():
        custompodresources = item.get("custompodresources")
        for i in range(len(custompodresources)):
            if i == 0:
                # Leave head node resources as template default
                continue
            resource = custompodresources[i]
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
):
    if "generictemplate" in item.keys():
        head = item.get("generictemplate").get("spec").get("headGroupSpec")
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
            update_image(spec, image)
            update_env(spec, env)
            if comp == head:
                update_resources(spec, 2, 2, 8, 8, 0)
            else:
                update_resources(spec, min_cpu, max_cpu, min_memory, max_memory, gpu)


def write_user_appwrapper(user_yaml, output_file_name):
    with open(output_file_name, "w") as outfile:
        yaml.dump(user_yaml, outfile, default_flow_style=False)
    print(f"Written to: {output_file_name}")


def generate_appwrapper(
    name: str,
    namespace: str,
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
):
    user_yaml = read_template(template)
    appwrapper_name, cluster_name = gen_names(name)
    resources = user_yaml.get("spec", "resources")
    item = resources["resources"].get("GenericItems")[0]
    route_item = resources["resources"].get("GenericItems")[1]
    update_names(user_yaml, item, appwrapper_name, cluster_name, namespace)
    update_labels(user_yaml, instascale, instance_types)
    update_custompodresources(
        item, min_cpu, max_cpu, min_memory, max_memory, gpu, workers
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
    )
    update_dashboard_route(route_item, cluster_name, namespace)
    outfile = appwrapper_name + ".yaml"
    write_user_appwrapper(user_yaml, outfile)
    return outfile


def main():
    parser = argparse.ArgumentParser(description="Generate user AppWrapper")
    parser.add_argument(
        "--name",
        required=False,
        default="",
        help="User selected name for AppWrapper and Ray Cluster (auto-generated if not provided)",
    )
    parser.add_argument(
        "--min-cpu",
        type=int,
        required=True,
        help="min number of CPU(s) in a worker required for running job",
    )
    parser.add_argument(
        "--max-cpu",
        type=int,
        required=True,
        help="max number of CPU(s) in a worker required for running job",
    )
    parser.add_argument(
        "--min-memory",
        type=int,
        required=True,
        help="min RAM required in a worker for running job, in GB",
    )
    parser.add_argument(
        "--max-memory",
        type=int,
        required=True,
        help="max RAM required in a worker for running job, in GB",
    )
    parser.add_argument(
        "--gpu",
        type=int,
        required=True,
        help="GPU(s) required in a worker for running job",
    )
    parser.add_argument(
        "--workers",
        type=int,
        required=True,
        help="How many workers are required in the cluster",
    )
    parser.add_argument(
        "--template", required=True, help="Template AppWrapper yaml file"
    )
    parser.add_argument(
        "--image",
        required=False,
        default="rayproject/ray:latest",
        help="Ray image to be used (defaults to rayproject/ray:latest)",
    )
    parser.add_argument(
        "--instascale",
        default=False,
        required=False,
        action="store_true",
        help="Indicates that instascale is installed on the cluster",
    )
    parser.add_argument(
        "--instance-types",
        type=str,
        nargs="+",
        default=[],
        required=False,
        help="Head,worker instance types (space separated)",
    )
    parser.add_argument(
        "--namespace",
        required=False,
        default="default",
        help="Set the kubernetes namespace you want to deploy your cluster to. Default. If left blank, uses the 'default' namespace",
    )

    args = parser.parse_args()
    name = args.name
    min_cpu = args.min_cpu
    max_cpu = args.max_cpu
    min_memory = args.min_memory
    max_memory = args.max_memory
    gpu = args.gpu
    workers = args.workers
    template = args.template
    image = args.image
    instascale = args.instascale
    instance_types = args.instance_types
    namespace = args.namespace
    env = {}

    outfile = generate_appwrapper(
        name,
        namespace,
        min_cpu,
        max_cpu,
        min_memory,
        max_memory,
        gpu,
        workers,
        template,
        image,
        instascale,
        instance_types,
        env,
    )
    return outfile


if __name__ == "__main__":
    main()

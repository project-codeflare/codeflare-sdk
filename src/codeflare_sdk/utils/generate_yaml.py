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


def gen_dashboard_ingress_name(cluster_name):
    return f"ray-dashboard-{cluster_name}"


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


def update_dashboard_route(route_item, cluster_name, namespace):
    metadata = route_item.get("template", {}).get("metadata")
    metadata["name"] = gen_dashboard_ingress_name(cluster_name)
    metadata["namespace"] = namespace
    metadata["labels"]["odh-ray-cluster-service"] = f"{cluster_name}-head-svc"
    spec = route_item.get("template", {}).get("spec")
    spec["to"]["name"] = f"{cluster_name}-head-svc"


# ToDo: refactor the update_x_route() functions
def update_rayclient_route(route_item, cluster_name, namespace):
    metadata = route_item.get("template", {}).get("metadata")
    metadata["name"] = f"rayclient-{cluster_name}"
    metadata["namespace"] = namespace
    metadata["labels"]["odh-ray-cluster-service"] = f"{cluster_name}-head-svc"
    spec = route_item.get("template", {}).get("spec")
    spec["to"]["name"] = f"{cluster_name}-head-svc"


def update_dashboard_exposure(
    ingress_item, route_item, cluster_name, namespace, ingress_options, ingress_domain
):
    if is_openshift_cluster():
        update_dashboard_route(route_item, cluster_name, namespace)
    else:
        update_dashboard_ingress(
            ingress_item, cluster_name, namespace, ingress_options, ingress_domain
        )


def update_rayclient_exposure(
    client_route_item, client_ingress_item, cluster_name, namespace, ingress_domain
):
    if is_openshift_cluster():
        update_rayclient_route(client_route_item, cluster_name, namespace)
    else:
        update_rayclient_ingress(
            client_ingress_item, cluster_name, namespace, ingress_domain
        )


def update_dashboard_ingress(
    ingress_item, cluster_name, namespace, ingress_options, ingress_domain
):  # pragma: no cover
    metadata = ingress_item.get("template", {}).get("metadata")
    spec = ingress_item.get("template", {}).get("spec")
    if ingress_options != {}:
        for index, ingress_option in enumerate(ingress_options["ingresses"]):
            if "ingressName" not in ingress_option.keys():
                raise ValueError(
                    f"Error: 'ingressName' is missing or empty for ingress item at index {index}"
                )
            if "port" not in ingress_option.keys():
                raise ValueError(
                    f"Error: 'port' is missing or empty for ingress item at index {index}"
                )
            elif not isinstance(ingress_option["port"], int):
                raise ValueError(
                    f"Error: 'port' is not of type int for ingress item at index {index}"
                )
            if ingress_option is not None:
                metadata["name"] = ingress_option["ingressName"]
                metadata["namespace"] = namespace
                metadata["labels"]["ingress-owner"] = cluster_name
                metadata["labels"]["ingress-options"] = "true"
                if (
                    "annotations" not in ingress_option.keys()
                    or ingress_option["annotations"] is None
                ):
                    del metadata["annotations"]
                else:
                    metadata["annotations"] = ingress_option["annotations"]
                if (
                    "path" not in ingress_option.keys()
                    or ingress_option["path"] is None
                ):
                    del spec["rules"][0]["http"]["paths"][0]["path"]
                else:
                    spec["rules"][0]["http"]["paths"][0]["path"] = ingress_option[
                        "path"
                    ]
                if (
                    "pathType" not in ingress_option.keys()
                    or ingress_option["pathType"] is None
                ):
                    spec["rules"][0]["http"]["paths"][0][
                        "pathType"
                    ] = "ImplementationSpecific"
                if (
                    "host" not in ingress_option.keys()
                    or ingress_option["host"] is None
                ):
                    del spec["rules"][0]["host"]
                else:
                    spec["rules"][0]["host"] = ingress_option["host"]
                if (
                    "ingressClassName" not in ingress_option.keys()
                    or ingress_option["ingressClassName"] is None
                ):
                    del spec["ingressClassName"]
                else:
                    spec["ingressClassName"] = ingress_option["ingressClassName"]

                spec["rules"][0]["http"]["paths"][0]["backend"]["service"][
                    "name"
                ] = f"{cluster_name}-head-svc"
    else:
        spec["ingressClassName"] = "nginx"
        metadata["name"] = gen_dashboard_ingress_name(cluster_name)
        metadata["labels"]["ingress-owner"] = cluster_name
        metadata["namespace"] = namespace
        spec["rules"][0]["http"]["paths"][0]["backend"]["service"][
            "name"
        ] = f"{cluster_name}-head-svc"
        if ingress_domain is None:
            raise ValueError(
                "ingress_domain is invalid. Please specify an ingress domain"
            )
        else:
            domain = ingress_domain
        del metadata["annotations"]
        spec["rules"][0]["host"] = f"ray-dashboard-{cluster_name}-{namespace}.{domain}"


def update_rayclient_ingress(
    ingress_item, cluster_name, namespace, ingress_domain
):  # pragma: no cover
    metadata = ingress_item.get("template", {}).get("metadata")
    spec = ingress_item.get("template", {}).get("spec")
    metadata["name"] = f"rayclient-{cluster_name}"
    metadata["namespace"] = namespace
    metadata["labels"]["odh-ray-cluster-service"] = f"{cluster_name}-head-svc"

    spec["rules"][0]["http"]["paths"][0]["backend"]["service"][
        "name"
    ] = f"{cluster_name}-head-svc"

    if ingress_domain is not None:
        ingressClassName = "nginx"
        annotations = {
            "nginx.ingress.kubernetes.io/rewrite-target": "/",
            "nginx.ingress.kubernetes.io/ssl-redirect": "true",
            "nginx.ingress.kubernetes.io/ssl-passthrough": "true",
        }
    else:
        raise ValueError("ingress_domain is invalid. Please specify a domain")

    metadata["annotations"] = annotations
    spec["ingressClassName"] = ingressClassName
    spec["rules"][0]["host"] = f"rayclient-{cluster_name}-{namespace}.{ingress_domain}"


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
    env,
    image_pull_secrets,
    head_cpus,
    head_memory,
    head_gpus,
):
    if "template" in item.keys():
        head = item.get("template").get("spec").get("headGroupSpec")
        head["rayStartParams"]["num-gpus"] = str(int(head_gpus))

        item.get("podSets")[1]["replicas"] = workers
        worker = item.get("template").get("spec").get("workerGroupSpecs")[0]
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


def update_ca_secret(ca_secret_item, cluster_name, namespace):
    from . import generate_cert

    metadata = ca_secret_item.get("template", {}).get("metadata")
    metadata["name"] = f"ca-secret-{cluster_name}"
    metadata["namespace"] = namespace
    metadata["labels"]["odh-ray-cluster-service"] = f"{cluster_name}-head-svc"
    data = ca_secret_item.get("template", {}).get("data")
    data["ca.key"], data["ca.crt"] = generate_cert.generate_ca_cert(365)


def enable_local_interactive(components, cluster_name, namespace, ingress_domain):
    rayclient_ingress_item = components[3]
    rayclient_route_item = components[4]
    ca_secret_item = components[5]
    item = components[0]
    update_ca_secret(ca_secret_item, cluster_name, namespace)
    # update_ca_secret_volumes
    item["template"]["spec"]["headGroupSpec"]["template"]["spec"]["volumes"][0][
        "secret"
    ]["secretName"] = f"ca-secret-{cluster_name}"
    item["template"]["spec"]["workerGroupSpecs"][0]["template"]["spec"]["volumes"][0][
        "secret"
    ]["secretName"] = f"ca-secret-{cluster_name}"
    # update_tls_env
    item["template"]["spec"]["headGroupSpec"]["template"]["spec"]["containers"][0][
        "env"
    ][1]["value"] = "1"
    item["template"]["spec"]["workerGroupSpecs"][0]["template"]["spec"]["containers"][
        0
    ]["env"][1]["value"] = "1"
    # update_init_container
    command = item["template"]["spec"]["headGroupSpec"]["template"]["spec"][
        "initContainers"
    ][0].get("command")[2]

    command = command.replace("deployment-name", cluster_name)

    if ingress_domain is None:
        raise ValueError(
            "ingress_domain is invalid. For creating the client route/ingress please specify an ingress domain"
        )
    else:
        domain = ingress_domain

    command = command.replace("server-name", domain)
    update_rayclient_exposure(
        rayclient_route_item,
        rayclient_ingress_item,
        cluster_name,
        namespace,
        ingress_domain,
    )
    item["generictemplate"]["metadata"]["annotations"][
        "sdk.codeflare.dev/local_interactive"
    ] = "True"
    item["generictemplate"]["metadata"]["annotations"][
        "sdk.codeflare.dev/ingress_domain"
    ] = ingress_domain

    item["template"]["spec"]["headGroupSpec"]["template"]["spec"]["initContainers"][
        0
    ].get("command")[2] = command


def apply_ingress_domain_annotation(resources, ingress_domain):
    item = resources["resources"].get("GenericItems")[0]
    item["generictemplate"]["metadata"]["annotations"][
        "sdk.codeflare.dev/ingress_domain"
    ] = ingress_domain


def del_from_list_by_name(l: list, target: typing.List[str]) -> list:
    return [x for x in l if x["name"] not in target]


def disable_raycluster_tls(components):
    generic_template_spec = components[0]["template"]["spec"]

    headGroupTemplateSpec = generic_template_spec["headGroupSpec"]["template"]["spec"]
    headGroupTemplateSpec["volumes"] = del_from_list_by_name(
        headGroupTemplateSpec.get("volumes", []),
        ["ca-vol", "server-cert"],
    )

    c: dict
    for c in generic_template_spec["headGroupSpec"]["template"]["spec"]["containers"]:
        c["volumeMounts"] = del_from_list_by_name(
            c.get("volumeMounts", []), ["ca-vol", "server-cert"]
        )

    if "initContainers" in generic_template_spec["headGroupSpec"]["template"]["spec"]:
        del generic_template_spec["headGroupSpec"]["template"]["spec"]["initContainers"]

    for workerGroup in generic_template_spec.get("workerGroupSpecs", []):
        workerGroupSpec = workerGroup["template"]["spec"]
        workerGroupSpec["volumes"] = del_from_list_by_name(
            workerGroupSpec.get("volumes", []),
            ["ca-vol", "server-cert"],
        )
        for c in workerGroup["template"]["spec"].get("containers", []):
            c["volumeMounts"] = del_from_list_by_name(
                c.get("volumeMounts", []), ["ca-vol", "server-cert"]
            )

    del generic_template_spec["workerGroupSpecs"][0]["template"]["spec"][
        "initContainers"
    ]

    updated_items = []
    for i in components[:]:
        if "rayclient-deployment-ingress" in i["template"]["metadata"]["name"]:
            continue
        if "rayclient-deployment-route" in i["template"]["metadata"]["name"]:
            continue
        if "ca-secret-deployment-name" in i["template"]["metadata"]["name"]:
            continue
        updated_items.append(i)

    components.clear()
    components.extend(updated_items)


def delete_route_or_ingress(components):
    if is_openshift_cluster():
        client_to_remove_name = "rayclient-deployment-ingress"
        dashboard_to_remove_name = "ray-dashboard-deployment-ingress"
    else:
        client_to_remove_name = "rayclient-deployment-route"
        dashboard_to_remove_name = "ray-dashboard-deployment-route"

    updated_items = []
    for i in components[:]:
        if dashboard_to_remove_name in i["template"]["metadata"]["name"]:
            continue
        elif client_to_remove_name in i["template"]["metadata"]["name"]:
            continue

        updated_items.append(i)

    components.clear()
    components.extend(updated_items)


def write_user_appwrapper(user_yaml, output_file_name):
    # Create the directory if it doesn't exist
    directory_path = os.path.dirname(output_file_name)
    if not os.path.exists(directory_path):
        os.makedirs(directory_path)

    with open(output_file_name, "w") as outfile:
        yaml.dump(user_yaml, outfile, default_flow_style=False)

    print(f"Written to: {output_file_name}")


def enable_openshift_oauth(user_yaml, cluster_name, namespace):
    config_check()
    k8_client = api_config_handler() or client.ApiClient()
    tls_mount_location = "/etc/tls/private"
    oauth_port = 8443
    oauth_sa_name = f"{cluster_name}-oauth-proxy"
    tls_secret_name = f"{cluster_name}-proxy-tls-secret"
    tls_volume_name = "proxy-tls-secret"
    port_name = "oauth-proxy"
    oauth_sidecar = _create_oauth_sidecar_object(
        namespace,
        tls_mount_location,
        oauth_port,
        oauth_sa_name,
        tls_volume_name,
        port_name,
    )
    tls_secret_volume = client.V1Volume(
        name=tls_volume_name,
        secret=client.V1SecretVolumeSource(secret_name=tls_secret_name),
    )
    # allows for setting value of Cluster object when initializing object from an existing AppWrapper on cluster
    user_yaml["metadata"]["annotations"] = user_yaml["metadata"].get("annotations", {})
    user_yaml["metadata"]["annotations"][
        "codeflare-sdk-use-oauth"
    ] = "true"  # if the user gets an
    ray_headgroup_pod = user_yaml["spec"]["components"][0]["template"]["spec"][
        "headGroupSpec"
    ]["template"]["spec"]
    user_yaml["spec"]["components"].pop(1)
    ray_headgroup_pod["serviceAccount"] = oauth_sa_name
    ray_headgroup_pod["volumes"] = ray_headgroup_pod.get("volumes", [])

    # we use a generic api client here so that the serialization function doesn't need to be mocked for unit tests
    ray_headgroup_pod["volumes"].append(
        client.ApiClient().sanitize_for_serialization(tls_secret_volume)
    )
    ray_headgroup_pod["containers"].append(
        client.ApiClient().sanitize_for_serialization(oauth_sidecar)
    )


def _create_oauth_sidecar_object(
    namespace: str,
    tls_mount_location: str,
    oauth_port: int,
    oauth_sa_name: str,
    tls_volume_name: str,
    port_name: str,
) -> client.V1Container:
    return client.V1Container(
        args=[
            f"--https-address=:{oauth_port}",
            "--provider=openshift",
            f"--openshift-service-account={oauth_sa_name}",
            "--upstream=http://localhost:8265",
            f"--tls-cert={tls_mount_location}/tls.crt",
            f"--tls-key={tls_mount_location}/tls.key",
            f"--cookie-secret={b64encode(urandom(64)).decode('utf-8')}",  # create random string for encrypting cookie
            f'--openshift-delegate-urls={{"/":{{"resource":"pods","namespace":"{namespace}","verb":"get"}}}}',
        ],
        image="registry.redhat.io/openshift4/ose-oauth-proxy@sha256:1ea6a01bf3e63cdcf125c6064cbd4a4a270deaf0f157b3eabb78f60556840366",
        name="oauth-proxy",
        ports=[client.V1ContainerPort(container_port=oauth_port, name=port_name)],
        resources=client.V1ResourceRequirements(limits=None, requests=None),
        volume_mounts=[
            client.V1VolumeMount(
                mount_path=tls_mount_location, name=tls_volume_name, read_only=True
            )
        ],
    )


def write_components(user_yaml: dict, output_file_name: str):
    # Create the directory if it doesn't exist
    directory_path = os.path.dirname(output_file_name)
    if not os.path.exists(directory_path):
        os.makedirs(directory_path)

    components = user_yaml.get("spec").get("components")
    open(output_file_name, "w").close()
    with open(output_file_name, "a") as outfile:
        for component in components:
            if "template" in component:
                outfile.write("---\n")
                yaml.dump(component["template"], outfile, default_flow_style=False)
    print(f"Written to: {output_file_name}")


def load_components(user_yaml: dict, name: str):
    component_list = []
    components = user_yaml.get("spec").get("components")
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
    mcad: bool,
    env,
    local_interactive: bool,
    image_pull_secrets: list,
    openshift_oauth: bool,
    ingress_domain: str,
    ingress_options: dict,
    write_to_file: bool,
):
    user_yaml = read_template(template)
    appwrapper_name, cluster_name = gen_names(name)
    components = user_yaml.get("spec").get("components")
    item = components[0]
    ingress_item = components[1]
    route_item = components[2]
    update_names(user_yaml, item, appwrapper_name, cluster_name, namespace)
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
    update_dashboard_exposure(
        ingress_item,
        route_item,
        cluster_name,
        namespace,
        ingress_options,
        ingress_domain,
    )
    if ingress_domain is not None:
        apply_ingress_domain_annotation(resources, ingress_domain)

    if local_interactive:
        enable_local_interactive(components, cluster_name, namespace, ingress_domain)
    else:
        disable_raycluster_tls(components)

    delete_route_or_ingress(components)

    if openshift_oauth:
        enable_openshift_oauth(user_yaml, cluster_name, namespace)

    directory_path = os.path.expanduser("~/.codeflare/appwrapper/")
    outfile = os.path.join(directory_path, appwrapper_name + ".yaml")

    if write_to_file:
        if mcad:
            write_user_appwrapper(user_yaml, outfile)
        else:
            write_components(user_yaml, outfile)
        return outfile
    else:
        if mcad:
            user_yaml = load_appwrapper(user_yaml, name)
        else:
            user_yaml = load_components(user_yaml, name)
        return user_yaml

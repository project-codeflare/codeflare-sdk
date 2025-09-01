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

import string
import sys
from codeflare_sdk.common.utils import constants
from codeflare_sdk.common.utils.utils import get_ray_image_for_python_version
from codeflare_sdk.ray.cluster.cluster import (
    Cluster,
    ClusterConfiguration,
)
import os
import yaml
from pathlib import Path
from kubernetes import client
from kubernetes.client import V1Toleration
from unittest.mock import patch

parent = Path(__file__).resolve().parents[4]  # project directory
aw_dir = os.path.expanduser("~/.codeflare/resources/")


def create_cluster_config(num_workers=2, write_to_file=False):
    config = ClusterConfiguration(
        name="unit-test-cluster",
        namespace="ns",
        num_workers=num_workers,
        worker_cpu_requests=3,
        worker_cpu_limits=4,
        worker_memory_requests=5,
        worker_memory_limits=6,
        appwrapper=True,
        write_to_file=write_to_file,
    )
    return config


def create_cluster(mocker, num_workers=2, write_to_file=False):
    cluster = Cluster(create_cluster_config(num_workers, write_to_file))
    return cluster


def patch_cluster_with_dynamic_client(mocker, cluster, dynamic_client=None):
    mocker.patch.object(cluster, "get_dynamic_client", return_value=dynamic_client)
    mocker.patch.object(cluster, "down", return_value=None)
    mocker.patch.object(cluster, "config_check", return_value=None)
    # mocker.patch.object(cluster, "_throw_for_no_raycluster", return_value=None)


def create_cluster_wrong_type():
    config = ClusterConfiguration(
        name="unit-test-cluster",
        namespace="ns",
        num_workers=True,
        worker_cpu_requests=[],
        worker_cpu_limits=4,
        worker_memory_requests=5,
        worker_memory_limits=6,
        worker_extended_resource_requests={"nvidia.com/gpu": 7},
        appwrapper=True,
        image_pull_secrets=["unit-test-pull-secret"],
        image=constants.CUDA_PY312_RUNTIME_IMAGE,
        write_to_file=True,
        labels={1: 1},
    )
    return config


def get_package_and_version(package_name, requirements_file_path):
    with open(requirements_file_path, "r") as file:
        for line in file:
            if line.strip().startswith(f"{package_name}=="):
                return line.strip()
    return None


def get_local_queue(group, version, namespace, plural):
    assert group == "kueue.x-k8s.io"
    assert version == "v1beta1"
    assert namespace == "ns"
    assert plural == "localqueues"
    local_queues = {
        "apiVersion": "kueue.x-k8s.io/v1beta1",
        "items": [
            {
                "apiVersion": "kueue.x-k8s.io/v1beta1",
                "kind": "LocalQueue",
                "metadata": {
                    "annotations": {"kueue.x-k8s.io/default-queue": "true"},
                    "name": "local-queue-default",
                    "namespace": "ns",
                },
                "spec": {"clusterQueue": "cluster-queue"},
            },
            {
                "apiVersion": "kueue.x-k8s.io/v1beta1",
                "kind": "LocalQueue",
                "metadata": {
                    "name": "team-a-queue",
                    "namespace": "ns",
                },
                "spec": {"clusterQueue": "team-a-queue"},
            },
        ],
        "kind": "LocalQueueList",
        "metadata": {"continue": "", "resourceVersion": "2266811"},
    }
    return local_queues


def arg_check_aw_apply_effect(group, version, namespace, plural, body, *args):
    assert group == "workload.codeflare.dev"
    assert version == "v1beta2"
    assert namespace == "ns"
    assert plural == "appwrappers"
    with open(f"{aw_dir}test.yaml") as f:
        aw = yaml.load(f, Loader=yaml.FullLoader)
    assert body == aw
    assert args == tuple()


def arg_check_aw_del_effect(group, version, namespace, plural, name, *args):
    assert group == "workload.codeflare.dev"
    assert version == "v1beta2"
    assert namespace == "ns"
    assert plural == "appwrappers"
    assert name == "test"
    assert args == tuple()


def get_cluster_object(file_a, file_b):
    with open(file_a) as f:
        cluster_a = yaml.load(f, Loader=yaml.FullLoader)
    with open(file_b) as f:
        cluster_b = yaml.load(f, Loader=yaml.FullLoader)

    return cluster_a, cluster_b


def get_ray_obj(group, version, namespace, plural):
    # To be used for mocking list_namespaced_custom_object for Ray Clusters
    rc_a = apply_template(
        f"{parent}/tests/test_cluster_yamls/support_clusters/test-rc-a.yaml",
        get_template_variables(),
    )
    rc_b = apply_template(
        f"{parent}/tests/test_cluster_yamls/support_clusters/test-rc-b.yaml",
        get_template_variables(),
    )

    rc_list = {"items": [rc_a, rc_b]}
    return rc_list


def get_ray_obj_with_status(group, version, namespace, plural):
    # To be used for mocking list_namespaced_custom_object for Ray Clusters with statuses
    rc_a = apply_template(
        f"{parent}/tests/test_cluster_yamls/support_clusters/test-rc-a.yaml",
        get_template_variables(),
    )
    rc_b = apply_template(
        f"{parent}/tests/test_cluster_yamls/support_clusters/test-rc-b.yaml",
        get_template_variables(),
    )

    rc_a.update(
        {
            "status": {
                "desiredWorkerReplicas": 1,
                "endpoints": {
                    "client": "10001",
                    "dashboard": "8265",
                    "gcs": "6379",
                    "metrics": "8080",
                },
                "head": {"serviceIP": "172.30.179.88"},
                "lastUpdateTime": "2024-03-05T09:55:37Z",
                "maxWorkerReplicas": 1,
                "minWorkerReplicas": 1,
                "observedGeneration": 1,
                "state": "ready",
            },
        }
    )
    rc_b.update(
        {
            "status": {
                "availableWorkerReplicas": 2,
                "desiredWorkerReplicas": 1,
                "endpoints": {
                    "client": "10001",
                    "dashboard": "8265",
                    "gcs": "6379",
                },
                "lastUpdateTime": "2023-02-22T16:26:16Z",
                "maxWorkerReplicas": 1,
                "minWorkerReplicas": 1,
                "state": "suspended",
            }
        }
    )

    rc_list = {"items": [rc_a, rc_b]}
    return rc_list


def get_aw_obj(group, version, namespace, plural):
    # To be used for mocking list_namespaced_custom_object for AppWrappers
    aw_a = apply_template(
        f"{parent}/tests/test_cluster_yamls/support_clusters/test-aw-a.yaml",
        get_template_variables(),
    )
    aw_b = apply_template(
        f"{parent}/tests/test_cluster_yamls/support_clusters/test-aw-b.yaml",
        get_template_variables(),
    )

    aw_list = {"items": [aw_a, aw_b]}
    return aw_list


def get_aw_obj_with_status(group, version, namespace, plural):
    # To be used for mocking list_namespaced_custom_object for AppWrappers with statuses
    aw_a = apply_template(
        f"{parent}/tests/test_cluster_yamls/support_clusters/test-aw-a.yaml",
        get_template_variables(),
    )
    aw_b = apply_template(
        f"{parent}/tests/test_cluster_yamls/support_clusters/test-aw-b.yaml",
        get_template_variables(),
    )

    aw_a.update(
        {
            "status": {
                "phase": "Running",
            },
        }
    )
    aw_b.update(
        {
            "status": {
                "phase": "Suspended",
            },
        }
    )

    aw_list = {"items": [aw_a, aw_b]}
    return aw_list


def get_named_aw(group, version, namespace, plural, name):
    aws = get_aw_obj("workload.codeflare.dev", "v1beta2", "ns", "appwrappers")
    return aws["items"][0]


def arg_check_del_effect(group, version, namespace, plural, name, *args):
    assert namespace == "ns"
    assert args == tuple()
    if plural == "appwrappers":
        assert group == "workload.codeflare.dev"
        assert version == "v1beta2"
        assert name == "unit-test-cluster"
    elif plural == "rayclusters":
        assert group == "ray.io"
        assert version == "v1"
        assert name == "unit-test-cluster-ray"
    elif plural == "ingresses":
        assert group == "networking.k8s.io"
        assert version == "v1"
        assert name == "ray-dashboard-unit-test-cluster-ray"


def apply_template(yaml_file_path, variables):
    with open(yaml_file_path, "r") as file:
        yaml_content = file.read()

    # Create a Template instance and substitute the variables
    template = string.Template(yaml_content)
    filled_yaml = template.substitute(variables)

    # Now load the filled YAML into a Python object
    return yaml.load(filled_yaml, Loader=yaml.FullLoader)


def get_expected_image():
    # Use centralized image selection logic (fallback to 3.12 for test consistency)
    return get_ray_image_for_python_version(warn_on_unsupported=True)


def get_template_variables():
    return {
        "image": get_expected_image(),
    }


def arg_check_apply_effect(group, version, namespace, plural, body, *args):
    assert namespace == "ns"
    assert args == tuple()
    if plural == "appwrappers":
        assert group == "workload.codeflare.dev"
        assert version == "v1beta2"
    elif plural == "rayclusters":
        assert group == "ray.io"
        assert version == "v1"
    elif plural == "ingresses":
        assert group == "networking.k8s.io"
        assert version == "v1"
    elif plural == "routes":
        assert group == "route.openshift.io"
        assert version == "v1"
    else:
        assert 1 == 0


def get_obj_none(group, version, namespace, plural):
    return {"items": []}


def route_list_retrieval(group, version, namespace, plural):
    assert group == "route.openshift.io"
    assert version == "v1"
    assert namespace == "ns"
    assert plural == "routes"
    return {
        "kind": "RouteList",
        "apiVersion": "route.openshift.io/v1",
        "metadata": {"resourceVersion": "6072398"},
        "items": [
            {
                "metadata": {
                    "name": "ray-dashboard-quicktest",
                    "namespace": "ns",
                },
                "spec": {
                    "host": "ray-dashboard-quicktest-opendatahub.apps.cluster.awsroute.org",
                    "to": {
                        "kind": "Service",
                        "name": "quicktest-head-svc",
                        "weight": 100,
                    },
                    "port": {"targetPort": "dashboard"},
                    "tls": {"termination": "edge"},
                },
            },
            {
                "metadata": {
                    "name": "rayclient-quicktest",
                    "namespace": "ns",
                },
                "spec": {
                    "host": "rayclient-quicktest-opendatahub.apps.cluster.awsroute.org",
                    "to": {
                        "kind": "Service",
                        "name": "quicktest-head-svc",
                        "weight": 100,
                    },
                    "port": {"targetPort": "client"},
                    "tls": {"termination": "passthrough"},
                },
            },
        ],
    }


def ingress_retrieval(
    cluster_name="unit-test-cluster", client_ing: bool = False, annotations: dict = None
):
    dashboard_ingress = mocked_ingress(8265, cluster_name, annotations)
    if client_ing:
        client_ingress = mocked_ingress(
            10001, cluster_name=cluster_name, annotations=annotations
        )
        mock_ingress_list = client.V1IngressList(
            items=[client_ingress, dashboard_ingress]
        )
    else:
        mock_ingress_list = client.V1IngressList(items=[dashboard_ingress])

    return mock_ingress_list


def mocked_ingress(port, cluster_name="unit-test-cluster", annotations: dict = None):
    labels = {"ingress-owner": cluster_name}
    if port == 10001:
        name = f"rayclient-{cluster_name}"
    else:
        name = f"ray-dashboard-{cluster_name}"
    mock_ingress = client.V1Ingress(
        metadata=client.V1ObjectMeta(
            name=name,
            annotations=annotations,
            labels=labels,
            owner_references=[
                client.V1OwnerReference(
                    api_version="v1", kind="Ingress", name=cluster_name, uid="unique-id"
                )
            ],
        ),
        spec=client.V1IngressSpec(
            rules=[
                client.V1IngressRule(
                    host=f"{name}-ns.apps.cluster.awsroute.org",
                    http=client.V1HTTPIngressRuleValue(
                        paths=[
                            client.V1HTTPIngressPath(
                                path_type="Prefix",
                                path="/",
                                backend=client.V1IngressBackend(
                                    service=client.V1IngressServiceBackend(
                                        name="head-svc-test",
                                        port=client.V1ServiceBackendPort(number=port),
                                    )
                                ),
                            )
                        ]
                    ),
                )
            ],
        ),
    )
    return mock_ingress


# Global dictionary to maintain state in the mock
cluster_state = {}


# The mock side_effect function for server_side_apply
def mock_server_side_apply(resource, body=None, name=None, namespace=None, **kwargs):
    # Simulate the behavior of server_side_apply:
    # Update a mock state that represents the cluster's current configuration.
    # Stores the state in a global dictionary for simplicity.

    global cluster_state

    if not resource or not body or not name or not namespace:
        raise ValueError("Missing required parameters for server_side_apply")

    # Extract worker count from the body if it exists
    try:
        worker_count = (
            body["spec"]["workerGroupSpecs"][0]["replicas"]
            if "spec" in body and "workerGroupSpecs" in body["spec"]
            else None
        )
    except KeyError:
        worker_count = None

    # Apply changes to the cluster_state mock
    cluster_state[name] = {
        "namespace": namespace,
        "worker_count": worker_count,
        "body": body,
    }

    # Return a response that mimics the behavior of a successful apply
    return {
        "status": "success",
        "applied": True,
        "name": name,
        "namespace": namespace,
        "worker_count": worker_count,
    }


@patch.dict("os.environ", {"NB_PREFIX": "test-prefix"})
def create_cluster_all_config_params(mocker, cluster_name, is_appwrapper) -> Cluster:
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        return_value=get_local_queue("kueue.x-k8s.io", "v1beta1", "ns", "localqueues"),
    )
    volumes, volume_mounts = get_example_extended_storage_opts()

    config = ClusterConfiguration(
        name=cluster_name,
        namespace="ns",
        head_cpu_requests=4,
        head_cpu_limits=8,
        head_memory_requests=12,
        head_memory_limits=16,
        head_extended_resource_requests={"nvidia.com/gpu": 1, "intel.com/gpu": 2},
        head_tolerations=[
            V1Toleration(
                key="key1", operator="Equal", value="value1", effect="NoSchedule"
            )
        ],
        worker_cpu_requests=4,
        worker_cpu_limits=8,
        worker_tolerations=[
            V1Toleration(
                key="key2", operator="Equal", value="value2", effect="NoSchedule"
            )
        ],
        num_workers=10,
        worker_memory_requests=12,
        worker_memory_limits=16,
        appwrapper=is_appwrapper,
        envs={"key1": "value1", "key2": "value2"},
        image="example/ray:tag",
        image_pull_secrets=["secret1", "secret2"],
        write_to_file=True,
        verify_tls=True,
        labels={"key1": "value1", "key2": "value2"},
        worker_extended_resource_requests={"nvidia.com/gpu": 1},
        extended_resource_mapping={"example.com/gpu": "GPU", "intel.com/gpu": "TPU"},
        overwrite_default_resource_mapping=True,
        local_queue="local-queue-default",
        annotations={
            "key1": "value1",
            "key2": "value2",
        },
        volumes=volumes,
        volume_mounts=volume_mounts,
    )
    return Cluster(config)


def get_example_extended_storage_opts():
    from kubernetes.client import (
        V1Volume,
        V1VolumeMount,
        V1EmptyDirVolumeSource,
        V1ConfigMapVolumeSource,
        V1KeyToPath,
        V1SecretVolumeSource,
    )

    volume_mounts = [
        V1VolumeMount(mount_path="/home/ray/test1", name="test"),
        V1VolumeMount(
            mount_path="/home/ray/test2",
            name="test2",
        ),
        V1VolumeMount(
            mount_path="/home/ray/test2",
            name="test3",
        ),
    ]

    volumes = [
        V1Volume(
            name="test",
            empty_dir=V1EmptyDirVolumeSource(size_limit="500Gi"),
        ),
        V1Volume(
            name="test2",
            config_map=V1ConfigMapVolumeSource(
                name="config-map-test",
                items=[V1KeyToPath(key="test", path="/home/ray/test2/data.txt")],
            ),
        ),
        V1Volume(name="test3", secret=V1SecretVolumeSource(secret_name="test-secret")),
    ]
    return volumes, volume_mounts

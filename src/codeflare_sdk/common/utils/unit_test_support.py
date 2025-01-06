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


def createClusterConfig():
    config = ClusterConfiguration(
        name="unit-test-cluster",
        namespace="ns",
        num_workers=2,
        worker_cpu_requests=3,
        worker_cpu_limits=4,
        worker_memory_requests=5,
        worker_memory_limits=6,
        appwrapper=True,
        write_to_file=False,
    )
    return config


def createClusterWithConfig(mocker):
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.get_cluster_custom_object",
        return_value={"spec": {"domain": "apps.cluster.awsroute.org"}},
    )
    cluster = Cluster(createClusterConfig())
    return cluster


def createClusterWrongType():
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
        image="quay.io/modh/ray@sha256:0d715f92570a2997381b7cafc0e224cfa25323f18b9545acfd23bc2b71576d06",
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
    rc_a_path = f"{parent}/tests/test_cluster_yamls/support_clusters/test-rc-a.yaml"
    rc_b_path = f"{parent}/tests/test_cluster_yamls/support_clusters/test-rc-b.yaml"
    rc_a, rc_b = get_cluster_object(rc_a_path, rc_b_path)

    rc_list = {"items": [rc_a, rc_b]}
    return rc_list


def get_ray_obj_with_status(group, version, namespace, plural):
    # To be used for mocking list_namespaced_custom_object for Ray Clusters with statuses
    rc_a_path = f"{parent}/tests/test_cluster_yamls/support_clusters/test-rc-a.yaml"
    rc_b_path = f"{parent}/tests/test_cluster_yamls/support_clusters/test-rc-b.yaml"
    rc_a, rc_b = get_cluster_object(rc_a_path, rc_b_path)

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
    aw_a_path = f"{parent}/tests/test_cluster_yamls/support_clusters/test-aw-a.yaml"
    aw_b_path = f"{parent}/tests/test_cluster_yamls/support_clusters/test-aw-b.yaml"
    aw_a, aw_b = get_cluster_object(aw_a_path, aw_b_path)

    aw_list = {"items": [aw_a, aw_b]}
    return aw_list


def get_aw_obj_with_status(group, version, namespace, plural):
    # To be used for mocking list_namespaced_custom_object for AppWrappers with statuses
    aw_a_path = f"{parent}/tests/test_cluster_yamls/support_clusters/test-aw-a.yaml"
    aw_b_path = f"{parent}/tests/test_cluster_yamls/support_clusters/test-aw-b.yaml"
    aw_a, aw_b = get_cluster_object(aw_a_path, aw_b_path)

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
    python_version = sys.version_info
    if python_version.major == 3 and python_version.minor == 9:
        return "quay.io/modh/ray@sha256:0d715f92570a2997381b7cafc0e224cfa25323f18b9545acfd23bc2b71576d06"
    else:
        return "quay.io/modh/ray@sha256:db667df1bc437a7b0965e8031e905d3ab04b86390d764d120e05ea5a5c18d1b4"


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
        annotations={"key1": "value1", "key2": "value2"},
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

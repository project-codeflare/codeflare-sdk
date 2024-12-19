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
from ..utils.unit_test_support import (
    apply_template,
    get_local_queue,
    createClusterConfig,
    get_template_variables,
)
from unittest.mock import patch
from codeflare_sdk.ray.cluster.cluster import Cluster, ClusterConfiguration
import yaml
import os
import filecmp
from pathlib import Path
from .kueue import list_local_queues

parent = Path(__file__).resolve().parents[4]  # project directory
aw_dir = os.path.expanduser("~/.codeflare/resources/")


def test_none_local_queue(mocker):
    mocker.patch("kubernetes.client.CustomObjectsApi.list_namespaced_custom_object")
    config = ClusterConfiguration(name="unit-test-aw-kueue", namespace="ns")
    config.name = "unit-test-aw-kueue"
    config.local_queue = None

    cluster = Cluster(config)
    assert cluster.config.local_queue == None


def test_cluster_creation_no_aw_local_queue(mocker):
    # With written resources
    # Create Ray Cluster with local queue specified
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.get_cluster_custom_object",
        return_value={"spec": {"domain": "apps.cluster.awsroute.org"}},
    )
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        return_value=get_local_queue("kueue.x-k8s.io", "v1beta1", "ns", "localqueues"),
    )
    config = createClusterConfig()
    config.name = "unit-test-cluster-kueue"
    config.write_to_file = True
    config.local_queue = "local-queue-default"
    cluster = Cluster(config)
    assert cluster.resource_yaml == f"{aw_dir}unit-test-cluster-kueue.yaml"
    expected_rc = apply_template(
        f"{parent}/tests/test_cluster_yamls/kueue/ray_cluster_kueue.yaml",
        get_template_variables(),
    )

    with open(f"{aw_dir}unit-test-cluster-kueue.yaml", "r") as f:
        cluster_kueue = yaml.load(f, Loader=yaml.FullLoader)
        assert cluster_kueue == expected_rc

    # With resources loaded in memory, no Local Queue specified.
    config = createClusterConfig()
    config.name = "unit-test-cluster-kueue"
    config.write_to_file = False
    cluster = Cluster(config)
    assert cluster.resource_yaml == expected_rc


def test_aw_creation_local_queue(mocker):
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.get_cluster_custom_object",
        return_value={"spec": {"domain": "apps.cluster.awsroute.org"}},
    )
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        return_value=get_local_queue("kueue.x-k8s.io", "v1beta1", "ns", "localqueues"),
    )
    config = createClusterConfig()
    config.name = "unit-test-aw-kueue"
    config.appwrapper = True
    config.write_to_file = True
    config.local_queue = "local-queue-default"
    cluster = Cluster(config)
    assert cluster.resource_yaml == f"{aw_dir}unit-test-aw-kueue.yaml"
    expected_rc = apply_template(
        f"{parent}/tests/test_cluster_yamls/kueue/aw_kueue.yaml",
        get_template_variables(),
    )

    with open(f"{aw_dir}unit-test-aw-kueue.yaml", "r") as f:
        aw_kueue = yaml.load(f, Loader=yaml.FullLoader)
        assert aw_kueue == expected_rc

    # With resources loaded in memory, no Local Queue specified.
    config = createClusterConfig()
    config.name = "unit-test-aw-kueue"
    config.appwrapper = True
    config.write_to_file = False
    cluster = Cluster(config)

    assert cluster.resource_yaml == expected_rc


def test_get_local_queue_exists_fail(mocker):
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.get_cluster_custom_object",
        return_value={"spec": {"domain": "apps.cluster.awsroute.org"}},
    )
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        return_value=get_local_queue("kueue.x-k8s.io", "v1beta1", "ns", "localqueues"),
    )
    config = createClusterConfig()
    config.name = "unit-test-aw-kueue"
    config.appwrapper = True
    config.write_to_file = True
    config.local_queue = "local_queue_doesn't_exist"
    try:
        Cluster(config)
    except ValueError as e:
        assert (
            str(e)
            == "local_queue provided does not exist or is not in this namespace. Please provide the correct local_queue name in Cluster Configuration"
        )


def test_list_local_queues(mocker):
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        return_value={
            "items": [
                {
                    "metadata": {"name": "lq1"},
                    "status": {"flavors": [{"name": "default"}]},
                },
                {
                    "metadata": {"name": "lq2"},
                    "status": {
                        "flavors": [{"name": "otherflavor"}, {"name": "default"}]
                    },
                },
            ]
        },
    )
    lqs = list_local_queues("ns")
    assert lqs == [
        {"name": "lq1", "flavors": ["default"]},
        {"name": "lq2", "flavors": ["otherflavor", "default"]},
    ]
    lqs = list_local_queues("ns", flavors=["otherflavor"])
    assert lqs == [{"name": "lq2", "flavors": ["otherflavor", "default"]}]
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        return_value={
            "items": [
                {
                    "metadata": {"name": "lq1"},
                    "status": {},
                },
            ]
        },
    )
    lqs = list_local_queues("ns", flavors=["default"])
    assert lqs == []


# Make sure to always keep this function last
def test_cleanup():
    os.remove(f"{aw_dir}unit-test-cluster-kueue.yaml")
    os.remove(f"{aw_dir}unit-test-aw-kueue.yaml")

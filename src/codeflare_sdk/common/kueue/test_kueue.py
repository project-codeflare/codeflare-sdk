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
    get_local_queue,
    create_cluster_config,
    get_template_variables,
    apply_template,
)
from unittest.mock import patch
from codeflare_sdk.ray.cluster.cluster import Cluster, ClusterConfiguration
import yaml
import os
import filecmp
from pathlib import Path
from .kueue import list_local_queues, local_queue_exists, add_queue_label

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
    config = create_cluster_config()
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
    config = create_cluster_config()
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
    config = create_cluster_config()
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
    config = create_cluster_config()
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
    config = create_cluster_config()
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


def test_local_queue_exists_found(mocker):
    # Mock Kubernetes client and list_namespaced_custom_object method
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mock_api_instance = mocker.Mock()
    mocker.patch("kubernetes.client.CustomObjectsApi", return_value=mock_api_instance)
    mocker.patch("codeflare_sdk.ray.cluster.cluster.config_check")

    # Mock return value for list_namespaced_custom_object
    mock_api_instance.list_namespaced_custom_object.return_value = {
        "items": [
            {"metadata": {"name": "existing-queue"}},
            {"metadata": {"name": "another-queue"}},
        ]
    }

    # Call the function
    namespace = "test-namespace"
    local_queue_name = "existing-queue"
    result = local_queue_exists(namespace, local_queue_name)

    # Assertions
    assert result is True
    mock_api_instance.list_namespaced_custom_object.assert_called_once_with(
        group="kueue.x-k8s.io",
        version="v1beta1",
        namespace=namespace,
        plural="localqueues",
    )


def test_local_queue_exists_not_found(mocker):
    # Mock Kubernetes client and list_namespaced_custom_object method
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mock_api_instance = mocker.Mock()
    mocker.patch("kubernetes.client.CustomObjectsApi", return_value=mock_api_instance)
    mocker.patch("codeflare_sdk.ray.cluster.cluster.config_check")

    # Mock return value for list_namespaced_custom_object
    mock_api_instance.list_namespaced_custom_object.return_value = {
        "items": [
            {"metadata": {"name": "another-queue"}},
            {"metadata": {"name": "different-queue"}},
        ]
    }

    # Call the function
    namespace = "test-namespace"
    local_queue_name = "non-existent-queue"
    result = local_queue_exists(namespace, local_queue_name)

    # Assertions
    assert result is False
    mock_api_instance.list_namespaced_custom_object.assert_called_once_with(
        group="kueue.x-k8s.io",
        version="v1beta1",
        namespace=namespace,
        plural="localqueues",
    )


import pytest
from unittest import mock  # If you're also using mocker from pytest-mock


def test_add_queue_label_with_valid_local_queue(mocker):
    # Mock the kubernetes.client.CustomObjectsApi and its response
    mock_api_instance = mocker.patch("kubernetes.client.CustomObjectsApi")
    mock_api_instance.return_value.list_namespaced_custom_object.return_value = {
        "items": [
            {"metadata": {"name": "valid-queue"}},
        ]
    }

    # Mock other dependencies
    mocker.patch("codeflare_sdk.common.kueue.local_queue_exists", return_value=True)
    mocker.patch(
        "codeflare_sdk.common.kueue.get_default_kueue_name",
        return_value="default-queue",
    )

    # Define input item and parameters
    item = {"metadata": {}}
    namespace = "test-namespace"
    local_queue = "valid-queue"

    # Call the function
    add_queue_label(item, namespace, local_queue)

    # Assert that the label is added to the item
    assert item["metadata"]["labels"] == {"kueue.x-k8s.io/queue-name": "valid-queue"}


def test_add_queue_label_with_invalid_local_queue(mocker):
    # Mock the kubernetes.client.CustomObjectsApi and its response
    mock_api_instance = mocker.patch("kubernetes.client.CustomObjectsApi")
    mock_api_instance.return_value.list_namespaced_custom_object.return_value = {
        "items": [
            {"metadata": {"name": "valid-queue"}},
        ]
    }

    # Mock the local_queue_exists function to return False
    mocker.patch("codeflare_sdk.common.kueue.local_queue_exists", return_value=False)

    # Define input item and parameters
    item = {"metadata": {}}
    namespace = "test-namespace"
    local_queue = "invalid-queue"

    # Call the function and expect a ValueError
    with pytest.raises(
        ValueError,
        match="local_queue provided does not exist or is not in this namespace",
    ):
        add_queue_label(item, namespace, local_queue)


# Make sure to always keep this function last
def test_cleanup():
    os.remove(f"{aw_dir}unit-test-cluster-kueue.yaml")
    os.remove(f"{aw_dir}unit-test-aw-kueue.yaml")

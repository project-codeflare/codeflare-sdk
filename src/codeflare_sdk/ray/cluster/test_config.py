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

from codeflare_sdk.common.utils.unit_test_support import createClusterWrongType
from codeflare_sdk.ray.cluster.cluster import ClusterConfiguration, Cluster
from pathlib import Path
from unittest.mock import patch
import filecmp
import pytest
import yaml
import os

parent = Path(__file__).resolve().parents[4]  # project directory
expected_clusters_dir = f"{parent}/tests/test_cluster_yamls"
aw_dir = os.path.expanduser("~/.codeflare/resources/")


def test_default_cluster_creation(mocker):
    # Create a Ray Cluster using the default config variables
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch("kubernetes.client.CustomObjectsApi.list_namespaced_custom_object")

    cluster = Cluster(
        ClusterConfiguration(
            name="default-cluster",
            namespace="ns",
        )
    )

    test_rc = yaml.load(cluster.app_wrapper_yaml, Loader=yaml.FullLoader)
    with open(f"{expected_clusters_dir}/ray/default-ray-cluster.yaml") as f:
        expected_rc = yaml.load(f, Loader=yaml.FullLoader)
        assert test_rc == expected_rc


def test_default_appwrapper_creation(mocker):
    # Create an AppWrapper using the default config variables
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch("kubernetes.client.CustomObjectsApi.list_namespaced_custom_object")

    cluster = Cluster(
        ClusterConfiguration(name="default-appwrapper", namespace="ns", appwrapper=True)
    )

    test_aw = yaml.load(cluster.app_wrapper_yaml, Loader=yaml.FullLoader)
    with open(f"{expected_clusters_dir}/ray/default-appwrapper.yaml") as f:
        expected_aw = yaml.load(f, Loader=yaml.FullLoader)
        assert test_aw == expected_aw


@patch.dict("os.environ", {"NB_PREFIX": "test-prefix"})
def test_config_creation_all_parameters(mocker):
    from codeflare_sdk.ray.cluster.config import DEFAULT_RESOURCE_MAPPING

    mocker.patch(
        "codeflare_sdk.common.kueue.kueue.local_queue_exists",
        return_value="true",
    )
    extended_resource_mapping = DEFAULT_RESOURCE_MAPPING
    extended_resource_mapping.update({"example.com/gpu": "GPU"})

    config = ClusterConfiguration(
        name="test-all-params",
        namespace="ns",
        head_info=["test1", "test2"],
        head_cpu_requests=4,
        head_cpu_limits=8,
        head_memory_requests=12,
        head_memory_limits=16,
        head_extended_resource_requests={"nvidia.com/gpu": 1},
        machine_types={"gpu.small", "gpu.large"},
        worker_cpu_requests=4,
        worker_cpu_limits=8,
        num_workers=10,
        worker_memory_requests=12,
        worker_memory_limits=16,
        template=f"{parent}/src/codeflare_sdk/ray/templates/base-template.yaml",
        appwrapper=False,
        envs={"key1": "value1", "key2": "value2"},
        image="example/ray:tag",
        image_pull_secrets=["secret1", "secret2"],
        write_to_file=True,
        verify_tls=True,
        labels={"key1": "value1", "key2": "value2"},
        worker_extended_resource_requests={"nvidia.com/gpu": 1},
        extended_resource_mapping=extended_resource_mapping,
        overwrite_default_resource_mapping=True,
        local_queue="local-queue-default",
    )
    Cluster(config)

    assert config.name == "test-all-params" and config.namespace == "ns"
    assert config.head_info == ["test1", "test2"]
    assert config.head_cpu_requests == 4
    assert config.head_cpu_limits == 8
    assert config.head_memory_requests == "12G"
    assert config.head_memory_limits == "16G"
    assert config.head_extended_resource_requests == {"nvidia.com/gpu": 1}
    assert config.machine_types == {"gpu.small", "gpu.large"}
    assert config.worker_cpu_requests == 4
    assert config.worker_cpu_limits == 8
    assert config.num_workers == 10
    assert config.worker_memory_requests == "12G"
    assert config.worker_memory_limits == "16G"
    assert (
        config.template
        == f"{parent}/src/codeflare_sdk/ray/templates/base-template.yaml"
    )
    assert config.appwrapper == False
    assert config.envs == {"key1": "value1", "key2": "value2"}
    assert config.image == "example/ray:tag"
    assert config.image_pull_secrets == ["secret1", "secret2"]
    assert config.write_to_file == True
    assert config.verify_tls == True
    assert config.labels == {"key1": "value1", "key2": "value2"}
    assert config.worker_extended_resource_requests == {"nvidia.com/gpu": 1}
    assert config.extended_resource_mapping == extended_resource_mapping
    assert config.overwrite_default_resource_mapping == True
    assert config.local_queue == "local-queue-default"

    assert filecmp.cmp(
        f"{aw_dir}test-all-params.yaml",
        f"{expected_clusters_dir}/ray/unit-test-all-params.yaml",
        shallow=True,
    )


def test_config_creation_wrong_type():
    with pytest.raises(TypeError):
        createClusterWrongType()


def test_cluster_config_deprecation_conversion(mocker):
    config = ClusterConfiguration(
        name="test",
        num_gpus=2,
        head_gpus=1,
        head_cpus=3,
        head_memory=16,
        min_memory=3,
        max_memory=4,
        min_cpus=1,
        max_cpus=2,
    )
    assert config.head_cpu_requests == 3
    assert config.head_cpu_limits == 3
    assert config.head_memory_requests == "16G"
    assert config.head_memory_limits == "16G"
    assert config.worker_extended_resource_requests == {"nvidia.com/gpu": 2}
    assert config.head_extended_resource_requests == {"nvidia.com/gpu": 1}
    assert config.worker_memory_requests == "3G"
    assert config.worker_memory_limits == "4G"
    assert config.worker_cpu_requests == 1
    assert config.worker_cpu_limits == 2


# Make sure to always keep this function last
def test_cleanup():
    os.remove(f"{aw_dir}test-all-params.yaml")

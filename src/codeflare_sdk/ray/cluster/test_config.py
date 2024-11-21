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

from codeflare_sdk.common.utils.unit_test_support import (
    apply_template,
    createClusterWrongType,
    get_example_extended_storage_opts,
    create_cluster_all_config_params,
    get_template_variables,
)
from codeflare_sdk.ray.cluster.cluster import ClusterConfiguration, Cluster
from pathlib import Path
import filecmp
import pytest
import os

parent = Path(__file__).resolve().parents[4]  # project directory
expected_clusters_dir = f"{parent}/tests/test_cluster_yamls"
aw_dir = os.path.expanduser("~/.codeflare/resources/")


def test_default_cluster_creation(mocker):
    # Create a Ray Cluster using the default config variables
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch("kubernetes.client.CustomObjectsApi.list_namespaced_custom_object")

    cluster = Cluster(ClusterConfiguration(name="default-cluster", namespace="ns"))

    expected_rc = apply_template(
        f"{expected_clusters_dir}/ray/default-ray-cluster.yaml",
        get_template_variables(),
    )
    assert cluster.resource_yaml == expected_rc


def test_default_appwrapper_creation(mocker):
    # Create an AppWrapper using the default config variables
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch("kubernetes.client.CustomObjectsApi.list_namespaced_custom_object")

    cluster = Cluster(
        ClusterConfiguration(name="default-appwrapper", namespace="ns", appwrapper=True)
    )

    expected_aw = apply_template(
        f"{expected_clusters_dir}/ray/default-appwrapper.yaml", get_template_variables()
    )
    assert cluster.resource_yaml == expected_aw


def test_config_creation_all_parameters(mocker):
    from codeflare_sdk.ray.cluster.config import DEFAULT_RESOURCE_MAPPING

    expected_extended_resource_mapping = DEFAULT_RESOURCE_MAPPING
    expected_extended_resource_mapping.update({"example.com/gpu": "GPU"})
    expected_extended_resource_mapping["intel.com/gpu"] = "TPU"
    volumes, volume_mounts = get_example_extended_storage_opts()

    cluster = create_cluster_all_config_params(mocker, "test-all-params", False)
    assert cluster.config.name == "test-all-params" and cluster.config.namespace == "ns"
    assert cluster.config.head_cpu_requests == 4
    assert cluster.config.head_cpu_limits == 8
    assert cluster.config.head_memory_requests == "12G"
    assert cluster.config.head_memory_limits == "16G"
    assert cluster.config.head_extended_resource_requests == {
        "nvidia.com/gpu": 1,
        "intel.com/gpu": 2,
    }
    assert cluster.config.worker_cpu_requests == 4
    assert cluster.config.worker_cpu_limits == 8
    assert cluster.config.num_workers == 10
    assert cluster.config.worker_memory_requests == "12G"
    assert cluster.config.worker_memory_limits == "16G"
    assert cluster.config.appwrapper == False
    assert cluster.config.envs == {"key1": "value1", "key2": "value2"}
    assert cluster.config.image == "example/ray:tag"
    assert cluster.config.image_pull_secrets == ["secret1", "secret2"]
    assert cluster.config.write_to_file == True
    assert cluster.config.verify_tls == True
    assert cluster.config.labels == {"key1": "value1", "key2": "value2"}
    assert cluster.config.worker_extended_resource_requests == {"nvidia.com/gpu": 1}
    assert (
        cluster.config.extended_resource_mapping == expected_extended_resource_mapping
    )
    assert cluster.config.overwrite_default_resource_mapping == True
    assert cluster.config.local_queue == "local-queue-default"
    assert cluster.config.annotations == {
        "app.kubernetes.io/managed-by": "test-prefix",
        "key1": "value1",
        "key2": "value2",
    }
    assert cluster.config.volumes == volumes
    assert cluster.config.volume_mounts == volume_mounts

    assert filecmp.cmp(
        f"{aw_dir}test-all-params.yaml",
        f"{expected_clusters_dir}/ray/unit-test-all-params.yaml",
        shallow=True,
    )


def test_all_config_params_aw(mocker):
    create_cluster_all_config_params(mocker, "aw-all-params", True)
    assert filecmp.cmp(
        f"{aw_dir}aw-all-params.yaml",
        f"{expected_clusters_dir}/appwrapper/unit-test-all-params.yaml",
        shallow=True,
    )


def test_config_creation_wrong_type():
    with pytest.raises(TypeError) as error_info:
        createClusterWrongType()

    assert len(str(error_info.value).splitlines()) == 4


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
    os.remove(f"{aw_dir}aw-all-params.yaml")

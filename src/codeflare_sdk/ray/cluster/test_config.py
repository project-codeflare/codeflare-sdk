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
    get_example_extended_storage_opts,
    create_cluster_wrong_type,
    create_cluster_all_config_params,
    get_template_variables,
)
from codeflare_sdk.ray.cluster.cluster import ClusterConfiguration, Cluster
from pathlib import Path
import filecmp
import pytest
import os
import yaml

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


@pytest.mark.filterwarnings("ignore::UserWarning")
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
    assert cluster.config.envs == {
        "key1": "value1",
        "key2": "value2",
        "RAY_USAGE_STATS_ENABLED": "0",
    }
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


@pytest.mark.filterwarnings("ignore::UserWarning")
def test_all_config_params_aw(mocker):
    create_cluster_all_config_params(mocker, "aw-all-params", True)

    assert filecmp.cmp(
        f"{aw_dir}aw-all-params.yaml",
        f"{expected_clusters_dir}/appwrapper/unit-test-all-params.yaml",
        shallow=True,
    )


def test_config_creation_wrong_type():
    with pytest.raises(TypeError) as error_info:
        create_cluster_wrong_type()

    assert len(str(error_info.value).splitlines()) == 4


def test_gcs_fault_tolerance_config_validation():
    config = ClusterConfiguration(
        name="test",
        namespace="ns",
        enable_gcs_ft=True,
        redis_address="redis:6379",
        redis_password_secret={"name": "redis-password-secret", "key": "password"},
        external_storage_namespace="new-ns",
    )

    assert config.enable_gcs_ft is True
    assert config.redis_address == "redis:6379"
    assert config.redis_password_secret == {
        "name": "redis-password-secret",
        "key": "password",
    }
    assert config.external_storage_namespace == "new-ns"

    try:
        ClusterConfiguration(name="test", namespace="ns", enable_gcs_ft=True)
    except ValueError as e:
        assert str(e) in "redis_address must be provided when enable_gcs_ft is True"

    try:
        ClusterConfiguration(
            name="test",
            namespace="ns",
            enable_gcs_ft=True,
            redis_address="redis:6379",
            redis_password_secret={"secret"},
        )
    except ValueError as e:
        assert (
            str(e)
            in "redis_password_secret must be a dictionary with 'name' and 'key' fields"
        )

    try:
        ClusterConfiguration(
            name="test",
            namespace="ns",
            enable_gcs_ft=True,
            redis_address="redis:6379",
            redis_password_secret={"wrong": "format"},
        )
    except ValueError as e:
        assert (
            str(e) in "redis_password_secret must contain both 'name' and 'key' fields"
        )


def test_ray_usage_stats_default(mocker):
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch("kubernetes.client.CustomObjectsApi.list_namespaced_custom_object")

    cluster = Cluster(
        ClusterConfiguration(name="default-usage-stats-cluster", namespace="ns")
    )

    # Verify that usage stats are disabled by default
    assert cluster.config.envs["RAY_USAGE_STATS_ENABLED"] == "0"

    # Check that the environment variable is set in the YAML
    head_container = cluster.resource_yaml["spec"]["headGroupSpec"]["template"]["spec"][
        "containers"
    ][0]
    env_vars = {env["name"]: env["value"] for env in head_container["env"]}
    assert env_vars["RAY_USAGE_STATS_ENABLED"] == "0"


def test_ray_usage_stats_enabled(mocker):
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch("kubernetes.client.CustomObjectsApi.list_namespaced_custom_object")

    cluster = Cluster(
        ClusterConfiguration(
            name="usage-stats-enabled-cluster",
            namespace="ns",
            enable_usage_stats=True,
        )
    )

    assert cluster.config.envs["RAY_USAGE_STATS_ENABLED"] == "1"

    head_container = cluster.resource_yaml["spec"]["headGroupSpec"]["template"]["spec"][
        "containers"
    ][0]
    env_vars = {env["name"]: env["value"] for env in head_container["env"]}
    assert env_vars["RAY_USAGE_STATS_ENABLED"] == "1"


# Make sure to always keep this function last
def test_cleanup():
    os.remove(f"{aw_dir}test-all-params.yaml")
    os.remove(f"{aw_dir}aw-all-params.yaml")

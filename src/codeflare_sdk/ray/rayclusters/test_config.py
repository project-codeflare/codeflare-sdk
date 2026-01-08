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
from .raycluster import RayCluster, DEFAULT_ACCELERATOR_CONFIGS
from pathlib import Path
import pytest
import os
import yaml

parent = Path(__file__).resolve().parents[4]  # project directory
expected_clusters_dir = f"{parent}/tests/test_cluster_yamls"
cluster_dir = os.path.expanduser("~/.codeflare/resources/")


def _strip_none_values(value):
    """Remove None values so K8s client defaults don't break fixture comparisons."""
    if isinstance(value, dict):
        return {
            key: _strip_none_values(val)
            for key, val in value.items()
            if val is not None
        }
    if isinstance(value, list):
        return [_strip_none_values(item) for item in value if item is not None]
    return value


def test_default_cluster_creation(mocker):
    # Create a Ray Cluster using the default config variables
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch("kubernetes.client.CustomObjectsApi.list_namespaced_custom_object")
    # Mock auth helpers so _build_standalone_ray_cluster can run without real K8s.
    mocker.patch("codeflare_sdk.ray.rayclusters.raycluster.config_check")
    # Return None so ApiClient() is used and we get standard serialization output.
    mocker.patch(
        "codeflare_sdk.ray.rayclusters.raycluster.get_api_client",
        return_value=None,
    )

    cluster = RayCluster(name="default-cluster", namespace="ns")
    cluster._resource_yaml = cluster._build_standalone_ray_cluster()

    expected_rc = apply_template(
        f"{expected_clusters_dir}/ray/default-ray-cluster.yaml",
        get_template_variables(),
    )

    # Strip None fields added by Kubernetes client serialization for comparison.
    assert _strip_none_values(cluster._resource_yaml) == expected_rc


@pytest.mark.filterwarnings("ignore::UserWarning")
def test_config_creation_all_parameters(mocker):
    expected_accelerator_configs = DEFAULT_ACCELERATOR_CONFIGS.copy()
    expected_accelerator_configs.update({"example.com/gpu": "GPU"})
    expected_accelerator_configs["intel.com/gpu"] = "TPU"
    volumes, volume_mounts = get_example_extended_storage_opts()

    # Helper now returns RayCluster directly
    cluster = create_cluster_all_config_params(mocker, "test-all-params")
    # Build the resource to generate the YAML file for comparison.
    # Ensure NB_PREFIX is set during build so managed-by is added to metadata.
    mocker.patch("codeflare_sdk.ray.rayclusters.raycluster.config_check")
    mocker.patch(
        "codeflare_sdk.ray.rayclusters.raycluster.get_api_client",
        return_value=None,
    )
    mocker.patch.dict(os.environ, {"NB_PREFIX": "test-prefix"})
    cluster._resource_yaml = cluster._build_standalone_ray_cluster()
    # Access attributes directly on RayCluster
    assert cluster.name == "test-all-params" and cluster.namespace == "ns"
    assert cluster.head_cpu_requests == 4
    assert cluster.head_cpu_limits == 8
    assert cluster.head_memory_requests == "12G"
    assert cluster.head_memory_limits == "16G"
    assert cluster.head_accelerators == {
        "nvidia.com/gpu": 1,
        "intel.com/gpu": 2,
    }
    assert cluster.worker_cpu_requests == 4
    assert cluster.worker_cpu_limits == 8
    assert cluster.num_workers == 10
    assert cluster.worker_memory_requests == "12G"
    assert cluster.worker_memory_limits == "16G"
    assert cluster.envs == {
        "key1": "value1",
        "key2": "value2",
        "RAY_USAGE_STATS_ENABLED": "0",
    }
    assert cluster.image == "example/ray:tag"
    assert cluster.image_pull_secrets == ["secret1", "secret2"]
    assert cluster.write_to_file == True
    assert cluster.verify_tls == True
    assert cluster.labels == {"key1": "value1", "key2": "value2"}
    assert cluster.worker_accelerators == {"nvidia.com/gpu": 1}
    assert cluster.overwrite_default_accelerator_configs == True
    assert cluster.local_queue == "local-queue-default"
    # NB_PREFIX affects build-time metadata, not the stored annotations attribute.
    assert cluster.annotations == {
        "key1": "value1",
        "key2": "value2",
    }
    assert cluster.volumes == volumes
    assert cluster.volume_mounts == volume_mounts

    # Compare YAML contents while ignoring None fields added by serialization.
    with open(f"{cluster_dir}test-all-params.yaml") as generated_file:
        generated_rc = yaml.safe_load(generated_file)
    with open(
        f"{expected_clusters_dir}/ray/unit-test-all-params.yaml"
    ) as expected_file:
        expected_rc = yaml.safe_load(expected_file)

    # RayCluster only applies NB_PREFIX to top-level metadata, not pod templates.
    def _drop_managed_by_from_templates(resource):
        if not resource:
            return
        head_annotations = (
            resource.get("spec", {})
            .get("headGroupSpec", {})
            .get("template", {})
            .get("metadata", {})
            .get("annotations", {})
        )
        head_annotations.pop("app.kubernetes.io/managed-by", None)
        for worker_group in resource.get("spec", {}).get("workerGroupSpecs", []):
            worker_annotations = (
                worker_group.get("template", {})
                .get("metadata", {})
                .get("annotations", {})
            )
            worker_annotations.pop("app.kubernetes.io/managed-by", None)

    _drop_managed_by_from_templates(generated_rc)
    _drop_managed_by_from_templates(expected_rc)
    assert _strip_none_values(generated_rc) == expected_rc


def test_config_creation_wrong_type():
    with pytest.raises(TypeError) as error_info:
        create_cluster_wrong_type()

    assert len(str(error_info.value).splitlines()) == 4


def test_gcs_fault_tolerance_config_validation():
    cluster = RayCluster(
        name="test",
        namespace="ns",
        enable_gcs_ft=True,
        redis_address="redis:6379",
        redis_password_secret={"name": "redis-password-secret", "key": "password"},
        external_storage_namespace="new-ns",
    )

    assert cluster.enable_gcs_ft is True
    assert cluster.redis_address == "redis:6379"
    assert cluster.redis_password_secret == {
        "name": "redis-password-secret",
        "key": "password",
    }
    assert cluster.external_storage_namespace == "new-ns"

    try:
        RayCluster(name="test", namespace="ns", enable_gcs_ft=True)
    except ValueError as e:
        assert str(e) in "redis_address must be provided when enable_gcs_ft is True"

    try:
        RayCluster(
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
        RayCluster(
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
    # Build the resource so _resource_yaml is populated for env checks.
    mocker.patch("codeflare_sdk.ray.rayclusters.raycluster.config_check")
    mocker.patch(
        "codeflare_sdk.ray.rayclusters.raycluster.get_api_client",
        return_value=None,
    )

    cluster = RayCluster(name="default-usage-stats-cluster", namespace="ns")
    cluster._resource_yaml = cluster._build_standalone_ray_cluster()

    # Verify that usage stats are disabled by default
    assert cluster.envs["RAY_USAGE_STATS_ENABLED"] == "0"

    # Check that the environment variable is set in the YAML
    head_container = cluster._resource_yaml["spec"]["headGroupSpec"]["template"][
        "spec"
    ]["containers"][0]
    env_vars = {env["name"]: env["value"] for env in head_container["env"]}
    assert env_vars["RAY_USAGE_STATS_ENABLED"] == "0"


def test_ray_usage_stats_enabled(mocker):
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch("kubernetes.client.CustomObjectsApi.list_namespaced_custom_object")
    # Build the resource so _resource_yaml is populated for env checks.
    mocker.patch("codeflare_sdk.ray.rayclusters.raycluster.config_check")
    mocker.patch(
        "codeflare_sdk.ray.rayclusters.raycluster.get_api_client",
        return_value=None,
    )

    cluster = RayCluster(
        name="usage-stats-enabled-cluster",
        namespace="ns",
        enable_usage_stats=True,
    )
    cluster._resource_yaml = cluster._build_standalone_ray_cluster()

    assert cluster.envs["RAY_USAGE_STATS_ENABLED"] == "1"

    head_container = cluster._resource_yaml["spec"]["headGroupSpec"]["template"][
        "spec"
    ]["containers"][0]
    env_vars = {env["name"]: env["value"] for env in head_container["env"]}
    assert env_vars["RAY_USAGE_STATS_ENABLED"] == "1"


# Make sure to always keep this function last
def test_cleanup():
    test_file = f"{cluster_dir}test-all-params.yaml"
    if os.path.exists(test_file):
        os.remove(test_file)

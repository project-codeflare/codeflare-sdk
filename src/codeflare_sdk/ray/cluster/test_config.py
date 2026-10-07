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

import os
from pathlib import Path

import pytest
import yaml

from codeflare_sdk.common.utils.unit_test_support import (
    apply_template,
    create_cluster_all_config_params,
    create_cluster_wrong_type,
    get_example_extended_storage_opts,
    get_template_variables,
)
from codeflare_sdk.ray.cluster.cluster import Cluster, ClusterConfiguration
from codeflare_sdk.ray.cluster.config import WorkerGroup

parent = Path(__file__).resolve().parents[4]  # project directory
expected_clusters_dir = f"{parent}/tests/test_cluster_yamls"
cluster_dir = os.path.expanduser("~/.codeflare/resources/")


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


@pytest.mark.filterwarnings("ignore::UserWarning")
def test_config_creation_all_parameters(mocker):
    from codeflare_sdk.ray.cluster.config import DEFAULT_RESOURCE_MAPPING

    expected_extended_resource_mapping = DEFAULT_RESOURCE_MAPPING
    expected_extended_resource_mapping.update({"example.com/gpu": "GPU"})
    expected_extended_resource_mapping["intel.com/gpu"] = "TPU"
    volumes, volume_mounts = get_example_extended_storage_opts()

    cluster = create_cluster_all_config_params(mocker, "test-all-params")
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
    assert cluster.config.envs == {
        "key1": "value1",
        "key2": "value2",
        "RAY_USAGE_STATS_ENABLED": "0",
    }
    assert cluster.config.image == "example/ray:tag"
    assert cluster.config.image_pull_secrets == ["secret1", "secret2"]
    assert cluster.config.write_to_file is True
    assert cluster.config.verify_tls is True
    assert cluster.config.labels == {"key1": "value1", "key2": "value2"}
    assert cluster.config.worker_extended_resource_requests == {"nvidia.com/gpu": 1}
    assert (
        cluster.config.extended_resource_mapping == expected_extended_resource_mapping
    )
    assert cluster.config.overwrite_default_resource_mapping is True
    assert cluster.config.local_queue == "local-queue-default"
    assert cluster.config.annotations == {
        "app.kubernetes.io/managed-by": "test-prefix",
        "key1": "value1",
        "key2": "value2",
    }
    assert cluster.config.volumes == volumes
    assert cluster.config.volume_mounts == volume_mounts

    with open(f"{cluster_dir}test-all-params.yaml", "r") as f:
        actual = yaml.load(f, Loader=yaml.FullLoader)
    expected = apply_template(
        f"{expected_clusters_dir}/ray/unit-test-all-params.yaml",
        get_template_variables(),
    )
    assert actual == expected


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


def test_config_name_optional_defaults_to_none():
    """ClusterConfiguration can be created without a name."""
    config = ClusterConfiguration()
    assert config.name is None


def test_config_name_none_skips_rfc1123_validation():
    """No RFC 1123 validation when name is None."""
    config = ClusterConfiguration(namespace="test-ns", num_workers=2)
    assert config.name is None


def test_config_name_set_still_validates_rfc1123():
    """RFC 1123 validation still runs when name is provided."""
    with pytest.raises(ValueError):
        ClusterConfiguration(name="INVALID_NAME")


def test_cluster_init_requires_name(mocker):
    """Cluster.__init__ raises ValueError when config.name is None."""
    mocker.patch("codeflare_sdk.ray.cluster.cluster.config_check")
    mocker.patch("codeflare_sdk.ray.cluster.cluster.get_api_client")
    config = ClusterConfiguration(namespace="test-ns")
    with pytest.raises(ValueError, match="name is required"):
        Cluster(config)


def test_cluster_name_validation():
    with pytest.raises(ValueError):
        ClusterConfiguration(name="TestCluster", namespace="ns")
    with pytest.raises(ValueError):
        ClusterConfiguration(name="testcluster-", namespace="ns")
    with pytest.raises(ValueError):
        ClusterConfiguration(name="-testcluster", namespace="ns")


def test_autoscaling_config_valid():
    config = ClusterConfiguration(
        name="autoscale-test",
        namespace="ns",
        enable_autoscaling=True,
        min_workers=1,
        max_workers=8,
    )
    assert config.enable_autoscaling is True
    assert config.min_workers == 1
    assert config.max_workers == 8


def test_autoscaling_config_zero_min_workers():
    config = ClusterConfiguration(
        name="autoscale-zero-min",
        namespace="ns",
        enable_autoscaling=True,
        min_workers=0,
        max_workers=4,
    )
    assert config.min_workers == 0
    assert config.max_workers == 4


def test_autoscaling_config_missing_workers():
    with pytest.raises(
        ValueError, match="min_workers and max_workers must be provided"
    ):
        ClusterConfiguration(
            name="autoscale-missing",
            namespace="ns",
            enable_autoscaling=True,
        )


def test_autoscaling_config_missing_max_workers():
    with pytest.raises(
        ValueError, match="min_workers and max_workers must be provided"
    ):
        ClusterConfiguration(
            name="autoscale-missing-max",
            namespace="ns",
            enable_autoscaling=True,
            min_workers=1,
        )


def test_autoscaling_config_negative_min_workers():
    with pytest.raises(ValueError, match="min_workers must be >= 0"):
        ClusterConfiguration(
            name="autoscale-negative",
            namespace="ns",
            enable_autoscaling=True,
            min_workers=-1,
            max_workers=4,
        )


def test_autoscaling_config_max_less_than_min():
    with pytest.raises(ValueError, match="max_workers must be >= min_workers"):
        ClusterConfiguration(
            name="autoscale-bad-range",
            namespace="ns",
            enable_autoscaling=True,
            min_workers=5,
            max_workers=2,
        )


def test_autoscaling_disabled_ignores_workers():
    with pytest.warns(UserWarning, match="min_workers and max_workers are ignored"):
        config = ClusterConfiguration(
            name="no-autoscale",
            namespace="ns",
            enable_autoscaling=False,
            min_workers=1,
            max_workers=8,
        )
    assert config.enable_autoscaling is False


def test_autoscaling_spec_generation(mocker):
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch("kubernetes.client.CustomObjectsApi.list_namespaced_custom_object")
    mocker.patch(
        "codeflare_sdk.common.kueue.kueue.get_default_kueue_name",
        return_value=None,
    )

    cluster = Cluster(
        ClusterConfiguration(
            name="autoscale-cluster",
            namespace="ns",
            enable_autoscaling=True,
            min_workers=2,
            max_workers=10,
        )
    )

    spec = cluster.resource_yaml["spec"]
    assert spec["enableInTreeAutoscaling"] is True
    worker_group = spec["workerGroupSpecs"][0]
    assert worker_group["replicas"] == 2
    assert worker_group["minReplicas"] == 2
    assert worker_group["maxReplicas"] == 10


def test_autoscaling_blocked_when_local_queue_set(mocker):
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch("kubernetes.client.CustomObjectsApi.list_namespaced_custom_object")
    mocker.patch(
        "codeflare_sdk.common.kueue.kueue.kueue_supports_elastic_workloads",
        return_value=False,
    )
    mocker.patch(
        "codeflare_sdk.common.kueue.kueue.is_rhoai_kueue_managed",
        return_value=False,
    )

    with pytest.raises(
        ValueError,
        match="Autoscaling is not supported when Kueue is enabled",
    ):
        Cluster(
            ClusterConfiguration(
                name="autoscale-kueue-explicit",
                namespace="ns",
                enable_autoscaling=True,
                min_workers=1,
                max_workers=8,
                local_queue="my-queue",
            )
        )


def test_autoscaling_blocked_when_default_queue_exists(mocker):
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch("kubernetes.client.CustomObjectsApi.list_namespaced_custom_object")
    mocker.patch(
        "codeflare_sdk.common.kueue.kueue.get_default_kueue_name",
        return_value="default-queue",
    )
    mocker.patch(
        "codeflare_sdk.common.kueue.kueue.kueue_supports_elastic_workloads",
        return_value=False,
    )
    mocker.patch(
        "codeflare_sdk.common.kueue.kueue.is_rhoai_kueue_managed",
        return_value=False,
    )

    with pytest.raises(
        ValueError,
        match="Autoscaling is not supported when Kueue is enabled",
    ):
        Cluster(
            ClusterConfiguration(
                name="autoscale-kueue-default",
                namespace="ns",
                enable_autoscaling=True,
                min_workers=1,
                max_workers=8,
            )
        )


def test_autoscaling_allowed_when_kueue_rhbok_14(mocker):
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch("kubernetes.client.CustomObjectsApi.list_namespaced_custom_object")
    mocker.patch(
        "codeflare_sdk.common.kueue.kueue.get_default_kueue_name",
        return_value="default-queue",
    )
    mocker.patch(
        "codeflare_sdk.common.kueue.kueue.kueue_supports_elastic_workloads",
        return_value=True,
    )
    mocker.patch(
        "codeflare_sdk.common.kueue.kueue.is_rhoai_kueue_managed",
        return_value=False,
    )

    cluster = Cluster(
        ClusterConfiguration(
            name="autoscale-kueue-rhbok14",
            namespace="ns",
            enable_autoscaling=True,
            min_workers=1,
            max_workers=8,
        )
    )

    spec = cluster.resource_yaml["spec"]
    assert spec["enableInTreeAutoscaling"] is True


def test_autoscaling_blocked_when_rhoai_managed_kueue(mocker):
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch("kubernetes.client.CustomObjectsApi.list_namespaced_custom_object")
    mocker.patch(
        "codeflare_sdk.common.kueue.kueue.get_default_kueue_name",
        return_value="default-queue",
    )
    mocker.patch(
        "codeflare_sdk.common.kueue.kueue.kueue_supports_elastic_workloads",
        return_value=True,
    )
    mocker.patch(
        "codeflare_sdk.common.kueue.kueue.is_rhoai_kueue_managed",
        return_value=True,
    )

    with pytest.raises(
        ValueError,
        match="Autoscaling is not supported when Kueue is enabled",
    ):
        Cluster(
            ClusterConfiguration(
                name="autoscale-rhoai-managed-kueue",
                namespace="ns",
                enable_autoscaling=True,
                min_workers=1,
                max_workers=8,
            )
        )


def test_autoscaling_allowed_when_no_queue(mocker):
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch("kubernetes.client.CustomObjectsApi.list_namespaced_custom_object")
    mocker.patch(
        "codeflare_sdk.common.kueue.kueue.get_default_kueue_name",
        return_value=None,
    )

    cluster = Cluster(
        ClusterConfiguration(
            name="autoscale-no-kueue",
            namespace="ns",
            enable_autoscaling=True,
            min_workers=1,
            max_workers=8,
        )
    )

    spec = cluster.resource_yaml["spec"]
    assert spec["enableInTreeAutoscaling"] is True


def test_autoscaling_disabled_spec_unchanged(mocker):
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch("kubernetes.client.CustomObjectsApi.list_namespaced_custom_object")

    cluster = Cluster(
        ClusterConfiguration(
            name="fixed-cluster",
            namespace="ns",
            num_workers=3,
        )
    )

    spec = cluster.resource_yaml["spec"]
    assert spec["enableInTreeAutoscaling"] is False
    worker_group = spec["workerGroupSpecs"][0]
    assert worker_group["replicas"] == 3
    assert worker_group["minReplicas"] == 3
    assert worker_group["maxReplicas"] == 3


# --- WorkerGroup tests ---


def test_worker_group_basic():
    wg = WorkerGroup(group_name="gpu-workers", replicas=2)
    assert wg.group_name == "gpu-workers"
    assert wg.replicas == 2
    assert wg.min_replicas is None
    assert wg.max_replicas is None
    assert wg.cpu_requests == 1
    assert wg.cpu_limits == 1
    assert wg.memory_requests == "3G"
    assert wg.memory_limits == "6G"
    assert wg.gpu_type is None
    assert wg.gpu_count is None
    assert wg.image is None
    assert wg.envs == {}
    assert wg.labels == {}
    assert wg.tolerations is None


def test_worker_group_memory_int_to_string():
    wg = WorkerGroup(group_name="mem-test", memory_requests=16, memory_limits=32)
    assert wg.memory_requests == "16G"
    assert wg.memory_limits == "32G"


def test_worker_group_memory_str_no_unit():
    wg = WorkerGroup(group_name="mem-str", memory_requests="8", memory_limits="16")
    assert wg.memory_requests == "8G"
    assert wg.memory_limits == "16G"


def test_worker_group_memory_str_with_unit():
    wg = WorkerGroup(group_name="mem-unit", memory_requests="8Gi", memory_limits="16Gi")
    assert wg.memory_requests == "8Gi"
    assert wg.memory_limits == "16Gi"


def test_worker_group_gpu():
    wg = WorkerGroup(
        group_name="gpu-group",
        gpu_type="nvidia.com/gpu",
        gpu_count=4,
    )
    assert wg.gpu_type == "nvidia.com/gpu"
    assert wg.gpu_count == 4


def test_worker_group_gpu_type_without_count():
    with pytest.raises(ValueError, match="gpu_count is required"):
        WorkerGroup(group_name="bad-gpu", gpu_type="nvidia.com/gpu")


def test_worker_group_gpu_count_without_type():
    with pytest.raises(ValueError, match="gpu_type is required"):
        WorkerGroup(group_name="bad-gpu", gpu_count=2)


def test_worker_group_min_max_replicas():
    wg = WorkerGroup(group_name="scaling", replicas=2, min_replicas=1, max_replicas=8)
    assert wg.min_replicas == 1
    assert wg.max_replicas == 8


def test_worker_group_max_less_than_min():
    with pytest.raises(
        ValueError, match="min_replicas=5 cannot be greater than max_replicas=2"
    ):
        WorkerGroup(group_name="bad-range", min_replicas=5, max_replicas=2)


def test_worker_group_group_name_required():
    with pytest.raises(TypeError):
        WorkerGroup()


def test_worker_group_empty_group_name():
    with pytest.raises(ValueError, match="group_name is required"):
        WorkerGroup(group_name="")


def test_worker_group_whitespace_group_name():
    with pytest.raises(ValueError, match="group_name is required"):
        WorkerGroup(group_name="   ")


def test_worker_group_negative_replicas():
    with pytest.raises(ValueError, match="replicas=-1"):
        WorkerGroup(group_name="bad-replicas", replicas=-1)


def test_worker_group_negative_min_replicas():
    with pytest.raises(ValueError, match="min_replicas=-1"):
        WorkerGroup(group_name="bad-min", replicas=1, min_replicas=-1, max_replicas=3)


def test_worker_group_negative_max_replicas():
    with pytest.raises(ValueError, match="max_replicas=-1"):
        WorkerGroup(group_name="bad-max", replicas=1, min_replicas=1, max_replicas=-1)


def test_worker_group_negative_int_cpu_requests():
    with pytest.raises(ValueError, match="cpu_requests=-1"):
        WorkerGroup(group_name="bad-cpu-int", cpu_requests=-1)


def test_worker_group_negative_int_memory_requests():
    with pytest.raises(ValueError, match="memory_requests=-1"):
        WorkerGroup(group_name="bad-mem-int", memory_requests=-1)


def test_worker_group_invalid_cpu_limits():
    with pytest.raises(ValueError, match="cpu_limits='bad'"):
        WorkerGroup(group_name="bad-cpu-lim", cpu_limits="bad")


def test_worker_group_invalid_memory_limits():
    with pytest.raises(ValueError, match="memory_limits='bad'"):
        WorkerGroup(group_name="bad-mem-lim", memory_limits="bad")


def test_worker_group_cpu_requests_must_be_int_or_str():
    with pytest.raises(ValueError, match="cpu_requests=True"):
        WorkerGroup(group_name="bad-cpu-type", cpu_requests=True)


def test_worker_group_memory_requests_must_be_int_or_str():
    with pytest.raises(ValueError, match="memory_requests=None"):
        WorkerGroup(group_name="bad-mem-type", memory_requests=None)


def test_worker_group_invalid_cpu_requests():
    with pytest.raises(ValueError, match="cpu_requests='not-cpu'"):
        WorkerGroup(group_name="bad-cpu", cpu_requests="not-cpu")


def test_worker_group_invalid_memory_requests():
    with pytest.raises(ValueError, match="memory_requests='lots'"):
        WorkerGroup(group_name="bad-mem", memory_requests="lots")


@pytest.mark.parametrize(
    "extended_resources, error_match",
    [
        ([], "must be a dict"),
        ({"": 1}, "names must be non-empty strings"),
        ({"example.com/accelerator": True}, "values must be ints or strings"),
    ],
)
def test_worker_group_extended_resource_validation(extended_resources, error_match):
    with pytest.raises(ValueError, match=error_match):
        WorkerGroup(
            group_name="bad-extended-resource",
            extended_resource_requests=extended_resources,
        )


def test_worker_group_negative_gpu_count():
    with pytest.raises(ValueError, match="gpu_count=-1"):
        WorkerGroup(
            group_name="bad-gpu-count",
            gpu_type="nvidia.com/gpu",
            gpu_count=-1,
        )


def test_cluster_config_additional_worker_groups():
    config = ClusterConfiguration(
        name="multi-group",
        namespace="ns",
        additional_worker_groups=[
            WorkerGroup(group_name="cpu-workers", replicas=4),
            WorkerGroup(
                group_name="gpu-workers",
                replicas=2,
                gpu_type="nvidia.com/gpu",
                gpu_count=4,
            ),
        ],
    )
    assert len(config.additional_worker_groups) == 2
    assert config.additional_worker_groups[0].group_name == "cpu-workers"
    assert config.additional_worker_groups[1].group_name == "gpu-workers"


def test_cluster_config_duplicate_group_names():
    with pytest.raises(ValueError, match="Duplicate worker group name"):
        ClusterConfiguration(
            name="dup-groups",
            namespace="ns",
            additional_worker_groups=[
                WorkerGroup(group_name="same-name", replicas=2),
                WorkerGroup(group_name="same-name", replicas=4),
            ],
        )


def test_cluster_config_group_name_collides_with_default():
    with pytest.raises(
        ValueError, match="conflicts with the default worker group name"
    ):
        ClusterConfiguration(
            name="my-cluster",
            namespace="ns",
            additional_worker_groups=[
                WorkerGroup(group_name="small-group-my-cluster", replicas=2),
            ],
        )


def test_cluster_config_invalid_worker_group_type():
    with pytest.raises(TypeError, match="additional_worker_groups"):
        ClusterConfiguration(
            name="bad-type",
            namespace="ns",
            additional_worker_groups=[{"group_name": "not-a-dataclass"}],
        )


def test_additional_worker_groups_in_yaml(mocker):
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch("kubernetes.client.CustomObjectsApi.list_namespaced_custom_object")

    from kubernetes.client import V1Toleration

    cluster = Cluster(
        ClusterConfiguration(
            name="multi-group-cluster",
            namespace="ns",
            num_workers=2,
            image="quay.io/rhoai/ray:default",
            envs={"CLUSTER_VAR": "base"},
            labels={"team": "ml"},
            additional_worker_groups=[
                WorkerGroup(
                    group_name="gpu-inference",
                    replicas=3,
                    cpu_requests=4,
                    cpu_limits=4,
                    memory_requests="16G",
                    memory_limits="32G",
                    gpu_type="nvidia.com/gpu",
                    gpu_count=2,
                    image="quay.io/rhoai/ray:gpu",
                    envs={"MODEL": "llama", "CLUSTER_VAR": "override"},
                    labels={"accelerator": "gpu", "team": "inference"},
                    tolerations=[
                        V1Toleration(
                            key="nvidia.com/gpu",
                            operator="Exists",
                            effect="NoSchedule",
                        )
                    ],
                ),
            ],
        )
    )

    spec = cluster.resource_yaml["spec"]
    assert len(spec["workerGroupSpecs"]) == 2

    # First group is the default from flat fields
    default_group = spec["workerGroupSpecs"][0]
    assert default_group["groupName"] == "small-group-multi-group-cluster"
    assert default_group["replicas"] == 2

    # Second group is from additional_worker_groups
    gpu_group = spec["workerGroupSpecs"][1]
    assert gpu_group["groupName"] == "gpu-inference"
    assert gpu_group["replicas"] == 3
    assert gpu_group["minReplicas"] == 3
    assert gpu_group["maxReplicas"] == 3

    # Check image
    gpu_container = gpu_group["template"]["spec"]["containers"][0]
    assert gpu_container["image"] == "quay.io/rhoai/ray:gpu"

    # Check GPU resources
    assert gpu_container["resources"]["limits"]["nvidia.com/gpu"] == 2
    assert gpu_container["resources"]["requests"]["nvidia.com/gpu"] == 2

    # Check CPU/memory
    assert gpu_container["resources"]["requests"]["cpu"] == 4
    assert gpu_container["resources"]["limits"]["cpu"] == 4
    assert gpu_container["resources"]["requests"]["memory"] == "16G"
    assert gpu_container["resources"]["limits"]["memory"] == "32G"

    # Check env merge (group overrides cluster)
    env_vars = {e["name"]: e["value"] for e in gpu_container["env"]}
    assert env_vars["CLUSTER_VAR"] == "override"
    assert env_vars["MODEL"] == "llama"
    assert env_vars["RAY_USAGE_STATS_ENABLED"] == "0"

    # Check tolerations
    tolerations = gpu_group["template"]["spec"]["tolerations"]
    assert len(tolerations) == 1
    assert tolerations[0]["key"] == "nvidia.com/gpu"

    # Check ray start params
    assert gpu_group["rayStartParams"]["num-gpus"] == "2"
    assert gpu_group["rayStartParams"]["num-cpus"] == "4"


def test_additional_worker_group_inherits_image(mocker):
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch("kubernetes.client.CustomObjectsApi.list_namespaced_custom_object")

    cluster = Cluster(
        ClusterConfiguration(
            name="inherit-image",
            namespace="ns",
            image="quay.io/rhoai/ray:base-image",
            additional_worker_groups=[
                WorkerGroup(group_name="no-image-group", replicas=1),
            ],
        )
    )

    spec = cluster.resource_yaml["spec"]
    extra_group = spec["workerGroupSpecs"][1]
    container = extra_group["template"]["spec"]["containers"][0]
    assert container["image"] == "quay.io/rhoai/ray:base-image"


def test_additional_worker_group_inherits_tolerations(mocker):
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch("kubernetes.client.CustomObjectsApi.list_namespaced_custom_object")

    from kubernetes.client import V1Toleration

    cluster = Cluster(
        ClusterConfiguration(
            name="inherit-tol",
            namespace="ns",
            worker_tolerations=[
                V1Toleration(key="default-key", operator="Exists", effect="NoSchedule")
            ],
            additional_worker_groups=[
                WorkerGroup(group_name="inherit-group", replicas=1),
            ],
        )
    )

    spec = cluster.resource_yaml["spec"]
    extra_group = spec["workerGroupSpecs"][1]
    tolerations = extra_group["template"]["spec"]["tolerations"]
    assert len(tolerations) == 1
    assert tolerations[0]["key"] == "default-key"


def test_additional_worker_group_with_autoscaling(mocker):
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch("kubernetes.client.CustomObjectsApi.list_namespaced_custom_object")

    cluster = Cluster(
        ClusterConfiguration(
            name="autoscale-groups",
            namespace="ns",
            additional_worker_groups=[
                WorkerGroup(
                    group_name="scaling-group",
                    replicas=2,
                    min_replicas=1,
                    max_replicas=10,
                ),
            ],
        )
    )

    spec = cluster.resource_yaml["spec"]
    extra_group = spec["workerGroupSpecs"][1]
    assert extra_group["replicas"] == 2
    assert extra_group["minReplicas"] == 1
    assert extra_group["maxReplicas"] == 10


def test_additional_worker_groups_empty_by_default(mocker):
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch("kubernetes.client.CustomObjectsApi.list_namespaced_custom_object")

    cluster = Cluster(ClusterConfiguration(name="no-extras", namespace="ns"))

    spec = cluster.resource_yaml["spec"]
    assert len(spec["workerGroupSpecs"]) == 1


def test_additional_worker_group_with_image_pull_secrets(mocker):
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch("kubernetes.client.CustomObjectsApi.list_namespaced_custom_object")

    cluster = Cluster(
        ClusterConfiguration(
            name="pull-secrets",
            namespace="ns",
            image_pull_secrets=["my-registry-secret"],
            additional_worker_groups=[
                WorkerGroup(group_name="with-secrets", replicas=1),
            ],
        )
    )

    spec = cluster.resource_yaml["spec"]
    extra_group = spec["workerGroupSpecs"][1]
    secrets = extra_group["template"]["spec"]["imagePullSecrets"]
    assert len(secrets) == 1
    assert secrets[0]["name"] == "my-registry-secret"


def test_additional_worker_group_empty_tolerations_opts_out(mocker):
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch("kubernetes.client.CustomObjectsApi.list_namespaced_custom_object")

    from kubernetes.client import V1Toleration

    cluster = Cluster(
        ClusterConfiguration(
            name="no-tol-inherit",
            namespace="ns",
            worker_tolerations=[
                V1Toleration(key="default-key", operator="Exists", effect="NoSchedule")
            ],
            additional_worker_groups=[
                WorkerGroup(group_name="no-tol", replicas=1, tolerations=[]),
            ],
        )
    )

    spec = cluster.resource_yaml["spec"]
    extra_group = spec["workerGroupSpecs"][1]
    assert extra_group["template"]["spec"].get("tolerations") is None


def test_additional_worker_group_labels_merge(mocker):
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch("kubernetes.client.CustomObjectsApi.list_namespaced_custom_object")

    cluster = Cluster(
        ClusterConfiguration(
            name="label-merge",
            namespace="ns",
            labels={"team": "ml", "env": "prod"},
            additional_worker_groups=[
                WorkerGroup(
                    group_name="labeled",
                    replicas=1,
                    labels={"team": "inference", "accelerator": "gpu"},
                ),
            ],
        )
    )

    spec = cluster.resource_yaml["spec"]
    extra_group = spec["workerGroupSpecs"][1]
    pod_labels = extra_group["template"]["metadata"]["labels"]
    assert pod_labels["team"] == "inference"
    assert pod_labels["env"] == "prod"
    assert pod_labels["accelerator"] == "gpu"


# Make sure to always keep this function last
def test_cleanup():
    os.remove(f"{cluster_dir}test-all-params.yaml")

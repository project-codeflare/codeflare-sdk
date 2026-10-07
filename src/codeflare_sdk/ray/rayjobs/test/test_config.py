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

"""Tests for rayjobs config module: build_ray_cluster_spec and file volume helpers."""

import pytest
from codeflare_sdk.ray.cluster.config import ClusterConfiguration, WorkerGroup
from codeflare_sdk.ray.rayjobs.config import (
    build_ray_cluster_spec,
    validate_secret_size,
    build_file_secret_spec,
    build_file_volume_specs,
    add_file_volumes,
)
from codeflare_sdk.common.utils.constants import RAY_VERSION
from kubernetes.client import (
    V1Volume,
    V1VolumeMount,
    V1SecretVolumeSource,
    V1Toleration,
)


# --- build_ray_cluster_spec tests ---


def test_build_spec_basic(mocker):
    """Basic spec generation produces expected CRD structure."""
    mocker.patch(
        "codeflare_sdk.ray.cluster.raycluster_spec.update_image",
        return_value="ray:2.58.0-py312",
    )
    config = ClusterConfiguration(num_workers=2)
    spec = build_ray_cluster_spec(config, "test-cluster")

    assert spec["rayVersion"] == RAY_VERSION
    assert spec["enableInTreeAutoscaling"] is False
    assert "headGroupSpec" in spec
    assert "workerGroupSpecs" in spec
    assert len(spec["workerGroupSpecs"]) == 1

    worker = spec["workerGroupSpecs"][0]
    assert worker["replicas"] == 2
    assert worker["minReplicas"] == 2
    assert worker["maxReplicas"] == 2
    assert worker["groupName"] == "small-group-test-cluster"


def test_build_spec_head_ray_params(mocker):
    """Head rayStartParams include num-cpus, num-gpus, resources."""
    mocker.patch(
        "codeflare_sdk.ray.cluster.raycluster_spec.update_image",
        return_value="ray:latest",
    )
    config = ClusterConfiguration(head_cpu_limits=4)
    spec = build_ray_cluster_spec(config, "test")
    params = spec["headGroupSpec"]["rayStartParams"]

    assert "num-cpus" in params
    assert "num-gpus" in params
    assert "resources" in params
    assert params["dashboard-host"] == "0.0.0.0"


def test_build_spec_worker_container_name(mocker):
    """Worker container name is 'machine-learning'."""
    mocker.patch(
        "codeflare_sdk.ray.cluster.raycluster_spec.update_image",
        return_value="ray:latest",
    )
    config = ClusterConfiguration()
    spec = build_ray_cluster_spec(config, "test")
    worker_container = spec["workerGroupSpecs"][0]["template"].spec.containers[0]
    assert worker_container.name == "machine-learning"


def test_build_spec_restart_policy_never(mocker):
    """Pod specs have restartPolicy: Never for RayJob."""
    mocker.patch(
        "codeflare_sdk.ray.cluster.raycluster_spec.update_image",
        return_value="ray:latest",
    )
    config = ClusterConfiguration()
    spec = build_ray_cluster_spec(config, "test")
    head_pod = spec["headGroupSpec"]["template"].spec
    worker_pod = spec["workerGroupSpecs"][0]["template"].spec
    assert head_pod.restart_policy == "Never"
    assert worker_pod.restart_policy == "Never"


def test_build_spec_odh_volumes(mocker):
    """ODH CA cert volumes are always added."""
    mocker.patch(
        "codeflare_sdk.ray.cluster.raycluster_spec.update_image",
        return_value="ray:latest",
    )
    config = ClusterConfiguration()
    spec = build_ray_cluster_spec(config, "test")
    head_volumes = spec["headGroupSpec"]["template"].spec.volumes
    volume_names = [v.name for v in head_volumes]
    assert "odh-trusted-ca-cert" in volume_names
    assert "odh-ca-cert" in volume_names


def test_build_spec_with_gpu(mocker):
    """GPU counts appear in rayStartParams."""
    mocker.patch(
        "codeflare_sdk.ray.cluster.raycluster_spec.update_image",
        return_value="ray:latest",
    )
    config = ClusterConfiguration(
        worker_extended_resource_requests={"nvidia.com/gpu": 2},
    )
    spec = build_ray_cluster_spec(config, "test")
    params = spec["workerGroupSpecs"][0]["rayStartParams"]
    assert params["num-gpus"] == "2"


def test_build_spec_with_environment_variables(mocker):
    """Environment variables are set in containers."""
    mocker.patch(
        "codeflare_sdk.ray.cluster.raycluster_spec.update_image",
        return_value="ray:latest",
    )
    config = ClusterConfiguration(
        envs={"CUDA_VISIBLE_DEVICES": "0", "RAY_DISABLE_IMPORT_WARNING": "1"},
    )
    spec = build_ray_cluster_spec(config, "test-cluster")

    head_container = spec["headGroupSpec"]["template"].spec.containers[0]
    env_vars = {env.name: env.value for env in head_container.env}
    assert env_vars["CUDA_VISIBLE_DEVICES"] == "0"
    assert env_vars["RAY_DISABLE_IMPORT_WARNING"] == "1"

    worker_container = spec["workerGroupSpecs"][0]["template"].spec.containers[0]
    worker_env_vars = {env.name: env.value for env in worker_container.env}
    assert worker_env_vars["CUDA_VISIBLE_DEVICES"] == "0"


def test_build_spec_with_tolerations(mocker):
    """Tolerations are applied to pod specs."""
    mocker.patch(
        "codeflare_sdk.ray.cluster.raycluster_spec.update_image",
        return_value="ray:latest",
    )
    head_toleration = V1Toleration(
        key="node-role.kubernetes.io/master", operator="Exists", effect="NoSchedule"
    )
    worker_toleration = V1Toleration(
        key="nvidia.com/gpu", operator="Exists", effect="NoSchedule"
    )
    config = ClusterConfiguration(
        head_tolerations=[head_toleration],
        worker_tolerations=[worker_toleration],
    )
    spec = build_ray_cluster_spec(config, "test-cluster")

    head_pod = spec["headGroupSpec"]["template"].spec
    assert len(head_pod.tolerations) == 1
    assert head_pod.tolerations[0].key == "node-role.kubernetes.io/master"

    worker_pod = spec["workerGroupSpecs"][0]["template"].spec
    assert len(worker_pod.tolerations) == 1
    assert worker_pod.tolerations[0].key == "nvidia.com/gpu"


def test_build_spec_with_image_pull_secrets(mocker):
    """Image pull secrets are applied to pod specs."""
    mocker.patch(
        "codeflare_sdk.ray.cluster.raycluster_spec.update_image",
        return_value="ray:latest",
    )
    config = ClusterConfiguration(
        image_pull_secrets=["my-registry-secret", "another-secret"]
    )
    spec = build_ray_cluster_spec(config, "test-cluster")

    head_secrets = spec["headGroupSpec"]["template"].spec.image_pull_secrets
    assert len(head_secrets) == 2
    assert head_secrets[0].name == "my-registry-secret"

    worker_secrets = spec["workerGroupSpecs"][0]["template"].spec.image_pull_secrets
    assert len(worker_secrets) == 2


def test_build_spec_with_custom_volumes(mocker):
    """Custom volumes and volume mounts are applied."""
    mocker.patch(
        "codeflare_sdk.ray.cluster.raycluster_spec.update_image",
        return_value="ray:latest",
    )
    custom_volume = V1Volume(name="custom-data", empty_dir={})
    custom_mount = V1VolumeMount(name="custom-data", mount_path="/data")
    config = ClusterConfiguration(
        volumes=[custom_volume],
        volume_mounts=[custom_mount],
    )
    spec = build_ray_cluster_spec(config, "test-cluster")

    head_volumes = spec["headGroupSpec"]["template"].spec.volumes
    assert len(head_volumes) > 1
    volume_names = [v.name for v in head_volumes]
    assert "custom-data" in volume_names
    assert "odh-trusted-ca-cert" in volume_names


def test_build_spec_uses_update_image(mocker):
    """Spec generation calls update_image for containers."""
    mock_update_image = mocker.patch(
        "codeflare_sdk.ray.cluster.raycluster_spec.update_image",
        return_value="mocked-image:latest",
    )
    config = ClusterConfiguration(image="custom-image:v1")
    spec = build_ray_cluster_spec(config, "test-cluster")

    assert mock_update_image.called
    head_container = spec["headGroupSpec"]["template"].spec.containers[0]
    assert head_container.image == "mocked-image:latest"
    worker_container = spec["workerGroupSpecs"][0]["template"].spec.containers[0]
    assert worker_container.image == "mocked-image:latest"


def test_build_spec_image_pull_policy_always(mocker):
    """Image pull policy is Always."""
    mocker.patch(
        "codeflare_sdk.ray.cluster.raycluster_spec.update_image",
        return_value="ray:latest",
    )
    config = ClusterConfiguration()
    spec = build_ray_cluster_spec(config, "test")

    head_container = spec["headGroupSpec"]["template"].spec.containers[0]
    assert head_container.image_pull_policy == "Always"
    worker_container = spec["workerGroupSpecs"][0]["template"].spec.containers[0]
    assert worker_container.image_pull_policy == "Always"


def test_build_spec_autoscaling_disabled_for_kueue(mocker):
    """Autoscaling is disabled and worker replicas are fixed."""
    mocker.patch(
        "codeflare_sdk.ray.cluster.raycluster_spec.update_image",
        return_value="ray:latest",
    )
    config = ClusterConfiguration(num_workers=3)
    spec = build_ray_cluster_spec(config, "kueue-cluster")

    assert spec["enableInTreeAutoscaling"] is False
    worker_spec = spec["workerGroupSpecs"][0]
    assert worker_spec["replicas"] == 3
    assert worker_spec["minReplicas"] == 3
    assert worker_spec["maxReplicas"] == 3


def test_build_spec_default_image_integration(mocker):
    """Spec generation works with default images."""
    mocker.patch(
        "codeflare_sdk.ray.cluster.raycluster_spec.update_image",
        return_value="ray:default",
    )
    config = ClusterConfiguration()
    spec = build_ray_cluster_spec(config, "test-cluster")

    head_container = spec["headGroupSpec"]["template"].spec.containers[0]
    assert head_container.image is not None
    assert len(head_container.image) > 0

    worker_container = spec["workerGroupSpecs"][0]["template"].spec.containers[0]
    assert worker_container.image == head_container.image


# --- File volume helper tests ---


def test_validate_secret_size_under_limit():
    """Files under 1MB pass validation."""
    files = {"test.py": "print('hello')"}
    validate_secret_size(files)


def test_validate_secret_size_over_limit():
    """Files over 1MB raise ValueError."""
    files = {"big.py": "x" * (1024 * 1024 + 1)}
    with pytest.raises(ValueError, match="exceeds 1MB"):
        validate_secret_size(files)


def test_build_file_secret_spec_structure():
    """Secret spec has correct structure and labels."""
    spec = build_file_secret_spec("test-job", "test-ns", {"a.py": "code"})
    assert spec["apiVersion"] == "v1"
    assert spec["kind"] == "Secret"
    assert spec["metadata"]["name"] == "test-job-files"
    assert spec["metadata"]["namespace"] == "test-ns"
    assert spec["metadata"]["labels"]["ray.io/job-name"] == "test-job"
    assert spec["data"] == {"a.py": "code"}


def test_build_file_volume_specs():
    """Volume and mount specs are correct."""
    vol, mount = build_file_volume_specs("my-secret", "/mnt/files")
    assert vol["name"] == "ray-job-files"
    assert vol["secret"]["secretName"] == "my-secret"
    assert mount["name"] == "ray-job-files"
    assert mount["mountPath"] == "/mnt/files"


def test_add_file_volumes_adds_volume_and_mount():
    """add_file_volumes adds volume and mount to config."""
    config = ClusterConfiguration()
    add_file_volumes(config, "my-secret")
    assert len(config.volumes) == 1
    assert config.volumes[0].name == "ray-job-files"
    assert len(config.volume_mounts) == 1
    assert config.volume_mounts[0].name == "ray-job-files"


def test_add_file_volumes_skips_duplicate_volume():
    """add_file_volumes skips if volume already exists."""
    config = ClusterConfiguration()
    config.volumes.append(
        V1Volume(name="ray-job-files", secret=V1SecretVolumeSource(secret_name="old"))
    )
    add_file_volumes(config, "new-secret")
    assert len(config.volumes) == 1
    assert len(config.volume_mounts) == 0


def test_add_file_volumes_skips_duplicate_mount():
    """add_file_volumes skips if mount already exists."""
    config = ClusterConfiguration()
    config.volume_mounts.append(V1VolumeMount(name="ray-job-files", mount_path="/old"))
    add_file_volumes(config, "new-secret")
    assert len(config.volumes) == 0
    assert len(config.volume_mounts) == 1


# --- Additional worker group tests for rayjobs ---


def test_build_spec_with_additional_worker_groups(mocker):
    """Additional worker groups produce extra workerGroupSpecs entries."""
    mocker.patch(
        "codeflare_sdk.ray.cluster.raycluster_spec.update_image",
        return_value="ray:default",
    )
    config = ClusterConfiguration(
        num_workers=2,
        image="ray:default",
        envs={"CLUSTER_VAR": "base"},
        additional_worker_groups=[
            WorkerGroup(
                group_name="gpu-workers",
                replicas=3,
                cpu_requests=4,
                cpu_limits=4,
                memory_requests="16G",
                memory_limits="32G",
                gpu_type="nvidia.com/gpu",
                gpu_count=2,
                image="ray:gpu",
                envs={"MODEL": "llama", "CLUSTER_VAR": "override"},
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
    spec = build_ray_cluster_spec(config, "test-job")

    assert len(spec["workerGroupSpecs"]) == 2

    gpu_group = spec["workerGroupSpecs"][1]
    assert gpu_group["groupName"] == "gpu-workers"
    assert gpu_group["replicas"] == 3
    assert gpu_group["minReplicas"] == 3
    assert gpu_group["maxReplicas"] == 3

    container = gpu_group["template"].spec.containers[0]
    assert container.image == "ray:gpu"
    assert container.resources.limits["nvidia.com/gpu"] == 2
    assert container.resources.requests["nvidia.com/gpu"] == 2
    assert container.resources.requests["cpu"] == 4
    assert container.resources.requests["memory"] == "16G"

    env_vars = {e.name: e.value for e in container.env}
    assert env_vars["CLUSTER_VAR"] == "override"
    assert env_vars["MODEL"] == "llama"
    assert env_vars["RAY_USAGE_STATS_ENABLED"] == "0"

    assert gpu_group["rayStartParams"]["num-gpus"] == "2"
    assert gpu_group["rayStartParams"]["num-cpus"] == "4"

    tolerations = gpu_group["template"].spec.tolerations
    assert len(tolerations) == 1
    assert tolerations[0].key == "nvidia.com/gpu"


def test_build_spec_additional_group_inherits_image(mocker):
    """Worker group with image=None inherits cluster-level image."""
    mocker.patch(
        "codeflare_sdk.ray.rayjobs.config.update_image",
        return_value="ray:inherited",
    )
    config = ClusterConfiguration(
        image="ray:base",
        additional_worker_groups=[
            WorkerGroup(group_name="no-image", replicas=1),
        ],
    )
    spec = build_ray_cluster_spec(config, "test-job")

    extra_group = spec["workerGroupSpecs"][1]
    container = extra_group["template"].spec.containers[0]
    assert container.image == "ray:inherited"


def test_build_spec_additional_group_inherits_tolerations(mocker):
    """Worker group with tolerations=None inherits cluster-level worker_tolerations."""
    mocker.patch(
        "codeflare_sdk.ray.rayjobs.config.update_image",
        return_value="ray:latest",
    )
    config = ClusterConfiguration(
        worker_tolerations=[
            V1Toleration(key="default-key", operator="Exists", effect="NoSchedule")
        ],
        additional_worker_groups=[
            WorkerGroup(group_name="inherit-tol", replicas=1),
        ],
    )
    spec = build_ray_cluster_spec(config, "test-job")

    extra_group = spec["workerGroupSpecs"][1]
    tolerations = extra_group["template"].spec.tolerations
    assert len(tolerations) == 1
    assert tolerations[0].key == "default-key"


def test_build_spec_additional_group_autoscaling(mocker):
    """Worker group with min/max replicas produces correct spec."""
    mocker.patch(
        "codeflare_sdk.ray.rayjobs.config.update_image",
        return_value="ray:latest",
    )
    config = ClusterConfiguration(
        additional_worker_groups=[
            WorkerGroup(
                group_name="scaling",
                replicas=2,
                min_replicas=1,
                max_replicas=10,
            ),
        ],
    )
    spec = build_ray_cluster_spec(config, "test-job")

    extra_group = spec["workerGroupSpecs"][1]
    assert extra_group["replicas"] == 2
    assert extra_group["minReplicas"] == 1
    assert extra_group["maxReplicas"] == 10


def test_build_spec_additional_group_no_gpu(mocker):
    """Worker group without GPU produces num-gpus=0."""
    mocker.patch(
        "codeflare_sdk.ray.rayjobs.config.update_image",
        return_value="ray:latest",
    )
    config = ClusterConfiguration(
        additional_worker_groups=[
            WorkerGroup(group_name="cpu-only", replicas=4),
        ],
    )
    spec = build_ray_cluster_spec(config, "test-job")

    extra_group = spec["workerGroupSpecs"][1]
    assert extra_group["rayStartParams"]["num-gpus"] == "0"


def test_build_spec_additional_group_no_envs(mocker):
    """Worker group with no envs and no cluster envs produces no env list."""
    mocker.patch(
        "codeflare_sdk.ray.rayjobs.config.update_image",
        return_value="ray:latest",
    )
    config = ClusterConfiguration(
        envs={},
        enable_usage_stats=False,
        additional_worker_groups=[
            WorkerGroup(group_name="bare", replicas=1),
        ],
    )
    spec = build_ray_cluster_spec(config, "test-job")

    extra_group = spec["workerGroupSpecs"][1]
    container = extra_group["template"].spec.containers[0]
    env_vars = {e.name: e.value for e in container.env}
    assert env_vars["RAY_USAGE_STATS_ENABLED"] == "0"


def test_build_spec_multiple_additional_groups(mocker):
    """Multiple additional worker groups all appear in spec."""
    mocker.patch(
        "codeflare_sdk.ray.rayjobs.config.update_image",
        return_value="ray:latest",
    )
    config = ClusterConfiguration(
        additional_worker_groups=[
            WorkerGroup(group_name="group-a", replicas=2),
            WorkerGroup(group_name="group-b", replicas=3),
            WorkerGroup(group_name="group-c", replicas=1),
        ],
    )
    spec = build_ray_cluster_spec(config, "test-job")

    assert len(spec["workerGroupSpecs"]) == 4
    group_names = [g["groupName"] for g in spec["workerGroupSpecs"]]
    assert "group-a" in group_names
    assert "group-b" in group_names
    assert "group-c" in group_names


def test_build_spec_additional_group_with_image_pull_secrets(mocker):
    """Image pull secrets from cluster config are applied to additional groups."""
    mocker.patch(
        "codeflare_sdk.ray.rayjobs.config.update_image",
        return_value="ray:latest",
    )
    config = ClusterConfiguration(
        image_pull_secrets=["my-secret"],
        additional_worker_groups=[
            WorkerGroup(group_name="with-secrets", replicas=1),
        ],
    )
    spec = build_ray_cluster_spec(config, "test-job")

    extra_group = spec["workerGroupSpecs"][1]
    secrets = extra_group["template"].spec.image_pull_secrets
    assert len(secrets) == 1
    assert secrets[0].name == "my-secret"


def test_build_spec_additional_group_labels_merge(mocker):
    """Labels from cluster config and worker group are merged on pod template."""
    mocker.patch(
        "codeflare_sdk.ray.rayjobs.config.update_image",
        return_value="ray:latest",
    )
    config = ClusterConfiguration(
        labels={"team": "ml", "env": "prod"},
        additional_worker_groups=[
            WorkerGroup(
                group_name="labeled",
                replicas=1,
                labels={"team": "inference", "accelerator": "gpu"},
            ),
        ],
    )
    spec = build_ray_cluster_spec(config, "test-job")

    extra_group = spec["workerGroupSpecs"][1]
    pod_labels = extra_group["template"].metadata.labels
    assert pod_labels["team"] == "inference"
    assert pod_labels["env"] == "prod"
    assert pod_labels["accelerator"] == "gpu"


def test_build_spec_additional_group_empty_tolerations(mocker):
    """Empty tolerations list opts out of inheritance."""
    mocker.patch(
        "codeflare_sdk.ray.rayjobs.config.update_image",
        return_value="ray:latest",
    )
    config = ClusterConfiguration(
        worker_tolerations=[
            V1Toleration(key="default-key", operator="Exists", effect="NoSchedule")
        ],
        additional_worker_groups=[
            WorkerGroup(group_name="no-tol", replicas=1, tolerations=[]),
        ],
    )
    spec = build_ray_cluster_spec(config, "test-job")

    extra_group = spec["workerGroupSpecs"][1]
    assert extra_group["template"].spec.tolerations is None


def test_build_spec_no_additional_groups(mocker):
    """No additional groups means only the default worker group."""
    mocker.patch(
        "codeflare_sdk.ray.rayjobs.config.update_image",
        return_value="ray:latest",
    )
    config = ClusterConfiguration()
    spec = build_ray_cluster_spec(config, "test-job")
    assert len(spec["workerGroupSpecs"]) == 1


class TestGcsFaultToleranceInRayJobSpec:
    """RHOAIENG-98943: a RayJob-managed cluster must honour GCS fault tolerance.

    Before this, enable_gcs_ft was accepted and validated by
    ClusterConfiguration and then dropped on the floor by this builder, so the
    head node came up with no Redis to recover from and nothing said so.
    """

    def test_options_absent_when_disabled(self, mocker):
        mocker.patch(
            "codeflare_sdk.ray.cluster.raycluster_spec.update_image",
            return_value="ray:latest",
        )
        spec = build_ray_cluster_spec(ClusterConfiguration(), "test-job")
        assert "gcsFaultToleranceOptions" not in spec

    def test_redis_address_reaches_the_embedded_spec(self, mocker):
        mocker.patch(
            "codeflare_sdk.ray.cluster.raycluster_spec.update_image",
            return_value="ray:latest",
        )
        config = ClusterConfiguration(
            enable_gcs_ft=True, redis_address="redis-svc:6379"
        )
        spec = build_ray_cluster_spec(config, "test-job")
        assert spec["gcsFaultToleranceOptions"]["redisAddress"] == "redis-svc:6379"

    def test_external_storage_namespace_and_password_reach_the_spec(self, mocker):
        mocker.patch(
            "codeflare_sdk.ray.cluster.raycluster_spec.update_image",
            return_value="ray:latest",
        )
        config = ClusterConfiguration(
            enable_gcs_ft=True,
            redis_address="redis-svc:6379",
            external_storage_namespace="ft-ns",
            redis_password_secret={"name": "redis-secret", "key": "password"},
        )
        options = build_ray_cluster_spec(config, "test-job")["gcsFaultToleranceOptions"]

        assert options["externalStorageNamespace"] == "ft-ns"
        assert options["redisPassword"] == {
            "valueFrom": {"secretKeyRef": {"name": "redis-secret", "key": "password"}}
        }


class TestLabelsReachPodTemplates:
    """RHOAIENG-98942: config.labels reached additional worker groups only.

    _build_additional_worker_group_spec merged config.labels into its pod
    template, while the head and default worker templates passed annotations
    and nothing else — so ClusterConfiguration(labels=...) landed on extra
    worker groups and nowhere else, with no error.
    """

    def _templates(self, mocker, **kwargs):
        mocker.patch(
            "codeflare_sdk.ray.cluster.raycluster_spec.update_image",
            return_value="ray:latest",
        )
        spec = build_ray_cluster_spec(ClusterConfiguration(**kwargs), "test-job")
        return (
            spec["headGroupSpec"]["template"],
            spec["workerGroupSpecs"][0]["template"],
        )

    def test_labels_land_on_head_and_default_worker(self, mocker):
        head, worker = self._templates(mocker, labels={"team": "ml"})

        assert head.metadata.labels == {"team": "ml"}
        assert worker.metadata.labels == {"team": "ml"}

    def test_labels_coexist_with_annotations(self, mocker):
        head, _ = self._templates(
            mocker, labels={"team": "ml"}, annotations={"example.com/a": "b"}
        )

        assert head.metadata.labels == {"team": "ml"}
        assert head.metadata.annotations == {"example.com/a": "b"}

    def test_no_labels_leaves_metadata_untouched(self, mocker):
        head, worker = self._templates(mocker)

        assert head.metadata is None
        assert worker.metadata is None

    def test_additional_worker_groups_still_merge_group_labels(self, mocker):
        mocker.patch(
            "codeflare_sdk.ray.rayjobs.config.update_image",
            return_value="ray:latest",
        )
        config = ClusterConfiguration(
            labels={"team": "ml"},
            additional_worker_groups=[
                WorkerGroup(group_name="extra", labels={"tier": "gpu"})
            ],
        )
        spec = build_ray_cluster_spec(config, "test-job")

        extra = spec["workerGroupSpecs"][1]["template"]
        assert extra.metadata.labels == {"team": "ml", "tier": "gpu"}

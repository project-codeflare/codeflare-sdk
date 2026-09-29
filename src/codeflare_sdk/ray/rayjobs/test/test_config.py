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
from codeflare_sdk.ray.cluster.config import ClusterConfiguration
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
        "codeflare_sdk.ray.rayjobs.config.update_image",
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
        "codeflare_sdk.ray.rayjobs.config.update_image",
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
        "codeflare_sdk.ray.rayjobs.config.update_image",
        return_value="ray:latest",
    )
    config = ClusterConfiguration()
    spec = build_ray_cluster_spec(config, "test")
    worker_container = spec["workerGroupSpecs"][0]["template"].spec.containers[0]
    assert worker_container.name == "machine-learning"


def test_build_spec_restart_policy_never(mocker):
    """Pod specs have restartPolicy: Never for RayJob."""
    mocker.patch(
        "codeflare_sdk.ray.rayjobs.config.update_image",
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
        "codeflare_sdk.ray.rayjobs.config.update_image",
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
        "codeflare_sdk.ray.rayjobs.config.update_image",
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
        "codeflare_sdk.ray.rayjobs.config.update_image",
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
        "codeflare_sdk.ray.rayjobs.config.update_image",
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
        "codeflare_sdk.ray.rayjobs.config.update_image",
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
        "codeflare_sdk.ray.rayjobs.config.update_image",
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
        "codeflare_sdk.ray.rayjobs.config.update_image",
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
        "codeflare_sdk.ray.rayjobs.config.update_image",
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
        "codeflare_sdk.ray.rayjobs.config.update_image",
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
        "codeflare_sdk.ray.rayjobs.config.update_image",
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

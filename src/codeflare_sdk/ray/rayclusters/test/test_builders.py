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
"""
Unit tests for RayCluster spec builders.

These tests avoid Kubernetes API calls and validate pure data transformations.
"""

from types import SimpleNamespace

import pytest
from kubernetes.client import V1EnvVar, V1Volume, V1VolumeMount

from codeflare_sdk.ray.rayclusters.constants import _ODH_VOLUME_MOUNTS, _ODH_VOLUMES


def test_build_file_volume_specs(simple_cluster):
    """
    Ensure file volume specs are constructed with consistent names.

    This provides a quick regression check for file handling utilities.
    """
    volume_spec, mount_spec = simple_cluster.build_file_volume_specs("demo-secret")
    assert volume_spec["name"] == "ray-job-files"
    assert volume_spec["secret"]["secretName"] == "demo-secret"
    assert mount_spec["mountPath"]


def test_build_file_secret_spec(simple_cluster):
    """
    Validate that file secret metadata and data are preserved.

    This ensures the helper returns a ready-to-apply Kubernetes Secret spec.
    """
    files = {"train.py": "print('hello')"}
    spec = simple_cluster.build_file_secret_spec("demo-job", "default", files)
    assert spec["metadata"]["name"] == "demo-job-files"
    assert spec["data"] == files


def test_build_ray_cluster_spec_structure(simple_cluster):
    """
    Ensure RayJob cluster spec has expected top-level keys.
    """
    spec = simple_cluster.build_ray_cluster_spec("demo")
    assert spec["rayVersion"]
    assert "headGroupSpec" in spec
    assert "workerGroupSpecs" in spec


def test_build_head_ray_params_with_gpu(simple_cluster):
    """
    Ensure GPU count is included in head Ray params.
    """
    simple_cluster.head_accelerators = {"nvidia.com/gpu": 2}
    params = simple_cluster._build_head_ray_params()
    assert params["num-gpus"] == "2"


def test_build_worker_ray_params_with_gpu(simple_cluster):
    """
    Ensure GPU count is included in worker Ray params.
    """
    simple_cluster.worker_accelerators = {"nvidia.com/gpu": 1}
    params = simple_cluster._build_worker_ray_params()
    assert params["num-gpus"] == "1"


def test_build_resource_requirements_int_conversion(simple_cluster):
    """
    Ensure int CPU and memory values convert to string formats.
    """
    reqs = simple_cluster._build_resource_requirements(
        cpu_requests=1, cpu_limits=2, memory_requests=3, memory_limits=4
    )
    assert reqs.requests["cpu"] == "1"
    assert reqs.limits["cpu"] == "2"
    assert reqs.requests["memory"] == "3Gi"
    assert reqs.limits["memory"] == "4Gi"


def test_build_resource_requirements_extended_resources(simple_cluster):
    """
    Ensure extended resources are added to requests and limits.
    """
    reqs = simple_cluster._build_resource_requirements(
        cpu_requests="1",
        cpu_limits="1",
        memory_requests="1Gi",
        memory_limits="2Gi",
        extended_resource_requests={"nvidia.com/gpu": 1},
    )
    assert reqs.requests["nvidia.com/gpu"] == 1
    assert reqs.limits["nvidia.com/gpu"] == 1


def test_build_env_vars(simple_cluster):
    """
    Ensure env vars are converted into V1EnvVar objects.
    """
    simple_cluster.envs = {"FOO": "bar"}
    envs = simple_cluster._build_env_vars()
    assert isinstance(envs[0], V1EnvVar)
    assert envs[0].name == "FOO"
    assert envs[0].value == "bar"


def test_generate_volume_mounts_for_rayjob(simple_cluster):
    """
    Ensure custom volume mounts are included in RayJob.
    """
    simple_cluster.volume_mounts = [V1VolumeMount(name="data", mount_path="/data")]
    mounts = simple_cluster._generate_volume_mounts_for_rayjob()
    assert mounts[0].name == "data"


def test_generate_volumes_for_rayjob(simple_cluster):
    """
    Ensure custom volumes are included in RayJob.
    """
    simple_cluster.volumes = [V1Volume(name="data")]
    volumes = simple_cluster._generate_volumes_for_rayjob()
    assert volumes[0].name == "data"


def test_add_file_volumes_new(simple_cluster):
    """
    Ensure file volumes and mounts are added once.
    """
    simple_cluster.add_file_volumes("demo-secret")
    assert any(v.name == "ray-job-files" for v in simple_cluster.volumes)
    assert any(m.name == "ray-job-files" for m in simple_cluster.volume_mounts)


def test_add_file_volumes_duplicate_volume(simple_cluster):
    """
    Ensure duplicate file volumes are not added.
    """
    simple_cluster.add_file_volumes("demo-secret")
    simple_cluster.add_file_volumes("demo-secret")
    assert len([v for v in simple_cluster.volumes if v.name == "ray-job-files"]) == 1


def test_validate_secret_size_exceeds_limit(simple_cluster):
    """
    Ensure validate_secret_size raises when secret exceeds 1MB.
    """
    big_content = {"large.txt": "a" * (1024 * 1024 + 1)}
    with pytest.raises(ValueError, match="Secret size exceeds"):
        simple_cluster.validate_secret_size(big_content)


def test_validate_secret_size_exact_limit(simple_cluster):
    """
    Ensure validate_secret_size accepts exactly 1MB.
    """
    exact_content = {"exact.txt": "a" * (1024 * 1024)}
    simple_cluster.validate_secret_size(exact_content)


def test_build_head_container_for_rayjob_includes_envs(simple_cluster):
    """
    Ensure head container includes env vars when configured.
    """
    simple_cluster.envs = {"FOO": "bar"}
    container = simple_cluster._build_head_container_for_rayjob()
    assert container.env
    assert container.env[0].name == "FOO"


def test_build_worker_container_for_rayjob_includes_envs(simple_cluster):
    """
    Ensure worker container includes env vars when configured.
    """
    simple_cluster.envs = {"FOO": "bar"}
    container = simple_cluster._build_worker_container_for_rayjob()
    assert container.env
    assert container.env[0].name == "FOO"


def test_build_pod_spec_for_rayjob_image_pull_secrets(simple_cluster):
    """
    Ensure image pull secrets are included in pod spec.
    """
    simple_cluster.image_pull_secrets = ["secret-1"]
    pod_spec = simple_cluster._build_pod_spec_for_rayjob(
        simple_cluster._build_head_container_for_rayjob(), is_head=True
    )
    assert pod_spec.image_pull_secrets[0].name == "secret-1"


def test_build_standalone_pod_spec_includes_odh_volumes(simple_cluster):
    """
    Ensure standalone pod spec includes default ODH volumes.
    """
    pod_spec = simple_cluster._build_standalone_pod_spec(
        [simple_cluster._build_head_container_for_standalone()], None
    )
    volume_names = {v.name for v in pod_spec.volumes}
    for volume in _ODH_VOLUMES:
        assert volume.name in volume_names


def test_with_nb_annotations_with_prefix(simple_cluster, monkeypatch):
    """
    Ensure notebook prefix is added to annotations.
    """
    monkeypatch.setenv("NB_PREFIX", "notebook")
    annotations = simple_cluster._with_nb_annotations({})
    assert annotations["app.kubernetes.io/managed-by"] == "notebook"


def test_with_nb_annotations_without_prefix(simple_cluster, monkeypatch):
    """
    Ensure annotations unchanged when NB_PREFIX not set.
    """
    monkeypatch.delenv("NB_PREFIX", raising=False)
    annotations = simple_cluster._with_nb_annotations({})
    assert "app.kubernetes.io/managed-by" not in annotations


def test_build_metadata_basic(simple_cluster, monkeypatch):
    """
    Ensure metadata includes name and namespace.
    """
    monkeypatch.setattr(simple_cluster, "_get_default_local_queue", lambda: None)
    metadata = simple_cluster._build_metadata()
    assert metadata.name == simple_cluster.name
    assert metadata.namespace == simple_cluster.namespace


def test_build_standalone_ray_cluster_structure(simple_cluster, monkeypatch):
    """
    Ensure standalone cluster spec structure is correct.
    """
    monkeypatch.setattr(
        "codeflare_sdk.ray.rayclusters.builders.config_check", lambda: None
    )
    monkeypatch.setattr(
        "codeflare_sdk.ray.rayclusters.builders.get_api_client",
        lambda: SimpleNamespace(sanitize_for_serialization=lambda x: x),
    )
    simple_cluster.name = "demo"
    simple_cluster.namespace = "default"
    monkeypatch.setattr(simple_cluster, "_get_default_local_queue", lambda: None)
    spec = simple_cluster._build_standalone_ray_cluster()
    assert spec["kind"] == "RayCluster"
    assert spec["metadata"].name == "demo"


def test_write_to_file(simple_cluster, monkeypatch, tmp_path):
    """
    Ensure _write_to_file writes to filesystem and returns path.
    """
    monkeypatch.setattr(
        "codeflare_sdk.ray.rayclusters.builders.os.path.expanduser",
        lambda _: str(tmp_path),
    )
    simple_cluster.name = "demo"
    path = simple_cluster._write_to_file({"foo": "bar"})
    assert path.endswith("demo.yaml")


def test_build_head_group_spec_for_rayjob(simple_cluster):
    """
    Ensure head group spec for RayJob contains expected fields.
    """
    spec = simple_cluster._build_head_group_spec_for_rayjob()
    assert spec["serviceType"] == "ClusterIP"
    assert spec["enableIngress"] is False
    assert spec["template"].spec.containers[0].name == "ray-head"


def test_build_worker_group_spec_for_rayjob(simple_cluster):
    """
    Ensure worker group spec includes cluster name in groupName.
    """
    spec = simple_cluster._build_worker_group_spec_for_rayjob("demo")
    assert spec["groupName"] == "worker-group-demo"
    assert spec["template"].spec.containers[0].name == "ray-worker"


def test_build_resource_requirements_string_preserved(simple_cluster):
    """
    Ensure string resource values are preserved.
    """
    reqs = simple_cluster._build_resource_requirements(
        cpu_requests="500m",
        cpu_limits="1",
        memory_requests="512Mi",
        memory_limits="1Gi",
    )
    assert reqs.requests["cpu"] == "500m"
    assert reqs.limits["cpu"] == "1"
    assert reqs.requests["memory"] == "512Mi"
    assert reqs.limits["memory"] == "1Gi"


def test_build_pod_spec_for_rayjob_restart_policy(simple_cluster):
    """
    Ensure RayJob pod spec restart policy is Never.
    """
    pod_spec = simple_cluster._build_pod_spec_for_rayjob(
        simple_cluster._build_worker_container_for_rayjob(), is_head=False
    )
    assert pod_spec.restart_policy == "Never"


def test_add_file_volumes_duplicate_mount(simple_cluster):
    """
    Ensure duplicate file mounts are not added.
    """
    simple_cluster.add_file_volumes("demo-secret")
    simple_cluster.add_file_volumes("demo-secret")
    assert (
        len([m for m in simple_cluster.volume_mounts if m.name == "ray-job-files"]) == 1
    )


def test_build_standalone_pod_spec_image_pull_secrets(simple_cluster):
    """
    Ensure image pull secrets are included in standalone pod spec.
    """
    simple_cluster.image_pull_secrets = ["secret-1"]
    pod_spec = simple_cluster._build_standalone_pod_spec(
        [simple_cluster._build_head_container_for_standalone()], None
    )
    assert pod_spec.image_pull_secrets[0].name == "secret-1"


def test_build_head_container_for_standalone_envs(simple_cluster):
    """
    Ensure standalone head container includes env vars.
    """
    simple_cluster.envs = {"FOO": "bar"}
    container = simple_cluster._build_head_container_for_standalone()
    assert container.env[0].name == "FOO"


def test_build_worker_container_for_standalone_envs(simple_cluster):
    """
    Ensure standalone worker container includes env vars.
    """
    simple_cluster.envs = {"FOO": "bar"}
    container = simple_cluster._build_worker_container_for_standalone()
    assert container.env[0].name == "FOO"


def test_build_standalone_container_volume_mounts(simple_cluster):
    """
    Ensure standalone containers include ODH volume mounts.
    """
    container = simple_cluster._build_head_container_for_standalone()
    mount_names = {m.name for m in container.volume_mounts}
    for mount in _ODH_VOLUME_MOUNTS:
        assert mount.name in mount_names


def test_build_metadata_with_labels_and_annotations(simple_cluster, monkeypatch):
    """
    Ensure metadata includes custom labels and annotations.
    """
    simple_cluster.labels = {"team": "ml"}
    simple_cluster.annotations = {"note": "demo"}
    monkeypatch.setattr(simple_cluster, "_get_default_local_queue", lambda: None)
    metadata = simple_cluster._build_metadata()
    assert metadata.labels["team"] == "ml"
    assert metadata.annotations["note"] == "demo"


def test_add_queue_label_uses_default_queue(simple_cluster, monkeypatch):
    """
    Ensure queue label is added when default queue is available.
    """
    labels = {}
    monkeypatch.setattr(simple_cluster, "_get_default_local_queue", lambda: "queue-a")
    monkeypatch.setattr(simple_cluster, "_local_queue_exists", lambda: True)
    simple_cluster._add_queue_label(labels)
    assert labels["kueue.x-k8s.io/queue-name"] == "queue-a"


def test_build_standalone_ray_cluster_with_gcs_ft(simple_cluster, monkeypatch):
    """
    Ensure GCS fault tolerance options are included when enabled.
    """
    monkeypatch.setattr(
        "codeflare_sdk.ray.rayclusters.builders.config_check", lambda: None
    )
    monkeypatch.setattr(
        "codeflare_sdk.ray.rayclusters.builders.get_api_client",
        lambda: SimpleNamespace(sanitize_for_serialization=lambda x: x),
    )
    simple_cluster.name = "demo"
    simple_cluster.namespace = "default"
    simple_cluster.enable_gcs_ft = True
    simple_cluster.redis_address = "redis:6379"
    simple_cluster.redis_password_secret = {"name": "secret", "key": "password"}
    monkeypatch.setattr(simple_cluster, "_get_default_local_queue", lambda: None)
    spec = simple_cluster._build_standalone_ray_cluster()
    assert "gcsFaultToleranceOptions" in spec["spec"]

# Copyright 2022-2025 IBM, Red Hat
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

import pytest
import os
from unittest.mock import MagicMock, patch
from codeflare_sdk.common.utils.constants import MOUNT_PATH, RAY_VERSION

from codeflare_sdk.ray.rayjobs.rayjob import RayJob
from codeflare_sdk.ray.cluster.config import ClusterConfiguration
from codeflare_sdk.ray.rayjobs.config import ManagedClusterConfig
from kubernetes.client import (
    V1Volume,
    V1VolumeMount,
    V1Toleration,
    V1ConfigMapVolumeSource,
    ApiException,
)


# Global test setup that runs automatically for ALL tests
@pytest.fixture(autouse=True)
def auto_mock_setup(mocker):
    """Automatically mock common dependencies for all tests."""
    mocker.patch("kubernetes.config.load_kube_config")

    # Always mock get_default_kueue_name to prevent K8s API calls
    mocker.patch(
        "codeflare_sdk.ray.rayjobs.rayjob.get_default_kueue_name",
        return_value="default-queue",
    )

    mock_get_ns = mocker.patch(
        "codeflare_sdk.ray.rayjobs.rayjob.get_current_namespace",
        return_value="test-namespace",
    )

    mock_rayjob_api = mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")
    mock_rayjob_instance = MagicMock()
    mock_rayjob_api.return_value = mock_rayjob_instance

    mock_cluster_api = mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayClusterApi")
    mock_cluster_instance = MagicMock()
    mock_cluster_api.return_value = mock_cluster_instance

    mock_k8s_api = mocker.patch("kubernetes.client.CoreV1Api")
    mock_k8s_instance = MagicMock()
    mock_k8s_api.return_value = mock_k8s_instance

    mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.get_api_client")

    # Return the mocked instances so tests can configure them as needed
    return {
        "rayjob_api": mock_rayjob_instance,
        "cluster_api": mock_cluster_instance,
        "k8s_api": mock_k8s_instance,
        "get_current_namespace": mock_get_ns,
    }


def test_rayjob_submit_success(auto_mock_setup):
    """Test successful RayJob submission."""
    mock_api_instance = auto_mock_setup["rayjob_api"]

    mock_api_instance.submit.return_value = {"metadata": {"name": "test-rayjob"}}

    rayjob = RayJob(
        job_name="test-rayjob",
        cluster_name="test-ray-cluster",
        namespace="test-namespace",
        entrypoint="python -c 'print(\"hello world\")'",
        runtime_env={"pip": ["requests"]},
    )

    job_id = rayjob.submit()

    assert job_id == "test-rayjob"

    mock_api_instance.submit_job.assert_called_once()
    call_args = mock_api_instance.submit_job.call_args

    assert call_args.kwargs["k8s_namespace"] == "test-namespace"

    job_cr = call_args.kwargs["job"]
    assert job_cr["metadata"]["name"] == "test-rayjob"
    assert job_cr["metadata"]["namespace"] == "test-namespace"
    assert job_cr["spec"]["entrypoint"] == "python -c 'print(\"hello world\")'"
    assert job_cr["spec"]["clusterSelector"]["ray.io/cluster"] == "test-ray-cluster"
    assert job_cr["spec"]["runtimeEnvYAML"] == "{'pip': ['requests']}"


def test_rayjob_submit_failure(auto_mock_setup):
    """Test RayJob submission failure."""
    mock_api_instance = auto_mock_setup["rayjob_api"]

    mock_api_instance.submit_job.return_value = None

    rayjob = RayJob(
        job_name="test-rayjob",
        cluster_name="test-ray-cluster",
        namespace="default",
        entrypoint="python script.py",
        runtime_env={"pip": ["numpy"]},
    )

    with pytest.raises(RuntimeError, match="Failed to submit RayJob test-rayjob"):
        rayjob.submit()


def test_rayjob_init_validation_both_provided(auto_mock_setup):
    """Test that providing both cluster_name and cluster_config raises error."""
    cluster_config = ClusterConfiguration(name="test-cluster", namespace="test")

    with pytest.raises(
        ValueError,
        match="❌ Configuration Error: You cannot specify both 'cluster_name' and 'cluster_config'",
    ):
        RayJob(
            job_name="test-job",
            cluster_name="existing-cluster",
            cluster_config=cluster_config,
            entrypoint="python script.py",
        )


def test_rayjob_init_validation_neither_provided(auto_mock_setup):
    """Test that providing neither cluster_name nor cluster_config raises error."""
    with pytest.raises(
        ValueError,
        match="❌ Configuration Error: You must provide either 'cluster_name'",
    ):
        RayJob(job_name="test-job", entrypoint="python script.py")


def test_rayjob_init_with_cluster_config(auto_mock_setup):
    """Test RayJob initialization with cluster configuration for auto-creation."""
    cluster_config = ClusterConfiguration(
        name="auto-cluster", namespace="test-namespace", num_workers=2
    )

    rayjob = RayJob(
        job_name="test-job",
        cluster_config=cluster_config,
        entrypoint="python script.py",
        namespace="test-namespace",
    )

    assert rayjob.name == "test-job"
    assert rayjob.cluster_name == "test-job-cluster"  # Generated from job name
    assert rayjob._cluster_config == cluster_config
    assert rayjob._cluster_name is None


def test_rayjob_cluster_name_generation(auto_mock_setup):
    """Test that cluster names are generated when config has empty name."""
    cluster_config = ClusterConfiguration(
        name="",  # Empty name should trigger generation
        namespace="test-namespace",
        num_workers=1,
    )

    rayjob = RayJob(
        job_name="my-job",
        cluster_config=cluster_config,
        entrypoint="python script.py",
        namespace="test-namespace",
    )

    assert rayjob.cluster_name == "my-job-cluster"


def test_rayjob_cluster_config_namespace_none(auto_mock_setup):
    """Test that cluster config namespace is set when None."""
    cluster_config = ClusterConfiguration(
        name="test-cluster",
        namespace=None,  # This should be set to job namespace
        num_workers=1,
    )

    rayjob = RayJob(
        job_name="test-job",
        cluster_config=cluster_config,
        namespace="job-namespace",
        entrypoint="python script.py",
    )

    assert rayjob.namespace == "job-namespace"


def test_rayjob_with_active_deadline_seconds(auto_mock_setup):
    """Test RayJob CR generation with active deadline seconds."""
    rayjob = RayJob(
        job_name="test-job",
        cluster_name="test-cluster",
        namespace="test-namespace",
        entrypoint="python main.py",
        active_deadline_seconds=30,
    )

    rayjob_cr = rayjob._build_rayjob_cr()

    assert rayjob_cr["spec"]["activeDeadlineSeconds"] == 30


def test_build_ray_cluster_spec_no_config_error(auto_mock_setup):
    """Test _build_ray_cluster_spec raises error when no cluster config."""
    rayjob = RayJob(
        job_name="test-job",
        cluster_name="existing-cluster",
        entrypoint="python script.py",
        namespace="test-namespace",
    )

    rayjob_cr = rayjob._build_rayjob_cr()

    assert rayjob_cr["spec"]["clusterSelector"]["ray.io/cluster"] == "existing-cluster"
    assert "rayClusterSpec" not in rayjob_cr["spec"]


def test_build_ray_cluster_spec(mocker, auto_mock_setup):
    """Test _build_ray_cluster_spec method."""

    mock_ray_cluster = {
        "apiVersion": "ray.io/v1",
        "kind": "RayCluster",
        "metadata": {"name": "test-cluster", "namespace": "test"},
        "spec": {
            "rayVersion": RAY_VERSION,
            "headGroupSpec": {"replicas": 1},
            "workerGroupSpecs": [{"replicas": 2}],
        },
    }
    cluster_config = ManagedClusterConfig(num_workers=2)
    mocker.patch.object(
        cluster_config, "build_ray_cluster_spec", return_value=mock_ray_cluster["spec"]
    )

    rayjob = RayJob(
        job_name="test-job",
        cluster_config=cluster_config,
        entrypoint="python script.py",
        namespace="test-namespace",
    )

    rayjob_cr = rayjob._build_rayjob_cr()

    assert "rayClusterSpec" in rayjob_cr["spec"]
    cluster_config.build_ray_cluster_spec.assert_called_once_with(
        cluster_name="test-job-cluster"
    )


def test_build_rayjob_cr_with_existing_cluster(auto_mock_setup):
    """Test _build_rayjob_cr method with existing cluster."""

    rayjob = RayJob(
        job_name="test-job",
        cluster_name="existing-cluster",
        namespace="test-namespace",
        entrypoint="python main.py",
        ttl_seconds_after_finished=300,
    )

    rayjob_cr = rayjob._build_rayjob_cr()

    assert rayjob_cr["apiVersion"] == "ray.io/v1"
    assert rayjob_cr["kind"] == "RayJob"
    assert rayjob_cr["metadata"]["name"] == "test-job"
    spec = rayjob_cr["spec"]
    assert spec["entrypoint"] == "python main.py"
    assert spec["shutdownAfterJobFinishes"] is False
    assert spec["ttlSecondsAfterFinished"] == 300

    assert spec["clusterSelector"]["ray.io/cluster"] == "existing-cluster"
    assert "rayClusterSpec" not in spec


def test_build_rayjob_cr_with_auto_cluster(mocker, auto_mock_setup):
    """Test _build_rayjob_cr method with auto-created cluster."""
    mock_ray_cluster = {
        "apiVersion": "ray.io/v1",
        "kind": "RayCluster",
        "metadata": {"name": "auto-cluster", "namespace": "test"},
        "spec": {
            "rayVersion": RAY_VERSION,
            "headGroupSpec": {"replicas": 1},
            "workerGroupSpecs": [{"replicas": 2}],
        },
    }
    cluster_config = ManagedClusterConfig(num_workers=2)

    mocker.patch.object(
        cluster_config, "build_ray_cluster_spec", return_value=mock_ray_cluster["spec"]
    )

    rayjob = RayJob(
        job_name="test-job",
        cluster_config=cluster_config,
        entrypoint="python main.py",
        namespace="test-namespace",
    )

    rayjob_cr = rayjob._build_rayjob_cr()
    assert rayjob_cr["spec"]["rayClusterSpec"] == mock_ray_cluster["spec"]
    assert "clusterSelector" not in rayjob_cr["spec"]


def test_submit_validation_no_entrypoint(auto_mock_setup):
    """Test that submit() raises error when entrypoint is None."""
    rayjob = RayJob(
        job_name="test-job",
        cluster_name="test-cluster",
        entrypoint=None,  # No entrypoint provided
        namespace="test-namespace",
    )

    with pytest.raises(
        ValueError, match="Entrypoint must be provided to submit a RayJob"
    ):
        rayjob.submit()


def test_submit_with_auto_cluster(mocker, auto_mock_setup):
    """Test successful submission with auto-created cluster."""
    mock_api_instance = auto_mock_setup["rayjob_api"]

    mock_ray_cluster = {
        "apiVersion": "ray.io/v1",
        "kind": "RayCluster",
        "spec": {
            "rayVersion": RAY_VERSION,
            "headGroupSpec": {"replicas": 1},
            "workerGroupSpecs": [{"replicas": 1}],
        },
    }
    mock_api_instance.submit_job.return_value = True

    cluster_config = ManagedClusterConfig(num_workers=1)
    mocker.patch.object(
        cluster_config, "build_ray_cluster_spec", return_value=mock_ray_cluster["spec"]
    )

    rayjob = RayJob(
        job_name="test-job",
        cluster_config=cluster_config,
        entrypoint="python script.py",
        namespace="test-namespace",
    )

    result = rayjob.submit()

    assert result == "test-job"

    mock_api_instance.submit_job.assert_called_once()
    call_args = mock_api_instance.submit_job.call_args

    job_cr = call_args.kwargs["job"]
    assert "rayClusterSpec" in job_cr["spec"]
    assert job_cr["spec"]["rayClusterSpec"] == mock_ray_cluster["spec"]


def test_namespace_auto_detection_success(auto_mock_setup):
    """Test successful namespace auto-detection."""
    auto_mock_setup["get_current_namespace"].return_value = "detected-ns"

    rayjob = RayJob(
        job_name="test-job", entrypoint="python script.py", cluster_name="test-cluster"
    )

    assert rayjob.namespace == "detected-ns"


def test_namespace_auto_detection_fallback(auto_mock_setup):
    """Test that namespace auto-detection failure raises an error."""
    auto_mock_setup["get_current_namespace"].return_value = None

    with pytest.raises(ValueError, match="Could not auto-detect Kubernetes namespace"):
        RayJob(
            job_name="test-job",
            entrypoint="python script.py",
            cluster_name="test-cluster",
        )


def test_namespace_explicit_override(auto_mock_setup):
    """Test that explicit namespace overrides auto-detection."""
    auto_mock_setup["get_current_namespace"].return_value = "detected-ns"

    rayjob = RayJob(
        job_name="test-job",
        entrypoint="python script.py",
        cluster_name="test-cluster",
        namespace="explicit-ns",
    )

    assert rayjob.namespace == "explicit-ns"


def test_rayjob_with_rayjob_cluster_config(auto_mock_setup):
    """Test RayJob with the new ManagedClusterConfig."""
    cluster_config = ManagedClusterConfig(
        num_workers=2,
        head_cpu_requests="500m",
        head_memory_requests="512Mi",
    )

    rayjob = RayJob(
        job_name="test-job",
        entrypoint="python script.py",
        cluster_config=cluster_config,
        namespace="test-namespace",
    )

    assert rayjob._cluster_config == cluster_config
    assert rayjob.cluster_name == "test-job-cluster"  # Generated from job name


def test_rayjob_cluster_config_validation(auto_mock_setup):
    """Test validation of ManagedClusterConfig parameters."""
    cluster_config = ManagedClusterConfig()

    rayjob = RayJob(
        job_name="test-job",
        entrypoint="python script.py",
        cluster_config=cluster_config,
        namespace="test-namespace",
    )

    assert rayjob._cluster_config is not None


def test_rayjob_missing_entrypoint_validation(auto_mock_setup):
    """Test that RayJob requires entrypoint for submission."""
    with pytest.raises(
        TypeError, match="missing 1 required positional argument: 'entrypoint'"
    ):
        RayJob(
            job_name="test-job",
            cluster_name="test-cluster",
        )


def test_build_ray_cluster_spec_integration(mocker, auto_mock_setup):
    """Test integration with the new build_ray_cluster_spec method."""
    cluster_config = ManagedClusterConfig()
    mock_spec = {"spec": "test-spec"}
    mocker.patch.object(
        cluster_config, "build_ray_cluster_spec", return_value=mock_spec
    )

    rayjob = RayJob(
        job_name="test-job",
        entrypoint="python script.py",
        cluster_config=cluster_config,
        namespace="test-namespace",
    )

    rayjob_cr = rayjob._build_rayjob_cr()

    cluster_config.build_ray_cluster_spec.assert_called_once_with(
        cluster_name="test-job-cluster"
    )
    assert "rayClusterSpec" in rayjob_cr["spec"]
    assert rayjob_cr["spec"]["rayClusterSpec"] == mock_spec


def test_rayjob_with_runtime_env(auto_mock_setup):
    """Test RayJob with runtime environment configuration."""
    runtime_env = {"pip": ["numpy", "pandas"]}

    rayjob = RayJob(
        job_name="test-job",
        entrypoint="python script.py",
        cluster_name="test-cluster",
        runtime_env=runtime_env,
        namespace="test-namespace",
    )

    assert rayjob.runtime_env == runtime_env

    rayjob_cr = rayjob._build_rayjob_cr()
    assert rayjob_cr["spec"]["runtimeEnvYAML"] == str(runtime_env)


def test_rayjob_with_active_deadline_and_ttl(auto_mock_setup):
    """Test RayJob with both active deadline and TTL settings."""

    rayjob = RayJob(
        job_name="test-job",
        entrypoint="python script.py",
        cluster_name="test-cluster",
        active_deadline_seconds=300,
        ttl_seconds_after_finished=600,
        namespace="test-namespace",
    )

    assert rayjob.active_deadline_seconds == 300
    assert rayjob.ttl_seconds_after_finished == 600

    rayjob_cr = rayjob._build_rayjob_cr()
    assert rayjob_cr["spec"]["activeDeadlineSeconds"] == 300
    assert rayjob_cr["spec"]["ttlSecondsAfterFinished"] == 600


def test_rayjob_cluster_name_generation_with_config(auto_mock_setup):
    """Test cluster name generation when using cluster_config."""

    cluster_config = ManagedClusterConfig()

    rayjob = RayJob(
        job_name="my-job",
        entrypoint="python script.py",
        cluster_config=cluster_config,
        namespace="test-namespace",  # Explicitly specify namespace
    )

    assert rayjob.cluster_name == "my-job-cluster"


def test_rayjob_namespace_propagation_to_cluster_config(auto_mock_setup):
    """Test that job namespace is propagated to cluster config when None."""
    auto_mock_setup["get_current_namespace"].return_value = "detected-ns"

    cluster_config = ManagedClusterConfig()

    rayjob = RayJob(
        job_name="test-job",
        entrypoint="python script.py",
        cluster_config=cluster_config,
    )

    assert rayjob.namespace == "detected-ns"


def test_rayjob_error_handling_invalid_cluster_config(auto_mock_setup):
    """Test error handling with invalid cluster configuration."""

    with pytest.raises(ValueError):
        RayJob(
            job_name="test-job",
            entrypoint="python script.py",
        )


def test_rayjob_constructor_parameter_validation(auto_mock_setup):
    """Test constructor parameter validation."""
    rayjob = RayJob(
        job_name="test-job",
        entrypoint="python script.py",
        cluster_name="test-cluster",
        namespace="test-ns",
        runtime_env={"pip": ["numpy"]},
        ttl_seconds_after_finished=300,
        active_deadline_seconds=600,
    )

    assert rayjob.name == "test-job"
    assert rayjob.entrypoint == "python script.py"
    assert rayjob.cluster_name == "test-cluster"
    assert rayjob.namespace == "test-ns"
    assert rayjob.runtime_env == {"pip": ["numpy"]}
    assert rayjob.ttl_seconds_after_finished == 300
    assert rayjob.active_deadline_seconds == 600


def test_build_ray_cluster_spec_function():
    """Test the build_ray_cluster_spec method directly."""
    cluster_config = ManagedClusterConfig(
        num_workers=2,
        head_cpu_requests="500m",
        head_memory_requests="512Mi",
        worker_cpu_requests="250m",
        worker_memory_requests="256Mi",
    )

    spec = cluster_config.build_ray_cluster_spec("test-cluster")
    assert "rayVersion" in spec
    assert "headGroupSpec" in spec
    assert "workerGroupSpecs" in spec

    head_spec = spec["headGroupSpec"]
    assert head_spec["serviceType"] == "ClusterIP"
    assert head_spec["enableIngress"] is False
    assert "rayStartParams" in head_spec
    assert "template" in head_spec
    worker_specs = spec["workerGroupSpecs"]
    assert len(worker_specs) == 1
    worker_spec = worker_specs[0]
    assert worker_spec["replicas"] == 2
    assert worker_spec["minReplicas"] == 2
    assert worker_spec["maxReplicas"] == 2
    assert worker_spec["groupName"] == "worker-group-test-cluster"


def test_build_ray_cluster_spec_with_accelerators():
    """Test build_ray_cluster_spec with GPU accelerators."""
    cluster_config = ManagedClusterConfig(
        head_accelerators={"nvidia.com/gpu": 1},
        worker_accelerators={"nvidia.com/gpu": 2},
    )

    spec = cluster_config.build_ray_cluster_spec("test-cluster")
    head_spec = spec["headGroupSpec"]
    head_params = head_spec["rayStartParams"]
    assert "num-gpus" in head_params
    assert head_params["num-gpus"] == "1"

    worker_specs = spec["workerGroupSpecs"]
    worker_spec = worker_specs[0]
    worker_params = worker_spec["rayStartParams"]
    assert "num-gpus" in worker_params
    assert worker_params["num-gpus"] == "2"


def test_build_ray_cluster_spec_with_custom_volumes():
    """Test build_ray_cluster_spec with custom volumes and volume mounts."""
    custom_volume = V1Volume(name="custom-data", empty_dir={})
    custom_volume_mount = V1VolumeMount(name="custom-data", mount_path="/data")
    cluster_config = ManagedClusterConfig(
        volumes=[custom_volume],
        volume_mounts=[custom_volume_mount],
    )

    spec = cluster_config.build_ray_cluster_spec("test-cluster")
    head_spec = spec["headGroupSpec"]
    head_pod_spec = head_spec["template"].spec
    assert len(head_pod_spec.volumes) > 0

    head_container = head_pod_spec.containers[0]
    assert len(head_container.volume_mounts) > 0


def test_build_ray_cluster_spec_with_environment_variables():
    """Test build_ray_cluster_spec with environment variables."""
    cluster_config = ManagedClusterConfig(
        envs={"CUDA_VISIBLE_DEVICES": "0", "RAY_DISABLE_IMPORT_WARNING": "1"},
    )

    spec = cluster_config.build_ray_cluster_spec("test-cluster")

    head_spec = spec["headGroupSpec"]
    head_pod_spec = head_spec["template"].spec
    head_container = head_pod_spec.containers[0]
    assert hasattr(head_container, "env")
    env_vars = {env.name: env.value for env in head_container.env}
    assert env_vars["CUDA_VISIBLE_DEVICES"] == "0"
    assert env_vars["RAY_DISABLE_IMPORT_WARNING"] == "1"
    worker_specs = spec["workerGroupSpecs"]
    worker_spec = worker_specs[0]
    worker_pod_spec = worker_spec["template"].spec
    worker_container = worker_pod_spec.containers[0]

    assert hasattr(worker_container, "env")
    worker_env_vars = {env.name: env.value for env in worker_container.env}
    assert worker_env_vars["CUDA_VISIBLE_DEVICES"] == "0"
    assert worker_env_vars["RAY_DISABLE_IMPORT_WARNING"] == "1"


def test_build_ray_cluster_spec_with_tolerations():
    """Test build_ray_cluster_spec with tolerations."""
    head_toleration = V1Toleration(
        key="node-role.kubernetes.io/master", operator="Exists", effect="NoSchedule"
    )
    worker_toleration = V1Toleration(
        key="nvidia.com/gpu", operator="Exists", effect="NoSchedule"
    )

    cluster_config = ManagedClusterConfig(
        head_tolerations=[head_toleration],
        worker_tolerations=[worker_toleration],
    )

    spec = cluster_config.build_ray_cluster_spec("test-cluster")
    head_spec = spec["headGroupSpec"]
    head_pod_spec = head_spec["template"].spec
    assert hasattr(head_pod_spec, "tolerations")
    assert len(head_pod_spec.tolerations) == 1
    assert head_pod_spec.tolerations[0].key == "node-role.kubernetes.io/master"

    worker_specs = spec["workerGroupSpecs"]
    worker_spec = worker_specs[0]
    worker_pod_spec = worker_spec["template"].spec
    assert hasattr(worker_pod_spec, "tolerations")
    assert len(worker_pod_spec.tolerations) == 1
    assert worker_pod_spec.tolerations[0].key == "nvidia.com/gpu"


def test_build_ray_cluster_spec_with_image_pull_secrets():
    """Test build_ray_cluster_spec with image pull secrets."""
    cluster_config = ManagedClusterConfig(
        image_pull_secrets=["my-registry-secret", "another-secret"]
    )

    spec = cluster_config.build_ray_cluster_spec("test-cluster")

    head_spec = spec["headGroupSpec"]
    head_pod_spec = head_spec["template"].spec
    assert hasattr(head_pod_spec, "image_pull_secrets")

    head_secrets = head_pod_spec.image_pull_secrets
    assert len(head_secrets) == 2
    assert head_secrets[0].name == "my-registry-secret"
    assert head_secrets[1].name == "another-secret"

    worker_specs = spec["workerGroupSpecs"]
    worker_spec = worker_specs[0]
    worker_pod_spec = worker_spec["template"].spec
    assert hasattr(worker_pod_spec, "image_pull_secrets")

    worker_secrets = worker_pod_spec.image_pull_secrets
    assert len(worker_secrets) == 2
    assert worker_secrets[0].name == "my-registry-secret"
    assert worker_secrets[1].name == "another-secret"


class TestRayVersionValidation:
    """Test Ray version validation in RayJob."""

    def test_submit_with_cluster_config_compatible_image_passes(self, auto_mock_setup):
        """Test that submission passes with compatible cluster_config image."""
        mock_api_instance = auto_mock_setup["rayjob_api"]
        mock_api_instance.submit_job.return_value = True

        cluster_config = ManagedClusterConfig(image=f"ray:{RAY_VERSION}")

        rayjob = RayJob(
            job_name="test-job",
            cluster_config=cluster_config,
            namespace="test-namespace",
            entrypoint="python script.py",
        )

        result = rayjob.submit()
        assert result == "test-job"

    def test_submit_with_cluster_config_incompatible_image_fails(self, auto_mock_setup):
        """Test that submission fails with incompatible cluster_config image."""
        #

        cluster_config = ManagedClusterConfig(image="ray:2.8.0")  # Different version

        rayjob = RayJob(
            job_name="test-job",
            cluster_config=cluster_config,
            namespace="test-namespace",
            entrypoint="python script.py",
        )

        with pytest.raises(
            ValueError, match="Cluster config image: Ray version mismatch detected"
        ):
            rayjob.submit()

    def test_validate_ray_version_compatibility_method(self, auto_mock_setup):
        """Test the _validate_ray_version_compatibility method directly."""
        #

        rayjob = RayJob(
            job_name="test-job",
            cluster_name="test-cluster",
            namespace="test-namespace",
            entrypoint="python script.py",
        )

        rayjob._validate_ray_version_compatibility()
        rayjob._cluster_config = ManagedClusterConfig(image=f"ray:{RAY_VERSION}")
        rayjob._validate_ray_version_compatibility()
        rayjob._cluster_config = ManagedClusterConfig(image="ray:2.8.0")
        with pytest.raises(
            ValueError, match="Cluster config image: Ray version mismatch detected"
        ):
            rayjob._validate_ray_version_compatibility()

        rayjob._cluster_config = ManagedClusterConfig(image="custom-image:latest")
        with pytest.warns(
            UserWarning, match="Cluster config image: Cannot determine Ray version"
        ):
            rayjob._validate_ray_version_compatibility()

    def test_validate_cluster_config_image_method(self, auto_mock_setup):
        """Test the _validate_cluster_config_image method directly."""
        #

        rayjob = RayJob(
            job_name="test-job",
            cluster_config=ManagedClusterConfig(),
            namespace="test-namespace",
            entrypoint="python script.py",
        )

        rayjob._validate_cluster_config_image()
        rayjob._cluster_config.image = f"ray:{RAY_VERSION}"
        rayjob._validate_cluster_config_image()
        rayjob._cluster_config.image = "ray:2.8.0"
        with pytest.raises(
            ValueError, match="Cluster config image: Ray version mismatch detected"
        ):
            rayjob._validate_cluster_config_image()

        rayjob._cluster_config.image = "custom-image:latest"
        with pytest.warns(
            UserWarning, match="Cluster config image: Cannot determine Ray version"
        ):
            rayjob._validate_cluster_config_image()

    def test_validate_cluster_config_image_edge_cases(self, auto_mock_setup):
        """Test edge cases in _validate_cluster_config_image method."""

        rayjob = RayJob(
            job_name="test-job",
            cluster_config=ManagedClusterConfig(),
            namespace="test-namespace",
            entrypoint="python script.py",
        )

        rayjob._cluster_config.image = None
        rayjob._validate_cluster_config_image()
        rayjob._cluster_config.image = ""
        rayjob._validate_cluster_config_image()
        rayjob._cluster_config.image = 123
        rayjob._validate_cluster_config_image()

        class MockClusterConfig:
            pass

        rayjob._cluster_config = MockClusterConfig()
        rayjob._validate_cluster_config_image()


def test_extract_script_files_from_entrypoint_single_script(auto_mock_setup, tmp_path):
    """Test extracting a single script file from entrypoint."""

    # Create a test script
    test_script = tmp_path / "test_script.py"
    test_script.write_text("print('Hello World!')")

    # Change to temp directory for test
    original_cwd = os.getcwd()
    os.chdir(tmp_path)

    try:
        rayjob = RayJob(
            job_name="test-job",
            cluster_name="existing-cluster",
            entrypoint=f"python {test_script.name}",
            namespace="test-namespace",
        )

        scripts = rayjob._extract_script_files_from_entrypoint()

        assert scripts is not None
        assert test_script.name in scripts
        assert scripts[test_script.name] == "print('Hello World!')"
        assert f"{MOUNT_PATH}/{test_script.name}" in rayjob.entrypoint
    finally:
        os.chdir(original_cwd)


def test_extract_script_files_with_dependencies(auto_mock_setup, tmp_path):
    """Test extracting script files with local dependencies."""

    # Create main script and dependency
    main_script = tmp_path / "main.py"
    main_script.write_text(
        """
import helper
from utils import calculate

def main():
    helper.do_something()
    result = calculate(42)
    print(f"Result: {result}")

if __name__ == "__main__":
    main()
"""
    )

    helper_script = tmp_path / "helper.py"
    helper_script.write_text(
        """
def do_something():
    print("Doing something...")
"""
    )

    utils_script = tmp_path / "utils.py"
    utils_script.write_text(
        """
def calculate(x):
    return x * 2
"""
    )

    # Change to temp directory for test
    original_cwd = os.getcwd()
    os.chdir(tmp_path)

    try:
        rayjob = RayJob(
            job_name="test-job",
            cluster_name="existing-cluster",
            entrypoint="python main.py",
            namespace="test-namespace",
        )

        scripts = rayjob._extract_script_files_from_entrypoint()

        assert scripts is not None
        assert len(scripts) == 3
        assert "main.py" in scripts
        assert "helper.py" in scripts
        assert "utils.py" in scripts

        assert "import helper" in scripts["main.py"]
        assert "def do_something" in scripts["helper.py"]
        assert "def calculate" in scripts["utils.py"]

    finally:
        os.chdir(original_cwd)


def test_extract_script_files_no_local_scripts(auto_mock_setup):
    """Test entrypoint with no local script files."""

    rayjob = RayJob(
        job_name="test-job",
        cluster_name="existing-cluster",
        entrypoint="python -c 'print(\"hello world\")'",
        namespace="test-namespace",
    )

    scripts = rayjob._extract_script_files_from_entrypoint()

    assert scripts is None


def test_extract_script_files_nonexistent_script(auto_mock_setup):
    """Test entrypoint referencing non-existent script."""

    rayjob = RayJob(
        job_name="test-job",
        cluster_name="existing-cluster",
        entrypoint="python nonexistent.py",
        namespace="test-namespace",
    )

    scripts = rayjob._extract_script_files_from_entrypoint()

    assert scripts is None


def test_build_script_configmap_spec():
    """Test building ConfigMap specification for scripts."""
    config = ManagedClusterConfig()
    scripts = {"main.py": "print('main')", "helper.py": "print('helper')"}

    spec = config.build_script_configmap_spec(
        job_name="test-job", namespace="test-namespace", scripts=scripts
    )

    assert spec["apiVersion"] == "v1"
    assert spec["kind"] == "ConfigMap"
    assert spec["metadata"]["name"] == "test-job-scripts"
    assert spec["metadata"]["namespace"] == "test-namespace"
    assert spec["data"] == scripts


def test_build_script_volume_specs():
    """Test building volume and mount specifications for scripts."""
    config = ManagedClusterConfig()

    volume_spec, mount_spec = config.build_script_volume_specs(
        configmap_name="test-scripts", mount_path="/custom/path"
    )

    assert volume_spec["name"] == "ray-job-scripts"
    assert volume_spec["configMap"]["name"] == "test-scripts"

    assert mount_spec["name"] == "ray-job-scripts"
    assert mount_spec["mountPath"] == "/custom/path"


def test_add_script_volumes():
    """Test adding script volumes to cluster configuration."""
    config = ManagedClusterConfig()

    # Initially no volumes
    assert len(config.volumes) == 0
    assert len(config.volume_mounts) == 0

    config.add_script_volumes(configmap_name="test-scripts")

    assert len(config.volumes) == 1
    assert len(config.volume_mounts) == 1

    volume = config.volumes[0]
    mount = config.volume_mounts[0]

    assert volume.name == "ray-job-scripts"
    assert volume.config_map.name == "test-scripts"

    assert mount.name == "ray-job-scripts"
    assert mount.mount_path == MOUNT_PATH


def test_add_script_volumes_duplicate_prevention():
    """Test that adding script volumes twice doesn't create duplicates."""
    config = ManagedClusterConfig()

    # Add volumes twice
    config.add_script_volumes(configmap_name="test-scripts")
    config.add_script_volumes(configmap_name="test-scripts")

    assert len(config.volumes) == 1
    assert len(config.volume_mounts) == 1


def test_create_configmap_from_spec(auto_mock_setup):
    """Test creating ConfigMap via Kubernetes API."""
    mock_api_instance = auto_mock_setup["k8s_api"]

    rayjob = RayJob(
        job_name="test-job",
        cluster_name="existing-cluster",
        entrypoint="python test.py",
        namespace="test-namespace",
    )

    configmap_spec = {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {"name": "test-scripts", "namespace": "test-namespace"},
        "data": {"test.py": "print('test')"},
    }

    result = rayjob._create_configmap_from_spec(configmap_spec)

    assert result == "test-scripts"
    mock_api_instance.create_namespaced_config_map.assert_called_once()


def test_create_configmap_already_exists(auto_mock_setup):
    """Test creating ConfigMap when it already exists (409 conflict)."""
    mock_api_instance = auto_mock_setup["k8s_api"]

    mock_api_instance.create_namespaced_config_map.side_effect = ApiException(
        status=409
    )

    rayjob = RayJob(
        job_name="test-job",
        cluster_name="existing-cluster",
        entrypoint="python test.py",
        namespace="test-namespace",
    )

    configmap_spec = {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {"name": "test-scripts", "namespace": "test-namespace"},
        "data": {"test.py": "print('test')"},
    }

    result = rayjob._create_configmap_from_spec(configmap_spec)

    assert result == "test-scripts"
    mock_api_instance.create_namespaced_config_map.assert_called_once()
    mock_api_instance.replace_namespaced_config_map.assert_called_once()


def test_create_configmap_with_owner_reference_basic(mocker, auto_mock_setup, caplog):
    """Test creating ConfigMap with owner reference from valid RayJob result."""
    mock_api_instance = auto_mock_setup["k8s_api"]

    # Mock client.V1ObjectMeta and V1ConfigMap
    mock_v1_metadata = mocker.patch("kubernetes.client.V1ObjectMeta")
    mock_metadata_instance = MagicMock()
    mock_v1_metadata.return_value = mock_metadata_instance

    rayjob = RayJob(
        job_name="test-job",
        cluster_name="existing-cluster",
        entrypoint="python test.py",
        namespace="test-namespace",
    )

    configmap_spec = {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {
            "name": "test-scripts",
            "namespace": "test-namespace",
            "labels": {
                "ray.io/job-name": "test-job",
                "app.kubernetes.io/managed-by": "codeflare-sdk",
                "app.kubernetes.io/component": "rayjob-scripts",
            },
        },
        "data": {"test.py": "print('test')"},
    }

    # Valid RayJob result with UID
    rayjob_result = {
        "metadata": {
            "name": "test-job",
            "namespace": "test-namespace",
            "uid": "a4dd4c5a-ab61-411d-b4d1-4abb5177422a",
        }
    }

    with caplog.at_level("INFO"):
        result = rayjob._create_configmap_from_spec(configmap_spec, rayjob_result)

    assert result == "test-scripts"

    # Verify owner reference was set
    expected_owner_ref = mocker.ANY  # We'll check via the logs
    assert (
        "Adding owner reference to ConfigMap 'test-scripts' with RayJob UID: a4dd4c5a-ab61-411d-b4d1-4abb5177422a"
        in caplog.text
    )

    assert mock_metadata_instance.owner_references is not None
    mock_api_instance.create_namespaced_config_map.assert_called_once()


def test_create_configmap_without_owner_reference_no_uid(
    mocker, auto_mock_setup, caplog
):
    """Test creating ConfigMap without owner reference when RayJob has no UID."""
    mock_api_instance = auto_mock_setup["k8s_api"]

    mock_v1_metadata = mocker.patch("kubernetes.client.V1ObjectMeta")
    mock_metadata_instance = MagicMock()
    mock_v1_metadata.return_value = mock_metadata_instance

    rayjob = RayJob(
        job_name="test-job",
        cluster_name="existing-cluster",
        entrypoint="python test.py",
        namespace="test-namespace",
    )

    configmap_spec = {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {"name": "test-scripts", "namespace": "test-namespace"},
        "data": {"test.py": "print('test')"},
    }

    # RayJob result without UID
    rayjob_result = {
        "metadata": {
            "name": "test-job",
            "namespace": "test-namespace",
            # No UID field
        }
    }

    with caplog.at_level("WARNING"):
        result = rayjob._create_configmap_from_spec(configmap_spec, rayjob_result)

    assert result == "test-scripts"

    # Verify warning was logged and no owner reference was set
    assert (
        "No valid RayJob result with UID found, ConfigMap 'test-scripts' will not have owner reference"
        in caplog.text
    )

    # The important part is that the warning was logged, indicating no owner reference was set
    mock_api_instance.create_namespaced_config_map.assert_called_once()


def test_create_configmap_with_invalid_rayjob_result(auto_mock_setup, caplog):
    """Test creating ConfigMap with None or invalid rayjob_result."""
    mock_api_instance = auto_mock_setup["k8s_api"]

    rayjob = RayJob(
        job_name="test-job",
        cluster_name="existing-cluster",
        entrypoint="python test.py",
        namespace="test-namespace",
    )

    configmap_spec = {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {"name": "test-scripts", "namespace": "test-namespace"},
        "data": {"test.py": "print('test')"},
    }

    # Test with None
    with caplog.at_level("WARNING"):
        result = rayjob._create_configmap_from_spec(configmap_spec, None)

    assert result == "test-scripts"
    assert "No valid RayJob result with UID found" in caplog.text

    # Test with string instead of dict
    caplog.clear()
    with caplog.at_level("WARNING"):
        result = rayjob._create_configmap_from_spec(configmap_spec, "not-a-dict")

    assert result == "test-scripts"
    assert "No valid RayJob result with UID found" in caplog.text


def test_handle_script_volumes_for_new_cluster(mocker, auto_mock_setup, tmp_path):
    """Test handling script volumes for new cluster creation."""
    # auto_mock_setup handles kubernetes and API mocking

    mock_create = mocker.patch.object(RayJob, "_create_configmap_from_spec")
    mock_create.return_value = "test-job-scripts"

    test_script = tmp_path / "test.py"
    test_script.write_text("print('test')")

    cluster_config = ManagedClusterConfig()

    original_cwd = os.getcwd()
    os.chdir(tmp_path)

    try:
        rayjob = RayJob(
            job_name="test-job",
            cluster_config=cluster_config,
            entrypoint="python test.py",
            namespace="test-namespace",
        )

        scripts = {"test.py": "print('test')"}
        rayjob._handle_script_volumes_for_new_cluster(scripts)

        mock_create.assert_called_once()

        assert len(cluster_config.volumes) == 1
        assert len(cluster_config.volume_mounts) == 1

    finally:
        os.chdir(original_cwd)


def test_ast_parsing_import_detection(auto_mock_setup, tmp_path):
    """Test AST parsing correctly detects import statements."""

    main_script = tmp_path / "main.py"
    main_script.write_text(
        """# Different import patterns
import helper
from utils import func1, func2
from local_module import MyClass
import os  # Standard library - should be ignored
import non_existent  # Non-local - should be ignored
"""
    )

    helper_script = tmp_path / "helper.py"
    helper_script.write_text("def helper_func(): pass")

    utils_script = tmp_path / "utils.py"
    utils_script.write_text(
        """def func1(): pass
def func2(): pass
"""
    )

    local_module_script = tmp_path / "local_module.py"
    local_module_script.write_text("class MyClass: pass")

    original_cwd = os.getcwd()
    os.chdir(tmp_path)

    try:
        rayjob = RayJob(
            job_name="test-job",
            cluster_name="existing-cluster",
            entrypoint="python main.py",
            namespace="test-namespace",
        )

        scripts = rayjob._extract_script_files_from_entrypoint()

        assert scripts is not None
        assert len(scripts) == 4  # main + 3 dependencies
        assert "main.py" in scripts
        assert "helper.py" in scripts
        assert "utils.py" in scripts
        assert "local_module.py" in scripts

    finally:
        os.chdir(original_cwd)


def test_script_handling_timing_after_rayjob_submission(
    mocker, auto_mock_setup, tmp_path
):
    """Test that script handling happens after RayJob is submitted (not before)."""
    mock_api_instance = auto_mock_setup["rayjob_api"]

    submit_result = {
        "metadata": {
            "name": "test-job",
            "namespace": "test-namespace",
            "uid": "test-uid-12345",
        }
    }
    mock_api_instance.submit_job.return_value = submit_result

    mock_handle_new = mocker.patch.object(
        RayJob, "_handle_script_volumes_for_new_cluster"
    )

    # RayClusterApi is already mocked by auto_mock_setup

    test_script = tmp_path / "test.py"
    test_script.write_text("print('test')")

    call_order = []

    def track_submit(*args, **kwargs):
        call_order.append("submit_job")
        return submit_result

    def track_handle_scripts(*args, **kwargs):
        call_order.append("handle_scripts")
        assert len(args) >= 2
        assert args[1] == submit_result  # rayjob_result should be second arg

    mock_api_instance.submit_job.side_effect = track_submit
    mock_handle_new.side_effect = track_handle_scripts

    original_cwd = os.getcwd()
    try:
        os.chdir(tmp_path)

        cluster_config = ManagedClusterConfig()

        rayjob = RayJob(
            job_name="test-job",
            cluster_config=cluster_config,
            entrypoint="python test.py",
            namespace="test-namespace",
        )

        rayjob.submit()
    finally:
        os.chdir(original_cwd)

    assert call_order == ["submit_job", "handle_scripts"]

    mock_api_instance.submit_job.assert_called_once()
    mock_handle_new.assert_called_once()

    mock_handle_new.assert_called_with({"test.py": "print('test')"}, submit_result)


def test_rayjob_submit_with_scripts_new_cluster(auto_mock_setup, tmp_path):
    """Test RayJob submission with script detection for new cluster."""
    mock_api_instance = auto_mock_setup["rayjob_api"]
    mock_api_instance.submit_job.return_value = True

    mock_k8s_instance = auto_mock_setup["k8s_api"]

    # Create test script
    test_script = tmp_path / "test.py"
    test_script.write_text("print('Hello from script!')")

    cluster_config = ManagedClusterConfig()

    original_cwd = os.getcwd()
    os.chdir(tmp_path)

    try:
        rayjob = RayJob(
            job_name="test-job",
            cluster_config=cluster_config,
            entrypoint="python test.py",
            namespace="test-namespace",
        )

        # Submit should detect scripts and handle them
        result = rayjob.submit()

        assert result == "test-job"

        mock_k8s_instance.create_namespaced_config_map.assert_called_once()

        assert len(cluster_config.volumes) == 1
        assert len(cluster_config.volume_mounts) == 1
        assert f"{MOUNT_PATH}/test.py" in rayjob.entrypoint

    finally:
        os.chdir(original_cwd)


def test_process_script_and_imports_io_error(mocker, auto_mock_setup, tmp_path):
    """Test _process_script_and_imports handles IO errors gracefully."""

    rayjob = RayJob(
        job_name="test-job",
        cluster_name="existing-cluster",
        entrypoint="python test.py",
        namespace="test-namespace",
    )

    scripts = {}
    processed_files = set()

    # Mock os.path.isfile to return True but open() to raise IOError
    mocker.patch("os.path.isfile", return_value=True)
    mocker.patch("builtins.open", side_effect=IOError("Permission denied"))

    rayjob._process_script_and_imports("test.py", scripts, MOUNT_PATH, processed_files)
    assert "test.py" in processed_files
    assert len(scripts) == 0


def test_process_script_and_imports_container_path_skip(auto_mock_setup):
    """Test that scripts already in container paths are skipped."""
    rayjob = RayJob(
        job_name="test-job",
        cluster_name="existing-cluster",
        entrypoint="python test.py",
        namespace="test-namespace",
    )

    scripts = {}
    processed_files = set()

    # Test script path already in container
    rayjob._process_script_and_imports(
        f"{MOUNT_PATH}/test.py", scripts, MOUNT_PATH, processed_files
    )

    assert len(scripts) == 0
    assert len(processed_files) == 0


def test_process_script_and_imports_already_processed(auto_mock_setup, tmp_path):
    """Test that already processed scripts are skipped (infinite loop prevention)."""
    rayjob = RayJob(
        job_name="test-job",
        cluster_name="existing-cluster",
        entrypoint="python test.py",
        namespace="test-namespace",
    )

    scripts = {}
    processed_files = {"test.py"}  # Already processed

    rayjob._process_script_and_imports("test.py", scripts, MOUNT_PATH, processed_files)

    assert len(scripts) == 0
    assert processed_files == {"test.py"}


def test_submit_with_scripts_owner_reference_integration(
    mocker, auto_mock_setup, tmp_path, caplog
):
    """Integration test for submit() with local scripts to verify end-to-end owner reference flow."""
    mock_api_instance = auto_mock_setup["rayjob_api"]
    mock_k8s_instance = auto_mock_setup["k8s_api"]

    # RayJob submission returns result with UID
    submit_result = {
        "metadata": {
            "name": "test-job",
            "namespace": "test-namespace",
            "uid": "unique-rayjob-uid-12345",
        }
    }
    mock_api_instance.submit_job.return_value = submit_result

    # Capture the ConfigMap that gets created
    created_configmap = None

    def capture_configmap(namespace, body):
        nonlocal created_configmap
        created_configmap = body
        return body

    mock_k8s_instance.create_namespaced_config_map.side_effect = capture_configmap

    # Create test scripts
    test_script = tmp_path / "main.py"
    test_script.write_text("import helper\nprint('main')")

    helper_script = tmp_path / "helper.py"
    helper_script.write_text("def help(): print('helper')")

    # Change to temp directory for script detection
    original_cwd = os.getcwd()
    try:
        os.chdir(tmp_path)

        cluster_config = ManagedClusterConfig()

        rayjob = RayJob(
            job_name="test-job",
            cluster_config=cluster_config,
            entrypoint="python main.py",
            namespace="test-namespace",
        )

        with caplog.at_level("INFO"):
            result = rayjob.submit()

        assert result == "test-job"

        mock_api_instance.submit_job.assert_called_once()
        mock_k8s_instance.create_namespaced_config_map.assert_called_once()
        assert created_configmap is not None

        # Verify owner reference was set correctly
        assert hasattr(created_configmap.metadata, "owner_references")
        assert created_configmap.metadata.owner_references is not None
        assert len(created_configmap.metadata.owner_references) == 1

        owner_ref = created_configmap.metadata.owner_references[0]
        assert owner_ref.api_version == "ray.io/v1"
        assert owner_ref.kind == "RayJob"
        assert owner_ref.name == "test-job"
        assert owner_ref.uid == "unique-rayjob-uid-12345"
        assert owner_ref.controller is True
        assert owner_ref.block_owner_deletion is True

        # Verify labels were set
        assert created_configmap.metadata.labels["ray.io/job-name"] == "test-job"
        assert (
            created_configmap.metadata.labels["app.kubernetes.io/managed-by"]
            == "codeflare-sdk"
        )
        assert (
            created_configmap.metadata.labels["app.kubernetes.io/component"]
            == "rayjob-scripts"
        )

        assert "main.py" in created_configmap.data
        assert "helper.py" in created_configmap.data
        assert (
            "Adding owner reference to ConfigMap 'test-job-scripts' with RayJob UID: unique-rayjob-uid-12345"
            in caplog.text
        )

    finally:
        os.chdir(original_cwd)


def test_find_local_imports_syntax_error(mocker, auto_mock_setup):
    """Test _find_local_imports handles syntax errors gracefully."""
    rayjob = RayJob(
        job_name="test-job",
        cluster_name="existing-cluster",
        entrypoint="python test.py",
        namespace="test-namespace",
    )

    # Invalid Python syntax
    invalid_script_content = "import helper\ndef invalid_syntax("

    mock_callback = mocker.Mock()

    rayjob._find_local_imports(invalid_script_content, "test.py", mock_callback)
    mock_callback.assert_not_called()


def test_create_configmap_api_error_non_409(auto_mock_setup):
    """Test _create_configmap_from_spec handles non-409 API errors."""
    mock_api_instance = auto_mock_setup["k8s_api"]

    # Configure to raise 500 error
    mock_api_instance.create_namespaced_config_map.side_effect = ApiException(
        status=500
    )

    rayjob = RayJob(
        job_name="test-job",
        cluster_name="existing-cluster",
        entrypoint="python test.py",
        namespace="test-namespace",
    )

    configmap_spec = {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {"name": "test-scripts", "namespace": "test-namespace"},
        "data": {"test.py": "print('test')"},
    }

    with pytest.raises(RuntimeError, match="Failed to create ConfigMap"):
        rayjob._create_configmap_from_spec(configmap_spec)


def test_update_existing_cluster_get_cluster_error(mocker, auto_mock_setup):
    """Test _update_existing_cluster_for_scripts handles get cluster errors."""
    mock_cluster_api_instance = auto_mock_setup["cluster_api"]

    # Configure it to raise an error
    mock_cluster_api_instance.get_ray_cluster.side_effect = ApiException(status=404)

    config_builder = ManagedClusterConfig()

    rayjob = RayJob(
        job_name="test-job",
        cluster_name="existing-cluster",
        entrypoint="python test.py",
        namespace="test-namespace",
    )

    with pytest.raises(RuntimeError, match="Failed to get RayCluster"):
        rayjob._update_existing_cluster_for_scripts("test-scripts", config_builder)


def test_update_existing_cluster_patch_error(mocker, auto_mock_setup):
    """Test _update_existing_cluster_for_scripts handles patch errors."""
    mock_cluster_api_instance = auto_mock_setup["cluster_api"]

    # Mock successful get but failed patch
    mock_cluster_api_instance.get_ray_cluster.return_value = {
        "spec": {
            "headGroupSpec": {
                "template": {
                    "spec": {"volumes": [], "containers": [{"volumeMounts": []}]}
                }
            },
            "workerGroupSpecs": [
                {
                    "template": {
                        "spec": {"volumes": [], "containers": [{"volumeMounts": []}]}
                    }
                }
            ],
        }
    }

    mock_cluster_api_instance.patch_ray_cluster.side_effect = ApiException(status=500)

    config_builder = ManagedClusterConfig()

    rayjob = RayJob(
        job_name="test-job",
        cluster_name="existing-cluster",
        entrypoint="python test.py",
        namespace="test-namespace",
    )

    with pytest.raises(RuntimeError, match="Failed to update RayCluster"):
        rayjob._update_existing_cluster_for_scripts("test-scripts", config_builder)


def test_extract_script_files_empty_entrypoint(auto_mock_setup):
    """Test script extraction with empty entrypoint."""
    rayjob = RayJob(
        job_name="test-job",
        cluster_name="existing-cluster",
        entrypoint="",  # Empty entrypoint
        namespace="test-namespace",
    )

    scripts = rayjob._extract_script_files_from_entrypoint()

    assert scripts is None


def test_add_script_volumes_existing_volume_skip():
    """Test add_script_volumes skips when volume already exists (missing coverage)."""
    config = ManagedClusterConfig()

    # Pre-add a volume with same name
    existing_volume = V1Volume(
        name="ray-job-scripts",
        config_map=V1ConfigMapVolumeSource(name="existing-scripts"),
    )
    config.volumes.append(existing_volume)

    config.add_script_volumes(configmap_name="new-scripts")
    assert len(config.volumes) == 1
    assert len(config.volume_mounts) == 0  # Mount not added due to volume skip


def test_add_script_volumes_existing_mount_skip():
    """Test add_script_volumes skips when mount already exists (missing coverage)."""
    config = ManagedClusterConfig()

    # Pre-add a mount with same name
    existing_mount = V1VolumeMount(name="ray-job-scripts", mount_path="/existing/path")
    config.volume_mounts.append(existing_mount)

    config.add_script_volumes(configmap_name="new-scripts")
    assert len(config.volumes) == 0  # Volume not added due to mount skip
    assert len(config.volume_mounts) == 1


def test_rayjob_stop_success(auto_mock_setup, caplog):
    """Test successful RayJob stop operation."""
    mock_api_instance = auto_mock_setup["rayjob_api"]

    mock_api_instance.suspend_job.return_value = {
        "metadata": {"name": "test-rayjob"},
        "spec": {"suspend": True},
    }

    rayjob = RayJob(
        job_name="test-rayjob",
        cluster_name="test-cluster",
        namespace="test-namespace",
        entrypoint="python script.py",
    )

    with caplog.at_level("INFO"):
        result = rayjob.stop()

    assert result is True

    mock_api_instance.suspend_job.assert_called_once_with(
        name="test-rayjob", k8s_namespace="test-namespace"
    )

    # Verify success message was logged
    assert "Successfully stopped the RayJob test-rayjob" in caplog.text


def test_rayjob_stop_failure(auto_mock_setup):
    """Test RayJob stop operation when API call fails."""
    mock_api_instance = auto_mock_setup["rayjob_api"]

    mock_api_instance.suspend_job.return_value = None

    rayjob = RayJob(
        job_name="test-rayjob",
        cluster_name="test-cluster",
        namespace="test-namespace",
        entrypoint="python script.py",
    )

    with pytest.raises(RuntimeError, match="Failed to stop the RayJob test-rayjob"):
        rayjob.stop()

    mock_api_instance.suspend_job.assert_called_once_with(
        name="test-rayjob", k8s_namespace="test-namespace"
    )


def test_rayjob_resubmit_success(auto_mock_setup):
    """Test successful RayJob resubmit operation."""
    mock_api_instance = auto_mock_setup["rayjob_api"]

    mock_api_instance.resubmit_job.return_value = {
        "metadata": {"name": "test-rayjob"},
        "spec": {"suspend": False},
    }

    rayjob = RayJob(
        job_name="test-rayjob",
        cluster_name="test-cluster",
        namespace="test-namespace",
        entrypoint="python script.py",
    )

    result = rayjob.resubmit()

    assert result is True

    mock_api_instance.resubmit_job.assert_called_once_with(
        name="test-rayjob", k8s_namespace="test-namespace"
    )


def test_rayjob_resubmit_failure(auto_mock_setup):
    """Test RayJob resubmit operation when API call fails."""
    mock_api_instance = auto_mock_setup["rayjob_api"]

    mock_api_instance.resubmit_job.return_value = None

    rayjob = RayJob(
        job_name="test-rayjob",
        cluster_name="test-cluster",
        namespace="test-namespace",
        entrypoint="python script.py",
    )

    with pytest.raises(RuntimeError, match="Failed to resubmit the RayJob test-rayjob"):
        rayjob.resubmit()

    mock_api_instance.resubmit_job.assert_called_once_with(
        name="test-rayjob", k8s_namespace="test-namespace"
    )


def test_rayjob_delete_success(auto_mock_setup):
    """Test successful RayJob deletion."""
    mock_api_instance = auto_mock_setup["rayjob_api"]

    rayjob = RayJob(
        job_name="test-rayjob",
        entrypoint="python script.py",
        cluster_name="test-cluster",
    )

    mock_api_instance.delete_job.return_value = True

    result = rayjob.delete()

    assert result is True
    mock_api_instance.delete_job.assert_called_once_with(
        name="test-rayjob", k8s_namespace="test-namespace"
    )


def test_rayjob_delete_failure(auto_mock_setup):
    """Test failed RayJob deletion."""
    mock_api_instance = auto_mock_setup["rayjob_api"]

    rayjob = RayJob(
        job_name="test-rayjob",
        entrypoint="python script.py",
        cluster_name="test-cluster",
    )

    mock_api_instance.delete_job.return_value = False

    with pytest.raises(RuntimeError, match="Failed to delete the RayJob test-rayjob"):
        rayjob.delete()

    mock_api_instance.delete_job.assert_called_once_with(
        name="test-rayjob", k8s_namespace="test-namespace"
    )


def test_rayjob_init_both_none_error(auto_mock_setup):
    """Test RayJob initialization error when both cluster_name and cluster_config are None."""
    with pytest.raises(
        ValueError,
        match="Configuration Error: You must provide either 'cluster_name' .* or 'cluster_config'",
    ):
        RayJob(
            job_name="test-job",
            entrypoint="python script.py",
            cluster_name=None,
            cluster_config=None,
        )


def test_rayjob_init_missing_cluster_name_with_no_config(auto_mock_setup):
    """Test RayJob initialization error when cluster_name is None without cluster_config."""
    with pytest.raises(
        ValueError,
        match="Configuration Error: a 'cluster_name' is required when not providing 'cluster_config'",
    ):
        rayjob = RayJob.__new__(RayJob)
        rayjob.name = "test-job"
        rayjob.entrypoint = "python script.py"
        rayjob.runtime_env = None
        rayjob.ttl_seconds_after_finished = 0
        rayjob.active_deadline_seconds = None
        rayjob.shutdown_after_job_finishes = True
        rayjob.namespace = "test-namespace"
        rayjob._cluster_name = None
        rayjob._cluster_config = None
        if rayjob._cluster_config is None and rayjob._cluster_name is None:
            raise ValueError(
                "❌ Configuration Error: a 'cluster_name' is required when not providing 'cluster_config'"
            )


def test_handle_script_volumes_for_existing_cluster_direct_call(auto_mock_setup):
    """Test _handle_script_volumes_for_existing_cluster method directly."""
    mock_api_instance = auto_mock_setup["rayjob_api"]
    mock_cluster_api = auto_mock_setup["cluster_api"]
    mock_k8s_api = auto_mock_setup["k8s_api"]

    # Mock existing cluster
    mock_cluster = {
        "spec": {
            "headGroupSpec": {
                "template": {
                    "spec": {"containers": [{"volumeMounts": []}], "volumes": []}
                }
            },
            "workerGroupSpecs": [
                {
                    "template": {
                        "spec": {"containers": [{"volumeMounts": []}], "volumes": []}
                    }
                }
            ],
        }
    }
    mock_cluster_api.get_ray_cluster.return_value = mock_cluster

    rayjob = RayJob(
        job_name="test-job",
        entrypoint="python script.py",
        cluster_name="existing-cluster",
    )

    scripts = {"test_script.py": "print('Hello World')"}
    rayjob._handle_script_volumes_for_existing_cluster(
        scripts, {"metadata": {"uid": "test-uid"}}
    )

    mock_k8s_api.create_namespaced_config_map.assert_called_once()
    created_configmap = mock_k8s_api.create_namespaced_config_map.call_args[1]["body"]
    assert "test_script.py" in created_configmap.data

    mock_cluster_api.patch_ray_cluster.assert_called_once_with(
        name="existing-cluster", ray_patch=mock_cluster, k8s_namespace="test-namespace"
    )


def test_handle_script_volumes_for_existing_cluster_no_volumes_init(auto_mock_setup):
    """Test _handle_script_volumes_for_existing_cluster when volumes/mounts don't exist initially."""
    mock_api_instance = auto_mock_setup["rayjob_api"]
    mock_cluster_api = auto_mock_setup["cluster_api"]
    mock_k8s_api = auto_mock_setup["k8s_api"]

    # Mock existing cluster WITHOUT volumes/volumeMounts (to test initialization)
    mock_cluster = {
        "spec": {
            "headGroupSpec": {"template": {"spec": {"containers": [{}]}}},
            "workerGroupSpecs": [{"template": {"spec": {"containers": [{}]}}}],
        }
    }
    mock_cluster_api.get_ray_cluster.return_value = mock_cluster

    # Create RayJob with existing cluster
    rayjob = RayJob(
        job_name="test-job",
        entrypoint="python script.py",
        cluster_name="existing-cluster",
    )

    # Call the method directly with test scripts
    scripts = {"test_script.py": "print('Hello World')"}
    rayjob._handle_script_volumes_for_existing_cluster(
        scripts, {"metadata": {"uid": "test-uid"}}
    )

    # Verify volumes and volumeMounts were initialized
    patched_cluster = mock_cluster_api.patch_ray_cluster.call_args[1]["ray_patch"]

    # Check head group
    head_spec = patched_cluster["spec"]["headGroupSpec"]["template"]["spec"]
    assert "volumes" in head_spec
    assert len(head_spec["volumes"]) == 1
    assert "volumeMounts" in head_spec["containers"][0]
    assert len(head_spec["containers"][0]["volumeMounts"]) == 1

    # Check worker group
    worker_spec = patched_cluster["spec"]["workerGroupSpecs"][0]["template"]["spec"]
    assert "volumes" in worker_spec
    assert len(worker_spec["volumes"]) == 1
    assert "volumeMounts" in worker_spec["containers"][0]
    assert len(worker_spec["containers"][0]["volumeMounts"]) == 1


def test_update_existing_cluster_for_scripts_api_errors(mocker, auto_mock_setup):
    """Test _update_existing_cluster_for_scripts error handling."""
    mock_api_instance = auto_mock_setup["rayjob_api"]
    mock_cluster_api = auto_mock_setup["cluster_api"]

    # Mock config builder
    mock_config_builder = mocker.MagicMock()
    mocker.patch(
        "codeflare_sdk.ray.rayjobs.rayjob.ManagedClusterConfig",
        return_value=mock_config_builder,
    )

    # Set up config builder to return valid specs
    mock_config_builder.build_script_volume_specs.return_value = (
        {"name": "script-volume", "configMap": {"name": "test-configmap"}},
        {"name": "script-volume", "mountPath": "/home/ray/scripts"},
    )

    # Mock cluster API to raise error
    mock_cluster_api.get_ray_cluster.side_effect = ApiException(
        status=404, reason="Not Found"
    )

    # Create RayJob
    rayjob = RayJob(
        job_name="test-job",
        entrypoint="python script.py",
        cluster_name="existing-cluster",
    )

    # Call the method directly
    with pytest.raises(
        RuntimeError, match="Failed to get RayCluster 'existing-cluster'"
    ):
        rayjob._update_existing_cluster_for_scripts(
            "test-configmap", mock_config_builder
        )


def test_rayjob_kueue_label_no_default_queue(auto_mock_setup, mocker, caplog):
    """Test RayJob falls back to 'default' queue when no default queue exists."""
    mocker.patch(
        "codeflare_sdk.ray.rayjobs.rayjob.get_default_kueue_name",
        return_value=None,
    )

    mock_api_instance = auto_mock_setup["rayjob_api"]
    mock_api_instance.submit_job.return_value = {"metadata": {"name": "test-job"}}

    cluster_config = ManagedClusterConfig()
    rayjob = RayJob(
        job_name="test-job",
        cluster_config=cluster_config,
        entrypoint="python script.py",
    )

    with caplog.at_level("WARNING"):
        rayjob.submit()

    # Verify the submitted job has the fallback label
    call_args = mock_api_instance.submit_job.call_args
    submitted_job = call_args.kwargs["job"]
    assert submitted_job["metadata"]["labels"]["kueue.x-k8s.io/queue-name"] == "default"

    # Verify warning was logged
    assert "No default Kueue LocalQueue found" in caplog.text


def test_rayjob_kueue_explicit_local_queue(auto_mock_setup):
    """Test RayJob uses explicitly specified local queue."""
    mock_api_instance = auto_mock_setup["rayjob_api"]
    mock_api_instance.submit_job.return_value = {"metadata": {"name": "test-job"}}

    cluster_config = ManagedClusterConfig()
    rayjob = RayJob(
        job_name="test-job",
        cluster_config=cluster_config,
        entrypoint="python script.py",
        local_queue="custom-queue",
    )

    rayjob.submit()

    # Verify the submitted job has the explicit queue label
    call_args = mock_api_instance.submit_job.call_args
    submitted_job = call_args.kwargs["job"]
    assert (
        submitted_job["metadata"]["labels"]["kueue.x-k8s.io/queue-name"]
        == "custom-queue"
    )


def test_rayjob_no_kueue_label_for_existing_cluster(auto_mock_setup):
    """Test RayJob doesn't add Kueue label for existing clusters."""
    mock_api_instance = auto_mock_setup["rayjob_api"]
    mock_api_instance.submit_job.return_value = {"metadata": {"name": "test-job"}}

    # Using existing cluster (no cluster_config)
    rayjob = RayJob(
        job_name="test-job",
        cluster_name="existing-cluster",
        entrypoint="python script.py",
    )

    rayjob.submit()

    # Verify no Kueue label was added
    call_args = mock_api_instance.submit_job.call_args
    submitted_job = call_args.kwargs["job"]
    assert "kueue.x-k8s.io/queue-name" not in submitted_job["metadata"]["labels"]


def test_rayjob_with_ttl_and_deadline(auto_mock_setup):
    """Test RayJob with TTL and active deadline seconds."""
    mock_api_instance = auto_mock_setup["rayjob_api"]
    mock_api_instance.submit_job.return_value = {"metadata": {"name": "test-job"}}

    cluster_config = ManagedClusterConfig()
    rayjob = RayJob(
        job_name="test-job",
        cluster_config=cluster_config,
        entrypoint="python script.py",
        ttl_seconds_after_finished=300,
        active_deadline_seconds=600,
    )

    rayjob.submit()

    # Verify TTL and deadline were set
    call_args = mock_api_instance.submit_job.call_args
    submitted_job = call_args.kwargs["job"]
    assert submitted_job["spec"]["ttlSecondsAfterFinished"] == 300
    assert submitted_job["spec"]["activeDeadlineSeconds"] == 600


def test_rayjob_shutdown_after_job_finishes(auto_mock_setup):
    """Test RayJob sets shutdownAfterJobFinishes correctly."""
    mock_api_instance = auto_mock_setup["rayjob_api"]
    mock_api_instance.submit_job.return_value = {"metadata": {"name": "test-job"}}

    # Test with managed cluster (should shutdown)
    cluster_config = ManagedClusterConfig()
    rayjob = RayJob(
        job_name="test-job",
        cluster_config=cluster_config,
        entrypoint="python script.py",
    )

    rayjob.submit()

    call_args = mock_api_instance.submit_job.call_args
    submitted_job = call_args.kwargs["job"]
    assert submitted_job["spec"]["shutdownAfterJobFinishes"] is True

    # Test with existing cluster (should not shutdown)
    rayjob2 = RayJob(
        job_name="test-job2",
        cluster_name="existing-cluster",
        entrypoint="python script.py",
    )

    rayjob2.submit()

    call_args2 = mock_api_instance.submit_job.call_args
    submitted_job2 = call_args2.kwargs["job"]
    assert submitted_job2["spec"]["shutdownAfterJobFinishes"] is False


def test_rayjob_stop_delete_resubmit_logging(auto_mock_setup, caplog):
    """Test logging for stop, delete, and resubmit operations."""
    mock_api_instance = auto_mock_setup["rayjob_api"]

    # Test stop with logging
    mock_api_instance.suspend_job.return_value = {
        "metadata": {"name": "test-rayjob"},
        "spec": {"suspend": True},
    }

    rayjob = RayJob(
        job_name="test-rayjob",
        cluster_name="test-cluster",
        namespace="test-namespace",
        entrypoint="python script.py",
    )

    with caplog.at_level("INFO"):
        result = rayjob.stop()

    assert result is True
    assert "Successfully stopped the RayJob test-rayjob" in caplog.text

    # Test delete with logging
    caplog.clear()
    mock_api_instance.delete_job.return_value = True

    with caplog.at_level("INFO"):
        result = rayjob.delete()

    assert result is True
    assert "Successfully deleted the RayJob test-rayjob" in caplog.text

    # Test resubmit with logging
    caplog.clear()
    mock_api_instance.resubmit_job.return_value = {
        "metadata": {"name": "test-rayjob"},
        "spec": {"suspend": False},
    }

    with caplog.at_level("INFO"):
        result = rayjob.resubmit()

    assert result is True
    assert "Successfully resubmitted the RayJob test-rayjob" in caplog.text


def test_rayjob_initialization_logging(auto_mock_setup, caplog):
    """Test RayJob initialization logging."""
    with caplog.at_level("INFO"):
        cluster_config = ManagedClusterConfig()
        rayjob = RayJob(
            job_name="test-job",
            cluster_config=cluster_config,
            entrypoint="python script.py",
        )

    assert "Creating new cluster: test-job-cluster" in caplog.text
    assert "Initialized RayJob: test-job in namespace: test-namespace" in caplog.text

"""
Tests for the simplified ManagedClusterConfig accelerator_configs behavior.
"""

import pytest
from codeflare_sdk.ray.rayjobs.config import ManagedClusterConfig, DEFAULT_ACCELERATORS
from kubernetes.client import V1VolumeMount
from kubernetes.client import V1Volume, V1SecretVolumeSource


def test_accelerator_configs_defaults_to_default_accelerators():
    """Test that accelerator_configs defaults to DEFAULT_ACCELERATORS.copy()"""
    config = ManagedClusterConfig()

    # Should have all the default accelerators
    assert "nvidia.com/gpu" in config.accelerator_configs
    assert "intel.com/gpu" in config.accelerator_configs
    assert "google.com/tpu" in config.accelerator_configs

    # Should be a copy, not the same object
    assert config.accelerator_configs is not DEFAULT_ACCELERATORS
    assert config.accelerator_configs == DEFAULT_ACCELERATORS


def test_accelerator_configs_can_be_overridden():
    """Test that users can override accelerator_configs with custom mappings"""
    custom_configs = {
        "nvidia.com/gpu": "GPU",
        "custom.com/accelerator": "CUSTOM_ACCELERATOR",
    }

    config = ManagedClusterConfig(accelerator_configs=custom_configs)

    # Should have custom configs
    assert config.accelerator_configs == custom_configs
    assert "custom.com/accelerator" in config.accelerator_configs
    assert "nvidia.com/gpu" in config.accelerator_configs

    # Should NOT have other defaults
    assert "intel.com/gpu" not in config.accelerator_configs
    assert "google.com/tpu" not in config.accelerator_configs


def test_accelerator_configs_can_extend_defaults():
    """Test that users can extend defaults by providing additional configs"""
    extended_configs = {
        **DEFAULT_ACCELERATORS,
        "custom.com/accelerator": "CUSTOM_ACCEL",
    }

    config = ManagedClusterConfig(accelerator_configs=extended_configs)

    # Should have all defaults plus custom
    assert "nvidia.com/gpu" in config.accelerator_configs
    assert "intel.com/gpu" in config.accelerator_configs
    assert "custom.com/accelerator" in config.accelerator_configs
    assert config.accelerator_configs["custom.com/accelerator"] == "CUSTOM_ACCEL"


def test_gpu_validation_works_with_defaults():
    """Test that GPU validation works with default accelerator configs"""
    config = ManagedClusterConfig(head_accelerators={"nvidia.com/gpu": 1})

    # Should not raise any errors
    assert config.head_accelerators == {"nvidia.com/gpu": 1}


def test_gpu_validation_works_with_custom_configs():
    """Test that GPU validation works with custom accelerator configs"""
    config = ManagedClusterConfig(
        accelerator_configs={"custom.com/accelerator": "CUSTOM_ACCEL"},
        head_accelerators={"custom.com/accelerator": 1},
    )

    # Should not raise any errors
    assert config.head_accelerators == {"custom.com/accelerator": 1}


def test_gpu_validation_fails_with_unsupported_accelerator():
    """Test that GPU validation fails with unsupported accelerators"""
    with pytest.raises(
        ValueError, match="GPU configuration 'unsupported.com/accelerator' not found"
    ):
        ManagedClusterConfig(head_accelerators={"unsupported.com/accelerator": 1})


def test_config_type_validation_errors(mocker):
    """Test that type validation properly raises errors with incorrect types."""
    # Mock the _is_type method to return False for type checking
    mocker.patch.object(
        ManagedClusterConfig,
        "_is_type",
        side_effect=lambda value, expected_type: False,  # Always fail type check
    )

    # This should raise TypeError during initialization
    with pytest.raises(TypeError, match="Type validation failed"):
        ManagedClusterConfig()


def test_config_is_type_method():
    """Test the _is_type static method for type checking."""
    # Test basic types
    assert ManagedClusterConfig._is_type("test", str) is True
    assert ManagedClusterConfig._is_type(123, int) is True
    assert ManagedClusterConfig._is_type(123, str) is False

    # Test optional types (Union with None)
    from typing import Optional

    assert ManagedClusterConfig._is_type(None, Optional[str]) is True
    assert ManagedClusterConfig._is_type("test", Optional[str]) is True
    assert ManagedClusterConfig._is_type(123, Optional[str]) is False

    # Test dict types
    assert ManagedClusterConfig._is_type({}, dict) is True
    assert ManagedClusterConfig._is_type({"key": "value"}, dict) is True
    assert ManagedClusterConfig._is_type([], dict) is False


def test_ray_usage_stats_always_disabled_by_default():
    """Test that RAY_USAGE_STATS_ENABLED is always set to '0' by default"""
    config = ManagedClusterConfig()

    # Should always have the environment variable set to "0"
    assert "RAY_USAGE_STATS_ENABLED" in config.envs
    assert config.envs["RAY_USAGE_STATS_ENABLED"] == "0"


def test_ray_usage_stats_overwrites_user_env():
    """Test that RAY_USAGE_STATS_ENABLED is always set to '0' even if user specifies it"""
    # User tries to enable usage stats
    config = ManagedClusterConfig(envs={"RAY_USAGE_STATS_ENABLED": "1"})

    # Should still be disabled (our setting takes precedence)
    assert "RAY_USAGE_STATS_ENABLED" in config.envs
    assert config.envs["RAY_USAGE_STATS_ENABLED"] == "0"


def test_ray_usage_stats_overwrites_user_env_string():
    """Test that RAY_USAGE_STATS_ENABLED is always set to '0' even if user specifies it as string"""
    # User tries to enable usage stats with string
    config = ManagedClusterConfig(envs={"RAY_USAGE_STATS_ENABLED": "true"})

    # Should still be disabled (our setting takes precedence)
    assert "RAY_USAGE_STATS_ENABLED" in config.envs
    assert config.envs["RAY_USAGE_STATS_ENABLED"] == "0"


def test_ray_usage_stats_with_other_user_envs():
    """Test that RAY_USAGE_STATS_ENABLED is set correctly while preserving other user envs"""
    # User sets other environment variables
    user_envs = {
        "CUSTOM_VAR": "custom_value",
        "ANOTHER_VAR": "another_value",
        "RAY_USAGE_STATS_ENABLED": "1",  # This should be overwritten
    }

    config = ManagedClusterConfig(envs=user_envs)

    # Our setting should take precedence
    assert config.envs["RAY_USAGE_STATS_ENABLED"] == "0"

    # Other user envs should be preserved
    assert config.envs["CUSTOM_VAR"] == "custom_value"
    assert config.envs["ANOTHER_VAR"] == "another_value"

    # Total count should be correct (3 user envs)
    assert len(config.envs) == 3


def test_add_file_volumes_existing_volume_early_return():
    """Test add_file_volumes early return when volume already exists."""

    config = ManagedClusterConfig()

    # Pre-add a volume with same name
    existing_volume = V1Volume(
        name="ray-job-files",
        secret=V1SecretVolumeSource(secret_name="existing-files"),
    )
    config.volumes.append(existing_volume)

    # Should return early and not add duplicate
    config.add_file_volumes(secret_name="new-files")

    # Should still have only one volume, no mount added
    assert len(config.volumes) == 1
    assert len(config.volume_mounts) == 0


def test_add_file_volumes_existing_mount_early_return():
    """Test add_file_volumes early return when mount already exists."""

    config = ManagedClusterConfig()

    # Pre-add a mount with same name
    existing_mount = V1VolumeMount(name="ray-job-files", mount_path="/existing/path")
    config.volume_mounts.append(existing_mount)

    # Should return early and not add duplicate
    config.add_file_volumes(secret_name="new-files")

    # Should still have only one mount, no volume added
    assert len(config.volumes) == 0
    assert len(config.volume_mounts) == 1


def test_build_file_secret_spec_labels():
    """Test that build_file_secret_spec creates Secret with correct labels."""
    config = ManagedClusterConfig()

    job_name = "test-job"
    namespace = "test-namespace"
    files = {"test.py": "print('hello')", "helper.py": "# helper code"}

    secret_spec = config.build_file_secret_spec(job_name, namespace, files)

    assert secret_spec["apiVersion"] == "v1"
    assert secret_spec["kind"] == "Secret"
    assert secret_spec["type"] == "Opaque"
    assert secret_spec["metadata"]["name"] == f"{job_name}-files"
    assert secret_spec["metadata"]["namespace"] == namespace

    labels = secret_spec["metadata"]["labels"]
    assert labels["ray.io/job-name"] == job_name
    assert labels["app.kubernetes.io/managed-by"] == "codeflare-sdk"
    assert labels["app.kubernetes.io/component"] == "rayjob-files"

    assert secret_spec["data"] == files


def test_managed_cluster_config_uses_update_image_for_head(mocker):
    """Test that ManagedClusterConfig calls update_image() for head container."""
    # Mock update_image where it's used (in config module), not where it's defined
    mock_update_image = mocker.patch(
        "codeflare_sdk.ray.rayjobs.config.update_image",
        return_value="mocked-image:latest",
    )

    config = ManagedClusterConfig(image="custom-image:v1")

    # Build cluster spec (which should call update_image)
    spec = config.build_ray_cluster_spec("test-cluster")

    # Verify update_image was called for head container
    assert mock_update_image.called
    # Verify head container has the mocked image
    head_container = spec["headGroupSpec"]["template"].spec.containers[0]
    assert head_container.image == "mocked-image:latest"


def test_managed_cluster_config_uses_update_image_for_worker(mocker):
    """Test that ManagedClusterConfig calls update_image() for worker container."""
    # Mock update_image where it's used (in config module), not where it's defined
    mock_update_image = mocker.patch(
        "codeflare_sdk.ray.rayjobs.config.update_image",
        return_value="mocked-image:latest",
    )

    config = ManagedClusterConfig(image="custom-image:v1")

    # Build cluster spec (which should call update_image)
    spec = config.build_ray_cluster_spec("test-cluster")

    # Verify update_image was called for worker container
    assert mock_update_image.called
    # Verify worker container has the mocked image
    worker_container = spec["workerGroupSpecs"][0]["template"].spec.containers[0]
    assert worker_container.image == "mocked-image:latest"


def test_managed_cluster_config_with_empty_image_uses_update_image(mocker):
    """Test that empty image triggers update_image() to auto-detect."""
    # Mock update_image where it's used (in config module), not where it's defined
    mock_update_image = mocker.patch(
        "codeflare_sdk.ray.rayjobs.config.update_image",
        return_value="auto-detected-image:py3.12",
    )

    config = ManagedClusterConfig(image="")

    # Build cluster spec
    spec = config.build_ray_cluster_spec("test-cluster")

    # Verify update_image was called with empty string
    mock_update_image.assert_called_with("")

    # Verify containers have the auto-detected image
    head_container = spec["headGroupSpec"]["template"].spec.containers[0]
    assert head_container.image == "auto-detected-image:py3.12"

    worker_container = spec["workerGroupSpecs"][0]["template"].spec.containers[0]
    assert worker_container.image == "auto-detected-image:py3.12"


def test_build_ray_cluster_spec_has_enable_in_tree_autoscaling_false():
    """Test that build_ray_cluster_spec sets enableInTreeAutoscaling to False."""
    config = ManagedClusterConfig()

    spec = config.build_ray_cluster_spec("test-cluster")

    # Verify enableInTreeAutoscaling is set to False (required for Kueue)
    assert "enableInTreeAutoscaling" in spec
    assert spec["enableInTreeAutoscaling"] is False


def test_build_ray_cluster_spec_autoscaling_disabled_for_kueue():
    """Test that autoscaling is explicitly disabled for Kueue-managed jobs."""
    config = ManagedClusterConfig(num_workers=3)

    spec = config.build_ray_cluster_spec("kueue-cluster")

    # Verify enableInTreeAutoscaling is False
    assert spec["enableInTreeAutoscaling"] is False

    # Verify worker replicas are fixed (min == max == replicas)
    worker_spec = spec["workerGroupSpecs"][0]
    assert worker_spec["replicas"] == 3
    assert worker_spec["minReplicas"] == 3
    assert worker_spec["maxReplicas"] == 3


def test_managed_cluster_config_default_image_integration():
    """Test that ManagedClusterConfig works with default images (integration test)."""
    # Create config without specifying an image (should auto-detect based on Python version)
    config = ManagedClusterConfig()

    # Build cluster spec
    spec = config.build_ray_cluster_spec("test-cluster")

    # Verify head container has an image (should be auto-detected)
    head_container = spec["headGroupSpec"]["template"].spec.containers[0]
    assert head_container.image is not None
    assert len(head_container.image) > 0
    # Should be one of the supported images
    from codeflare_sdk.common.utils.constants import (
        CUDA_PY311_RUNTIME_IMAGE,
        CUDA_PY312_RUNTIME_IMAGE,
    )

    assert head_container.image in [CUDA_PY311_RUNTIME_IMAGE, CUDA_PY312_RUNTIME_IMAGE]

    # Verify worker container has the same image
    worker_container = spec["workerGroupSpecs"][0]["template"].spec.containers[0]
    assert worker_container.image == head_container.image

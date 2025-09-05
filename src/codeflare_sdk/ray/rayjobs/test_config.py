"""
Tests for the simplified ManagedClusterConfig accelerator_configs behavior.
"""

import pytest
from codeflare_sdk.ray.rayjobs.config import ManagedClusterConfig, DEFAULT_ACCELERATORS


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


def test_add_script_volumes_existing_volume_early_return():
    """Test add_script_volumes early return when volume already exists."""
    from kubernetes.client import V1Volume, V1ConfigMapVolumeSource

    config = ManagedClusterConfig()

    # Pre-add a volume with same name
    existing_volume = V1Volume(
        name="ray-job-scripts",
        config_map=V1ConfigMapVolumeSource(name="existing-scripts"),
    )
    config.volumes.append(existing_volume)

    # Should return early and not add duplicate
    config.add_script_volumes(configmap_name="new-scripts")

    # Should still have only one volume, no mount added
    assert len(config.volumes) == 1
    assert len(config.volume_mounts) == 0


def test_add_script_volumes_existing_mount_early_return():
    """Test add_script_volumes early return when mount already exists."""
    from kubernetes.client import V1VolumeMount

    config = ManagedClusterConfig()

    # Pre-add a mount with same name
    existing_mount = V1VolumeMount(name="ray-job-scripts", mount_path="/existing/path")
    config.volume_mounts.append(existing_mount)

    # Should return early and not add duplicate
    config.add_script_volumes(configmap_name="new-scripts")

    # Should still have only one mount, no volume added
    assert len(config.volumes) == 0
    assert len(config.volume_mounts) == 1


def test_build_script_configmap_spec_labels():
    """Test that build_script_configmap_spec creates ConfigMap with correct labels."""
    config = ManagedClusterConfig()

    job_name = "test-job"
    namespace = "test-namespace"
    scripts = {"script.py": "print('hello')", "helper.py": "# helper code"}

    configmap_spec = config.build_script_configmap_spec(job_name, namespace, scripts)

    assert configmap_spec["apiVersion"] == "v1"
    assert configmap_spec["kind"] == "ConfigMap"
    assert configmap_spec["metadata"]["name"] == f"{job_name}-scripts"
    assert configmap_spec["metadata"]["namespace"] == namespace

    labels = configmap_spec["metadata"]["labels"]
    assert labels["ray.io/job-name"] == job_name
    assert labels["app.kubernetes.io/managed-by"] == "codeflare-sdk"
    assert labels["app.kubernetes.io/component"] == "rayjob-scripts"

    assert configmap_spec["data"] == scripts

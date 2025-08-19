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

"""
Tests for the simplified RayJobClusterConfig accelerator_configs behavior.
"""

import pytest
from codeflare_sdk.ray.rayjobs.config import RayJobClusterConfig, DEFAULT_ACCELERATORS


def test_accelerator_configs_defaults_to_default_accelerators():
    """Test that accelerator_configs defaults to DEFAULT_ACCELERATORS.copy()"""
    config = RayJobClusterConfig()

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

    config = RayJobClusterConfig(accelerator_configs=custom_configs)

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

    config = RayJobClusterConfig(accelerator_configs=extended_configs)

    # Should have all defaults plus custom
    assert "nvidia.com/gpu" in config.accelerator_configs
    assert "intel.com/gpu" in config.accelerator_configs
    assert "custom.com/accelerator" in config.accelerator_configs
    assert config.accelerator_configs["custom.com/accelerator"] == "CUSTOM_ACCEL"


def test_gpu_validation_works_with_defaults():
    """Test that GPU validation works with default accelerator configs"""
    config = RayJobClusterConfig(head_accelerators={"nvidia.com/gpu": 1})

    # Should not raise any errors
    assert config.head_accelerators == {"nvidia.com/gpu": 1}


def test_gpu_validation_works_with_custom_configs():
    """Test that GPU validation works with custom accelerator configs"""
    config = RayJobClusterConfig(
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
        RayJobClusterConfig(head_accelerators={"unsupported.com/accelerator": 1})

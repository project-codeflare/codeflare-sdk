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
Unit tests for the RayCluster dataclass behavior.

These tests focus on configuration defaults and local validation logic.
"""

from typing import Optional

import pytest

from codeflare_sdk.ray.rayclusters import RayCluster
from codeflare_sdk.ray.rayclusters.constants import DEFAULT_ACCELERATORS


def test_usage_stats_env_default(simple_cluster):
    """
    Ensure the usage stats environment variable is set by default.

    This validates that __post_init__ adds a predictable value.
    """
    assert simple_cluster.envs["RAY_USAGE_STATS_ENABLED"] == "0"


def test_default_accelerator_configs_included(simple_cluster):
    """
    Ensure default accelerator mappings are always available.

    This protects against missing required Ray resource names.
    """
    for key, value in DEFAULT_ACCELERATORS.items():
        assert simple_cluster.accelerator_configs[key] == value


def test_post_init_sets_internal_state():
    """Ensure internal state fields are initialized."""
    cluster = RayCluster(name="test-cluster", namespace="default")
    assert cluster._resource_yaml is None
    assert cluster._job_submission_client is None


def test_post_init_tls_warning(capsys):
    """Ensure disabling TLS verification prints a warning."""
    RayCluster(name="test-cluster", namespace="default", verify_tls=False)
    captured = capsys.readouterr()
    assert "TLS verification has been disabled" in captured.out


def test_post_init_usage_stats_enabled():
    """Ensure usage stats environment variable is enabled when configured."""
    cluster = RayCluster(
        name="test-cluster", namespace="default", enable_usage_stats=True
    )
    assert cluster.envs["RAY_USAGE_STATS_ENABLED"] == "1"


def test_post_init_usage_stats_disabled():
    """Ensure usage stats environment variable is disabled when configured."""
    cluster = RayCluster(
        name="test-cluster", namespace="default", enable_usage_stats=False
    )
    assert cluster.envs["RAY_USAGE_STATS_ENABLED"] == "0"


def test_post_init_gcs_ft_validation_missing_redis():
    """Ensure GCS FT requires redis_address."""
    with pytest.raises(ValueError, match="redis_address must be provided"):
        RayCluster(name="test-cluster", namespace="default", enable_gcs_ft=True)


def test_post_init_gcs_ft_validation_invalid_secret_type():
    """Ensure redis_password_secret must be a dict."""
    with pytest.raises(ValueError, match="redis_password_secret must be a dictionary"):
        RayCluster(
            name="test-cluster",
            namespace="default",
            enable_gcs_ft=True,
            redis_address="redis:6379",
            redis_password_secret="not-a-dict",
        )


def test_post_init_gcs_ft_validation_missing_secret_fields():
    """Ensure redis_password_secret includes name and key."""
    with pytest.raises(ValueError, match="redis_password_secret must contain"):
        RayCluster(
            name="test-cluster",
            namespace="default",
            enable_gcs_ft=True,
            redis_address="redis:6379",
            redis_password_secret={"name": "secret-only"},
        )


def test_post_init_gcs_ft_valid():
    """Ensure valid GCS FT configuration passes validation."""
    cluster = RayCluster(
        name="test-cluster",
        namespace="default",
        enable_gcs_ft=True,
        redis_address="redis:6379",
        redis_password_secret={"name": "secret", "key": "password"},
    )
    assert cluster.enable_gcs_ft is True


def test_validate_types_invalid_int():
    """Ensure invalid integer types raise TypeError."""
    with pytest.raises(TypeError, match="Type validation failed"):
        RayCluster(name="test-cluster", namespace="default", num_workers="two")


def test_validate_types_invalid_list():
    """Ensure invalid list element types raise TypeError."""
    with pytest.raises(TypeError, match="Type validation failed"):
        RayCluster(
            name="test-cluster",
            namespace="default",
            image_pull_secrets=[123],
        )


def test_validate_types_invalid_dict():
    """Ensure invalid dict key/value types raise TypeError."""
    with pytest.raises(TypeError, match="Type validation failed"):
        RayCluster(
            name="test-cluster",
            namespace="default",
            labels={1: "value"},
        )


def test_validate_types_optional_none():
    """Ensure Optional fields accept None values."""
    cluster = RayCluster(name="test-cluster", namespace=None, local_queue=None)
    assert cluster.namespace is None
    assert cluster.local_queue is None


def test_is_type_union():
    """Ensure Union type checking works."""
    assert RayCluster._is_type(1, int | str)
    assert RayCluster._is_type("value", int | str)
    assert not RayCluster._is_type([], int | str)


def test_is_type_list():
    """Ensure List type checking works."""
    assert RayCluster._is_type(["a", "b"], list[str])
    assert not RayCluster._is_type(["a", 1], list[str])


def test_is_type_dict():
    """Ensure Dict type checking works."""
    assert RayCluster._is_type({"a": 1}, dict[str, int])
    assert not RayCluster._is_type({1: "a"}, dict[str, int])


def test_is_type_tuple():
    """Ensure Tuple type checking works."""
    assert RayCluster._is_type((1, "a"), tuple[int, str])
    assert not RayCluster._is_type((1, 2), tuple[int, str])


def test_is_type_bool_not_int():
    """Ensure bool is not treated as int."""
    assert not RayCluster._is_type(True, int)


def test_is_type_optional():
    """Ensure Optional type checking works."""
    assert RayCluster._is_type(None, Optional[str])
    assert RayCluster._is_type("value", Optional[str])


def test_memory_to_string_int_conversion():
    """Ensure int memory values convert to Gi strings."""
    cluster = RayCluster(
        name="test-cluster",
        namespace="default",
        head_memory_requests=4,
        head_memory_limits=5,
        worker_memory_requests=6,
        worker_memory_limits=7,
    )
    assert cluster.head_memory_requests == "4Gi"
    assert cluster.head_memory_limits == "5Gi"
    assert cluster.worker_memory_requests == "6Gi"
    assert cluster.worker_memory_limits == "7Gi"


def test_memory_to_string_string_preserved():
    """Ensure string memory values are preserved."""
    cluster = RayCluster(
        name="test-cluster",
        namespace="default",
        head_memory_requests="4Gi",
        head_memory_limits="5Gi",
        worker_memory_requests="6Gi",
        worker_memory_limits="7Gi",
    )
    assert cluster.head_memory_requests == "4Gi"
    assert cluster.head_memory_limits == "5Gi"
    assert cluster.worker_memory_requests == "6Gi"
    assert cluster.worker_memory_limits == "7Gi"


def test_str_mem_no_unit_add_gi():
    """Ensure string numbers get Gi suffix for head and worker."""
    cluster = RayCluster(
        name="test-cluster",
        namespace="default",
        head_memory_requests="4",
        head_memory_limits="5",
        worker_memory_requests="6",
        worker_memory_limits="7",
    )
    assert cluster.head_memory_requests == "4Gi"
    assert cluster.head_memory_limits == "5Gi"
    assert cluster.worker_memory_requests == "6Gi"
    assert cluster.worker_memory_limits == "7Gi"


def test_str_mem_no_unit_preserves_units():
    """Ensure memory strings with units remain unchanged."""
    cluster = RayCluster(
        name="test-cluster",
        namespace="default",
        head_memory_requests="4Gi",
        head_memory_limits="5Gi",
        worker_memory_requests="6Gi",
        worker_memory_limits="7Gi",
    )
    assert cluster.head_memory_requests == "4Gi"
    assert cluster.head_memory_limits == "5Gi"
    assert cluster.worker_memory_requests == "6Gi"
    assert cluster.worker_memory_limits == "7Gi"


def test_str_mem_no_unit_non_decimal_preserved():
    """Ensure non-decimal strings remain unchanged."""
    cluster = RayCluster(
        name="test-cluster",
        namespace="default",
        head_memory_requests="4GiB",
        head_memory_limits="5GiB",
        worker_memory_requests="6GiB",
        worker_memory_limits="7GiB",
    )
    assert cluster.head_memory_requests == "4GiB"
    assert cluster.head_memory_limits == "5GiB"
    assert cluster.worker_memory_requests == "6GiB"
    assert cluster.worker_memory_limits == "7GiB"


def test_combine_accelerator_configs_custom_added():
    """Ensure custom accelerator configs merge with defaults."""
    cluster = RayCluster(
        name="test-cluster",
        namespace="default",
        accelerator_configs={"custom.com/accel": "CUSTOM"},
    )
    assert cluster.accelerator_configs["custom.com/accel"] == "CUSTOM"
    assert cluster.accelerator_configs["nvidia.com/gpu"] == "GPU"


def test_combine_accelerator_configs_overwrite_error():
    """Ensure overwriting defaults without flag raises ValueError."""
    with pytest.raises(ValueError, match="Accelerator config already exists"):
        RayCluster(
            name="test-cluster",
            namespace="default",
            accelerator_configs={"nvidia.com/gpu": "CUSTOM"},
        )


def test_combine_accelerator_configs_overwrite_allowed():
    """Ensure overwriting defaults allowed with flag and warning."""
    with pytest.warns(UserWarning, match="Overwriting default accelerator configs"):
        cluster = RayCluster(
            name="test-cluster",
            namespace="default",
            accelerator_configs={"nvidia.com/gpu": "CUSTOM"},
            overwrite_default_accelerator_configs=True,
        )
    assert cluster.accelerator_configs["nvidia.com/gpu"] == "CUSTOM"


def test_validate_accelerator_config_valid():
    """Ensure valid accelerator configs pass validation."""
    cluster = RayCluster(
        name="test-cluster",
        namespace="default",
        head_accelerators={"nvidia.com/gpu": 1},
    )
    assert cluster.head_accelerators["nvidia.com/gpu"] == 1


def test_validate_accelerator_config_missing():
    """Ensure unknown accelerators raise ValueError."""
    with pytest.raises(ValueError, match="Accelerator 'unknown.com/accel'"):
        RayCluster(
            name="test-cluster",
            namespace="default",
            head_accelerators={"unknown.com/accel": 1},
        )


# -------------------------------------------------------------------------
# Memory Edge Case Tests
# -------------------------------------------------------------------------


def test_memory_zero_value_int():
    """Ensure zero memory values are handled correctly as integers."""
    cluster = RayCluster(
        name="test-cluster",
        namespace="default",
        head_memory_requests=0,
        head_memory_limits=0,
        worker_memory_requests=0,
        worker_memory_limits=0,
    )
    assert cluster.head_memory_requests == "0Gi"
    assert cluster.head_memory_limits == "0Gi"
    assert cluster.worker_memory_requests == "0Gi"
    assert cluster.worker_memory_limits == "0Gi"


def test_memory_zero_value_string():
    """Ensure zero memory values as decimal strings get Gi suffix."""
    cluster = RayCluster(
        name="test-cluster",
        namespace="default",
        head_memory_requests="0",
        head_memory_limits="0",
        worker_memory_requests="0",
        worker_memory_limits="0",
    )
    assert cluster.head_memory_requests == "0Gi"
    assert cluster.head_memory_limits == "0Gi"
    assert cluster.worker_memory_requests == "0Gi"
    assert cluster.worker_memory_limits == "0Gi"


def test_memory_with_unit_preserved():
    """Ensure memory values with units (Mi, Gi, etc.) are preserved."""
    cluster = RayCluster(
        name="test-cluster",
        namespace="default",
        head_memory_requests="512Mi",
        head_memory_limits="1Gi",
        worker_memory_requests="256Mi",
        worker_memory_limits="2Gi",
    )
    assert cluster.head_memory_requests == "512Mi"
    assert cluster.head_memory_limits == "1Gi"
    assert cluster.worker_memory_requests == "256Mi"
    assert cluster.worker_memory_limits == "2Gi"


def test_memory_large_values():
    """Ensure large memory values are handled correctly."""
    cluster = RayCluster(
        name="test-cluster",
        namespace="default",
        head_memory_requests=128,
        head_memory_limits=256,
    )
    assert cluster.head_memory_requests == "128Gi"
    assert cluster.head_memory_limits == "256Gi"

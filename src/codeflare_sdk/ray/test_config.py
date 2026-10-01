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

"""Unit tests for the unified RayClusterConfig pydantic v2 model."""

import pytest
from kubernetes.client import V1Toleration, V1Volume, V1VolumeMount
from pydantic import ValidationError

from codeflare_sdk.ray.config import DEFAULT_ACCELERATORS, RayClusterConfig


class TestDefaultInstantiation:
    """Verify RayClusterConfig() with all defaults produces correct values."""

    def test_default_instantiation(self):
        cfg = RayClusterConfig()

        # Identity
        assert cfg.name is None
        assert cfg.namespace is None

        # Head resources
        assert cfg.head_cpu_requests == 2
        assert cfg.head_cpu_limits == 2
        assert cfg.head_memory_requests == "8G"
        assert cfg.head_memory_limits == "8G"
        assert cfg.head_accelerators == {}
        assert cfg.head_tolerations is None

        # Worker resources
        assert cfg.worker_cpu_requests == 1
        assert cfg.worker_cpu_limits == 1
        assert cfg.worker_memory_requests == "2G"
        assert cfg.worker_memory_limits == "2G"
        assert cfg.worker_accelerators == {}
        assert cfg.worker_tolerations is None
        assert cfg.num_workers == 1

        # Autoscaling
        assert cfg.enable_autoscaling is False
        assert cfg.min_workers is None
        assert cfg.max_workers is None

        # Accelerator mapping
        assert cfg.accelerator_configs == DEFAULT_ACCELERATORS

        # Environment and images
        assert cfg.envs == {"RAY_USAGE_STATS_ENABLED": "0"}
        assert cfg.image == ""
        assert cfg.image_pull_secrets == []

        # Kueue
        assert cfg.local_queue is None
        assert cfg.priority_class is None

        # Kubernetes metadata
        assert cfg.labels == {}
        assert cfg.annotations == {}
        assert cfg.volumes == []
        assert cfg.volume_mounts == []

        # Cluster behavior
        assert cfg.write_to_file is False
        assert cfg.verify_tls is True
        assert cfg.enable_usage_stats is False

        # GCS fault tolerance
        assert cfg.enable_gcs_ft is False
        assert cfg.redis_address is None
        assert cfg.redis_password_secret is None
        assert cfg.external_storage_namespace is None


class TestExtraFieldsForbidden:
    """ConfigDict(extra='forbid') rejects unknown fields."""

    def test_extra_fields_forbidden(self):
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            RayClusterConfig(unknown_field="value")


class TestAllParameters:
    """Instantiation with every field set to non-default values."""

    def test_all_parameters(self):
        tolerations = [V1Toleration(key="gpu", operator="Exists", effect="NoSchedule")]
        volumes = [V1Volume(name="data", empty_dir={})]
        volume_mounts = [V1VolumeMount(name="data", mount_path="/data")]

        cfg = RayClusterConfig(
            name="my-cluster",
            namespace="test-ns",
            head_cpu_requests=4,
            head_cpu_limits=8,
            head_memory_requests="16Gi",
            head_memory_limits="32Gi",
            head_accelerators={"nvidia.com/gpu": 2},
            head_tolerations=tolerations,
            worker_cpu_requests=2,
            worker_cpu_limits=4,
            worker_memory_requests="8Gi",
            worker_memory_limits="16Gi",
            worker_accelerators={"nvidia.com/gpu": 1},
            worker_tolerations=tolerations,
            num_workers=4,
            enable_autoscaling=True,
            min_workers=2,
            max_workers=8,
            accelerator_configs={**DEFAULT_ACCELERATORS, "custom.io/accel": "CUSTOM"},
            envs={"MY_VAR": "value"},
            image="quay.io/my-org/ray:2.9",
            image_pull_secrets=["my-secret"],
            local_queue="team-queue",
            priority_class="high-priority",
            labels={"team": "ml"},
            annotations={"note": "test"},
            volumes=volumes,
            volume_mounts=volume_mounts,
            write_to_file=True,
            verify_tls=True,
            enable_usage_stats=True,
            enable_gcs_ft=True,
            redis_address="redis:6379",
            redis_password_secret={"name": "redis-secret", "key": "password"},
            external_storage_namespace="backup-ns",
        )

        assert cfg.name == "my-cluster"
        assert cfg.namespace == "test-ns"
        assert cfg.head_cpu_requests == 4
        assert cfg.head_cpu_limits == 8
        assert cfg.head_memory_requests == "16Gi"
        assert cfg.head_memory_limits == "32Gi"
        assert cfg.head_accelerators == {"nvidia.com/gpu": 2}
        assert cfg.head_tolerations == tolerations
        assert cfg.worker_cpu_requests == 2
        assert cfg.worker_cpu_limits == 4
        assert cfg.worker_memory_requests == "8Gi"
        assert cfg.worker_memory_limits == "16Gi"
        assert cfg.worker_accelerators == {"nvidia.com/gpu": 1}
        assert cfg.worker_tolerations == tolerations
        assert cfg.num_workers == 4
        assert cfg.enable_autoscaling is True
        assert cfg.min_workers == 2
        assert cfg.max_workers == 8
        assert "custom.io/accel" in cfg.accelerator_configs
        assert cfg.envs["MY_VAR"] == "value"
        assert cfg.envs["RAY_USAGE_STATS_ENABLED"] == "1"
        assert cfg.image == "quay.io/my-org/ray:2.9"
        assert cfg.image_pull_secrets == ["my-secret"]
        assert cfg.local_queue == "team-queue"
        assert cfg.priority_class == "high-priority"
        assert cfg.labels == {"team": "ml"}
        assert cfg.annotations == {"note": "test"}
        assert cfg.volumes == volumes
        assert cfg.volume_mounts == volume_mounts
        assert cfg.write_to_file is True
        assert cfg.enable_gcs_ft is True
        assert cfg.redis_address == "redis:6379"
        assert cfg.redis_password_secret == {"name": "redis-secret", "key": "password"}
        assert cfg.external_storage_namespace == "backup-ns"


class TestMemoryNormalization:
    """Memory fields normalize bare ints and decimal strings to 'NG' format."""

    def test_memory_normalization_int_to_string(self):
        cfg = RayClusterConfig(head_memory_requests=16)
        assert cfg.head_memory_requests == "16G"

    def test_memory_normalization_decimal_string(self):
        cfg = RayClusterConfig(head_memory_requests="16")
        assert cfg.head_memory_requests == "16G"

    def test_memory_string_with_unit_unchanged(self):
        cfg = RayClusterConfig(head_memory_requests="8Gi")
        assert cfg.head_memory_requests == "8Gi"

    def test_all_memory_fields_normalize(self):
        cfg = RayClusterConfig(
            head_memory_requests=10,
            head_memory_limits=20,
            worker_memory_requests=4,
            worker_memory_limits=8,
        )
        assert cfg.head_memory_requests == "10G"
        assert cfg.head_memory_limits == "20G"
        assert cfg.worker_memory_requests == "4G"
        assert cfg.worker_memory_limits == "8G"


class TestNameValidation:
    """Cluster name must be a valid RFC 1123 subdomain if provided."""

    def test_name_validation_valid(self):
        cfg = RayClusterConfig(name="my-cluster")
        assert cfg.name == "my-cluster"

    def test_name_validation_invalid_uppercase(self):
        with pytest.raises(ValidationError, match="RFC 1123"):
            RayClusterConfig(name="MyCluster")

    def test_name_validation_invalid_trailing_hyphen(self):
        with pytest.raises(ValidationError, match="RFC 1123"):
            RayClusterConfig(name="my-cluster-")

    def test_name_validation_invalid_leading_hyphen(self):
        with pytest.raises(ValidationError, match="RFC 1123"):
            RayClusterConfig(name="-my-cluster")

    def test_name_none_accepted(self):
        cfg = RayClusterConfig(name=None)
        assert cfg.name is None

    def test_name_empty_string_rejected(self):
        with pytest.raises(ValidationError, match="RFC 1123"):
            RayClusterConfig(name="")

    def test_name_default_none(self):
        cfg = RayClusterConfig()
        assert cfg.name is None


class TestAutoscalingValidation:
    """Autoscaling model validator enforces min/max worker constraints."""

    def test_autoscaling_valid(self):
        cfg = RayClusterConfig(enable_autoscaling=True, min_workers=1, max_workers=8)
        assert cfg.enable_autoscaling is True
        assert cfg.min_workers == 1
        assert cfg.max_workers == 8

    def test_autoscaling_zero_min_workers(self):
        cfg = RayClusterConfig(enable_autoscaling=True, min_workers=0, max_workers=4)
        assert cfg.min_workers == 0

    def test_autoscaling_missing_workers(self):
        with pytest.raises(
            ValidationError, match="min_workers and max_workers must be provided"
        ):
            RayClusterConfig(enable_autoscaling=True)

    def test_autoscaling_missing_max_workers(self):
        with pytest.raises(
            ValidationError, match="min_workers and max_workers must be provided"
        ):
            RayClusterConfig(enable_autoscaling=True, min_workers=1)

    def test_autoscaling_negative_min(self):
        with pytest.raises(ValidationError, match="min_workers must be >= 0"):
            RayClusterConfig(enable_autoscaling=True, min_workers=-1, max_workers=4)

    def test_autoscaling_max_less_than_min(self):
        with pytest.raises(ValidationError, match="max_workers must be >= min_workers"):
            RayClusterConfig(enable_autoscaling=True, min_workers=5, max_workers=2)

    def test_autoscaling_disabled_ignores_workers(self):
        with pytest.warns(UserWarning, match="min_workers and max_workers are ignored"):
            cfg = RayClusterConfig(
                enable_autoscaling=False, min_workers=1, max_workers=8
            )
        assert cfg.enable_autoscaling is False


class TestGcsFaultTolerance:
    """GCS FT model validator enforces redis_address and secret format."""

    def test_gcs_ft_valid(self):
        cfg = RayClusterConfig(
            enable_gcs_ft=True,
            redis_address="redis:6379",
            redis_password_secret={"name": "redis-secret", "key": "password"},
            external_storage_namespace="backup-ns",
        )
        assert cfg.enable_gcs_ft is True
        assert cfg.redis_address == "redis:6379"
        assert cfg.redis_password_secret == {
            "name": "redis-secret",
            "key": "password",
        }
        assert cfg.external_storage_namespace == "backup-ns"

    def test_gcs_ft_missing_redis(self):
        with pytest.raises(
            ValidationError,
            match="redis_address must be provided when enable_gcs_ft is True",
        ):
            RayClusterConfig(enable_gcs_ft=True)

    def test_gcs_ft_bad_password_secret_missing_name(self):
        with pytest.raises(
            ValidationError,
            match="redis_password_secret must contain both 'name' and 'key' fields",
        ):
            RayClusterConfig(
                enable_gcs_ft=True,
                redis_address="redis:6379",
                redis_password_secret={"key": "password"},
            )

    def test_gcs_ft_bad_password_secret_missing_key(self):
        with pytest.raises(
            ValidationError,
            match="redis_password_secret must contain both 'name' and 'key' fields",
        ):
            RayClusterConfig(
                enable_gcs_ft=True,
                redis_address="redis:6379",
                redis_password_secret={"name": "redis-secret"},
            )


class TestAcceleratorValidation:
    """Accelerator keys must exist in accelerator_configs."""

    def test_accelerator_validation_valid_default(self):
        cfg = RayClusterConfig(head_accelerators={"nvidia.com/gpu": 1})
        assert cfg.head_accelerators == {"nvidia.com/gpu": 1}

    def test_accelerator_validation_invalid_head(self):
        with pytest.raises(
            ValidationError, match="accelerator 'unknown.io/device' not found"
        ):
            RayClusterConfig(head_accelerators={"unknown.io/device": 1})

    def test_accelerator_validation_invalid_worker(self):
        with pytest.raises(
            ValidationError, match="accelerator 'unknown.io/device' not found"
        ):
            RayClusterConfig(worker_accelerators={"unknown.io/device": 1})

    def test_accelerator_configs_default(self):
        cfg = RayClusterConfig()
        assert cfg.accelerator_configs == DEFAULT_ACCELERATORS

    def test_accelerator_configs_default_is_copy(self):
        cfg1 = RayClusterConfig()
        cfg2 = RayClusterConfig()
        assert cfg1.accelerator_configs is not cfg2.accelerator_configs

    def test_accelerator_configs_custom_override(self):
        custom = {"my.io/gpu": "GPU"}
        cfg = RayClusterConfig(accelerator_configs=custom)
        assert cfg.accelerator_configs == custom
        assert "nvidia.com/gpu" not in cfg.accelerator_configs

    def test_accelerator_configs_extend(self):
        extended = {**DEFAULT_ACCELERATORS, "custom.io/accel": "CUSTOM"}
        cfg = RayClusterConfig(
            accelerator_configs=extended,
            head_accelerators={"custom.io/accel": 1},
        )
        assert "custom.io/accel" in cfg.accelerator_configs
        assert "nvidia.com/gpu" in cfg.accelerator_configs


class TestKueueFields:
    """Kueue integration fields accepted with proper validation (AC2)."""

    def test_kueue_local_queue(self):
        cfg = RayClusterConfig(local_queue="my-queue")
        assert cfg.local_queue == "my-queue"

    def test_kueue_priority_class(self):
        cfg = RayClusterConfig(priority_class="high-priority")
        assert cfg.priority_class == "high-priority"

    def test_kueue_both_fields(self):
        cfg = RayClusterConfig(local_queue="team-queue", priority_class="batch-low")
        assert cfg.local_queue == "team-queue"
        assert cfg.priority_class == "batch-low"


class TestUsageStats:
    """RAY_USAGE_STATS_ENABLED env var set by enable_usage_stats."""

    def test_usage_stats_default_disabled(self):
        cfg = RayClusterConfig()
        assert cfg.envs["RAY_USAGE_STATS_ENABLED"] == "0"

    def test_usage_stats_enabled(self):
        cfg = RayClusterConfig(enable_usage_stats=True)
        assert cfg.envs["RAY_USAGE_STATS_ENABLED"] == "1"

    def test_usage_stats_overrides_user_env(self):
        cfg = RayClusterConfig(
            envs={"RAY_USAGE_STATS_ENABLED": "1"}, enable_usage_stats=False
        )
        assert cfg.envs["RAY_USAGE_STATS_ENABLED"] == "0"


class TestTlsVerification:
    """TLS disabled emits UserWarning."""

    def test_verify_tls_false_warning(self):
        with pytest.warns(UserWarning, match="TLS verification has been disabled"):
            RayClusterConfig(verify_tls=False)


class TestTypeValidation:
    """Pydantic v2 native type validation rejects wrong types."""

    def test_type_validation_wrong_type(self):
        with pytest.raises(ValidationError):
            RayClusterConfig(num_workers="not_an_int")


class TestFieldParity:
    """Verify every field from both source classes has a corresponding
    field in RayClusterConfig (using the spec's field mapping table)."""

    # Mapping: ClusterConfiguration field -> RayClusterConfig field (or None if eliminated)
    CLUSTER_CONFIG_FIELD_MAP = {
        "name": "name",
        "namespace": "namespace",
        "head_cpu_requests": "head_cpu_requests",
        "head_cpu_limits": "head_cpu_limits",
        "head_memory_requests": "head_memory_requests",
        "head_memory_limits": "head_memory_limits",
        "head_extended_resource_requests": "head_accelerators",
        "head_tolerations": "head_tolerations",
        "worker_cpu_requests": "worker_cpu_requests",
        "worker_cpu_limits": "worker_cpu_limits",
        "num_workers": "num_workers",
        "worker_memory_requests": "worker_memory_requests",
        "worker_memory_limits": "worker_memory_limits",
        "worker_tolerations": "worker_tolerations",
        "envs": "envs",
        "image": "image",
        "image_pull_secrets": "image_pull_secrets",
        "write_to_file": "write_to_file",
        "verify_tls": "verify_tls",
        "labels": "labels",
        "worker_extended_resource_requests": "worker_accelerators",
        "extended_resource_mapping": "accelerator_configs",
        "overwrite_default_resource_mapping": None,  # eliminated by design
        "local_queue": "local_queue",
        "enable_autoscaling": "enable_autoscaling",
        "min_workers": "min_workers",
        "max_workers": "max_workers",
        "annotations": "annotations",
        "volumes": "volumes",
        "volume_mounts": "volume_mounts",
        "enable_gcs_ft": "enable_gcs_ft",
        "enable_usage_stats": "enable_usage_stats",
        "redis_address": "redis_address",
        "redis_password_secret": "redis_password_secret",
        "external_storage_namespace": "external_storage_namespace",
    }

    # Mapping: ManagedClusterConfig field -> RayClusterConfig field
    MANAGED_CONFIG_FIELD_MAP = {
        "head_cpu_requests": "head_cpu_requests",
        "head_cpu_limits": "head_cpu_limits",
        "head_memory_requests": "head_memory_requests",
        "head_memory_limits": "head_memory_limits",
        "head_accelerators": "head_accelerators",
        "head_tolerations": "head_tolerations",
        "worker_cpu_requests": "worker_cpu_requests",
        "worker_cpu_limits": "worker_cpu_limits",
        "num_workers": "num_workers",
        "worker_memory_requests": "worker_memory_requests",
        "worker_memory_limits": "worker_memory_limits",
        "worker_tolerations": "worker_tolerations",
        "envs": "envs",
        "image": "image",
        "image_pull_secrets": "image_pull_secrets",
        "labels": "labels",
        "worker_accelerators": "worker_accelerators",
        "accelerator_configs": "accelerator_configs",
        "annotations": "annotations",
        "volumes": "volumes",
        "volume_mounts": "volume_mounts",
    }

    def test_parity_cluster_config_fields(self):
        """Every ClusterConfiguration field maps to a RayClusterConfig field."""
        from dataclasses import fields as dataclass_fields

        from codeflare_sdk.ray.cluster.config import ClusterConfiguration

        cc_fields = {f.name for f in dataclass_fields(ClusterConfiguration)}
        ray_fields = set(RayClusterConfig.model_fields.keys())

        for cc_field in cc_fields:
            mapped = self.CLUSTER_CONFIG_FIELD_MAP.get(cc_field)
            assert mapped is not None or cc_field in self.CLUSTER_CONFIG_FIELD_MAP, (
                f"ClusterConfiguration field '{cc_field}' has no mapping entry. "
                f"Add it to CLUSTER_CONFIG_FIELD_MAP (use None if intentionally eliminated)."
            )
            if mapped is not None:
                assert mapped in ray_fields, (
                    f"ClusterConfiguration.{cc_field} maps to '{mapped}' "
                    f"but '{mapped}' is not a RayClusterConfig field."
                )

    def test_parity_managed_config_fields(self):
        """Every ManagedClusterConfig field maps to a RayClusterConfig field."""
        from dataclasses import fields as dataclass_fields

        from codeflare_sdk.ray.rayjobs.config import ManagedClusterConfig

        mcc_fields = {f.name for f in dataclass_fields(ManagedClusterConfig)}
        ray_fields = set(RayClusterConfig.model_fields.keys())

        for mcc_field in mcc_fields:
            mapped = self.MANAGED_CONFIG_FIELD_MAP.get(mcc_field)
            assert mapped is not None or mcc_field in self.MANAGED_CONFIG_FIELD_MAP, (
                f"ManagedClusterConfig field '{mcc_field}' has no mapping entry. "
                f"Add it to MANAGED_CONFIG_FIELD_MAP."
            )
            if mapped is not None:
                assert mapped in ray_fields, (
                    f"ManagedClusterConfig.{mcc_field} maps to '{mapped}' "
                    f"but '{mapped}' is not a RayClusterConfig field."
                )

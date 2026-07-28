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

    def test_name_default_none(self):
        cfg = RayClusterConfig()
        assert cfg.name is None

# Copyright 2026 IBM, Red Hat
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

"""Unit tests for the shared RayCluster spec pieces (RHOAIENG-98942)."""

import pytest

from codeflare_sdk.ray.cluster.config import ClusterConfiguration
from codeflare_sdk.ray.cluster.raycluster_spec import (
    gcs_fault_tolerance_options,
    worker_replica_counts,
)


class TestGcsFaultToleranceOptions:
    def test_returns_none_when_disabled(self):
        assert gcs_fault_tolerance_options(ClusterConfiguration(name="c")) is None

    def test_redis_address_only(self):
        config = ClusterConfiguration(
            name="c", enable_gcs_ft=True, redis_address="redis:6379"
        )
        assert gcs_fault_tolerance_options(config) == {"redisAddress": "redis:6379"}

    def test_external_storage_namespace_is_included(self):
        config = ClusterConfiguration(
            name="c",
            enable_gcs_ft=True,
            redis_address="redis:6379",
            external_storage_namespace="ns",
        )
        assert gcs_fault_tolerance_options(config)["externalStorageNamespace"] == "ns"

    def test_redis_password_becomes_a_secret_key_ref(self):
        config = ClusterConfiguration(
            name="c",
            enable_gcs_ft=True,
            redis_address="redis:6379",
            redis_password_secret={"name": "s", "key": "k"},
        )
        assert gcs_fault_tolerance_options(config)["redisPassword"] == {
            "valueFrom": {"secretKeyRef": {"name": "s", "key": "k"}}
        }

    def test_redis_address_is_required(self):
        # ClusterConfiguration rejects this combination at construction, so the
        # guard here only fires if a caller mutates the config afterwards.
        config = ClusterConfiguration(
            name="c", enable_gcs_ft=True, redis_address="redis:6379"
        )
        config.redis_address = None

        with pytest.raises(ValueError, match="redis_address must be provided"):
            gcs_fault_tolerance_options(config)


class TestWorkerReplicaCounts:
    def test_fixed_size_uses_num_workers_for_all_three(self):
        config = ClusterConfiguration(name="c", num_workers=4)
        assert worker_replica_counts(config) == (4, 4, 4)

    def test_autoscaling_uses_the_configured_range(self):
        config = ClusterConfiguration(
            name="c", enable_autoscaling=True, min_workers=2, max_workers=7
        )
        assert worker_replica_counts(config) == (2, 2, 7)

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

"""
RHOAIENG-98942: no ClusterConfiguration field may be silently ignored.

Two builders consume ClusterConfiguration and must stay in parity:

* standalone RayCluster: ``ray/cluster/build_ray_cluster.py``
* RayJob-embedded rayClusterSpec: ``ray/rayjobs/config.py``

A field added to one and forgotten in the other produces no error — the
cluster simply comes up without it. This module sets every field to a
recognisable sentinel, renders both specs, and asserts the sentinel reaches
both. Anything that legitimately does not reach a builder must be listed in
``CONTEXT_ONLY``, ``NOT_APPLICABLE`` or ``CONFLICTED`` with a reason, so the
decision is recorded rather than discovered later by a user.
"""

from dataclasses import fields
from unittest.mock import patch

import pytest
from kubernetes.client import V1Toleration, V1Volume, V1VolumeMount

from codeflare_sdk.ray.cluster import build_ray_cluster as brc
from codeflare_sdk.ray.cluster.config import ClusterConfiguration
from codeflare_sdk.ray.rayjobs.config import build_ray_cluster_spec

# Consumed before a builder ever sees them, so their absence is correct.
CONTEXT_ONLY = {
    "overwrite_default_resource_mapping": (
        "consumed by __post_init__ when merging extended_resource_mapping"
    ),
    "enable_usage_stats": (
        "consumed by __post_init__, which writes RAY_USAGE_STATS_ENABLED into envs"
    ),
    "verify_tls": "client-side only; governs dashboard calls, not the CR",
}

# Meaningful for a standalone RayCluster, meaningless inside a RayJob.
NOT_APPLICABLE = {
    "name": "RayJob derives the cluster name as '<job_name>-cluster'",
    "namespace": "the embedded rayClusterSpec has no metadata block",
    "write_to_file": "only the standalone path writes a YAML file",
}

# Set on both sides with undefined precedence. Tracked in RHOAIENG-98949.
CONFLICTED = {
    "local_queue": "RayJob takes its own local_queue and ignores the config's",
}

EXEMPT = {**CONTEXT_ONLY, **NOT_APPLICABLE, **CONFLICTED}

# One recognisable value per field, chosen so it survives into the rendered
# spec as a substring. Memory/CPU values are deliberately odd numbers so they
# cannot collide with a default.
SENTINELS = {
    "head_cpu_requests": "111m",
    "head_cpu_limits": "222m",
    "head_memory_requests": "17G",
    "head_memory_limits": "19G",
    "head_extended_resource_requests": {"sentinel.io/head-acc": 3},
    "head_tolerations": [V1Toleration(key="sentinel-head-toleration")],
    "worker_cpu_requests": "333m",
    "worker_cpu_limits": "444m",
    "worker_memory_requests": "21G",
    "worker_memory_limits": "23G",
    "worker_extended_resource_requests": {"sentinel.io/worker-acc": 5},
    "worker_tolerations": [V1Toleration(key="sentinel-worker-toleration")],
    "num_workers": 7,
    "envs": {"SENTINEL_ENV": "sentinel-env-value"},
    "image": "sentinel.io/ray:sentinel-tag",
    "image_pull_secrets": ["sentinel-pull-secret"],
    "labels": {"sentinel.io/label": "sentinel-label-value"},
    "annotations": {"sentinel.io/annotation": "sentinel-annotation-value"},
    "volumes": [V1Volume(name="sentinel-volume")],
    "volume_mounts": [V1VolumeMount(name="sentinel-volume", mount_path="/sentinel")],
    # Both accelerators above need an entry here, or __post_init__ rejects them.
    "extended_resource_mapping": {
        "sentinel.io/head-acc": "SENTINEL_ACC",
        "sentinel.io/worker-acc": "SENTINEL_WORKER_ACC",
    },
    "enable_gcs_ft": True,
    "redis_address": "sentinel-redis:6379",
    "redis_password_secret": {"name": "sentinel-secret", "key": "sentinel-key"},
    "external_storage_namespace": "sentinel-storage-namespace",
    "enable_autoscaling": True,
    "min_workers": 2,
    "max_workers": 9,
    "additional_worker_groups": [],
}

# The substring to look for, when it is not the sentinel value itself.
MARKERS = {
    "head_extended_resource_requests": "sentinel.io/head-acc",
    "worker_extended_resource_requests": "sentinel.io/worker-acc",
    "head_tolerations": "sentinel-head-toleration",
    "worker_tolerations": "sentinel-worker-toleration",
    "envs": "SENTINEL_ENV",
    # Rendered as V1LocalObjectReference(name=...), not as the list itself.
    "image_pull_secrets": "sentinel-pull-secret",
    "labels": "sentinel.io/label",
    "annotations": "sentinel.io/annotation",
    "volumes": "sentinel-volume",
    "volume_mounts": "/sentinel",
    "extended_resource_mapping": "SENTINEL_ACC",
    "redis_password_secret": "sentinel-secret",
    "enable_gcs_ft": None,  # observable only through the fields below
    "enable_autoscaling": None,  # observable through min/max replicas
    "num_workers": None,  # replicas, checked structurally below
    "additional_worker_groups": None,  # empty by default; covered separately
    "min_workers": None,
    "max_workers": None,
}

# Fields the RayJob path drops. Empty since RHOAIENG-98942 closed the last of
# them; kept as the mechanism, because the next drift is easier to record here
# than to rediscover. Entries are xfail(strict=True), so a gap that gets fixed
# without being removed from this dict fails the suite rather than passing
# quietly.
KNOWN_GAPS: dict = {}


def _configurable():
    for f in fields(ClusterConfiguration):
        if f.name in EXEMPT or MARKERS.get(f.name, "") is None:
            continue
        reason = KNOWN_GAPS.get(f.name)
        marks = [pytest.mark.xfail(strict=True, reason=reason)] if reason else []
        yield pytest.param(f.name, marks=marks, id=f.name)


CONFIGURABLE = list(_configurable())


class _FakeCluster:
    """build_ray_cluster() takes a Cluster; only .config is read."""

    def __init__(self, config):
        self.config = config


def _full_config(**overrides):
    values = {k: v for k, v in SENTINELS.items()}
    values.update(overrides)
    # GCS fault tolerance requires a redis address, and autoscaling requires
    # a worker range, so these travel together.
    return ClusterConfiguration(name="parity", namespace="parity-ns", **values)


def _render_standalone(config) -> str:
    # The standalone builder reaches the Kueue API while rendering — both
    # local_queue_exists() and get_default_local_queue() list LocalQueues —
    # which the RayJob builder never does. Lifting that I/O out of spec
    # construction is the point of RHOAIENG-98942; until then it has to be
    # stubbed to render a spec at all.
    with (
        patch.object(brc, "local_queue_exists", return_value=True),
        patch.object(brc, "get_default_local_queue", return_value=None),
    ):
        return repr(brc.build_ray_cluster(_FakeCluster(config)))


def _render_embedded(config) -> str:
    return repr(build_ray_cluster_spec(config=config, cluster_name="parity-cluster"))


@pytest.fixture
def rendered():
    # Function-scoped on purpose: the global autouse mock_kubernetes fixture in
    # conftest.py is function-scoped, and a wider scope here would run outside it.
    config = _full_config()
    return _render_standalone(config), _render_embedded(config)


@pytest.mark.parametrize("field_name", CONFIGURABLE)
def test_field_reaches_both_builders(field_name, rendered):
    """Every configurable field must appear in both rendered specs."""
    standalone, embedded = rendered
    marker = MARKERS.get(field_name) or str(SENTINELS[field_name])

    assert marker in standalone, f"{field_name} missing from the standalone RayCluster"
    assert marker in embedded, f"{field_name} missing from the RayJob rayClusterSpec"


def test_known_gaps_are_real_fields():
    """A gap entry that no longer matches a field would xfail nothing."""
    actual = {f.name for f in fields(ClusterConfiguration)}
    assert set(KNOWN_GAPS) <= actual
    assert all(reason for reason in KNOWN_GAPS.values())


def test_every_field_is_classified():
    """A new ClusterConfiguration field must be given a parity decision."""
    known = set(SENTINELS) | set(EXEMPT)
    actual = {f.name for f in fields(ClusterConfiguration)}

    unclassified = actual - known
    assert unclassified == set(), (
        f"New ClusterConfiguration field(s) {sorted(unclassified)}: add a sentinel "
        "so parity is checked, or list them in CONTEXT_ONLY / NOT_APPLICABLE / "
        "CONFLICTED with a reason."
    )
    assert known - actual == set(), "stale entry for a field that no longer exists"


def test_exemptions_each_carry_a_reason():
    """An exemption without a reason is an undocumented silent drop."""
    assert all(reason for reason in EXEMPT.values())


def test_worker_replicas_match_the_configured_count(rendered):
    """num_workers drives replicas on both paths (min/max under autoscaling)."""
    standalone, embedded = rendered

    # enable_autoscaling is on in the full config, so min/max_workers win.
    for spec in (standalone, embedded):
        assert "'minReplicas': 2" in spec
        assert "'maxReplicas': 9" in spec


def test_fixed_size_replicas_match_num_workers():
    """Without autoscaling, replicas come from num_workers on both paths."""
    config = _full_config(enable_autoscaling=False, min_workers=None, max_workers=None)
    standalone = _render_standalone(config)
    embedded = _render_embedded(config)

    for spec in (standalone, embedded):
        assert "'replicas': 7" in spec
        assert "'minReplicas': 7" in spec
        assert "'maxReplicas': 7" in spec

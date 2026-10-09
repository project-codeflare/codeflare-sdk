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
from kubernetes.client import ApiClient, V1Toleration, V1Volume, V1VolumeMount

from codeflare_sdk.ray.cluster import build_ray_cluster as brc
from codeflare_sdk.ray.cluster.config import ClusterConfiguration, WorkerGroup
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

# Standalone emits these; the RayJob path deliberately does not. 52a351a
# ("RHOAIENG-30720: Remove GCS FT for Lifecycled RayClusters") stripped them
# from the lifecycled path because head pod restarts lost state, and scoped the
# fix to standalone RayCluster only. #1091 then made ClusterConfiguration
# shared, so they are now accepted and validated here and ignored. Whether to
# emit or reject them is RHOAIENG-98943; until that is decided, the asymmetry
# is pinned by test_gcs_fault_tolerance_is_standalone_only rather than treated
# as drift.
PENDING_DECISION = {
    "enable_gcs_ft": "RHOAIENG-98943: GCS FT removed from the RayJob path by RHOAIENG-30720",
    "redis_address": "RHOAIENG-98943: GCS FT removed from the RayJob path by RHOAIENG-30720",
    "redis_password_secret": "RHOAIENG-98943: GCS FT removed from the RayJob path by RHOAIENG-30720",
    "external_storage_namespace": "RHOAIENG-98943: GCS FT removed from the RayJob path by RHOAIENG-30720",
}

# Reaches both paths, but lands somewhere different on each, so a presence
# check cannot express it. Pinned by test_labels_land_where_each_path_puts_them.
PARTIAL = {
    "labels": (
        "both paths carry them, to different places. #1184 put them on every "
        "RayJob pod template; standalone writes them to the RayCluster CR "
        "metadata and to additional worker group pods, but not to the head or "
        "default worker pods. Closing that changes existing standalone output, "
        "so it is RHOAIENG-99560 rather than this PR."
    ),
}

EXEMPT = {
    **CONTEXT_ONLY,
    **NOT_APPLICABLE,
    **CONFLICTED,
    **PENDING_DECISION,
    **PARTIAL,
}

# WorkerGroup travels inside ClusterConfiguration.additional_worker_groups and
# is assembled by a *second* pair of duplicated functions —
# build_ray_cluster._build_worker_group_spec and
# rayjobs.config._build_additional_worker_group_spec. Those can drift exactly
# as the main builders can, so every field gets a sentinel here too. An
# earlier version set only group_name and replicas, which meant envs, labels,
# tolerations, image, the GPU settings and extended resources could diverge
# between the two and this suite would still pass.
WORKER_GROUP_SENTINELS = {
    "group_name": "sentinel-extra-group",
    "replicas": 3,
    "min_replicas": 2,
    "max_replicas": 8,
    "cpu_requests": "555m",
    "cpu_limits": "666m",
    "memory_requests": "29G",
    "memory_limits": "31G",
    "gpu_type": "sentinel.io/wg-acc",
    "gpu_count": 13,
    "extended_resource_requests": {"sentinel.io/wg-ext": 11},
    "image": "sentinel.io/wg-image:sentinel-wg-tag",
    "envs": {"SENTINEL_WG_ENV": "sentinel-wg-env-value"},
    "labels": {"sentinel.io/wg-label": "sentinel-wg-label-value"},
    "tolerations": [V1Toleration(key="sentinel-wg-toleration")],
}

# The substring to look for, when it is not the sentinel value itself.
WORKER_GROUP_MARKERS = {
    "extended_resource_requests": "sentinel.io/wg-ext",
    "envs": "SENTINEL_WG_ENV",
    "labels": "sentinel.io/wg-label",
    "tolerations": "sentinel-wg-toleration",
    # Rendered as a resource name on the container, not as the bare string.
    "gpu_type": "sentinel.io/wg-acc",
}

# Counts, which a substring search cannot distinguish from any other number
# in the spec. Asserted structurally by the named test instead.
WORKER_GROUP_STRUCTURAL = {
    "replicas": "test_worker_group_replica_counts_match_on_both_paths",
    "min_replicas": "test_worker_group_replica_counts_match_on_both_paths",
    "max_replicas": "test_worker_group_replica_counts_match_on_both_paths",
    "gpu_count": "test_worker_group_gpu_count_matches_on_both_paths",
}

WORKER_GROUP = WorkerGroup(**WORKER_GROUP_SENTINELS)

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
        # WorkerGroup.gpu_type is mapped through this same dict; without an
        # entry it defaults to "GPU" and never reaches rayStartParams.
        "sentinel.io/wg-acc": "SENTINEL_WG_ACC",
    },
    "enable_gcs_ft": True,
    "redis_address": "sentinel-redis:6379",
    "redis_password_secret": {"name": "sentinel-secret", "key": "sentinel-key"},
    "external_storage_namespace": "sentinel-storage-namespace",
    "enable_autoscaling": True,
    "min_workers": 2,
    "max_workers": 9,
    "additional_worker_groups": [WORKER_GROUP],
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
    "additional_worker_groups": "sentinel-extra-group",
}

# Fields with no distinctive string of their own: a boolean or a count cannot
# be found by searching a rendered spec, and a substring check for "2" would
# pass on any spec that happens to contain a 2. Each is asserted against the
# structured spec instead, by the named test below.
#
# They are listed rather than skipped — an earlier version of this module
# filtered them out of the parametrized test, which quietly meant six fields
# were never parity-checked at all.
STRUCTURAL = {
    "num_workers": "test_replica_counts_match_on_both_paths",
    "min_workers": "test_replica_counts_match_on_both_paths",
    "max_workers": "test_replica_counts_match_on_both_paths",
    "enable_autoscaling": "test_autoscaling_flag_matches_on_both_paths",
}

# Fields the RayJob path drops. Empty since RHOAIENG-98942 closed the last of
# them; kept as the mechanism, because the next drift is easier to record here
# than to rediscover. Entries are xfail(strict=True), so a gap that gets fixed
# without being removed from this dict fails the suite rather than passing
# quietly.
KNOWN_GAPS: dict = {}


def _configurable():
    for f in fields(ClusterConfiguration):
        if f.name in EXEMPT or f.name in STRUCTURAL:
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


def _as_plain_dict(obj) -> dict:
    """Render Kubernetes model objects down to plain dicts.

    Both builders return dicts holding V1PodTemplateSpec and friends, so
    structural assertions need them flattened first. sanitize_for_serialization
    is pure — it makes no API call — so an unconfigured client is fine here.
    """
    return ApiClient().sanitize_for_serialization(obj)


def _spec_standalone(config) -> dict:
    # The standalone builder reaches the Kueue API while rendering — both
    # local_queue_exists() and get_default_local_queue() list LocalQueues —
    # which the RayJob builder never does. Lifting that I/O out of spec
    # construction is the point of RHOAIENG-98942; until then it has to be
    # stubbed to render a spec at all.
    with (
        patch.object(brc, "local_queue_exists", return_value=True),
        patch.object(brc, "get_default_local_queue", return_value=None),
    ):
        return _as_plain_dict(brc.build_ray_cluster(_FakeCluster(config)))["spec"]


def _spec_embedded(config) -> dict:
    return _as_plain_dict(
        build_ray_cluster_spec(config=config, cluster_name="parity-cluster")
    )


def _render_standalone(config) -> str:
    return repr(_spec_standalone(config))


def _render_embedded(config) -> str:
    return repr(_spec_embedded(config))


@pytest.fixture
def specs():
    """Both specs as plain dicts, for structural assertions."""
    # Function-scoped on purpose: the global autouse mock_kubernetes fixture in
    # conftest.py is function-scoped, and a wider scope here would run outside it.
    config = _full_config()
    return _spec_standalone(config), _spec_embedded(config)


@pytest.fixture
def rendered(specs):
    standalone, embedded = specs
    return repr(standalone), repr(embedded)


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


def test_structural_fields_name_a_real_test():
    """A field routed to a named test must actually have one."""
    here = globals()
    for field_name, test_name in STRUCTURAL.items():
        assert test_name in here, f"{field_name} points at missing {test_name}"


def _default_group(spec: dict) -> dict:
    return spec["workerGroupSpecs"][0]


def test_replica_counts_match_on_both_paths(specs):
    """num_workers / min_workers / max_workers, read off the spec."""
    # Autoscaling is on in the full config, so the min/max range wins.
    for spec in specs:
        group = _default_group(spec)
        assert (group["replicas"], group["minReplicas"], group["maxReplicas"]) == (
            2,
            2,
            9,
        )


def test_fixed_size_replica_counts_match_on_both_paths():
    """Without autoscaling all three come from num_workers, on both paths."""
    config = _full_config(enable_autoscaling=False, min_workers=None, max_workers=None)

    for spec in (_spec_standalone(config), _spec_embedded(config)):
        group = _default_group(spec)
        assert (group["replicas"], group["minReplicas"], group["maxReplicas"]) == (
            7,
            7,
            7,
        )


def test_autoscaling_flag_matches_on_both_paths():
    """enable_autoscaling reaches enableInTreeAutoscaling either way."""
    for enabled in (True, False):
        config = _full_config(
            enable_autoscaling=enabled,
            min_workers=2 if enabled else None,
            max_workers=9 if enabled else None,
        )
        for spec in (_spec_standalone(config), _spec_embedded(config)):
            assert spec["enableInTreeAutoscaling"] is enabled


def test_gcs_fault_tolerance_is_standalone_only():
    """The asymmetry is deliberate, so pin it rather than let it drift.

    52a351a removed GCS fault tolerance from the lifecycled path because the
    feature did not work (RHOAIENG-30720), and that fix was scoped to
    standalone RayCluster. Emitting it on the RayJob path would re-enable
    something nobody has validated there; RHOAIENG-98943 owns the decision.
    This test fails either way round, so whichever way it goes is a conscious
    change.
    """
    expected = {
        "redisAddress": "sentinel-redis:6379",
        "externalStorageNamespace": "sentinel-storage-namespace",
        "redisPassword": {
            "valueFrom": {
                "secretKeyRef": {"name": "sentinel-secret", "key": "sentinel-key"}
            }
        },
    }
    config = _full_config()

    assert _spec_standalone(config)["gcsFaultToleranceOptions"] == expected
    assert "gcsFaultToleranceOptions" not in _spec_embedded(config), (
        "the RayJob path emits GCS FT again — intended only once RHOAIENG-98943 "
        "decides to re-enable it, with validation on a lifecycled cluster"
    )

    off = _full_config(
        enable_gcs_ft=False,
        redis_address=None,
        redis_password_secret=None,
        external_storage_namespace=None,
    )
    assert "gcsFaultToleranceOptions" not in _spec_standalone(off)


def test_labels_land_where_each_path_puts_them(specs):
    """labels are PARTIAL: both paths carry them, to different places.

    A presence check passes on both, so it cannot express the difference.
    Since #1184 the RayJob path puts config.labels on every pod template.
    Standalone puts them on the RayCluster CR metadata and on additional
    worker group pods, but not on the head or default worker pods — so a
    NetworkPolicy selector still behaves differently between the two.

    The standalone gap is the remaining one; closing it adds labels to pods
    that do not have them today, which is a behaviour change and therefore
    RHOAIENG-99560, not this PR. Asserted in full so that either side moving
    is a conscious edit.
    """
    standalone, embedded = specs
    SENTINEL = "sentinel.io/label"

    def pod_labels(template):
        return ((template.get("metadata") or {}).get("labels")) or {}

    # Standalone: CR metadata yes, default pods no, extra group pods yes.
    assert (
        SENTINEL in standalone["workerGroupSpecs"][1]["template"]["metadata"]["labels"]
    )
    assert SENTINEL not in pod_labels(standalone["headGroupSpec"]["template"]), (
        "the standalone head pod now carries config.labels — that is the "
        "RHOAIENG-99560 fix; update docs/raycluster_spec_parity.md with it"
    )
    assert SENTINEL not in pod_labels(standalone["workerGroupSpecs"][0]["template"])

    # RayJob: every pod template, since #1184. No CR metadata block exists.
    for template in (
        embedded["headGroupSpec"]["template"],
        embedded["workerGroupSpecs"][0]["template"],
        embedded["workerGroupSpecs"][1]["template"],
    ):
        assert pod_labels(template)[SENTINEL] == "sentinel-label-value"


def test_additional_worker_groups_reach_both_paths(specs):
    """A configured extra group becomes a second workerGroupSpec on both sides."""
    for spec in specs:
        groups = spec["workerGroupSpecs"]
        assert len(groups) == 2, "the extra worker group did not reach this path"

        extra = groups[1]
        assert "sentinel-extra-group" in extra["groupName"]
        assert extra["replicas"] == 3


# --- WorkerGroup parity (RHOAIENG-98942) ---------------------------------
#
# additional_worker_groups is assembled by a second pair of duplicated
# functions, so it needs its own guard. Reviewed by @chipspeak: a sentinel
# that set only group_name and replicas let every other WorkerGroup field
# drift between the two builders while this suite stayed green.


def _worker_group_configurable():
    for f in fields(WorkerGroup):
        if f.name in WORKER_GROUP_STRUCTURAL:
            continue
        yield pytest.param(f.name, id=f.name)


WORKER_GROUP_CONFIGURABLE = list(_worker_group_configurable())


def _extra_group(spec: dict) -> dict:
    """The workerGroupSpec built from additional_worker_groups[0]."""
    return spec["workerGroupSpecs"][1]


@pytest.mark.parametrize("field_name", WORKER_GROUP_CONFIGURABLE)
def test_worker_group_field_reaches_both_builders(field_name, specs):
    """Every WorkerGroup field must appear in both rendered extra groups."""
    marker = WORKER_GROUP_MARKERS.get(field_name) or str(
        WORKER_GROUP_SENTINELS[field_name]
    )

    for spec, path in zip(specs, ("standalone RayCluster", "RayJob rayClusterSpec")):
        assert marker in repr(_extra_group(spec)), (
            f"WorkerGroup.{field_name} missing from the {path}"
        )


def test_every_worker_group_field_is_classified():
    """A new WorkerGroup field must be given a parity decision too.

    The same gate as test_every_field_is_classified, for the dataclass one
    level down. Without this, adding a field to WorkerGroup silently escapes
    the parity guard.
    """
    known = set(WORKER_GROUP_SENTINELS) | set(WORKER_GROUP_STRUCTURAL)
    actual = {f.name for f in fields(WorkerGroup)}

    unclassified = actual - known
    assert unclassified == set(), (
        f"New WorkerGroup field(s) {sorted(unclassified)}: add a sentinel to "
        "WORKER_GROUP_SENTINELS so parity is checked, or route it to a named "
        "test via WORKER_GROUP_STRUCTURAL."
    )
    assert known - actual == set(), "stale entry for a field that no longer exists"


def test_worker_group_structural_fields_name_a_real_test():
    here = globals()
    for field_name, test_name in WORKER_GROUP_STRUCTURAL.items():
        assert test_name in here, f"{field_name} points at missing {test_name}"


def test_worker_group_replica_counts_match_on_both_paths(specs):
    """replicas / min_replicas / max_replicas, read off the spec.

    The group carries its own explicit range, so neither builder may
    substitute the cluster-level autoscaling numbers.
    """
    for spec in specs:
        group = _extra_group(spec)
        assert (group["replicas"], group["minReplicas"], group["maxReplicas"]) == (
            3,
            2,
            8,
        )


def test_worker_group_replica_counts_default_to_replicas_on_both_paths():
    """min/max omitted means all three equal replicas, on both paths."""
    group = WorkerGroup(group_name="defaults-group", replicas=4)
    config = _full_config(additional_worker_groups=[group])

    for spec in (_spec_standalone(config), _spec_embedded(config)):
        built = _extra_group(spec)
        assert (built["replicas"], built["minReplicas"], built["maxReplicas"]) == (
            4,
            4,
            4,
        )


def test_worker_group_gpu_count_matches_on_both_paths(specs):
    """gpu_count reaches rayStartParams and the container resources alike."""
    for spec in specs:
        group = _extra_group(spec)
        assert group["rayStartParams"]["num-gpus"] == "13"

        resources = group["template"]["spec"]["containers"][0]["resources"]
        assert resources["limits"]["sentinel.io/wg-acc"] == 13
        assert resources["requests"]["sentinel.io/wg-acc"] == 13


def test_worker_group_image_overrides_the_cluster_image_on_both_paths(specs):
    """wg.image wins over config.image; omitting it inherits.

    A substring check cannot tell "the group image is used" from "the cluster
    image leaked in", because both are present elsewhere in the spec.
    """
    for spec in specs:
        container = _extra_group(spec)["template"]["spec"]["containers"][0]
        assert container["image"] == "sentinel.io/wg-image:sentinel-wg-tag"


def test_worker_group_without_an_image_inherits_the_cluster_one():
    group = WorkerGroup(group_name="inherit-group", replicas=1)
    config = _full_config(additional_worker_groups=[group])

    for spec in (_spec_standalone(config), _spec_embedded(config)):
        container = _extra_group(spec)["template"]["spec"]["containers"][0]
        assert container["image"] == SENTINELS["image"]


def test_worker_group_envs_merge_over_cluster_envs_on_both_paths(specs):
    """Group envs are added to the cluster's, not substituted for them."""
    for spec in specs:
        container = _extra_group(spec)["template"]["spec"]["containers"][0]
        names = {e["name"]: e["value"] for e in container["env"]}

        assert names["SENTINEL_WG_ENV"] == "sentinel-wg-env-value"
        assert names["SENTINEL_ENV"] == "sentinel-env-value"


def test_worker_group_labels_merge_over_cluster_labels_on_both_paths(specs):
    """Both paths merge config.labels under wg.labels for the extra group."""
    for spec in specs:
        labels = _extra_group(spec)["template"]["metadata"]["labels"]

        assert labels["sentinel.io/wg-label"] == "sentinel-wg-label-value"
        assert labels["sentinel.io/label"] == "sentinel-label-value"


def test_worker_group_tolerations_replace_the_cluster_ones_on_both_paths(specs):
    """wg.tolerations is an override, not a merge — pin that on both sides."""
    for spec in specs:
        tolerations = _extra_group(spec)["template"]["spec"]["tolerations"]

        assert [t["key"] for t in tolerations] == ["sentinel-wg-toleration"]


def test_worker_group_without_tolerations_inherits_the_worker_ones():
    group = WorkerGroup(group_name="inherit-tolerations", replicas=1)
    config = _full_config(additional_worker_groups=[group])

    for spec in (_spec_standalone(config), _spec_embedded(config)):
        tolerations = _extra_group(spec)["template"]["spec"]["tolerations"]
        assert [t["key"] for t in tolerations] == ["sentinel-worker-toleration"]

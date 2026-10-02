# Multi-Worker Group Support

**Jira:** RHOAIENG-72835
**Status:** Design
**Date:** 2026-10-02

## Problem

KubeRay's RayCluster CRD supports multiple `workerGroupSpecs[]`, each with independent resource profiles, images, tolerations, and environment variables. The SDK hardcodes a single worker group everywhere — `ClusterConfiguration` has flat `worker_*` fields, the builder emits one `workerGroupSpecs` entry, and `get_cluster()` reads only `workerGroupSpecs[0]`.

Users who need heterogeneous clusters (e.g. CPU preprocessing workers + GPU training workers) have to drop down to raw YAML.

## Solution

Add an optional `additional_worker_groups` field to `ClusterConfiguration`. The existing flat `worker_*` fields remain the default/primary group. Additional groups are defined as `WorkerGroup` dataclass instances appended to the list.

```python
from codeflare_sdk import ClusterConfiguration, WorkerGroup
from kubernetes.client import V1Toleration

config = ClusterConfiguration(
    name="heterogeneous-cluster",
    namespace="default",
    num_workers=4,
    worker_cpu_requests=2,
    worker_cpu_limits=2,
    worker_memory_requests=8,
    worker_memory_limits=8,
    image="quay.io/rhoai/ray:2.23.0-py311-cu121",
    additional_worker_groups=[
        WorkerGroup(
            group_name="gpu-inference",
            replicas=2,
            cpu_requests=4,
            cpu_limits=4,
            memory_requests="16G",
            memory_limits="16G",
            gpu_type="nvidia.com/gpu",
            gpu_count=4,
            image="quay.io/rhoai/ray:2.23.0-py311-cu124",
            envs={"MODEL_SHARD": "0"},
            tolerations=[
                V1Toleration(
                    key="nvidia.com/gpu",
                    operator="Exists",
                    effect="NoSchedule",
                ),
            ],
        ),
    ],
)
```

## WorkerGroup Dataclass

All fields on `WorkerGroup` directly — no nested spec object.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `group_name` | `str` | required | Unique name within the cluster. Maps to `groupName` in CRD. |
| `replicas` | `int` | `1` | Number of worker pods. |
| `min_replicas` | `int \| None` | `None` | Min replicas for autoscaling. If `None`, equals `replicas`. |
| `max_replicas` | `int \| None` | `None` | Max replicas for autoscaling. If `None`, equals `replicas`. |
| `cpu_requests` | `int \| str` | `1` | CPU requests per worker pod. |
| `cpu_limits` | `int \| str` | `1` | CPU limits per worker pod. |
| `memory_requests` | `int \| str` | `3` | Memory requests. Int treated as GB. |
| `memory_limits` | `int \| str` | `6` | Memory limits. Int treated as GB. |
| `gpu_type` | `str \| None` | `None` | Extended resource key, e.g. `"nvidia.com/gpu"`. |
| `gpu_count` | `int \| None` | `None` | Number of GPUs. Requires `gpu_type`. |
| `image` | `str \| None` | `None` | Container image. `None` inherits cluster-level. |
| `envs` | `dict[str, str]` | `{}` | Per-group env vars. Merged over cluster-level (group wins). |
| `labels` | `dict[str, str]` | `{}` | Pod labels. Merged over cluster-level (group wins). |
| `tolerations` | `list[V1Toleration] \| None` | `None` | Pod tolerations. `None` inherits `worker_tolerations` from cluster config. |

## Inheritance and Merge Strategy

When a `WorkerGroup` omits a field, it inherits from `ClusterConfiguration`:

| Field | Strategy |
|-------|----------|
| `envs` | `{**cluster_config.envs, **group.envs}` — group wins on key conflict |
| `labels` | `{**cluster_config.labels, **group.labels}` — group wins on key conflict |
| `tolerations` | If set on group, use group's. If `None`, inherit `cluster_config.worker_tolerations`. |
| `image` | If set on group, use group's. If `None`, inherit `cluster_config.image`. |

## Validation

- `group_name` is required (omitting raises `TypeError`).
- `group_name` values must be unique across all additional worker groups.
- `gpu_count` without `gpu_type` raises `ValueError`.
- `gpu_type` without `gpu_count` raises `ValueError`.
- `min_replicas` and `max_replicas` must satisfy `min_replicas <= max_replicas` when both are set.
- Memory int values converted to `"{n}G"` strings (same as existing `ClusterConfiguration` behavior).

## CRD Field Mapping

Each `WorkerGroup` produces one entry in `workerGroupSpecs[]`:

```yaml
workerGroupSpecs:
  - groupName: "gpu-inference"
    replicas: 2
    minReplicas: 2
    maxReplicas: 2
    rayStartParams:
      block: "true"
      num-cpus: "4"
      num-gpus: "4"
      resources: "{}"
    template:
      spec:
        tolerations:
          - key: nvidia.com/gpu
            operator: Exists
            effect: NoSchedule
        containers:
          - name: machine-learning
            image: quay.io/rhoai/ray:2.23.0-py311-cu124
            resources:
              requests:
                cpu: 4
                memory: "16G"
                nvidia.com/gpu: 4
              limits:
                cpu: 4
                memory: "16G"
                nvidia.com/gpu: 4
            env:
              - name: RAY_USAGE_STATS_ENABLED
                value: "0"
              - name: MODEL_SHARD
                value: "0"
```

### Fields intentionally excluded from v1

volumes, volumeMounts, initContainers, lifecycle, nodeSelector, topologySpreadConstraints. These can be added in future iterations.

## Files Changed

| File | Change |
|------|--------|
| `ray/cluster/config.py` | Add `WorkerGroup` dataclass. Add `additional_worker_groups` field to `ClusterConfiguration`. Validation. |
| `ray/cluster/build_ray_cluster.py` | Iterate `additional_worker_groups` to append entries to `workerGroupSpecs[]`. Handle inheritance/merge. |
| `ray/rayjobs/config.py` | Same iteration in `build_ray_cluster_spec()`. |
| `ray/cluster/cluster.py` | `get_cluster()` reconstructs `additional_worker_groups` from multi-group CRs. `_head_worker_extended_resources_from_rc_dict` handles all groups. |
| `ray/cluster/status.py` | `RayCluster` dataclass supports multiple worker group display. |
| `__init__.py` | Export `WorkerGroup`. |
| `docs/api/public-surface.json` | Register `WorkerGroup`. |
| Unit tests | Config validation, builder output with multiple groups, get_cluster roundtrip, env/label merge, image inheritance. |

## Backward Compatibility

Zero breaking changes. `additional_worker_groups` defaults to an empty list. Existing code that uses flat `worker_*` fields continues to produce a single-group cluster.

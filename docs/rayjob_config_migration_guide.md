# RayJob Config Migration: ManagedClusterConfig → ClusterConfiguration

## Overview

As part of the RHAIENG-2063 consolidation, `ManagedClusterConfig` has been
removed. RayJobs now use `ClusterConfiguration` (the same dataclass used for
standalone Ray clusters) for their embedded cluster spec.

This guide covers the **behavioral deltas** in the generated RayJob CR that
upgraders should be aware of, even when call sites only rename the config type.

## Quick Migration

### Before

```python
from codeflare_sdk import RayJob, ManagedClusterConfig

job = RayJob(
    job_name="train",
    entrypoint="python train.py",
    namespace="my-ns",
    cluster_config=ManagedClusterConfig(
        num_workers=2,
        head_accelerators={"nvidia.com/gpu": 1},
        worker_accelerators={"nvidia.com/gpu": 1},
    ),
)
```

### After

```python
from codeflare_sdk import RayJob, ClusterConfiguration

job = RayJob(
    job_name="train",
    entrypoint="python train.py",
    namespace="my-ns",
    cluster_config=ClusterConfiguration(
        num_workers=2,
        head_extended_resource_requests={"nvidia.com/gpu": 1},
        worker_extended_resource_requests={"nvidia.com/gpu": 1},
    ),
)
```

## Field Renames

| ManagedClusterConfig | ClusterConfiguration |
|---|---|
| `head_accelerators` | `head_extended_resource_requests` |
| `worker_accelerators` | `worker_extended_resource_requests` |
| `accelerator_configs` | `extended_resource_mapping` |

All other field names (`num_workers`, `head_cpu_requests`, `image`, `envs`,
`volumes`, `volume_mounts`, `labels`, `annotations`, `tolerations`, etc.) are
unchanged.

## Behavioral Deltas in Generated RayJob CRs

Even with identical field values, the generated RayJob CR will differ from what
`ManagedClusterConfig` produced. Review these changes before upgrading
production workloads.

### 1. Default Resource Values Changed

| Field | ManagedClusterConfig | ClusterConfiguration |
|---|---|---|
| `head_cpu_requests` | `2` | `1` |
| `head_cpu_limits` | `2` | `2` |
| `head_memory_requests` | `8G` | `5G` |
| `head_memory_limits` | `8G` | `8G` |
| `worker_memory_requests` | `2G` | `3G` |
| `worker_memory_limits` | `2G` | `6G` |

**Impact**: Jobs relying on defaults will request different resources. If you
were using defaults, explicitly set the values you need.

### 2. enableInTreeAutoscaling Now Tracks Configuration

| | ManagedClusterConfig | ClusterConfiguration |
|---|---|---|
| `enableInTreeAutoscaling` | Always `False` | Follows `config.enable_autoscaling` (default `False`) |

**Impact**: Functionally identical when using defaults (`False`). However,
`ClusterConfiguration` now supports setting `enable_autoscaling=True` with
`min_workers`/`max_workers` for RayJobs — this was previously blocked.

### 3. autoscalerOptions Always Present

The old config omitted the `autoscalerOptions` block entirely. The new config
always includes it:

```yaml
autoscalerOptions:
  upscalingMode: Default
  idleTimeoutSeconds: 60
  resources:
    requests: {cpu: 500m, memory: 512Mi}
    limits: {cpu: 500m, memory: 512Mi}
```

**Impact**: No functional change when `enableInTreeAutoscaling` is `False` —
KubeRay ignores autoscaler options in that case. The block is present for
consistency with standalone RayCluster specs.

### 4. imagePullPolicy Changed from IfNotPresent to Always

| | ManagedClusterConfig | ClusterConfiguration |
|---|---|---|
| `imagePullPolicy` | `IfNotPresent` | `Always` |

**Impact**: Pods will re-pull images on every restart. This adds startup
latency when using mutable tags (e.g., `latest`) but ensures the latest image
is always used. For large images or air-gapped environments, consider pinning
to a digest.

### 5. ODH CA Certificate Volumes Merged by Default

The new config automatically includes ODH trusted CA certificate volumes and
mounts:

- `odh-trusted-ca-cert` → `/etc/pki/tls/certs/odh-trusted-ca-bundle.crt`
  and `/etc/ssl/certs/odh-trusted-ca-bundle.crt`
- `odh-ca-cert` → `/etc/pki/tls/certs/odh-ca-bundle.crt`
  and `/etc/ssl/certs/odh-ca-bundle.crt`

These reference optional ConfigMaps, so they are safe on non-ODH clusters
(the mounts simply won't contain data).

**Impact**: RayJob pods will have additional volume mounts. User-provided
volumes and mounts are preserved and merged with the ODH defaults.

### 6. Cluster Name Derivation

Both old and new configs derive the cluster name from the RayJob name. No
change in behavior.

## Checklist for Upgraders

1. **Rename the import**: `ManagedClusterConfig` → `ClusterConfiguration`
2. **Rename fields**: `head_accelerators` → `head_extended_resource_requests`,
   `worker_accelerators` → `worker_extended_resource_requests`,
   `accelerator_configs` → `extended_resource_mapping`
3. **Review resource defaults**: If you relied on defaults, explicitly set
   `head_cpu_requests`, `head_memory_requests`, `worker_memory_requests`,
   and `worker_memory_limits` to the old values if needed
4. **Test image pull behavior**: Verify the `Always` pull policy works in
   your environment
5. **Verify autoscaling intent**: If you set `enable_autoscaling=True`, ensure
   `min_workers` and `max_workers` are configured

---

**Last Updated:** September 2026
**Applies to:** CodeFlare SDK (single-entrypoint branch)

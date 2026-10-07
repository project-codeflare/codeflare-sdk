# RayCluster spec parity audit

`ClusterConfiguration` feeds two spec builders:

| Path | Builder | Produces |
| --- | --- | --- |
| Standalone `Cluster` | `ray/cluster/build_ray_cluster.py` | a whole `RayCluster` resource |
| `RayJob(cluster_config=...)` | `ray/rayjobs/config.py` | the `rayClusterSpec` embedded in a RayJob |

They were written separately and drifted. A field wired into one and forgotten
in the other raises nothing — the cluster simply comes up without it. This page
records where every field lands and why.

The shared, side-effect-free pieces now live in
`ray/cluster/raycluster_spec.py`, and
`src/codeflare_sdk/ray/test_builder_parity.py` enforces the table below: it
sets each field to a sentinel, renders both specs, and fails if a sentinel
reaches only one. A new field that is neither given a sentinel nor classified
here fails `test_every_field_is_classified`.

Tracked under RHOAIENG-98942.

## SUPPORTED — reaches both builders (29)

Head: `head_cpu_requests`, `head_cpu_limits`, `head_memory_requests`,
`head_memory_limits`, `head_extended_resource_requests`, `head_tolerations`.

Workers: `num_workers`, `worker_cpu_requests`, `worker_cpu_limits`,
`worker_memory_requests`, `worker_memory_limits`,
`worker_extended_resource_requests`, `worker_tolerations`,
`additional_worker_groups`.

Autoscaling: `enable_autoscaling`, `min_workers`, `max_workers`.

Pod spec: `image`, `image_pull_secrets`, `envs`, `labels`, `annotations`,
`volumes`, `volume_mounts`, `extended_resource_mapping`.

GCS fault tolerance: `enable_gcs_ft`, `redis_address`,
`redis_password_secret`, `external_storage_namespace`.

### Known asymmetry within SUPPORTED

`labels` lands in different places by necessity. The standalone path writes
them onto the `RayCluster` metadata *and* the RayJob path writes them onto the
head and worker pod templates — the embedded `rayClusterSpec` has no metadata
block to carry them. Pod templates are also where this path already put them
for `additional_worker_groups`.

## CONTEXT_ONLY — consumed before a builder sees them (3)

| Field | Where it is consumed |
| --- | --- |
| `overwrite_default_resource_mapping` | `__post_init__`, when merging `extended_resource_mapping` |
| `enable_usage_stats` | `__post_init__`, which writes `RAY_USAGE_STATS_ENABLED` into `envs` |
| `verify_tls` | client-side only; governs dashboard calls, not the CR |

Their absence from both builders is correct.

## NOT_APPLICABLE — meaningful standalone, meaningless inside a RayJob (3)

| Field | Why |
| --- | --- |
| `name` | RayJob derives the cluster name as `<job_name>-cluster` |
| `namespace` | the embedded `rayClusterSpec` has no metadata block |
| `write_to_file` | only the standalone path writes a YAML file |

## CONFLICTED — set on both sides with undefined precedence (1)

| Field | Conflict |
| --- | --- |
| `local_queue` | `RayJob` takes its own `local_queue` argument and ignores the config's. Tracked in RHOAIENG-98949. |

## Purity, and why the builders are not a single function

`build_ray_cluster()` reaches the Kubernetes API three times while rendering:

- `local_queue_exists()` — lists LocalQueues
- `get_default_local_queue()` — lists LocalQueues
- `validate_autoscaling_with_kueue()` → `get_default_kueue_name()` — lists LocalQueues

`build_ray_cluster_spec()` makes no calls at all. Folding them into one
function would give the RayJob path network calls it does not make today, so
`raycluster_spec.py` holds only pure rendering and each caller keeps its own
cluster lookups. Anything moved there in future must stay free of I/O.

Related: RHOAIENG-98944 covers the Kueue/autoscaling validation the RayJob path
does not yet perform.

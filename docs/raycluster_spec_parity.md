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

## SUPPORTED — reaches both builders (24)

Head: `head_cpu_requests`, `head_cpu_limits`, `head_memory_requests`,
`head_memory_limits`, `head_extended_resource_requests`, `head_tolerations`.

Workers: `num_workers`, `worker_cpu_requests`, `worker_cpu_limits`,
`worker_memory_requests`, `worker_memory_limits`,
`worker_extended_resource_requests`, `worker_tolerations`,
`additional_worker_groups`.

Autoscaling: `enable_autoscaling`, `min_workers`, `max_workers`.

Pod spec: `image`, `image_pull_secrets`, `envs`, `annotations`,
`volumes`, `volume_mounts`, `extended_resource_mapping`.

## PARTIAL — reaches both builders, but lands differently (1)

`labels` is not fully unified:

| Path | CR metadata | head pod | default worker pod | extra worker pods |
| --- | --- | --- | --- | --- |
| Standalone | yes | **no** | **no** | yes |
| RayJob | n/a — no metadata block | yes | yes | yes |

A presence check passes on both, so it cannot express the difference. #1184
put `config.labels` on every RayJob pod template; the standalone builder is
now the one that leaves them off the head and default worker pods, which is
what a NetworkPolicy selector or a cost-allocation label actually needs.

Closing the standalone gap adds labels to pods that do not carry them today —
a behaviour change, so it belongs to RHOAIENG-99560 rather than to this
consolidation. Pinned in full by `test_labels_land_where_each_path_puts_them`,
so either side moving is a conscious edit.

## PENDING DECISION — standalone only, deliberately (4)

`enable_gcs_ft`, `redis_address`, `redis_password_secret` and
`external_storage_namespace` reach the standalone builder and **not** the
RayJob one. This is not drift.

Commit `52a351a` ("RHOAIENG-30720: Remove GCS FT for Lifecycled RayClusters")
removed them from the lifecycled path because the feature did not work — head
pod restarts lost state — and RHOAIENG-30720 scoped its fix to standalone
RayCluster, stating the RayJob implementation was out of scope. #1091 then made
`ClusterConfiguration` the shared config object, so the four fields are now
accepted and validated on the RayJob path and silently ignored.

That middle state is the actual bug. Resolving it means either rejecting the
fields there or emitting them after validating GCS FT on a lifecycled cluster.
**RHOAIENG-98943** owns the decision; until then the asymmetry is pinned by
`test_gcs_fault_tolerance_is_standalone_only`, which fails if either side
changes.

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

## What is shared, and what is still duplicated

Shared in `raycluster_spec.py`, called by both paths: the ODH CA volumes and
mounts, CPU/memory/extended resource requirements, GPU counting, the
`rayStartParams` resources string, the head and worker containers, and replica
counts. `gcs_fault_tolerance_options()` also lives there but is called by the
standalone path only — see PENDING DECISION above.

Still assembled independently by each builder, and the subject of the
follow-up to this work:

- the `headGroupSpec` / `workerGroupSpecs` dicts and their `rayStartParams`
- `_build_worker_group_spec` and `_build_additional_worker_group_spec`, two
  copies of additional worker group assembly
- the standalone path's CR wrapper (`apiVersion`, `kind`, `metadata`),
  which has no RayJob equivalent

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

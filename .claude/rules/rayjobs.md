---
paths:
  - src/codeflare_sdk/ray/rayjobs/**
---

# ray/rayjobs (job layer)

Manages RayJob custom resources: submission, status tracking, runtime environment, and managed clusters.
Jobs that create their own RayCluster take a `ClusterConfiguration` (the same dataclass the standalone
cluster layer uses); `config.py` turns it into the embedded `rayClusterSpec`.

## Key Abstractions

- **`RayJob`** (`rayjob.py`): primary job lifecycle API
- **`build_ray_cluster_spec`** (`config.py`): builds the embedded RayCluster spec
  from a `ClusterConfiguration`. The pieces it shares with the standalone builder
  live in `ray/cluster/raycluster_spec.py` — add a new field to that module, not
  to one builder, or `ray/test_builder_parity.py` fails (RHOAIENG-98942)
- **`_build_additional_worker_group_spec`** (`config.py`): the RayJob copy of
  additional-worker-group assembly. `build_ray_cluster._build_worker_group_spec`
  is the standalone copy; the two are *not* shared yet (RHOAIENG-99560), so a
  change to one needs the same change to the other. A new `WorkerGroup` field
  also needs a sentinel in `WORKER_GROUP_SENTINELS` in `ray/test_builder_parity.py`,
  or `test_every_worker_group_field_is_classified` fails
- **`runtime_env.py`**: Ray runtime environment dict construction
- **`status.py`**: `RayJobDeploymentStatus`, `CodeflareRayJobStatus`, `RayJobInfo`
- **`test/`**: subdirectory tests with shared `conftest.py` and `auto_mock_setup` fixture

## Dependencies

- Auth: `common.kubernetes_cluster.auth`
- Kueue: `common.kueue.kueue`
- Utils: `common.utils` (constants, image selection, validation, namespace)
- Vendored: `vendored.python_client` (`RayjobApi`, `RayClusterApi`) — only layer allowed to import vendored code
  (CI-enforced via import-linter)

## Import Boundaries

- May import from `common.*` and `codeflare_sdk.vendored` (sole vendored consumer)
- Must NOT import from `ray.client`
- May import from `ray.cluster` for the shared config and spec builder only —
  `cluster.config` (`ClusterConfiguration`, `WorkerGroup`) and
  `cluster.raycluster_spec`. #1091 made `ClusterConfiguration` the single config
  object and RHOAIENG-98942 made the spec pieces shared, so this edge is
  intentional. Nothing else from `ray.cluster` (notably `cluster.cluster`) may be
  imported. Not CI-enforced — `.importlinter` has no contract for it.
- New public symbols must be exported in `ray/rayjobs/__init__.py` and, if user-facing,
  re-exported in `src/codeflare_sdk/__init__.py`

## Commands

- Unit tests: `pytest src/codeflare_sdk/ray/rayjobs/`
- See `ray/rayjobs/test/conftest.py` for the `auto_mock_setup` fixture pattern

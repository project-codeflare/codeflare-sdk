---
paths:
  - src/codeflare_sdk/ray/rayjobs/**
---

# ray/rayjobs (job layer)

Manages RayJob custom resources: submission, status tracking, runtime environment, and managed clusters.
`ManagedClusterConfig` embeds cluster config for jobs that create their own RayCluster.

## Key Abstractions

- **`RayJob`** (`rayjob.py`): primary job lifecycle API
- **`ManagedClusterConfig`** (`config.py`): cluster spec for jobs with embedded RayCluster
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
- Must NOT import from `ray.cluster` or `ray.client`
- New public symbols must be exported in `ray/rayjobs/__init__.py` and, if user-facing,
  re-exported in `src/codeflare_sdk/__init__.py`

## Commands

- Unit tests: `pytest src/codeflare_sdk/ray/rayjobs/`
- See `ray/rayjobs/test/conftest.py` for the `auto_mock_setup` fixture pattern

---
paths:
  - src/codeflare_sdk/ray/cluster/**
---

# ray/cluster (cluster layer)

Manages RayCluster custom resources: configuration, creation, status polling, and teardown.
`ClusterConfiguration` is the primary user-facing config object; `Cluster` drives the K8s lifecycle.

## Key Abstractions

- **`Cluster`** (`cluster.py`): lifecycle API — create, delete, status, job submission helpers
- **`ClusterConfiguration`** (`config.py`): typed dataclass for cluster spec — no `common/` imports
- **`build_ray_cluster.py`**: constructs K8s manifests from `ClusterConfiguration`
- **`status.py`**: `RayClusterStatus`, `CodeFlareClusterStatus`, `RayCluster` typed status objects
- **`pretty_print.py`**: CLI/table output (internal, not exported at package root)

## Dependencies

- Auth: `common.kubernetes_cluster.auth` (`config_check`, `get_api_client`)
- Error handling: `common._kube_api_error_handling`
- Namespace: `common.utils.get_current_namespace` (package-level import)
- Kueue: `common.kueue` (lazy import in `build_ray_cluster.py`)
- Widgets: `common.widgets.widgets` (Jupyter notebook UI only — creates circular dep with widgets layer)

## Import Boundaries

- May import from `common.kubernetes_cluster`, `common.kueue`, `common.utils`
- Must NOT import from `codeflare_sdk.vendored` — use SDK wrappers in `ray/rayjobs/` instead
  (CI-enforced via import-linter)
- Must NOT import from `ray.rayjobs` or `ray.client`
- Prefer `from ...common.utils import ...` over deep imports from `common.utils.constants`,
  `.utils`, `.validation` (prose-only until utils facade is expanded)

## Commands

- Unit tests: `pytest src/codeflare_sdk/ray/cluster/`
- Colocated tests: `test_*.py` next to source; use helpers from `common/utils/unit_test_support.py`

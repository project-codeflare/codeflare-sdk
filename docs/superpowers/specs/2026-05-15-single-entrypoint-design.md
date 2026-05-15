# Single Entrypoint Design: `Codeflare` Class

**Date**: 2026-05-15
**Status**: Draft
**Author**: Saad Zaher

## Overview

Introduce a single `Codeflare` class as the primary entrypoint for the SDK. It owns authentication (exclusively via kube-authkit), SDK-level configuration, and provides namespace-accessor handlers for clusters and jobs.

## Goals

1. Single entrypoint: `cf = Codeflare(config=SDKConfig(...))`
2. Handler pattern: `cf.clusters.*` and `cf.jobs.*`
3. Authentication via kube-authkit only — remove all legacy auth classes
4. Coexist with existing `Cluster`/`RayJob` classes (they become return types from handlers)
5. Default namespace, retries, timeout, and logging configured once at SDK level

## Non-Goals

- Dependency injection into `Cluster`/`RayJob` internals (future improvement)
- Multi-client support (multiple `Codeflare` instances with different credentials)
- Breaking changes to `Cluster`, `ClusterConfiguration`, `RayJob`, or `ManagedClusterConfig`

## Architecture

```
Codeflare(config=SDKConfig)
├── .config: SDKConfig
│   ├── auth: kube_authkit.AuthConfig
│   ├── retries: int
│   ├── timeout: int
│   ├── namespace: Optional[str]
│   └── log_level: str
├── .clusters: ClusterHandler
│   ├── .create(name, ...) -> Cluster
│   ├── .get(name, ...) -> Cluster
│   ├── .list(...) -> List[RayCluster]
│   └── .list_queued(...) -> List[RayCluster]
└── .jobs: JobHandler
    ├── .submit(name, entrypoint, ...) -> RayJob
    └── .create(name, entrypoint, ...) -> RayJob
```

### Internal Wiring

The `Codeflare.__init__()` method:

1. Creates a K8s `ApiClient` via `kube_authkit.get_k8s_client(config=auth_config)`
2. Sets the module-level global via the existing `set_api_client()` function
3. Instantiates `ClusterHandler` and `JobHandler`, passing a reference to `self`

Existing code paths (`Cluster`, `RayJob`, Kueue, etc.) call `get_api_client()` internally, which returns the global client. This means the new entrypoint "just works" without modifying internals.

## Components

### `SDKConfig` Dataclass

```python
@dataclass
class SDKConfig:
    auth: AuthConfig = field(default_factory=lambda: AuthConfig(method="auto"))
    retries: int = 3
    timeout: int = 300
    namespace: Optional[str] = None
    log_level: str = "WARNING"
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `auth` | `AuthConfig` | `AuthConfig(method="auto")` | kube-authkit authentication config |
| `retries` | `int` | `3` | Number of retries for K8s API calls |
| `timeout` | `int` | `300` | Default timeout in seconds for blocking operations |
| `namespace` | `Optional[str]` | `None` | Default namespace; auto-detected if not set |
| `log_level` | `str` | `"WARNING"` | Logging level for `codeflare_sdk` logger |

### `Codeflare` Class

```python
class Codeflare:
    def __init__(self, config: Optional[SDKConfig] = None):
        self.config = config or SDKConfig()
        logging.getLogger("codeflare_sdk").setLevel(self.config.log_level)
        self._client = get_k8s_client(config=self.config.auth)
        set_api_client(self._client)
        self.clusters = ClusterHandler(self)
        self.jobs = JobHandler(self)
```

No-arg construction `Codeflare()` works via auto-detection (kubeconfig or in-cluster).

### `ClusterHandler`

```python
class ClusterHandler:
    def __init__(self, sdk: "Codeflare"):
        self._sdk = sdk

    def create(self, name: str, namespace: Optional[str] = None, **kwargs) -> Cluster:
        """Create and return a new Cluster (does not apply it yet)."""
        ns = namespace or self._sdk.config.namespace
        cluster_config = ClusterConfiguration(name=name, namespace=ns, **kwargs)
        return Cluster(cluster_config)

    def get(self, name: str, namespace: Optional[str] = None, **kwargs) -> Cluster:
        """Retrieve an existing cluster by name."""
        ns = namespace or self._sdk.config.namespace or "default"
        return get_cluster(cluster_name=name, namespace=ns, **kwargs)

    def list(self, namespace: Optional[str] = None) -> list:
        """List all Ray clusters in a namespace."""
        ns = namespace or self._sdk.config.namespace or "default"
        return list_all_clusters(ns, print_to_console=False)

    def list_queued(self, namespace: Optional[str] = None) -> list:
        """List all queued Ray clusters in a namespace."""
        ns = namespace or self._sdk.config.namespace or "default"
        return list_all_queued(ns, print_to_console=False)
```

### `JobHandler`

```python
class JobHandler:
    def __init__(self, sdk: "Codeflare"):
        self._sdk = sdk

    def submit(self, name: str, entrypoint: str, namespace: Optional[str] = None,
               **kwargs) -> RayJob:
        """Create and immediately submit a RayJob."""
        ns = namespace or self._sdk.config.namespace
        job = RayJob(job_name=name, entrypoint=entrypoint, namespace=ns, **kwargs)
        job.submit()
        return job

    def create(self, name: str, entrypoint: str, namespace: Optional[str] = None,
               **kwargs) -> RayJob:
        """Create a RayJob without submitting it (for inspection/modification)."""
        ns = namespace or self._sdk.config.namespace
        return RayJob(job_name=name, entrypoint=entrypoint, namespace=ns, **kwargs)
```

## Legacy Auth Removal

The following classes and functions are **removed** (not deprecated — removed):

| Removed | Replacement |
|---------|-------------|
| `TokenAuthentication` | `SDKConfig(auth=AuthConfig(token="..."))` |
| `KubeConfigFileAuthentication` | `SDKConfig(auth=AuthConfig(method="kubeconfig"))` |
| `Authentication` (abstract base) | No replacement needed |
| `KubeConfiguration` (abstract base) | No replacement needed |
| `set_api_client()` (public export) | `Codeflare(config=SDKConfig(auth=...))` |

The `set_api_client()` function remains in `auth.py` as an internal function (used by `Codeflare.__init__`), but is no longer exported from `__init__.py`.

The `config_check()` and `get_api_client()` functions remain unchanged — they are internal utilities used by `Cluster`, `RayJob`, and other code paths.

## File Layout

### New Files

| File | Contents |
|------|----------|
| `src/codeflare_sdk/codeflare.py` | `Codeflare`, `SDKConfig`, `ClusterHandler`, `JobHandler` |

### Modified Files

| File | Changes |
|------|---------|
| `src/codeflare_sdk/__init__.py` | Export `Codeflare`, `SDKConfig`. Remove `Authentication`, `KubeConfiguration`, `TokenAuthentication`, `KubeConfigFileAuthentication`, `set_api_client` exports. |
| `src/codeflare_sdk/common/kubernetes_cluster/auth.py` | Remove `TokenAuthentication`, `KubeConfigFileAuthentication`, `Authentication`, `KubeConfiguration` classes. Keep `config_check()`, `get_api_client()`, `set_api_client()` as internal functions. |
| `src/codeflare_sdk/common/__init__.py` | Remove legacy auth class exports. |

## Usage Examples

### Minimal (auto-detect auth)

```python
from codeflare_sdk import Codeflare

cf = Codeflare()
clusters = cf.clusters.list(namespace="my-ns")
```

### Token auth with config

```python
from codeflare_sdk import Codeflare, SDKConfig
from kube_authkit import AuthConfig

cf = Codeflare(config=SDKConfig(
    auth=AuthConfig(
        k8s_api_host="https://api.my-cluster.com:6443",
        token="sha256~abc123..."
    ),
    namespace="my-project",
    retries=5,
    timeout=600,
    log_level="DEBUG"
))

# Create and apply a cluster
cluster = cf.clusters.create(
    name="train-cluster",
    num_workers=4,
    worker_extended_resource_requests={"nvidia.com/gpu": 1}
)
cluster.apply()
cluster.wait_ready()

# Submit a job to the cluster
job = cf.jobs.submit(
    name="training-job",
    entrypoint="python train.py",
    cluster_name="train-cluster"
)
job.status()
```

### In a notebook

```python
from codeflare_sdk import Codeflare, SDKConfig
from kube_authkit import AuthConfig

cf = Codeflare(config=SDKConfig(
    auth=AuthConfig(method="auto"),
    namespace="data-science"
))

# List what's running
cf.clusters.list()

# Get an existing cluster
cluster = cf.clusters.get("my-existing-cluster")
cluster.details()
```

## Testing Strategy

- Unit tests for `SDKConfig` validation (bad log_level, negative retries, etc.)
- Unit tests for `Codeflare.__init__` with mocked kube-authkit
- Unit tests for `ClusterHandler` methods (mock `Cluster`, `get_cluster`, etc.)
- Unit tests for `JobHandler` methods (mock `RayJob`)
- Integration test: verify `Codeflare()` sets the global `api_client` correctly
- Test that removed classes are no longer importable from `codeflare_sdk`

## Error Handling

- `Codeflare.__init__` raises on auth failure (kube-authkit exceptions propagate)
- `SDKConfig.__post_init__` validates `retries >= 0`, `timeout > 0`, and `log_level` is valid
- Handler methods propagate existing exceptions from `Cluster`/`RayJob` unchanged

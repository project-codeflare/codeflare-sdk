# Authentication Migration Guide

## Overview

CodeFlare SDK now uses [kube-authkit](https://github.com/opendatahub-io/kube-authkit)
exclusively for Kubernetes authentication, exposed through the `Codeflare`
single entrypoint. The legacy authentication classes and several top-level
convenience re-exports have been removed.

## Removed Exports

The following imports from `codeflare_sdk` will raise `ImportError`:

| Removed Import | Replacement |
|---|---|
| `from codeflare_sdk import TokenAuthentication` | Use `Codeflare(config=SDKConfig(auth=AuthConfig(...)))` |
| `from codeflare_sdk import KubeConfigFileAuthentication` | Use `AuthConfig(method="kubeconfig")` |
| `from codeflare_sdk import Authentication` | Removed (base class) |
| `from codeflare_sdk import KubeConfiguration` | Removed (base class) |
| `from codeflare_sdk import set_api_client` | Handled internally by `Codeflare.__init__()` |
| `from codeflare_sdk import AuthConfig` | `from kube_authkit import AuthConfig` |
| `from codeflare_sdk import get_k8s_client` | `from kube_authkit import get_k8s_client` |
| `from codeflare_sdk import ManagedClusterConfig` | `from codeflare_sdk import ClusterConfiguration` (see [RayJob config migration](rayjob_config_migration_guide.md)) |

## Canonical Import Pattern

```python
from codeflare_sdk import Codeflare, SDKConfig
from kube_authkit import AuthConfig
```

`Codeflare` handles authentication, client setup, and namespace scoping in
one step. `AuthConfig` comes from `kube_authkit` directly — it is no longer
re-exported by `codeflare_sdk`.

## Quick Migration

### Before

```python
from codeflare_sdk import (
    TokenAuthentication,
    Cluster,
    ClusterConfiguration,
)

auth = TokenAuthentication(
    token="sha256~xxxxx",
    server="https://api.cluster.example.com:6443",
    skip_tls=False,
)
auth.login()

cluster = Cluster(ClusterConfiguration(
    name="my-cluster",
    num_workers=2,
))
cluster.apply()
cluster.wait_ready()

cluster.down()
auth.logout()
```

### After (Recommended — Codeflare Entrypoint)

```python
from codeflare_sdk import Codeflare, SDKConfig
from kube_authkit import AuthConfig

cf = Codeflare(config=SDKConfig(
    auth=AuthConfig(
        method="openshift",
        k8s_api_host="https://api.cluster.example.com:6443",
        token="sha256~xxxxx",
    ),
    namespace="my-project",
))

cluster = cf.clusters.create(name="my-cluster", num_workers=2)
cluster.apply()
cluster.wait_ready()

cluster.down()
# No logout needed
```

### After (Direct API — Without Codeflare Entrypoint)

If you need the `Cluster` class directly (e.g., existing code that only
needs auth updated), use `kube_authkit` to create the client and the SDK's
internal `set_api_client` to register it:

```python
from kube_authkit import AuthConfig, get_k8s_client
from codeflare_sdk import Cluster, ClusterConfiguration
from codeflare_sdk.common.kubernetes_cluster.auth import set_api_client

auth_config = AuthConfig(
    method="openshift",
    k8s_api_host="https://api.cluster.example.com:6443",
    token="sha256~xxxxx",
)
api_client = get_k8s_client(config=auth_config)
set_api_client(api_client)

cluster = Cluster(ClusterConfiguration(name="my-cluster", num_workers=2))
cluster.apply()
```

Note: `set_api_client` is no longer a top-level export. Import it from
`codeflare_sdk.common.kubernetes_cluster.auth` if needed. Prefer the
`Codeflare` entrypoint for new code.

## Authentication Methods

### Auto-Detection (Default)

```python
cf = Codeflare(config=SDKConfig(
    auth=AuthConfig(method="auto"),  # default — tries kubeconfig, then in-cluster
    namespace="my-project",
))
```

### OpenShift Token

```python
cf = Codeflare(config=SDKConfig(
    auth=AuthConfig(
        method="openshift",
        k8s_api_host="https://api.cluster.example.com:6443",
        token="sha256~xxxxx",  # oc whoami -t
    ),
    namespace="my-project",
))
```

### OIDC (Device Flow)

```python
cf = Codeflare(config=SDKConfig(
    auth=AuthConfig(
        method="oidc",
        k8s_api_host="https://api.cluster.example.com:6443",
        oidc_issuer="https://keycloak.example.com/auth/realms/myrealm",
        client_id="codeflare-sdk",
        use_device_flow=True,
    ),
    namespace="my-project",
))
```

### Kubeconfig File

```python
cf = Codeflare(config=SDKConfig(
    auth=AuthConfig(method="kubeconfig"),  # uses ~/.kube/config
    namespace="my-project",
))
```

### In-Cluster Service Account

```python
# Inside a Kubernetes pod with a service account
cf = Codeflare(config=SDKConfig(
    auth=AuthConfig(method="auto"),  # auto-detects in-cluster
    namespace="my-project",
))
```

## SDKConfig Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `auth` | `AuthConfig` | `AuthConfig(method="auto")` | kube-authkit authentication configuration |
| `namespace` | `str` or `None` | `None` | Default namespace. Falls back to `"default"` if not set |
| `log_level` | `str` | `"WARNING"` | Logging level: `CRITICAL`, `DEBUG`, `ERROR`, `INFO`, `WARNING` |

## AuthConfig Parameters (kube-authkit)

| Parameter | Type | Description |
|---|---|---|
| `method` | `str` | `"auto"`, `"kubeconfig"`, `"incluster"`, `"oidc"`, `"openshift"` |
| `k8s_api_host` | `str` | Kubernetes API server URL (optional, auto-detected) |
| `token` | `str` | Bearer token (for `"openshift"` method) |
| `oidc_issuer` | `str` | OIDC issuer URL (for `"oidc"` method) |
| `client_id` | `str` | OIDC client ID (for `"oidc"` method) |
| `client_secret` | `str` | OIDC client secret (optional) |
| `use_device_flow` | `bool` | Use OIDC device code flow (default: `False`) |
| `use_keyring` | `bool` | Store tokens in system keyring (default: `False`) |
| `ca_cert` | `str` | Path to custom CA certificate |
| `verify_ssl` | `bool` | SSL certificate verification (default: `True`) |

## Common Migration Issues

### ImportError for Removed Classes

**Problem:**
```
ImportError: cannot import name 'TokenAuthentication' from 'codeflare_sdk'
```

**Solution:** Replace with the `Codeflare` entrypoint pattern shown above.
See the [Removed Exports](#removed-exports) table for the full list.

### `set_api_client` Not Found at Top Level

**Problem:**
```
ImportError: cannot import name 'set_api_client' from 'codeflare_sdk'
```

**Solution:** Use the `Codeflare` class, which calls `set_api_client`
internally. If you need it directly, import from
`codeflare_sdk.common.kubernetes_cluster.auth`.

### `AuthConfig` Not Found at Top Level

**Problem:**
```
ImportError: cannot import name 'AuthConfig' from 'codeflare_sdk'
```

**Solution:** Import directly from kube-authkit:
```python
from kube_authkit import AuthConfig
```

### TLS Verification

**Problem:**
```python
# Old pattern used skip_tls=True
auth = TokenAuthentication(token="...", server="...", skip_tls=True)
```

**Solution:**
```python
# New pattern uses verify_ssl=False (inverted logic)
auth_config = AuthConfig(method="openshift", k8s_api_host="...", token="...", verify_ssl=False)
```

### No login()/logout() Calls

kube-authkit handles authentication when `Codeflare.__init__()` calls
`get_k8s_client()`. There is no `login()`/`logout()` lifecycle to manage.

## Testing Your Migration

```python
from codeflare_sdk import Codeflare, SDKConfig
from kube_authkit import AuthConfig

cf = Codeflare(config=SDKConfig(
    auth=AuthConfig(
        method="openshift",
        k8s_api_host="https://api.cluster.example.com:6443",
        token="sha256~xxxxx",
    ),
    namespace="my-project",
))

# If this succeeds, authentication is working
clusters = cf.clusters.list()
print(f"Found {len(clusters)} clusters")
```

## Getting Help

- **kube-authkit Documentation**: https://github.com/opendatahub-io/kube-authkit
- **CodeFlare SDK Issues**: https://github.com/project-codeflare/codeflare-sdk/issues
- **RayJob Config Migration**: [rayjob_config_migration_guide.md](rayjob_config_migration_guide.md)

---

**Last Updated:** September 2026
**Applies to:** CodeFlare SDK (single-entrypoint branch)

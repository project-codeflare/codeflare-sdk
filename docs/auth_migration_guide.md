# Authentication Migration Guide

## Overview

CodeFlare SDK has migrated to using [kube-authkit](https://github.com/opendatahub-io/kube-authkit) for Kubernetes authentication. This provides support for additional authentication methods including OAuth2, OIDC, OpenShift OAuth, and more.

The legacy `TokenAuthentication` and `KubeConfigFileAuthentication` classes are now deprecated but remain fully functional for backward compatibility.

## Why the Change?

- **More Authentication Methods**: Support for OIDC, OAuth2, OpenShift OAuth, Service Account, and more
- **Better Maintained**: kube-authkit is actively maintained and follows Kubernetes authentication best practices
- **Automatic Detection**: Auto-detects available authentication methods (kubeconfig, in-cluster, etc.)
- **Security First**: Built with security best practices and automatic token refresh

## Migration Timeline

- **v0.34.0 (Current)**: kube-authkit added, deprecation warnings shown
- **v0.35.0**: All examples and documentation updated to new pattern
- **v1.0.0**: Legacy classes (`TokenAuthentication`, `KubeConfigFileAuthentication`) will be removed

## Quick Migration

### Before (Deprecated)

```python
from codeflare_sdk import TokenAuthentication

auth = TokenAuthentication(
    token="my-token",
    server="https://api.example.com:6443",
    skip_tls=False
)
auth.login()

# Your cluster operations
# ...

auth.logout()
```

### After (Recommended)

```python
from kube_authkit import AuthConfig, get_k8s_client

# Explicit token authentication
auth_config = AuthConfig(
    server="https://api.example.com:6443",
    token="my-token",
    verify_ssl=True  # Replaces skip_tls=False
)
api_client = get_k8s_client(config=auth_config)

# Your cluster operations - the SDK will automatically use the authenticated client
# ...

# No logout needed - authentication is managed automatically
```

## Migration Examples

### Example 1: Token-Based Authentication

**Old Pattern:**
```python
from codeflare_sdk import TokenAuthentication, Cluster, ClusterConfiguration

auth = TokenAuthentication(
    token="sha256~xxxxx",
    server="https://api.cluster.example.com:6443",
    skip_tls=False,
    ca_cert_path="/path/to/ca.crt"
)
auth.login()

cluster = Cluster(ClusterConfiguration(
    name='my-cluster',
    num_workers=2
))
cluster.apply()

auth.logout()
```

**New Pattern:**
```python
from kube_authkit import AuthConfig, get_k8s_client
from codeflare_sdk import Cluster, ClusterConfiguration

auth_config = AuthConfig(
    server="https://api.cluster.example.com:6443",
    token="sha256~xxxxx",
    verify_ssl=True,  # Note: verify_ssl=True replaces skip_tls=False
    ssl_ca_cert="/path/to/ca.crt"
)
api_client = get_k8s_client(config=auth_config)

# SDK automatically uses the authenticated client
cluster = Cluster(ClusterConfiguration(
    name='my-cluster',
    num_workers=2
))
cluster.apply()

# No logout needed
```

### Example 2: Kubeconfig File Authentication

**Old Pattern:**
```python
from codeflare_sdk import KubeConfigFileAuthentication

auth = KubeConfigFileAuthentication(kube_config_path="~/.kube/config")
auth.load_kube_config()
```

**New Pattern:**
```python
from kube_authkit import AuthConfig, get_k8s_client

# Option 1: Explicit kubeconfig path
auth_config = AuthConfig(kubeconfig_path="~/.kube/config")
api_client = get_k8s_client(config=auth_config)

# Option 2: Auto-detect (will find ~/.kube/config automatically)
api_client = get_k8s_client()
```

### Example 3: Auto-Detection (Recommended)

**New Feature - No Old Equivalent:**
```python
from kube_authkit import get_k8s_client
from codeflare_sdk import Cluster, ClusterConfiguration

# Automatically detects and uses available authentication:
# 1. Kubeconfig file (~/.kube/config)
# 2. In-cluster service account
# 3. Other configured methods
api_client = get_k8s_client()

# Use with CodeFlare SDK
cluster = Cluster(ClusterConfiguration(name='my-cluster', num_workers=2))
cluster.apply()
```

## New Authentication Methods

These authentication methods are now available with kube-authkit:

### OpenShift OAuth

```python
from kube_authkit import AuthConfig, get_k8s_client

auth_config = AuthConfig(
    server="https://api.openshift.example.com:6443",
    auth_type="openshift-oauth"
    # Will prompt for credentials or use saved token
)
api_client = get_k8s_client(config=auth_config)
```

### OIDC Authentication

```python
from kube_authkit import AuthConfig, get_k8s_client

# Device Flow (for CLI tools)
auth_config = AuthConfig(
    server="https://api.cluster.example.com:6443",
    auth_type="oidc",
    oidc_issuer_url="https://keycloak.example.com/auth/realms/myrealm",
    oidc_client_id="codeflare-sdk",
    use_device_flow=True
)
api_client = get_k8s_client(config=auth_config)

# Client Credentials Flow (for automation)
auth_config = AuthConfig(
    server="https://api.cluster.example.com:6443",
    auth_type="oidc",
    oidc_issuer_url="https://keycloak.example.com/auth/realms/myrealm",
    oidc_client_id="codeflare-sdk",
    oidc_client_secret="your-secret"
)
api_client = get_k8s_client(config=auth_config)
```

### In-Cluster Service Account

```python
from kube_authkit import get_k8s_client

# When running inside a Kubernetes pod, this automatically uses the service account
api_client = get_k8s_client()
```

## Parameter Mapping

| Old (TokenAuthentication) | New (AuthConfig) | Notes |
|---------------------------|------------------|-------|
| `token` | `token` | Same |
| `server` | `server` | Same |
| `skip_tls=True` | `verify_ssl=False` | **Inverted logic!** |
| `skip_tls=False` | `verify_ssl=True` | **Inverted logic!** |
| `ca_cert_path` | `ssl_ca_cert` | Different parameter name |
| N/A | `auth_type` | New - specify auth method |
| N/A | `oidc_issuer_url` | New - for OIDC |
| N/A | `oidc_client_id` | New - for OIDC |
| N/A | `oidc_client_secret` | New - for OIDC |

**⚠️ Important:** Note that `skip_tls` and `verify_ssl` have **inverted logic**:
- `skip_tls=True` → `verify_ssl=False`
- `skip_tls=False` → `verify_ssl=True`

## Common Migration Issues

### Issue 1: Deprecation Warnings

**Problem:**
```
DeprecationWarning: TokenAuthentication is deprecated and will be removed in a future version.
```

**Solution:**
Migrate to using `AuthConfig` from kube-authkit as shown in the examples above.

### Issue 2: TLS Verification Confusion

**Problem:**
```python
# This is WRONG
auth_config = AuthConfig(server="...", token="...", skip_tls=True)
# Error: AuthConfig has no parameter 'skip_tls'
```

**Solution:**
```python
# Correct - use verify_ssl with inverted logic
auth_config = AuthConfig(server="...", token="...", verify_ssl=False)
```

### Issue 3: Missing login() Call

**Problem:**
```python
auth_config = AuthConfig(...)
# Where do I call login()?
```

**Solution:**
kube-authkit handles authentication automatically when you call `get_k8s_client()`:
```python
auth_config = AuthConfig(...)
api_client = get_k8s_client(config=auth_config)  # Authentication happens here
```

## Testing Your Migration

After migrating, test your code:

```python
from kube_authkit import AuthConfig, get_k8s_client
from kubernetes import client

# Configure authentication
auth_config = AuthConfig(
    server="https://your-cluster:6443",
    token="your-token",
    verify_ssl=True
)
api_client = get_k8s_client(config=auth_config)

# Test connection
v1 = client.CoreV1Api(api_client)
try:
    namespaces = v1.list_namespace()
    print(f"✅ Authentication successful! Found {len(namespaces.items)} namespaces")
except Exception as e:
    print(f"❌ Authentication failed: {e}")
```

## Backward Compatibility

The legacy classes will continue to work until v1.0.0:

```python
# This still works but shows deprecation warnings
from codeflare_sdk import TokenAuthentication

auth = TokenAuthentication(token="...", server="...")
auth.login()  # Works, but you'll see a deprecation warning
```

To suppress warnings temporarily during migration:
```python
import warnings

with warnings.catch_warnings():
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    auth = TokenAuthentication(token="...", server="...")
    auth.login()
```

## Getting Help

- **kube-authkit Documentation**: https://github.com/opendatahub-io/kube-authkit
- **CodeFlare SDK Issues**: https://github.com/project-codeflare/codeflare-sdk/issues
- **Migration Questions**: Open an issue with the `authentication` label

## FAQ

**Q: Do I need to update my code immediately?**
A: No, but we recommend migrating before v1.0.0. Your existing code will continue to work with deprecation warnings.

**Q: Can I use both old and new authentication in the same codebase?**
A: Yes, during the transition period you can mix both approaches.

**Q: What if kube-authkit is not installed?**
A: Install it with: `pip install kube-authkit` or `pip install codeflare-sdk` (it's now a required dependency)

**Q: How do I authenticate in a Jupyter notebook?**
A: See the [auth_examples.ipynb](../demo-notebooks/guided-demos/auth_examples.ipynb) notebook for detailed examples.

**Q: Does this affect existing clusters or jobs?**
A: No, this only affects how you authenticate to Kubernetes. Your existing clusters and jobs are not affected.

**Q: What about RayJobClient authentication?**
A: RayJobClient uses Ray Dashboard authentication (bearer tokens), which is separate from Kubernetes authentication. This migration doesn't affect RayJobClient usage.

## Example: Complete Migration

Here's a complete before/after example:

**Before (old-code.py):**
```python
from codeflare_sdk import (
    TokenAuthentication,
    Cluster,
    ClusterConfiguration,
)

# Authenticate
auth = TokenAuthentication(
    token="sha256~xxxxx",
    server="https://api.cluster.example.com:6443",
    skip_tls=False
)
auth.login()

# Create cluster
cluster = Cluster(ClusterConfiguration(
    name='mnist-cluster',
    num_workers=2,
    worker_cpu_requests=1,
    worker_cpu_limits=2,
    worker_memory_requests=4,
    worker_memory_limits=8,
))

cluster.apply()
cluster.wait_ready()
print(cluster.details())

# Cleanup
cluster.down()
auth.logout()
```

**After (new-code.py):**
```python
from kube_authkit import AuthConfig, get_k8s_client
from codeflare_sdk import Cluster, ClusterConfiguration

# Authenticate
auth_config = AuthConfig(
    server="https://api.cluster.example.com:6443",
    token="sha256~xxxxx",
    verify_ssl=True
)
api_client = get_k8s_client(config=auth_config)

# Create cluster (SDK automatically uses authenticated client)
cluster = Cluster(ClusterConfiguration(
    name='mnist-cluster',
    num_workers=2,
    worker_cpu_requests=1,
    worker_cpu_limits=2,
    worker_memory_requests=4,
    worker_memory_limits=8,
))

cluster.apply()
cluster.wait_ready()
print(cluster.details())

# Cleanup (no logout needed)
cluster.down()
```

## Next Steps

1. Review the [authentication examples notebook](../demo-notebooks/guided-demos/auth_examples.ipynb)
2. Update your code using the patterns above
3. Test your changes
4. Report any issues on GitHub

---

**Last Updated:** January 2026
**Applies to:** CodeFlare SDK v0.34.0 and later

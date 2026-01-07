# CodeFlare SDK

[![Python application](https://github.com/project-codeflare/codeflare-sdk/actions/workflows/unit-tests.yml/badge.svg?branch=main)](https://github.com/project-codeflare/codeflare-sdk/actions/workflows/unit-tests.yml)
![coverage badge](./coverage.svg)

An intuitive, easy-to-use python interface for batch resource requesting, access, job submission, and observation. Simplifying the developer's life while enabling access to high-performance compute resources, either in the cloud or on-prem.

For guided demos and basics walkthroughs, check out the following links:

- Guided demo notebooks available [here](https://github.com/project-codeflare/codeflare-sdk/tree/main/demo-notebooks/guided-demos), and copies of the notebooks with [expected output](https://github.com/project-codeflare/codeflare-sdk/tree/main/demo-notebooks/guided-demos/notebook-ex-outputs) also available
- these demos can be copied into your current working directory when using the `codeflare-sdk` by using the `codeflare_sdk.copy_demo_nbs()` function
- Additionally, we have a [video walkthrough](https://www.youtube.com/watch?v=U76iIfd9EmE) of these basic demos from June, 2023

Full documentation can be found [here](https://project-codeflare.github.io/codeflare-sdk/index.html)

## Installation

Can be installed via `pip`: `pip install codeflare-sdk`

## Authentication

CodeFlare SDK uses [kube-authkit](https://github.com/opendatahub-io/kube-authkit) for Kubernetes authentication, supporting multiple authentication methods:

- **Auto-Detection** - Automatically detects kubeconfig or in-cluster authentication
- **Token-Based** - Authenticate with API server token
- **OIDC** - OpenID Connect authentication with device flow or client credentials
- **OpenShift OAuth** - Native OpenShift OAuth support
- **Kubeconfig** - Traditional kubeconfig file authentication
- **In-Cluster** - Service account authentication when running in a pod

### Quick Start

```python
from kube_authkit import get_k8s_client, AuthConfig
from codeflare_sdk import Cluster, ClusterConfiguration

# Option 1: Auto-detect authentication (recommended)
api_client = get_k8s_client()

# Option 2: Explicit token authentication
auth_config = AuthConfig(
    server="https://api.cluster.example.com:6443",
    token="your-token",
    verify_ssl=True
)
api_client = get_k8s_client(config=auth_config)

# Use with CodeFlare SDK
cluster = Cluster(ClusterConfiguration(
    name='my-cluster',
    num_workers=2,
))
cluster.apply()
```

### Migration from Legacy Authentication

If you're using the deprecated `TokenAuthentication` or `KubeConfigFileAuthentication` classes, please see our [Migration Guide](./docs/auth_migration_guide.md) for detailed instructions on updating to kube-authkit.

**Legacy classes (deprecated):**
```python
# ⚠️ Deprecated - will be removed in v1.0.0
from codeflare_sdk import TokenAuthentication
auth = TokenAuthentication(token="...", server="...")
auth.login()
```

**New recommended approach:**
```python
# ✅ Recommended
from kube_authkit import AuthConfig, get_k8s_client
auth_config = AuthConfig(server="...", token="...", verify_ssl=True)
api_client = get_k8s_client(config=auth_config)
```

## Development

Please see our [CONTRIBUTING.md](./CONTRIBUTING.md) for detailed instructions.

## Release Instructions

### Automated Releases

It is possible to use the Release Github workflow to do the release. This is generally the process we follow for releases

### Manual Releases

The following instructions apply when doing release manually. This may be required in instances where the automation is failing.

- Check and update the version in "pyproject.toml" file.
- Commit all the changes to the repository.
- Create Github release (<https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository#creating-a-release>).
- Build the Python package. `poetry build`
- If not present already, add the API token to Poetry.
`poetry config pypi-token.pypi API_TOKEN`
- Publish the Python package. `poetry publish`
- Trigger the [Publish Documentation](https://github.com/project-codeflare/codeflare-sdk/actions/workflows/publish-documentation.yaml) workflow

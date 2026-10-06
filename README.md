# CodeFlare SDK

[![Python application](https://github.com/project-codeflare/codeflare-sdk/actions/workflows/unit-tests.yml/badge.svg?branch=main)](https://github.com/project-codeflare/codeflare-sdk/actions/workflows/unit-tests.yml)
![coverage badge](./coverage.svg)

An intuitive, easy-to-use python interface for batch resource requesting, access, job submission, and observation. Simplifying the developer's life while enabling access to high-performance compute resources, either in the cloud or on-prem.

For guided demos and basics walkthroughs, check out the following links:

- Guided demo notebooks available [here](https://github.com/project-codeflare/codeflare-sdk/tree/main/demo-notebooks/guided-demos), and copies of the notebooks with [expected output](https://github.com/project-codeflare/codeflare-sdk/tree/main/demo-notebooks/guided-demos/notebook-ex-outputs) also available
- these demos can be copied into your current working directory when using the `codeflare-sdk` by using the `codeflare_sdk.copy_demo_nbs()` function
- Additionally, we have a [video walkthrough](https://www.youtube.com/watch?v=U76iIfd9EmE) of these basic demos from June, 2023

Full documentation can be found [here](https://project-codeflare.github.io/codeflare-sdk/index.html)

Admin guide for **heterogeneous Ray clusters under Kueue** (multiple worker groups,
``ResourceFlavor`` / ``ClusterQueue`` prerequisites):
[docs/sphinx/user-docs/kueue-heterogeneous-ray-clusters.rst](docs/sphinx/user-docs/kueue-heterogeneous-ray-clusters.rst)
(also in the published docs toctree after the next documentation release).

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

`Codeflare` is the single entrypoint. It authenticates and owns the resulting
Kubernetes client, so clusters and jobs created from it keep using that client.

```python
from kube_authkit import AuthConfig
from codeflare_sdk import ClusterConfiguration, Codeflare, SDKConfig

# Option 1: Auto-detect authentication (kubeconfig or in-cluster service account)
cf = Codeflare(config=SDKConfig(namespace='my-project'))

# Option 2: OIDC authentication
cf = Codeflare(config=SDKConfig(
    auth=AuthConfig(
        method="oidc",
        oidc_issuer="https://your-oidc-provider.com",
        client_id="your-client-id",
        use_device_flow=True,
    ),
    namespace='my-project',
))

# Option 3: OpenShift OAuth with token
cf = Codeflare(config=SDKConfig(
    auth=AuthConfig(
        method="openshift",
        k8s_api_host="https://api.example.com:6443",
        token="your-token",
    ),
    namespace='my-project',
))

# Now create your cluster. Every SDK entrypoint that takes a cluster
# description takes the same ClusterConfiguration object.
cluster = cf.clusters.create(ClusterConfiguration(name='my-cluster', num_workers=2))
cluster.apply()
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

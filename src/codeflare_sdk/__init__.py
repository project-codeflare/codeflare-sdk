from .ray import (
    Cluster,
    ClusterConfiguration,
    RayClusterStatus,
    CodeFlareClusterStatus,
    RayCluster,
    get_cluster,
    list_all_queued,
    list_all_clusters,
    AWManager,
    AppWrapperStatus,
    RayJobClient,
    RayJob,
    ManagedClusterConfig,
)

from .common.widgets import view_clusters

from .common import (
    Authentication,
    KubeConfiguration,
    TokenAuthentication,
    KubeConfigFileAuthentication,
)

from .common.kubernetes_cluster import set_api_client

# Export kube-authkit at top level for convenience
try:
    from kube_authkit import AuthConfig, get_k8s_client
except ImportError:
    pass  # Will show warning from auth.py

from .common.kueue import (
    list_local_queues,
)

from .common.utils import generate_cert
from .common.utils.demos import copy_demo_nbs

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("codeflare-sdk")  # use metadata associated with built package

except PackageNotFoundError:
    __version__ = "v0.0.0"

from .ray import (
    Cluster,  # Deprecated, use RayCluster instead
    ClusterConfiguration,  # Deprecated, use RayCluster instead
    RayCluster,  # New unified class (recommended) - combines config + operations
    RayClusterInfo,  # Status info dataclass
    RayClusterStatus,
    CodeFlareClusterStatus,
    get_cluster,
    list_all_queued,
    list_all_clusters,
    AWManager,
    AppWrapperStatus,
    RayJobClient,
    RayJob,
    ManagedClusterConfig,  # Deprecated, use RayCluster instead
)

from .common.widgets import view_clusters

from .common import (
    Authentication,
    KubeConfiguration,
    TokenAuthentication,
    KubeConfigFileAuthentication,
)

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

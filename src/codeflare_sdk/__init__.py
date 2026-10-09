from .ray import (
    Cluster,
    ClusterConfiguration,
    WorkerGroup,
    RayClusterStatus,
    CodeFlareClusterStatus,
    RayCluster,
    WorkerGroupStatus,
    get_cluster,
    list_all_queued,
    list_all_clusters,
    RayJobClient,
    RayJob,
)

from .common.widgets import view_clusters

from .codeflare import Codeflare, SDKConfig, JobOptions

# kube-authkit, re-exported for convenience as it was in v0.39.x. This is the
# current authentication interface, not a legacy one.
from .common.kubernetes_cluster import AuthConfig, get_k8s_client

# Deprecated as of v0.40.0, still working. See _compat for why it is back.
from ._compat import set_api_client

from .common.kueue import (
    list_local_queues,
)

from .common.utils import generate_cert
from .common.utils.demos import copy_demo_nbs

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("codeflare-sdk")

except PackageNotFoundError:
    __version__ = "v0.0.0"


def __getattr__(name):
    """Explain the v0.39.x names that are gone, instead of 'cannot import name'.

    ``ImportError`` rather than ``AttributeError`` on purpose — see
    ``codeflare_sdk._compat`` for the reasoning and its cost.
    """
    from ._compat import REMOVED

    if name in REMOVED:
        raise ImportError(REMOVED[name])
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

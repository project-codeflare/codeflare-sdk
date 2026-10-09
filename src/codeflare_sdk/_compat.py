# Copyright 2026 IBM, Red Hat
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Backward compatibility for the v0.39.x public surface (RHOAIENG-98947).

Two different situations, handled differently:

**Removed with notice.** ``TokenAuthentication`` and
``KubeConfigFileAuthentication`` carried a ``DeprecationWarning`` throughout
v0.39.x, so they are gone — earlier than the v1.0.0 that v0.39.1's README and
migration guide published, which is a deliberate call and one for the release
notes. ``ManagedClusterConfig`` was tech preview, so it needed no notice at
all. What they get here is an error that names the replacement, because the
alternative is a user reading ``cannot import name 'TokenAuthentication'``
and guessing.

**Removed without notice.** ``set_api_client`` never carried a warning, and
the v0.39.1 ``2_basic_interactive`` notebook opens with::

    from codeflare_sdk import Cluster, ClusterConfiguration, set_api_client

Dropping it broke working notebooks silently, which is not a removal we are
entitled to make. It is re-exported here and keeps working; the wrapper adds
the deprecation notice it should have had in the first place, so a later
release can remove it properly.

On raising ``ImportError`` rather than ``AttributeError``: ``from pkg import X``
calls ``getattr`` and, on ``AttributeError``, *discards the message* and raises
its own ``cannot import name X``. Since ``from ... import`` is how every one of
these names is actually written, an ``AttributeError`` would mean the migration
text is never seen. ``ImportError`` propagates intact. The cost is that
``hasattr(codeflare_sdk, "TokenAuthentication")`` raises instead of returning
``False``; that applies only to the names in ``REMOVED``, and losing the
message is the worse trade.
"""

import warnings
from typing import TYPE_CHECKING

from .common.kubernetes_cluster.auth import set_api_client as _set_api_client

if TYPE_CHECKING:  # pragma: no cover
    from kubernetes import client


def set_api_client(new_client: "client.ApiClient") -> None:
    """Set a custom Kubernetes API client for the SDK to use.

    .. deprecated:: 0.40.0
        Pass the client's :class:`~kube_authkit.AuthConfig` to
        :class:`~codeflare_sdk.Codeflare` instead. ``Codeflare`` binds the
        resulting client to the objects it creates, so two instances can talk
        to two clusters; the module-level client this function sets is global
        and the last caller wins.

    Args:
        new_client: The Kubernetes API client instance to use.
    """
    warnings.warn(
        "set_api_client() is deprecated and will be removed in a future "
        "release. Use Codeflare(config=SDKConfig(auth=AuthConfig(...))), "
        "which scopes the client to the clusters and jobs it creates instead "
        "of setting a process-wide global.",
        DeprecationWarning,
        stacklevel=2,
    )
    _set_api_client(new_client)


_TOKEN_AUTH = """\
TokenAuthentication was removed in v0.40.0, after being deprecated \
throughout v0.39.x. Use kube-authkit:

    from codeflare_sdk import Codeflare, SDKConfig
    from kube_authkit import AuthConfig

    cf = Codeflare(config=SDKConfig(auth=AuthConfig(
        method="openshift",
        k8s_api_host=<server>,
        token=<token>,
        verify_ssl=not <skip_tls>,   # ca_cert=<ca_cert_path>
    )))

cf.clusters.create(...) returns clusters bound to that client.\
"""

_KUBECONFIG_AUTH = """\
KubeConfigFileAuthentication was removed in v0.40.0, after being deprecated \
throughout v0.39.x. Use kube-authkit:

    from codeflare_sdk import Codeflare, SDKConfig
    from kube_authkit import AuthConfig

    cf = Codeflare(config=SDKConfig(auth=AuthConfig(
        method="kubeconfig", kubeconfig_path=<kube_config_path>,
    )))\
"""

_AUTH_BASE = """\
{name} was removed in v0.40.0 along with TokenAuthentication and \
KubeConfigFileAuthentication, the only classes that implemented it. \
Authentication is handled by kube_authkit.AuthConfig, which is a dataclass \
rather than a base class to subclass.\
"""

_MANAGED_CLUSTER_CONFIG = """\
ManagedClusterConfig was removed in v0.40.0. It was tech preview. Use \
ClusterConfiguration, which both cf.clusters.create() and \
cf.jobs.create(cluster_config=...) now accept. Three fields were renamed:
    head_accelerators    -> head_extended_resource_requests
    worker_accelerators  -> worker_extended_resource_requests
    accelerator_configs  -> extended_resource_mapping\
"""

#: Names that are gone for good, mapped to the message explaining what replaced
#: them. Consumed by ``codeflare_sdk.__getattr__``.
REMOVED = {
    "TokenAuthentication": _TOKEN_AUTH,
    "KubeConfigFileAuthentication": _KUBECONFIG_AUTH,
    "Authentication": _AUTH_BASE.format(name="Authentication"),
    "KubeConfiguration": _AUTH_BASE.format(name="KubeConfiguration"),
    "ManagedClusterConfig": _MANAGED_CLUSTER_CONFIG,
}

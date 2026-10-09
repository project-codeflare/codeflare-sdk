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

**Removed anyway.** ``TokenAuthentication`` and
``KubeConfigFileAuthentication`` warned throughout v0.39.x but were also
documented as surviving until v1.0.0, and the migration guide told token users
to stay on ``TokenAuthentication`` because ``AuthConfig`` supposedly could not
do tokens — which it can. ``ManagedClusterConfig`` (RHAIENG-2063) shipped no
warning at all and was used by two guided notebooks. None of these three is a
clean removal; keeping them out is a product decision, recorded in
RHOAIENG-98947. What they get here is an error naming the replacement, because
the alternative is a user reading ``cannot import name 'TokenAuthentication'``
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


# The snippets below must stay in step with the numbered methods in
# docs/sphinx/user-docs/authentication.rst, which is where a user sent here by
# the error will read next. That page uses method="openshift" with
# k8s_api_host and token, and a bare method="kubeconfig"; a custom CA goes
# through the CF_SDK_CA_CERT_PATH environment variable, not an AuthConfig
# field. AuthConfig does also accept kubeconfig_path, verify_ssl and ca_cert,
# but naming them here would teach a second style for no gain.

_TOKEN_AUTH = """\
TokenAuthentication was removed in v0.40.0. Note that v0.39.x documentation \
said it would survive until v1.0.0, and the auth migration guide told \
token users to stay on it; that is no longer true. kube-authkit does now \
support token auth directly (see authentication.rst, Method 1):

    from codeflare_sdk import Codeflare, SDKConfig
    from kube_authkit import AuthConfig

    cf = Codeflare(config=SDKConfig(auth=AuthConfig(
        method="openshift",
        k8s_api_host=<server>,
        token=<token>,
    )))

cf.clusters.create(...) returns clusters bound to that client. For a custom \
CA bundle, set the CF_SDK_CA_CERT_PATH environment variable.\
"""

_KUBECONFIG_AUTH = """\
KubeConfigFileAuthentication was removed in v0.40.0. Note that v0.39.x \
documentation said it would survive until v1.0.0; that is no longer true. \
Use kube-authkit (see authentication.rst, Method 4):

    from codeflare_sdk import Codeflare, SDKConfig
    from kube_authkit import AuthConfig

    cf = Codeflare(config=SDKConfig(auth=AuthConfig(method="kubeconfig")))

KUBECONFIG is respected if set, otherwise ~/.kube/config is used.\
"""

_AUTH_BASE = """\
{name} was removed in v0.40.0 along with TokenAuthentication and \
KubeConfigFileAuthentication, the only classes that implemented it. \
Authentication is handled by kube_authkit.AuthConfig, which is a dataclass \
rather than a base class to subclass.\
"""

_MANAGED_CLUSTER_CONFIG = """\
ManagedClusterConfig was removed in v0.40.0 (RHAIENG-2063), without a \
deprecation warning having been shipped first. Use ClusterConfiguration, \
which both cf.clusters.create() and cf.jobs.create(cluster_config=...) now \
accept. Three fields were renamed:
    head_accelerators    -> head_extended_resource_requests
    worker_accelerators  -> worker_extended_resource_requests
    accelerator_configs  -> extended_resource_mapping
Renaming is not sufficient. Four resource defaults differ, so a call site \
that only renames can produce a differently sized cluster:
    head_cpu_requests      2 -> 1
    head_memory_requests   8 -> 5
    worker_memory_requests 2 -> 3
    worker_memory_limits   2 -> 6
See docs/rayjob_config_migration_guide.md.\
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

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

"""
Single entrypoint for the CodeFlare SDK.

Usage:
    from codeflare_sdk import ClusterConfiguration, Codeflare, SDKConfig
    from kube_authkit import AuthConfig

    cf = Codeflare(config=SDKConfig(
        auth=AuthConfig(method="auto"),
        namespace="my-project",
    ))

    cluster = cf.clusters.create(
        ClusterConfiguration(name="my-cluster", num_workers=4)
    )
    cluster.apply()
"""

import copy
import logging
from dataclasses import dataclass, field
import builtins
from typing import Any, Dict, Optional, TypedDict, Union, Unpack, overload

from ray.runtime_env import RuntimeEnv

from kube_authkit import AuthConfig, get_k8s_client
from .common.kubernetes_cluster.auth import set_api_client
from .common.utils import get_current_namespace
from .ray.cluster.cluster import (
    Cluster,
    _get_cluster_strict,
    list_all_clusters,
    _delete_cluster,
    list_all_queued,
)
from .ray.cluster.config import ClusterConfiguration
from .ray.cluster.status import RayCluster
from .ray.rayjobs.rayjob import RayJob

_VALID_LOG_LEVELS = ("CRITICAL", "DEBUG", "ERROR", "INFO", "WARNING")


@dataclass
class SDKConfig:
    """Configuration for the CodeFlare SDK.

    Args:
        auth: kube-authkit AuthConfig for Kubernetes authentication.
        namespace: Default namespace for all operations. When unset, operations
            fall back to the namespace of the current Kubernetes context, and
            raise if none can be determined. See _resolve_namespace.
        log_level: Logging level for the codeflare_sdk logger.
    """

    auth: AuthConfig = field(default_factory=lambda: AuthConfig(method="auto"))
    namespace: Optional[str] = None
    log_level: str = "WARNING"

    def __post_init__(self):
        if self.log_level not in _VALID_LOG_LEVELS:
            raise ValueError(
                f"log_level must be one of {_VALID_LOG_LEVELS}, got '{self.log_level}'"
            )


def _resolve_namespace(namespace: Optional[str], sdk: "Codeflare") -> str:
    """Resolve the namespace for a facade operation.

    Precedence:
    1. The namespace passed to the operation.
    2. ``SDKConfig.namespace``.
    3. The namespace of the current Kubernetes/OpenShift context.
    4. Otherwise raise — the facade does not silently fall back to ``default``.

    Raises:
        ValueError: If no namespace can be determined.
    """
    if namespace:
        return namespace
    if sdk.config.namespace:
        return sdk.config.namespace
    detected = get_current_namespace()
    if detected:
        return detected
    raise ValueError(
        "❌ Configuration Error: could not determine a Kubernetes namespace. "
        "Pass 'namespace' to this call, set SDKConfig(namespace=...), or select a "
        "namespace in your current Kubernetes context."
    )


class JobOptions(TypedDict, total=False):
    """Optional keyword arguments shared by the :class:`JobHandler` overloads.

    Holds every :meth:`JobHandler.create` keyword except the execution target
    (``cluster_name`` / ``cluster_config``), which the overloads vary. Keeping
    them here means the overload pair does not restate the full signature.

    ``test_job_options_match_create_signature`` fails if the two drift.
    """

    runtime_env: Optional[Union[RuntimeEnv, Dict[str, Any]]]
    ttl_seconds_after_finished: int
    active_deadline_seconds: Optional[int]
    local_queue: Optional[str]
    priority_class: Optional[str]


class ClusterHandler:
    """Namespace accessor for Ray cluster operations."""

    def __init__(self, sdk: "Codeflare"):
        self._sdk = sdk

    def create(
        self,
        config: ClusterConfiguration,
        namespace: Optional[str] = None,
    ) -> "Cluster":
        """Create a new Cluster object (does not apply it to K8s yet).

        Takes a :class:`~codeflare_sdk.ray.cluster.config.ClusterConfiguration`,
        the same object ``cf.jobs.create(cluster_config=...)`` and ``Cluster()``
        take, so there is one way to describe a cluster across the SDK.

        The returned Cluster is bound to this Codeflare instance's Kubernetes
        client, so later operations on it are unaffected by any other Codeflare
        instance created afterwards.

        Args:
            config: Cluster configuration. ``config.name`` is required.
            namespace: K8s namespace, overriding ``config.namespace``. See
                namespace resolution precedence in :func:`_resolve_namespace`.

        Returns:
            Cluster instance ready for .apply().

        Raises:
            ValueError: If config.name is unset, or no namespace can be resolved.
        """
        if not config.name:
            raise ValueError(
                "❌ Configuration Error: ClusterConfiguration.name is required to "
                "create a cluster."
            )

        ns = _resolve_namespace(namespace or config.namespace, self._sdk)
        if ns != config.namespace:
            # A shallow copy, not dataclasses.replace: ClusterConfiguration's
            # __post_init__ is not idempotent (it merges the default accelerator
            # mapping into extended_resource_mapping and then rejects the merged
            # result), so reconstructing a configured instance raises.
            config = copy.copy(config)
            config.namespace = ns

        return Cluster(config, api_client=self._sdk.client)

    def get(
        self,
        name: str,
        namespace: Optional[str] = None,
        *,
        verify_tls: bool = True,
        write_to_file: bool = False,
    ) -> "Cluster":
        """Retrieve an existing cluster by name.

        The returned handle supports ``status()`` and ``down()`` but **not**
        ``apply()`` — the reconstructed configuration may not match the live
        spec.

        Unlike the standalone :func:`get_cluster` (which returns ``None`` on
        API errors for backward compatibility), this method calls the strict
        retrieval path and propagates the original Kubernetes API exception
        so callers can distinguish a 404 from a 403 or 500.

        Args:
            name: Cluster name.
            namespace: K8s namespace. See namespace resolution precedence in
                :func:`_resolve_namespace`.
            verify_tls: Whether to verify TLS when connecting to the cluster.
            write_to_file: Whether to write the retrieved resource to a YAML file.

        Returns:
            Cluster instance bound to this instance's Kubernetes client.

        Raises:
            ApiException: If the Kubernetes API call fails (404, 403, 500, …).
            ValueError: If no namespace can be resolved.
        """
        ns = _resolve_namespace(namespace, self._sdk)
        return _get_cluster_strict(
            cluster_name=name,
            namespace=ns,
            verify_tls=verify_tls,
            write_to_file=write_to_file,
            api_client=self._sdk.client,
        )

    def list(self, namespace: Optional[str] = None) -> builtins.list[RayCluster]:
        """List all Ray clusters in a namespace.

        Returns ``RayCluster`` status snapshots — the same type
        :func:`list_all_clusters` has always returned.  For a ``Cluster``
        lifecycle handle (``status()``, ``down()``, etc.), use
        :meth:`get`.

        Args:
            namespace: K8s namespace. See namespace resolution precedence in
                :func:`_resolve_namespace`.

        Returns:
            RayCluster status snapshots.

        Raises:
            ApiException: If the Kubernetes API fails.
            ValueError: If no namespace can be resolved.
        """
        ns = _resolve_namespace(namespace, self._sdk)
        return list_all_clusters(
            ns, print_to_console=False, api_client=self._sdk.client
        )

    def delete(self, name: str, namespace: Optional[str] = None) -> bool:
        """Delete a Ray cluster and its associated resources, including TLS certificates.

        .. note:: **TLS isolation limitation**

            Kubernetes client isolation is fully supported: each ``Codeflare``
            instance owns its own API client, and objects created through it
            talk only to that client's API server.

            TLS certificate storage is **not** isolated. Local certificate
            directories are keyed by ``{name}-{namespace}`` with no API-server
            component, so two instances targeting different API servers that
            contain identically named clusters in the same namespace share (and
            can delete) each other's certificates. The ``RAY_TLS_*``
            environment variables are also process-wide, so simultaneous mTLS
            connections to different API servers within a single process are
            not supported.

        Args:
            name: Cluster name.
            namespace: K8s namespace. See namespace resolution precedence in
                :func:`_resolve_namespace`.

        Returns:
            True if the cluster was deleted or already absent.

        Raises:
            ApiException: If deletion fails for a reason other than a missing
                cluster or a missing RayCluster CRD.
            RuntimeError: If the RayCluster CRD is not installed.
            OSError: If local TLS certificate cleanup fails.
            ValueError: If no namespace can be resolved.
        """
        ns = _resolve_namespace(namespace, self._sdk)
        return _delete_cluster(name, ns, api_client=self._sdk.client)

    def list_queued(self, namespace: Optional[str] = None) -> builtins.list:
        """List all queued Ray clusters in a namespace.

        Args:
            namespace: K8s namespace. See namespace resolution precedence in
                :func:`_resolve_namespace`.

        Returns:
            List of queued RayCluster objects.
        """
        ns = _resolve_namespace(namespace, self._sdk)
        return list_all_queued(ns, print_to_console=False, api_client=self._sdk.client)


class JobHandler:
    """Namespace accessor for RayJob operations."""

    def __init__(self, sdk: "Codeflare"):
        self._sdk = sdk

    def _build(
        self,
        name: str,
        entrypoint: str,
        namespace: Optional[str],
        cluster_name: Optional[str],
        cluster_config: Optional[ClusterConfiguration],
        runtime_env: Optional[Union[RuntimeEnv, Dict[str, Any]]],
        ttl_seconds_after_finished: int,
        active_deadline_seconds: Optional[int],
        local_queue: Optional[str],
        priority_class: Optional[str],
    ) -> "RayJob":
        """Construct a RayJob bound to this instance's client.

        Shared by :meth:`create` and :meth:`submit`. Those are overloaded, so
        they cannot call each other without re-narrowing the execution target.
        """
        ns = _resolve_namespace(namespace, self._sdk)
        return RayJob(
            job_name=name,
            entrypoint=entrypoint,
            cluster_name=cluster_name,
            cluster_config=cluster_config,
            namespace=ns,
            runtime_env=runtime_env,
            ttl_seconds_after_finished=ttl_seconds_after_finished,
            active_deadline_seconds=active_deadline_seconds,
            local_queue=local_queue,
            priority_class=priority_class,
            api_client=self._sdk.client,
        )

    @overload
    def create(
        self,
        name: str,
        entrypoint: str,
        namespace: Optional[str] = ...,
        *,
        cluster_name: str,
        **kwargs: Unpack[JobOptions],
    ) -> "RayJob": ...

    @overload
    def create(
        self,
        name: str,
        entrypoint: str,
        namespace: Optional[str] = ...,
        *,
        cluster_config: ClusterConfiguration,
        **kwargs: Unpack[JobOptions],
    ) -> "RayJob": ...

    def create(
        self,
        name: str,
        entrypoint: str,
        namespace: Optional[str] = None,
        *,
        cluster_name: Optional[str] = None,
        cluster_config: Optional[ClusterConfiguration] = None,
        runtime_env: Optional[Union[RuntimeEnv, Dict[str, Any]]] = None,
        ttl_seconds_after_finished: int = 0,
        active_deadline_seconds: Optional[int] = None,
        local_queue: Optional[str] = None,
        priority_class: Optional[str] = None,
    ) -> "RayJob":
        """Create a RayJob without submitting it.

        A job needs an execution target: pass exactly one of ``cluster_name``
        (run on an existing cluster) or ``cluster_config`` (the job creates and
        manages its own cluster). The two overloads make "exactly one" a type
        error rather than only a runtime one.

        Args:
            name: Job name.
            entrypoint: Python script or command to run.
            cluster_name: Name of an existing Ray cluster to run on.
            cluster_config: Configuration for a cluster the job will manage.
            namespace: K8s namespace. See namespace resolution precedence in
                :func:`_resolve_namespace`.
            runtime_env: Ray runtime environment, as a RuntimeEnv or dict.
            ttl_seconds_after_finished: Cleanup delay for managed clusters.
            active_deadline_seconds: Maximum job runtime before termination.
            local_queue: Kueue LocalQueue to submit to.
            priority_class: Kueue WorkloadPriorityClass name.

        Returns:
            RayJob instance (not yet submitted), bound to this instance's client.

        Raises:
            ValueError: If neither or both of cluster_name/cluster_config given.
        """
        return self._build(
            name,
            entrypoint,
            namespace,
            cluster_name,
            cluster_config,
            runtime_env,
            ttl_seconds_after_finished,
            active_deadline_seconds,
            local_queue,
            priority_class,
        )

    @overload
    def submit(
        self,
        name: str,
        entrypoint: str,
        namespace: Optional[str] = ...,
        *,
        cluster_name: str,
        **kwargs: Unpack[JobOptions],
    ) -> "RayJob": ...

    @overload
    def submit(
        self,
        name: str,
        entrypoint: str,
        namespace: Optional[str] = ...,
        *,
        cluster_config: ClusterConfiguration,
        **kwargs: Unpack[JobOptions],
    ) -> "RayJob": ...

    def submit(
        self,
        name: str,
        entrypoint: str,
        namespace: Optional[str] = None,
        *,
        cluster_name: Optional[str] = None,
        cluster_config: Optional[ClusterConfiguration] = None,
        runtime_env: Optional[Union[RuntimeEnv, Dict[str, Any]]] = None,
        ttl_seconds_after_finished: int = 0,
        active_deadline_seconds: Optional[int] = None,
        local_queue: Optional[str] = None,
        priority_class: Optional[str] = None,
    ) -> "RayJob":
        """Create and immediately submit a RayJob.

        Takes the same arguments as :meth:`create`; see there for the execution
        target requirement.

        Returns:
            Submitted RayJob instance, bound to this instance's client.

        Raises:
            ValueError: If neither or both of cluster_name/cluster_config given.
        """
        job = self._build(
            name,
            entrypoint,
            namespace,
            cluster_name,
            cluster_config,
            runtime_env,
            ttl_seconds_after_finished,
            active_deadline_seconds,
            local_queue,
            priority_class,
        )
        job.submit()
        return job

    def get(self, name: str, namespace: Optional[str] = None) -> "RayJob":
        """Retrieve an existing RayJob for status, stop, resubmit, or delete operations.

        Args:
            name: Job name.
            namespace: K8s namespace. See namespace resolution precedence in
                :func:`_resolve_namespace`.

        Returns:
            RayJob instance bound to this instance's Kubernetes client.

        Raises:
            ApiException: If the job is missing or the Kubernetes API fails.
            ValueError: If no namespace can be resolved.
        """
        ns = _resolve_namespace(namespace, self._sdk)
        return RayJob._get(name, ns, api_client=self._sdk.client)

    def list(self, namespace: Optional[str] = None) -> builtins.list["RayJob"]:
        """List existing RayJobs in a namespace.

        Args:
            namespace: K8s namespace. See namespace resolution precedence in
                :func:`_resolve_namespace`.

        Returns:
            RayJob instances bound to this instance's Kubernetes client.

        Raises:
            ApiException: If the Kubernetes API fails.
            ValueError: If no namespace can be resolved.
        """
        ns = _resolve_namespace(namespace, self._sdk)
        return RayJob._list(ns, api_client=self._sdk.client)

    def delete(self, name: str, namespace: Optional[str] = None) -> bool:
        """Delete a RayJob by name.

        Args:
            name: Job name.
            namespace: K8s namespace. See namespace resolution precedence in
                :func:`_resolve_namespace`.

        Returns:
            True if the job was deleted or already absent.

        Raises:
            ApiException: If deletion fails for a reason other than a missing job.
            ValueError: If no namespace can be resolved.
        """
        ns = _resolve_namespace(namespace, self._sdk)
        return RayJob._delete(name, ns, api_client=self._sdk.client)


class Codeflare:
    """Single entrypoint for the CodeFlare SDK.

    Authenticates to Kubernetes via kube-authkit and provides
    namespace-accessor handlers for clusters and jobs.

    Each instance owns its Kubernetes client, and every object created through
    it (``cf.clusters.create()``, ``cf.jobs.submit()``, ...) is bound to that
    client. Creating a second Codeflare instance therefore does not change which
    cluster the first instance's objects talk to.

    The module-level client is still set for backward compatibility, so direct
    APIs such as ``Cluster(config)`` that were not given an explicit client keep
    resolving the most recently created instance's client as before.

    .. note:: **Isolation scope**

        Kubernetes API client isolation is fully supported — each instance
        talks only to the API server it authenticated against.

        TLS certificate storage is **not** isolated: certificates are keyed
        by ``{cluster_name}-{namespace}`` without an API-server component,
        and ``RAY_TLS_*`` environment variables are process-wide. Running
        simultaneous mTLS connections to identically named clusters on
        different API servers within one process is not supported.

    Note: constructing a Codeflare instance means a client was created
    successfully; it does not prove the API server is reachable or the
    credentials are still valid.

    Args:
        config: SDK configuration. Defaults to auto-detection.
    """

    def __init__(self, config: Optional[SDKConfig] = None):
        self.config = config or SDKConfig()

        logging.getLogger("codeflare_sdk").setLevel(self.config.log_level)

        self._client = get_k8s_client(config=self.config.auth)
        # Legacy fallback only: direct APIs with no explicit client still read
        # this. Facade-created objects never rely on it.
        set_api_client(self._client)

        self.clusters = ClusterHandler(self)
        self.jobs = JobHandler(self)

    @property
    def client(self):
        """The Kubernetes API client owned by this instance."""
        return self._client

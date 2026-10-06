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
    from codeflare_sdk import Codeflare, SDKConfig
    from kube_authkit import AuthConfig

    cf = Codeflare(config=SDKConfig(
        auth=AuthConfig(method="auto"),
        namespace="my-project",
    ))

    cluster = cf.clusters.create(name="my-cluster", num_workers=4)
    cluster.apply()
"""

import logging
from dataclasses import dataclass, field
import builtins
from typing import Any, Dict, Optional, Union

from kube_authkit import AuthConfig, get_k8s_client
from .common.kubernetes_cluster.auth import set_api_client
from .common.utils import get_current_namespace
from .ray.cluster.cluster import (
    Cluster,
    get_cluster,
    list_all_clusters,
    list_all_queued,
)
from .ray.cluster.config import ClusterConfiguration
from .ray.rayjobs.rayjob import RayJob

_VALID_LOG_LEVELS = ("CRITICAL", "DEBUG", "ERROR", "INFO", "WARNING")


@dataclass
class SDKConfig:
    """Configuration for the CodeFlare SDK.

    Args:
        auth: kube-authkit AuthConfig for Kubernetes authentication.
        namespace: Default namespace for all operations. Falls back to 'default' if not set.
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


class ClusterHandler:
    """Namespace accessor for Ray cluster operations."""

    def __init__(self, sdk: "Codeflare"):
        self._sdk = sdk

    def create(self, name: str, namespace: Optional[str] = None, **kwargs) -> "Cluster":
        """Create a new Cluster object (does not apply it to K8s yet).

        The returned Cluster is bound to this Codeflare instance's Kubernetes
        client, so later operations on it are unaffected by any other Codeflare
        instance created afterwards.

        Args:
            name: Cluster name.
            namespace: K8s namespace. See namespace resolution precedence in
                :func:`_resolve_namespace`.
            **kwargs: Forwarded to ClusterConfiguration.

        Returns:
            Cluster instance ready for .apply().
        """
        ns = _resolve_namespace(namespace, self._sdk)
        cluster_config = ClusterConfiguration(name=name, namespace=ns, **kwargs)
        return Cluster(cluster_config, api_client=self._sdk.client)

    def get(self, name: str, namespace: Optional[str] = None, **kwargs) -> "Cluster":
        """Retrieve an existing cluster by name.

        Args:
            name: Cluster name.
            namespace: K8s namespace. See namespace resolution precedence in
                :func:`_resolve_namespace`.
            **kwargs: Forwarded to get_cluster.

        Returns:
            Cluster instance bound to this instance's Kubernetes client.
        """
        ns = _resolve_namespace(namespace, self._sdk)
        return get_cluster(
            cluster_name=name, namespace=ns, api_client=self._sdk.client, **kwargs
        )

    def list(self, namespace: Optional[str] = None) -> builtins.list:
        """List all Ray clusters in a namespace.

        Args:
            namespace: K8s namespace. See namespace resolution precedence in
                :func:`_resolve_namespace`.

        Returns:
            List of RayCluster objects.
        """
        ns = _resolve_namespace(namespace, self._sdk)
        return list_all_clusters(
            ns, print_to_console=False, api_client=self._sdk.client
        )

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

    def create(
        self,
        name: str,
        entrypoint: str,
        namespace: Optional[str] = None,
        *,
        cluster_name: Optional[str] = None,
        cluster_config: Optional[ClusterConfiguration] = None,
        runtime_env: Optional[Union[Dict[str, Any], Any]] = None,
        ttl_seconds_after_finished: int = 0,
        active_deadline_seconds: Optional[int] = None,
        local_queue: Optional[str] = None,
        priority_class: Optional[str] = None,
    ) -> "RayJob":
        """Create a RayJob without submitting it.

        A job needs an execution target: pass exactly one of ``cluster_name``
        (run on an existing cluster) or ``cluster_config`` (the job creates and
        manages its own cluster). These are named parameters rather than
        ``**kwargs`` so the requirement is visible to type checkers and IDEs.

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

    def submit(
        self,
        name: str,
        entrypoint: str,
        namespace: Optional[str] = None,
        *,
        cluster_name: Optional[str] = None,
        cluster_config: Optional[ClusterConfiguration] = None,
        runtime_env: Optional[Union[Dict[str, Any], Any]] = None,
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
        job = self.create(
            name=name,
            entrypoint=entrypoint,
            cluster_name=cluster_name,
            cluster_config=cluster_config,
            namespace=namespace,
            runtime_env=runtime_env,
            ttl_seconds_after_finished=ttl_seconds_after_finished,
            active_deadline_seconds=active_deadline_seconds,
            local_queue=local_queue,
            priority_class=priority_class,
        )
        job.submit()
        return job


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

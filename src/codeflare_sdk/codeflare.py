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
from typing import Optional

from kube_authkit import AuthConfig, get_k8s_client
from .common.kubernetes_cluster.auth import set_api_client
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
        retries: Number of retries for K8s API calls.
        timeout: Default timeout in seconds for blocking operations.
        namespace: Default namespace for all operations. Auto-detected if not set.
        log_level: Logging level for the codeflare_sdk logger.
    """

    auth: AuthConfig = field(default_factory=lambda: AuthConfig(method="auto"))
    retries: int = 3
    timeout: int = 300
    namespace: Optional[str] = None
    log_level: str = "WARNING"

    def __post_init__(self):
        if self.retries < 0:
            raise ValueError("retries must be >= 0")
        if self.timeout <= 0:
            raise ValueError("timeout must be > 0")
        if self.log_level not in _VALID_LOG_LEVELS:
            raise ValueError(
                f"log_level must be one of {_VALID_LOG_LEVELS}, got '{self.log_level}'"
            )


class ClusterHandler:
    """Namespace accessor for Ray cluster operations."""

    def __init__(self, sdk: "Codeflare"):
        self._sdk = sdk

    def create(self, name: str, namespace: Optional[str] = None, **kwargs) -> "Cluster":
        """Create a new Cluster object (does not apply it to K8s yet).

        Args:
            name: Cluster name.
            namespace: K8s namespace. Falls back to SDKConfig.namespace or 'default'.
            **kwargs: Forwarded to ClusterConfiguration.

        Returns:
            Cluster instance ready for .apply().
        """
        ns = namespace or self._sdk.config.namespace or "default"
        cluster_config = ClusterConfiguration(name=name, namespace=ns, **kwargs)
        return Cluster(cluster_config)

    def get(self, name: str, namespace: Optional[str] = None, **kwargs) -> "Cluster":
        """Retrieve an existing cluster by name.

        Args:
            name: Cluster name.
            namespace: K8s namespace. Falls back to SDKConfig.namespace or 'default'.
            **kwargs: Forwarded to get_cluster.

        Returns:
            Cluster instance.
        """
        ns = namespace or self._sdk.config.namespace or "default"
        return get_cluster(cluster_name=name, namespace=ns, **kwargs)

    def list(self, namespace: Optional[str] = None) -> list:
        """List all Ray clusters in a namespace.

        Args:
            namespace: K8s namespace. Falls back to SDKConfig.namespace or 'default'.

        Returns:
            List of RayCluster objects.
        """
        ns = namespace or self._sdk.config.namespace or "default"
        return list_all_clusters(ns, print_to_console=False)

    def list_queued(self, namespace: Optional[str] = None) -> list:
        """List all queued Ray clusters in a namespace.

        Args:
            namespace: K8s namespace. Falls back to SDKConfig.namespace or 'default'.

        Returns:
            List of queued RayCluster objects.
        """
        ns = namespace or self._sdk.config.namespace or "default"
        return list_all_queued(ns, print_to_console=False)


class JobHandler:
    """Namespace accessor for RayJob operations."""

    def __init__(self, sdk: "Codeflare"):
        self._sdk = sdk

    def submit(
        self,
        name: str,
        entrypoint: str,
        namespace: Optional[str] = None,
        **kwargs,
    ) -> "RayJob":
        """Create and immediately submit a RayJob.

        Args:
            name: Job name.
            entrypoint: Python script or command to run.
            namespace: K8s namespace. Falls back to SDKConfig.namespace or 'default'.
            **kwargs: Forwarded to RayJob constructor (cluster_name, cluster_config, etc.).

        Returns:
            Submitted RayJob instance.
        """
        ns = namespace or self._sdk.config.namespace or "default"
        job = RayJob(job_name=name, entrypoint=entrypoint, namespace=ns, **kwargs)
        job.submit()
        return job

    def create(
        self,
        name: str,
        entrypoint: str,
        namespace: Optional[str] = None,
        **kwargs,
    ) -> "RayJob":
        """Create a RayJob without submitting it.

        Args:
            name: Job name.
            entrypoint: Python script or command to run.
            namespace: K8s namespace. Falls back to SDKConfig.namespace or 'default'.
            **kwargs: Forwarded to RayJob constructor (cluster_name, cluster_config, etc.).

        Returns:
            RayJob instance (not yet submitted).
        """
        ns = namespace or self._sdk.config.namespace or "default"
        return RayJob(job_name=name, entrypoint=entrypoint, namespace=ns, **kwargs)


class Codeflare:
    """Single entrypoint for the CodeFlare SDK.

    Authenticates to Kubernetes via kube-authkit and provides
    namespace-accessor handlers for clusters and jobs.

    Args:
        config: SDK configuration. Defaults to auto-detection.
    """

    def __init__(self, config: Optional[SDKConfig] = None):
        self.config = config or SDKConfig()

        logging.getLogger("codeflare_sdk").setLevel(self.config.log_level)

        self._client = get_k8s_client(config=self.config.auth)
        set_api_client(self._client)

        self.clusters = ClusterHandler(self)
        self.jobs = JobHandler(self)

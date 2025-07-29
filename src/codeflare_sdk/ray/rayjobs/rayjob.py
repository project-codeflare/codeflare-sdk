# Copyright 2025 IBM, Red Hat
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
RayJob client for submitting and managing Ray jobs using the odh-kuberay-client.
"""

import logging
from typing import Dict, Any, Optional, Tuple
from odh_kuberay_client.kuberay_job_api import RayjobApi

from ..cluster.cluster import Cluster
from ..cluster.config import ClusterConfiguration
from ..cluster.build_ray_cluster import build_ray_cluster

from .status import (
    RayJobDeploymentStatus,
    CodeflareRayJobStatus,
    RayJobInfo,
)
from . import pretty_print


logger = logging.getLogger(__name__)


class RayJob:
    """
    A client for managing Ray jobs using the KubeRay operator.

    This class provides a simplified interface for submitting and managing
    RayJob CRs (using the KubeRay RayJob python client).
    """

    def __init__(
        self,
        job_name: str,
        cluster_name: Optional[str] = None,
        cluster_config: Optional[ClusterConfiguration] = None,
        namespace: str = "default",
        entrypoint: Optional[str] = None,
        runtime_env: Optional[Dict[str, Any]] = None,
        shutdown_after_job_finishes: bool = True,
        ttl_seconds_after_finished: int = 0,
        active_deadline_seconds: Optional[int] = None,
    ):
        """
        Initialize a RayJob instance.

        Args:
            job_name: The name for the Ray job
            cluster_name: The name of an existing Ray cluster (optional if cluster_config provided)
            cluster_config: Configuration for creating a new cluster (optional if cluster_name provided)
            namespace: The Kubernetes namespace (default: "default")
            entrypoint: The Python script or command to run (required for submission)
            runtime_env: Ray runtime environment configuration (optional)
            shutdown_after_job_finishes: Whether to automatically cleanup the cluster after job completion (default: True)
            ttl_seconds_after_finished: Seconds to wait before cleanup after job finishes (default: 0)
            active_deadline_seconds: Maximum time the job can run before being terminated (optional)
        """
        # Validate input parameters
        if cluster_name is None and cluster_config is None:
            raise ValueError("Either cluster_name or cluster_config must be provided")

        if cluster_name is not None and cluster_config is not None:
            raise ValueError("Cannot specify both cluster_name and cluster_config")

        self.name = job_name
        self.namespace = namespace
        self.entrypoint = entrypoint
        self.runtime_env = runtime_env
        self.shutdown_after_job_finishes = shutdown_after_job_finishes
        self.ttl_seconds_after_finished = ttl_seconds_after_finished
        self.active_deadline_seconds = active_deadline_seconds

        # Cluster configuration
        self._cluster_name = cluster_name
        self._cluster_config = cluster_config

        # Determine cluster name for the job
        if cluster_config is not None:
            # Ensure cluster config has the same namespace as the job
            if cluster_config.namespace is None:
                cluster_config.namespace = namespace
            elif cluster_config.namespace != namespace:
                logger.warning(
                    f"Cluster config namespace ({cluster_config.namespace}) differs from job namespace ({namespace})"
                )

            self.cluster_name = cluster_config.name or f"{job_name}-cluster"
            # Update the cluster config name if it wasn't set
            if not cluster_config.name:
                cluster_config.name = self.cluster_name
        else:
            self.cluster_name = cluster_name

        # Initialize the KubeRay job API client
        self._api = RayjobApi()

        logger.info(f"Initialized RayJob: {self.name} in namespace: {self.namespace}")

    def submit(self) -> str:
        """
        Submit the Ray job to the Kubernetes cluster.

        The RayJob CRD will automatically:
        - Create a new cluster if cluster_config was provided
        - Use existing cluster if cluster_name was provided
        - Clean up resources based on shutdown_after_job_finishes setting

        Returns:
            The job ID/name if submission was successful

        Raises:
            ValueError: If entrypoint is not provided
            RuntimeError: If job submission fails
        """
        # Validate required parameters
        if not self.entrypoint:
            raise ValueError("entrypoint must be provided to submit a RayJob")

        # Build the RayJob custom resource
        rayjob_cr = self._build_rayjob_cr()

        # Submit the job - KubeRay operator handles everything else
        logger.info(f"Submitting RayJob {self.name} to KubeRay operator")
        result = self._api.submit_job(k8s_namespace=self.namespace, job=rayjob_cr)

        if result:
            logger.info(f"Successfully submitted RayJob {self.name}")
            if self.shutdown_after_job_finishes:
                logger.info(
                    f"Cluster will be automatically cleaned up {self.ttl_seconds_after_finished}s after job completion"
                )
            return self.name
        else:
            raise RuntimeError(f"Failed to submit RayJob {self.name}")

    def _build_rayjob_cr(self) -> Dict[str, Any]:
        """
        Build the RayJob custom resource specification using native RayJob capabilities.
        """
        # Basic RayJob custom resource structure
        rayjob_cr = {
            "apiVersion": "ray.io/v1",
            "kind": "RayJob",
            "metadata": {
                "name": self.name,
                "namespace": self.namespace,
            },
            "spec": {
                "entrypoint": self.entrypoint,
                "shutdownAfterJobFinishes": self.shutdown_after_job_finishes,
                "ttlSecondsAfterFinished": self.ttl_seconds_after_finished,
            },
        }

        # Add active deadline if specified
        if self.active_deadline_seconds:
            rayjob_cr["spec"]["activeDeadlineSeconds"] = self.active_deadline_seconds

        # Add runtime environment if specified
        if self.runtime_env:
            rayjob_cr["spec"]["runtimeEnvYAML"] = str(self.runtime_env)

        # Configure cluster: either use existing or create new
        if self._cluster_config is not None:
            # Use rayClusterSpec to create a new cluster - leverage existing build logic
            ray_cluster_spec = self._build_ray_cluster_spec()
            rayjob_cr["spec"]["rayClusterSpec"] = ray_cluster_spec
            logger.info(f"RayJob will create new cluster: {self.cluster_name}")
        else:
            # Use clusterSelector to reference existing cluster
            rayjob_cr["spec"]["clusterSelector"] = {"ray.io/cluster": self.cluster_name}
            logger.info(f"RayJob will use existing cluster: {self.cluster_name}")

        return rayjob_cr

    def _build_ray_cluster_spec(self) -> Dict[str, Any]:
        """
        Build the RayCluster spec from ClusterConfiguration using existing build_ray_cluster logic.

        Returns:
            Dict containing the RayCluster spec for embedding in RayJob
        """
        if not self._cluster_config:
            raise RuntimeError("No cluster configuration provided")

        # Create a shallow copy of the cluster config to avoid modifying the original
        import copy

        temp_config = copy.copy(self._cluster_config)

        # Ensure we get a RayCluster (not AppWrapper) and don't write to file
        temp_config.appwrapper = False
        temp_config.write_to_file = False

        # Create a minimal Cluster object for the build process
        from ..cluster.cluster import Cluster

        temp_cluster = Cluster.__new__(Cluster)  # Create without calling __init__
        temp_cluster.config = temp_config

        """
        For now, RayJob with a new/auto-created cluster will not work with Kueue.
        This is due to the Kueue label not being propagated to the RayCluster.
        """

        # Use the existing build_ray_cluster function to generate the RayCluster
        ray_cluster_dict = build_ray_cluster(temp_cluster)

        # Extract just the RayCluster spec - RayJob CRD doesn't support metadata in rayClusterSpec
        # Note: CodeFlare Operator should still create dashboard routes for the RayCluster
        ray_cluster_spec = ray_cluster_dict["spec"]

        logger.info(
            f"Built RayCluster spec using existing build logic for cluster: {self.cluster_name}"
        )
        return ray_cluster_spec

    def status(
        self, print_to_console: bool = True
    ) -> Tuple[CodeflareRayJobStatus, bool]:
        """
        Get the status of the Ray job.

        Args:
            print_to_console (bool): Whether to print formatted status to console (default: True)

        Returns:
            Tuple of (CodeflareRayJobStatus, ready: bool) where ready indicates job completion
        """
        status_data = self._api.get_job_status(
            name=self.name, k8s_namespace=self.namespace
        )

        if not status_data:
            if print_to_console:
                pretty_print.print_no_job_found(self.name, self.namespace)
            return CodeflareRayJobStatus.UNKNOWN, False

        # Map deployment status to our enums
        deployment_status_str = status_data.get("jobDeploymentStatus", "Unknown")

        try:
            deployment_status = RayJobDeploymentStatus(deployment_status_str)
        except ValueError:
            deployment_status = RayJobDeploymentStatus.UNKNOWN

        # Create RayJobInfo dataclass
        job_info = RayJobInfo(
            name=self.name,
            job_id=status_data.get("jobId", ""),
            status=deployment_status,
            namespace=self.namespace,
            cluster_name=self.cluster_name,
            start_time=status_data.get("startTime"),
            end_time=status_data.get("endTime"),
            failed_attempts=status_data.get("failed", 0),
            succeeded_attempts=status_data.get("succeeded", 0),
        )

        # Map to CodeFlare status and determine readiness
        codeflare_status, ready = self._map_to_codeflare_status(deployment_status)

        if print_to_console:
            pretty_print.print_job_status(job_info)

        return codeflare_status, ready

    def _map_to_codeflare_status(
        self, deployment_status: RayJobDeploymentStatus
    ) -> Tuple[CodeflareRayJobStatus, bool]:
        """
        Map deployment status to CodeFlare status and determine readiness.

        Returns:
            Tuple of (CodeflareRayJobStatus, ready: bool)
        """
        status_mapping = {
            RayJobDeploymentStatus.COMPLETE: (CodeflareRayJobStatus.COMPLETE, True),
            RayJobDeploymentStatus.RUNNING: (CodeflareRayJobStatus.RUNNING, False),
            RayJobDeploymentStatus.FAILED: (CodeflareRayJobStatus.FAILED, False),
            RayJobDeploymentStatus.SUSPENDED: (CodeflareRayJobStatus.SUSPENDED, False),
        }

        return status_mapping.get(
            deployment_status, (CodeflareRayJobStatus.UNKNOWN, False)
        )

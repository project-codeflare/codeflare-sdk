# Copyright 2022-2025 IBM, Red Hat
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
RayJob client for submitting and managing Ray jobs using the kuberay python client.
"""

import logging
import warnings
from typing import Dict, Any, Optional, Tuple
from python_client.kuberay_job_api import RayjobApi

from codeflare_sdk.ray.rayjobs.config import ManagedClusterConfig

from ...common.utils import get_current_namespace
from ...common.utils.validation import validate_ray_version_compatibility

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
        entrypoint: str,
        cluster_name: Optional[str] = None,
        cluster_config: Optional[ManagedClusterConfig] = None,
        namespace: Optional[str] = None,
        runtime_env: Optional[Dict[str, Any]] = None,
        shutdown_after_job_finishes: Optional[bool] = None,
        ttl_seconds_after_finished: int = 0,
        active_deadline_seconds: Optional[int] = None,
    ):
        """
        Initialize a RayJob instance.

        Args:
            job_name: The name for the Ray job
            entrypoint: The Python script or command to run (required)
            cluster_name: The name of an existing Ray cluster (optional if cluster_config provided)
            cluster_config: Configuration for creating a new cluster (optional if cluster_name provided)
            namespace: The Kubernetes namespace (auto-detected if not specified)
            runtime_env: Ray runtime environment configuration (optional)
            shutdown_after_job_finishes: Whether to shut down cluster after job finishes (optional)
            ttl_seconds_after_finished: Seconds to wait before cleanup after job finishes (default: 0)
            active_deadline_seconds: Maximum time the job can run before being terminated (optional)

        Note:
            shutdown_after_job_finishes is automatically detected but can be overridden:
            - True if cluster_config is provided (new cluster will be cleaned up)
            - False if cluster_name is provided (existing cluster will not be shut down)
            - User can explicitly set this value to override auto-detection
        """
        if cluster_name is None and cluster_config is None:
            raise ValueError(
                "❌ Configuration Error: You must provide either 'cluster_name' (for existing cluster) "
                "or 'cluster_config' (to create new cluster), but not both."
            )

        if cluster_name is not None and cluster_config is not None:
            raise ValueError(
                "❌ Configuration Error: You cannot specify both 'cluster_name' and 'cluster_config'. "
                "Choose one approach:\n"
                "• Use 'cluster_name' to connect to an existing cluster\n"
                "• Use 'cluster_config' to create a new cluster"
            )

        if cluster_config is None and cluster_name is None:
            raise ValueError(
                "❌ Configuration Error: When not providing 'cluster_config', 'cluster_name' is required "
                "to specify which existing cluster to use."
            )

        self.name = job_name
        self.entrypoint = entrypoint
        self.runtime_env = runtime_env
        self.ttl_seconds_after_finished = ttl_seconds_after_finished
        self.active_deadline_seconds = active_deadline_seconds

        # Auto-set shutdown_after_job_finishes based on cluster_config presence
        # If cluster_config is provided, we want to clean up the cluster after job finishes
        # If using existing cluster, we don't want to shut it down
        # User can override this behavior by explicitly setting shutdown_after_job_finishes
        if shutdown_after_job_finishes is not None:
            self.shutdown_after_job_finishes = shutdown_after_job_finishes
        elif cluster_config is not None:
            self.shutdown_after_job_finishes = True
        else:
            self.shutdown_after_job_finishes = False

        if namespace is None:
            detected_namespace = get_current_namespace()
            if detected_namespace:
                self.namespace = detected_namespace
                logger.info(f"Auto-detected namespace: {self.namespace}")
            else:
                raise ValueError(
                    "❌ Configuration Error: Could not auto-detect Kubernetes namespace. "
                    "Please explicitly specify the 'namespace' parameter. "
                )
        else:
            self.namespace = namespace

        self._cluster_name = cluster_name
        self._cluster_config = cluster_config

        if cluster_config is not None:
            self.cluster_name = f"{job_name}-cluster"
            logger.info(f"Creating new cluster: {self.cluster_name}")
        else:
            # Using existing cluster: cluster_name must be provided
            if cluster_name is None:
                raise ValueError(
                    "❌ Configuration Error: a 'cluster_name' is required when not providing 'cluster_config'"
                )
            self.cluster_name = cluster_name
            logger.info(f"Using existing cluster: {self.cluster_name}")

        self._api = RayjobApi()

        logger.info(f"Initialized RayJob: {self.name} in namespace: {self.namespace}")

    def submit(self) -> str:
        # Validate required parameters
        if not self.entrypoint:
            raise ValueError("entrypoint must be provided to submit a RayJob")

        # Validate Ray version compatibility for both cluster_config and runtime_env
        self._validate_ray_version_compatibility()

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
            ray_cluster_spec = self._cluster_config.build_ray_cluster_spec(
                cluster_name=self.cluster_name
            )

            logger.info(
                f"Built RayCluster spec using RayJob-specific builder for cluster: {self.cluster_name}"
            )

            rayjob_cr["spec"]["rayClusterSpec"] = ray_cluster_spec

            logger.info(f"RayJob will create new cluster: {self.cluster_name}")
        else:
            # Use clusterSelector to reference existing cluster
            rayjob_cr["spec"]["clusterSelector"] = {"ray.io/cluster": self.cluster_name}
            logger.info(f"RayJob will use existing cluster: {self.cluster_name}")

        return rayjob_cr

    def _validate_ray_version_compatibility(self):
        """
        Validate Ray version compatibility for cluster_config image.
        Raises ValueError if there is a version mismatch.
        """
        # Validate cluster_config image if creating new cluster
        if self._cluster_config is not None:
            self._validate_cluster_config_image()

    def _validate_cluster_config_image(self):
        """
        Validate that the Ray version in cluster_config image matches the SDK's Ray version.
        """
        if not hasattr(self._cluster_config, "image"):
            logger.debug(
                "No image attribute found in cluster config, skipping validation"
            )
            return

        image = self._cluster_config.image
        if not image:
            logger.debug("Cluster config image is empty, skipping validation")
            return

        if not isinstance(image, str):
            logger.warning(
                f"Cluster config image should be a string, got {type(image).__name__}: {image}"
            )
            return  # Skip validation for malformed image

        is_compatible, is_warning, message = validate_ray_version_compatibility(image)
        if not is_compatible:
            raise ValueError(f"Cluster config image: {message}")
        elif is_warning:
            warnings.warn(f"Cluster config image: {message}")

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

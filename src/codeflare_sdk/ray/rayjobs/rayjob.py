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

from .status import (
    RayJobDeploymentStatus,
    CodeflareRayJobStatus,
    RayJobInfo,
)
from . import pretty_print

# Set up logging
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
        cluster_name: str,
        namespace: str = "default",
        entrypoint: str = "None",
        runtime_env: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize a RayJob instance.

        Args:
            name: The name for the Ray job
            namespace: The Kubernetes namespace to submit the job to (default: "default")
            cluster_name: The name of the Ray cluster to submit the job to
            **kwargs: Additional configuration options
        """
        self.name = job_name
        self.namespace = namespace
        self.cluster_name = cluster_name
        self.entrypoint = entrypoint
        self.runtime_env = runtime_env

        # Initialize the KubeRay job API client
        self._api = RayjobApi()

        logger.info(f"Initialized RayJob: {self.name} in namespace: {self.namespace}")

    def submit(
        self,
    ) -> str:
        """
        Submit the Ray job to the Kubernetes cluster.

        Args:
            entrypoint: The Python script or command to run
            runtime_env: Ray runtime environment configuration (optional)

        Returns:
            The job ID/name if submission was successful

        Raises:
            RuntimeError: If the job has already been submitted or submission fails
        """
        # Build the RayJob custom resource
        rayjob_cr = self._build_rayjob_cr(
            entrypoint=self.entrypoint,
            runtime_env=self.runtime_env,
        )

        # Submit the job
        logger.info(
            f"Submitting RayJob {self.name} to RayCluster {self.cluster_name} in namespace {self.namespace}"
        )
        result = self._api.submit_job(k8s_namespace=self.namespace, job=rayjob_cr)

        if result:
            logger.info(f"Successfully submitted RayJob {self.name}")
            return self.name
        else:
            raise RuntimeError(f"Failed to submit RayJob {self.name}")

    def _build_rayjob_cr(
        self,
        entrypoint: str,
        runtime_env: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Build the RayJob custom resource specification.

        This creates a minimal RayJob CR that can be extended later.
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
                "entrypoint": entrypoint,
                "clusterSelector": {"ray.io/cluster": self.cluster_name},
            },
        }

        # Add runtime environment if specified
        if runtime_env:
            rayjob_cr["spec"]["runtimeEnvYAML"] = str(runtime_env)

        return rayjob_cr

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

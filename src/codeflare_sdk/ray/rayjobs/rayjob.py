"""
RayJob client for submitting and managing Ray jobs using the odh-kuberay-client.
"""

import logging
from typing import Dict, Any, Optional
from odh_kuberay_client.kuberay_job_api import RayjobApi

# Set up logging
logger = logging.getLogger(__name__)


class RayJob:
    """
    A client for managing Ray jobs using the KubeRay operator.

    This class provides a simplified interface for submitting and managing
    Ray jobs in a Kubernetes cluster with the KubeRay operator installed.
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

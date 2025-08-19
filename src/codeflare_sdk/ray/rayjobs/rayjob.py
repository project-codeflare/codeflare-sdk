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
RayJob client for submitting and managing Ray jobs using the kuberay python client.
"""

import logging
import os
import re
import ast
from typing import Dict, Any, Optional, Tuple
from kubernetes import client
from ...common.kubernetes_cluster.auth import get_api_client
from python_client.kuberay_job_api import RayjobApi

from codeflare_sdk.ray.rayjobs.config import ManagedClusterConfig

from ...common.utils import get_current_namespace

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

        # Automatically handle script files for new clusters
        if self._cluster_config is not None:
            scripts = self._extract_script_files_from_entrypoint()
            if scripts:
                self._handle_script_volumes_for_new_cluster(scripts)

        # Handle script files for existing clusters
        elif self._cluster_name:
            scripts = self._extract_script_files_from_entrypoint()
            if scripts:
                self._handle_script_volumes_for_existing_cluster(scripts)

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

    def _extract_script_files_from_entrypoint(self) -> Optional[Dict[str, str]]:
        """
        Extract local Python script files from entrypoint command, plus their dependencies.

        Returns:
            Dict of {script_name: script_content} if local scripts found, None otherwise
        """
        if not self.entrypoint:
            return None

        scripts = {}
        mount_path = "/home/ray/scripts"
        processed_files = set()  # Avoid infinite loops

        # Look for Python file patterns in entrypoint (e.g., "python script.py", "python /path/to/script.py")
        python_file_pattern = r"(?:python\s+)?([./\w/]+\.py)"
        matches = re.findall(python_file_pattern, self.entrypoint)

        # Process main scripts from entrypoint files
        for script_path in matches:
            self._process_script_and_imports(
                script_path, scripts, mount_path, processed_files
            )

        # Update entrypoint paths to use mounted locations
        for script_path in matches:
            if script_path in [os.path.basename(s) for s in processed_files]:
                old_path = script_path
                new_path = f"{mount_path}/{os.path.basename(script_path)}"
                self.entrypoint = self.entrypoint.replace(old_path, new_path)

        return scripts if scripts else None

    def _process_script_and_imports(
        self,
        script_path: str,
        scripts: Dict[str, str],
        mount_path: str,
        processed_files: set,
    ):
        """Recursively process a script and its local imports"""
        if script_path in processed_files:
            return

        # Check if it's a local file (not already a container path)
        if script_path.startswith("/home/ray/") or not os.path.isfile(script_path):
            return

        processed_files.add(script_path)

        try:
            with open(script_path, "r") as f:
                script_content = f.read()

            script_name = os.path.basename(script_path)
            scripts[script_name] = script_content

            logger.info(
                f"Found local script: {script_path} -> will mount at {mount_path}/{script_name}"
            )

            # Parse imports in this script to find dependencies
            self._find_local_imports(
                script_content,
                script_path,
                lambda path: self._process_script_and_imports(
                    path, scripts, mount_path, processed_files
                ),
            )

        except (IOError, OSError) as e:
            logger.warning(f"Could not read script file {script_path}: {e}")

    def _find_local_imports(
        self, script_content: str, script_path: str, process_callback
    ):
        """
        Find local Python imports in script content and process them.

        Args:
            script_content: The content of the Python script
            script_path: Path to the current script (for relative imports)
            process_callback: Function to call for each found local import
        """

        try:
            # Parse the Python AST to find imports
            tree = ast.parse(script_content)
            script_dir = os.path.dirname(os.path.abspath(script_path))

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    # Handle: import module_name
                    for alias in node.names:
                        potential_file = os.path.join(script_dir, f"{alias.name}.py")
                        if os.path.isfile(potential_file):
                            process_callback(potential_file)

                elif isinstance(node, ast.ImportFrom):
                    # Handle: from module_name import something
                    if node.module:
                        potential_file = os.path.join(script_dir, f"{node.module}.py")
                        if os.path.isfile(potential_file):
                            process_callback(potential_file)

        except (SyntaxError, ValueError) as e:
            logger.debug(f"Could not parse imports from {script_path}: {e}")

    def _handle_script_volumes_for_new_cluster(self, scripts: Dict[str, str]):
        """Handle script volumes for new clusters (uses ManagedClusterConfig)."""
        # Build ConfigMap spec using config.py
        configmap_spec = self._cluster_config.build_script_configmap_spec(
            job_name=self.name, namespace=self.namespace, scripts=scripts
        )

        # Create ConfigMap via Kubernetes API
        configmap_name = self._create_configmap_from_spec(configmap_spec)

        # Add volumes to cluster config (config.py handles spec building)
        self._cluster_config.add_script_volumes(
            configmap_name=configmap_name, mount_path="/home/ray/scripts"
        )

    def _handle_script_volumes_for_existing_cluster(self, scripts: Dict[str, str]):
        """Handle script volumes for existing clusters (updates RayCluster CR)."""
        # Create config builder for utility methods
        config_builder = ManagedClusterConfig()

        # Build ConfigMap spec using config.py
        configmap_spec = config_builder.build_script_configmap_spec(
            job_name=self.name, namespace=self.namespace, scripts=scripts
        )

        # Create ConfigMap via Kubernetes API
        configmap_name = self._create_configmap_from_spec(configmap_spec)

        # Update existing RayCluster
        self._update_existing_cluster_for_scripts(configmap_name, config_builder)

    def _create_configmap_from_spec(self, configmap_spec: Dict[str, Any]) -> str:
        """
        Create ConfigMap from specification via Kubernetes API.

        Args:
            configmap_spec: ConfigMap specification dictionary

        Returns:
            str: Name of the created ConfigMap
        """

        configmap_name = configmap_spec["metadata"]["name"]

        # Convert dict spec to V1ConfigMap
        configmap = client.V1ConfigMap(
            metadata=client.V1ObjectMeta(**configmap_spec["metadata"]),
            data=configmap_spec["data"],
        )

        # Create ConfigMap via Kubernetes API
        k8s_api = client.CoreV1Api(get_api_client())
        try:
            k8s_api.create_namespaced_config_map(
                namespace=self.namespace, body=configmap
            )
            logger.info(
                f"Created ConfigMap '{configmap_name}' with {len(configmap_spec['data'])} scripts"
            )
        except client.ApiException as e:
            if e.status == 409:  # Already exists
                logger.info(f"ConfigMap '{configmap_name}' already exists, updating...")
                k8s_api.replace_namespaced_config_map(
                    name=configmap_name, namespace=self.namespace, body=configmap
                )
            else:
                raise RuntimeError(
                    f"Failed to create ConfigMap '{configmap_name}': {e}"
                )

        return configmap_name

    # Note: This only works once the pods have been restarted as the configmaps won't be picked up until then :/
    def _update_existing_cluster_for_scripts(
        self, configmap_name: str, config_builder: ManagedClusterConfig
    ):
        """
        Update existing RayCluster to add script volumes and mounts.

        Args:
            configmap_name: Name of the ConfigMap containing scripts
            config_builder: ManagedClusterConfig instance for building specs
        """

        # Get existing RayCluster
        api_instance = client.CustomObjectsApi(get_api_client())
        try:
            ray_cluster = api_instance.get_namespaced_custom_object(
                group="ray.io",
                version="v1",
                namespace=self.namespace,
                plural="rayclusters",
                name=self.cluster_name,
            )
        except client.ApiException as e:
            raise RuntimeError(f"Failed to get RayCluster '{self.cluster_name}': {e}")

        # Build script volume and mount specifications using config.py
        script_volume, script_mount = config_builder.build_script_volume_specs(
            configmap_name=configmap_name, mount_path="/home/ray/scripts"
        )

        # Helper function to check for duplicate volumes/mounts
        def volume_exists(volumes_list, volume_name):
            return any(v.get("name") == volume_name for v in volumes_list)

        def mount_exists(mounts_list, mount_name):
            return any(m.get("name") == mount_name for m in mounts_list)

        # Add volumes and mounts to head group
        head_spec = ray_cluster["spec"]["headGroupSpec"]["template"]["spec"]
        if "volumes" not in head_spec:
            head_spec["volumes"] = []
        if not volume_exists(head_spec["volumes"], script_volume["name"]):
            head_spec["volumes"].append(script_volume)

        head_container = head_spec["containers"][0]  # Ray head container
        if "volumeMounts" not in head_container:
            head_container["volumeMounts"] = []
        if not mount_exists(head_container["volumeMounts"], script_mount["name"]):
            head_container["volumeMounts"].append(script_mount)

        # Add volumes and mounts to worker groups
        for worker_group in ray_cluster["spec"]["workerGroupSpecs"]:
            worker_spec = worker_group["template"]["spec"]
            if "volumes" not in worker_spec:
                worker_spec["volumes"] = []
            if not volume_exists(worker_spec["volumes"], script_volume["name"]):
                worker_spec["volumes"].append(script_volume)

            worker_container = worker_spec["containers"][0]  # Ray worker container
            if "volumeMounts" not in worker_container:
                worker_container["volumeMounts"] = []
            if not mount_exists(worker_container["volumeMounts"], script_mount["name"]):
                worker_container["volumeMounts"].append(script_mount)

        # Update the RayCluster
        try:
            api_instance.patch_namespaced_custom_object(
                group="ray.io",
                version="v1",
                namespace=self.namespace,
                plural="rayclusters",
                name=self.cluster_name,
                body=ray_cluster,
            )
            logger.info(
                f"Updated RayCluster '{self.cluster_name}' with script volumes from ConfigMap '{configmap_name}'"
            )
        except client.ApiException as e:
            raise RuntimeError(
                f"Failed to update RayCluster '{self.cluster_name}': {e}"
            )

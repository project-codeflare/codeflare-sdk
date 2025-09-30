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
import os
import re
import ast
import yaml
from typing import Dict, Any, Optional, Tuple, List
from codeflare_sdk.common.kueue.kueue import get_default_kueue_name
from codeflare_sdk.common.utils.constants import MOUNT_PATH
from kubernetes import client

from codeflare_sdk.common.utils.utils import get_ray_image_for_python_version
from ...common.kubernetes_cluster.auth import get_api_client
from python_client.kuberay_job_api import RayjobApi
from python_client.kuberay_cluster_api import RayClusterApi
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

# Regex pattern for finding Python files in entrypoint commands
PYTHON_FILE_PATTERN = r"(?:python\s+)?([./\w/]+\.py)"


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
        ttl_seconds_after_finished: int = 0,
        active_deadline_seconds: Optional[int] = None,
        local_queue: Optional[str] = None,
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
            ttl_seconds_after_finished: Seconds to wait before cleanup after job finishes (default: 0)
            active_deadline_seconds: Maximum time the job can run before being terminated (optional)
            local_queue: The Kueue LocalQueue to submit the job to (optional)

        Note:
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
        self.local_queue = local_queue

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
        self._cluster_api = RayClusterApi()

        logger.info(f"Initialized RayJob: {self.name} in namespace: {self.namespace}")

    def submit(self) -> str:
        if not self.entrypoint:
            raise ValueError("Entrypoint must be provided to submit a RayJob")

        self._validate_ray_version_compatibility()

        # Extract files from entrypoint and runtime_env working_dir
        files = self._extract_all_local_files()

        # Create ConfigMap for files (will be mounted to submitter pod)
        configmap_name = None
        if files:
            configmap_name = f"{self.name}-files"

        rayjob_cr = self._build_rayjob_cr()

        logger.info(f"Submitting RayJob {self.name} to Kuberay operator")
        result = self._api.submit_job(k8s_namespace=self.namespace, job=rayjob_cr)

        if result:
            logger.info(f"Successfully submitted RayJob {self.name}")

            # Create ConfigMap with owner reference after RayJob exists
            if files:
                self._create_file_configmap(files, result)

            return self.name
        else:
            raise RuntimeError(f"Failed to submit RayJob {self.name}")

    def _create_file_configmap(
        self, files: Dict[str, str], rayjob_result: Dict[str, Any]
    ):
        """
        Create ConfigMap with owner reference for local files.
        """
        # Use a basic config builder for ConfigMap creation
        config_builder = ManagedClusterConfig()

        # Validate and build ConfigMap spec
        config_builder.validate_configmap_size(files)
        configmap_spec = config_builder.build_file_configmap_spec(
            job_name=self.name, namespace=self.namespace, files=files
        )

        # Create ConfigMap with owner reference
        configmap_name = self._create_configmap_from_spec(configmap_spec, rayjob_result)

    def stop(self):
        """
        Suspend the Ray job.
        """
        stopped = self._api.suspend_job(name=self.name, k8s_namespace=self.namespace)
        if stopped:
            logger.info(f"Successfully stopped the RayJob {self.name}")
            return True
        else:
            raise RuntimeError(f"Failed to stop the RayJob {self.name}")

    def resubmit(self):
        """
        Resubmit the Ray job.
        """
        if self._api.resubmit_job(name=self.name, k8s_namespace=self.namespace):
            logger.info(f"Successfully resubmitted the RayJob {self.name}")
            return True
        else:
            raise RuntimeError(f"Failed to resubmit the RayJob {self.name}")

    def delete(self):
        """
        Delete the Ray job.
        Returns True if deleted successfully or if already deleted.
        """
        deleted = self._api.delete_job(name=self.name, k8s_namespace=self.namespace)
        if deleted:
            logger.info(f"Successfully deleted the RayJob {self.name}")
            return True
        else:
            # The python client logs "rayjob custom resource already deleted"
            # and returns False when the job doesn't exist.
            # This is not an error - treat it as successful deletion.
            logger.info(f"RayJob {self.name} already deleted or does not exist")
            return True

    def _build_rayjob_cr(self) -> Dict[str, Any]:
        """
        Build the RayJob custom resource specification using native RayJob capabilities.
        """
        rayjob_cr = {
            "apiVersion": "ray.io/v1",
            "kind": "RayJob",
            "metadata": {
                "name": self.name,
                "namespace": self.namespace,
            },
            "spec": {
                "entrypoint": self.entrypoint,
                "ttlSecondsAfterFinished": self.ttl_seconds_after_finished,
                "shutdownAfterJobFinishes": self._cluster_config is not None,
            },
        }

        labels = {}
        # If cluster_config is provided, use the local_queue from the cluster_config
        if self._cluster_config is not None:
            if self.local_queue:
                labels["kueue.x-k8s.io/queue-name"] = self.local_queue
            else:
                default_queue = get_default_kueue_name(self.namespace)
                if default_queue:
                    labels["kueue.x-k8s.io/queue-name"] = default_queue
                else:
                    # No default queue found, use "default" as fallback
                    labels["kueue.x-k8s.io/queue-name"] = "default"
                    logger.warning(
                        f"No default Kueue LocalQueue found in namespace '{self.namespace}'. "
                        f"Using 'default' as the queue name. If a LocalQueue named 'default' "
                        f"does not exist, the RayJob submission will fail. "
                        f"To fix this, please explicitly specify the 'local_queue' parameter."
                    )

        rayjob_cr["metadata"]["labels"] = labels

        # When using Kueue (queue label present), start with suspend=true
        # Kueue will unsuspend the job once the workload is admitted
        if labels.get("kueue.x-k8s.io/queue-name"):
            rayjob_cr["spec"]["suspend"] = True

        # Add active deadline if specified
        if self.active_deadline_seconds:
            rayjob_cr["spec"]["activeDeadlineSeconds"] = self.active_deadline_seconds

        # Extract files once and use for both runtime_env and submitter pod
        files = self._extract_all_local_files()

        # Add runtime environment (can be inferred even if not explicitly specified)
        processed_runtime_env = self._process_runtime_env(files)
        if processed_runtime_env:
            rayjob_cr["spec"]["runtimeEnvYAML"] = processed_runtime_env

        # Add submitterPodTemplate if we have files to mount
        if files:
            configmap_name = f"{self.name}-files"
            rayjob_cr["spec"][
                "submitterPodTemplate"
            ] = self._build_submitter_pod_template(files, configmap_name)

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

    def _build_submitter_pod_template(
        self, files: Dict[str, str], configmap_name: str
    ) -> Dict[str, Any]:
        """
        Build submitterPodTemplate with ConfigMap volume mount for local files.

        Args:
            files: Dict of file_name -> file_content
            configmap_name: Name of the ConfigMap containing the files

        Returns:
            submitterPodTemplate specification
        """
        # Image has to be hard coded for the job submitter
        image = get_ray_image_for_python_version()
        if (
            self._cluster_config
            and hasattr(self._cluster_config, "image")
            and self._cluster_config.image
        ):
            image = self._cluster_config.image

        # Build ConfigMap items for each file
        config_map_items = []
        for file_name in files.keys():
            config_map_items.append({"key": file_name, "path": file_name})

        submitter_pod_template = {
            "spec": {
                "restartPolicy": "Never",
                "containers": [
                    {
                        "name": "ray-job-submitter",
                        "image": image,
                        "volumeMounts": [
                            {"name": "ray-job-files", "mountPath": MOUNT_PATH}
                        ],
                    }
                ],
                "volumes": [
                    {
                        "name": "ray-job-files",
                        "configMap": {
                            "name": configmap_name,
                            "items": config_map_items,
                        },
                    }
                ],
            }
        }

        logger.info(
            f"Built submitterPodTemplate with {len(files)} files mounted at {MOUNT_PATH}, using image: {image}"
        )
        return submitter_pod_template

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

    def _extract_files_from_entrypoint(self) -> Optional[Dict[str, str]]:
        """
        Extract local Python script files from entrypoint command, plus their dependencies.

        Returns:
            Dict of {file_name: file_content} if local files found, None otherwise
        """
        if not self.entrypoint:
            return None

        files = {}
        processed_files = set()  # Avoid infinite loops

        # Look for Python file patterns in entrypoint (e.g., "python script.py", "python /path/to/script.py")
        matches = re.findall(PYTHON_FILE_PATTERN, self.entrypoint)

        # Process main files from entrypoint
        for file_path in matches:
            self._process_file_and_imports(
                file_path, files, MOUNT_PATH, processed_files
            )

        return files if files else None

    def _process_file_and_imports(
        self,
        file_path: str,
        files: Dict[str, str],
        mount_path: str,
        processed_files: set,
    ):
        """
        Recursively process a file and its local imports
        """
        if file_path in processed_files:
            return

        # Check if it's a local file (not already a container path)
        if file_path.startswith("/home/ray/") or not os.path.isfile(file_path):
            return

        processed_files.add(file_path)

        try:
            with open(file_path, "r") as f:
                file_content = f.read()

            file_name = os.path.basename(file_path)
            files[file_name] = file_content

            logger.info(
                f"Found local file: {file_path} -> will mount at {mount_path}/{file_name}"
            )

            # Parse imports in this file to find dependencies
            self._find_local_imports(
                file_content,
                file_path,
                lambda path: self._process_file_and_imports(
                    path, files, mount_path, processed_files
                ),
            )

        except (IOError, OSError) as e:
            logger.warning(f"Could not read file {file_path}: {e}")

    def _find_local_imports(self, file_content: str, file_path: str, process_callback):
        """
        Find local Python imports in file content and process them.

        Args:
            file_content: The content of the Python file
            file_path: Path to the current file (for relative imports)
            process_callback: Function to call for each found local import
        """

        try:
            # Parse the Python AST to find imports
            tree = ast.parse(file_content)
            file_dir = os.path.dirname(os.path.abspath(file_path))

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    # Handle: import module_name
                    for alias in node.names:
                        potential_file = os.path.join(file_dir, f"{alias.name}.py")
                        if os.path.isfile(potential_file):
                            process_callback(potential_file)

                elif isinstance(node, ast.ImportFrom):
                    # Handle: from module_name import something
                    if node.module:
                        potential_file = os.path.join(file_dir, f"{node.module}.py")
                        if os.path.isfile(potential_file):
                            process_callback(potential_file)

        except (SyntaxError, ValueError) as e:
            logger.debug(f"Could not parse imports from {file_path}: {e}")

    def _extract_all_local_files(self) -> Optional[Dict[str, str]]:
        """
        Extract all local files from both entrypoint and runtime_env working_dir.

        Note: If runtime_env has a remote working_dir, we don't extract local files
        to avoid conflicts. The remote working_dir should contain all needed files.

        Returns:
            Dict of {file_name: file_content} if local files found, None otherwise
        """
        # If there's a remote working_dir, don't extract local files to avoid conflicts
        if (
            self.runtime_env
            and "working_dir" in self.runtime_env
            and not os.path.isdir(self.runtime_env["working_dir"])
        ):
            logger.info(
                f"Remote working_dir detected: {self.runtime_env['working_dir']}. "
                "Skipping local file extraction - all files should come from remote source."
            )
            return None

        files = {}
        processed_files = set()

        # Extract files from entrypoint (always check for local files in entrypoint)
        entrypoint_files = self._extract_files_from_entrypoint()
        if entrypoint_files:
            files.update(entrypoint_files)
            processed_files.update(entrypoint_files.keys())

        # Extract files from runtime_env working_dir if it's a local directory
        if (
            self.runtime_env
            and "working_dir" in self.runtime_env
            and os.path.isdir(self.runtime_env["working_dir"])
        ):
            working_dir_files = self._extract_working_dir_files(
                self.runtime_env["working_dir"], processed_files
            )
            if working_dir_files:
                files.update(working_dir_files)

        # If no working_dir specified in runtime_env, try to infer and extract files from inferred directory
        elif not self.runtime_env or "working_dir" not in self.runtime_env:
            inferred_working_dir = self._infer_working_dir_from_entrypoint()
            if inferred_working_dir:
                working_dir_files = self._extract_working_dir_files(
                    inferred_working_dir, processed_files
                )
                if working_dir_files:
                    files.update(working_dir_files)

        return files if files else None

    def _extract_working_dir_files(
        self, working_dir: str, processed_files: set
    ) -> Dict[str, str]:
        """
        Extract all Python files from working directory.

        Args:
            working_dir: Path to working directory
            processed_files: Set of already processed file names to avoid duplicates

        Returns:
            Dict of {file_name: file_content}
        """
        files_dict = {}

        try:
            for root, dirs, files in os.walk(working_dir):
                for file in files:
                    if file.endswith(".py") and file not in processed_files:
                        file_path = os.path.join(root, file)
                        try:
                            with open(file_path, "r") as f:
                                content = f.read()
                            files_dict[file] = content
                            processed_files.add(file)
                            logger.info(
                                f"Added working directory file: {file_path} -> {MOUNT_PATH}/{file}"
                            )
                        except (IOError, OSError) as e:
                            logger.warning(f"Could not read file {file_path}: {e}")
        except (IOError, OSError) as e:
            logger.warning(f"Could not scan working directory {working_dir}: {e}")

        return files_dict

    def _process_runtime_env(
        self, files: Optional[Dict[str, str]] = None
    ) -> Optional[str]:
        """
        Process runtime_env field to handle env_vars, pip dependencies, and working_dir.
        Can also infer working directory from entrypoint even if runtime_env is not provided.

        Returns:
            Processed runtime environment as YAML string, or None if no processing needed
        """
        processed_env = {}

        # Handle env_vars
        if self.runtime_env and "env_vars" in self.runtime_env:
            processed_env["env_vars"] = self.runtime_env["env_vars"]
            logger.info(
                f"Added {len(self.runtime_env['env_vars'])} environment variables to runtime_env"
            )

        # Handle pip dependencies
        if self.runtime_env and "pip" in self.runtime_env:
            pip_deps = self._process_pip_dependencies(self.runtime_env["pip"])
            if pip_deps:
                processed_env["pip"] = pip_deps

        # Handle working_dir - if it's a local path, set it to mount path
        if self.runtime_env and "working_dir" in self.runtime_env:
            working_dir = self.runtime_env["working_dir"]
            if os.path.isdir(working_dir):
                # Local working directory - will be mounted at MOUNT_PATH
                processed_env["working_dir"] = MOUNT_PATH
                logger.info(
                    f"Local working directory will be packaged and mounted at: {MOUNT_PATH}"
                )
                self._adjust_entrypoint_for_mounted_files()
            else:
                # Remote URI (e.g., GitHub) - pass through as-is
                processed_env["working_dir"] = working_dir
                logger.info(f"Using remote working directory: {working_dir}")

        # If no working_dir specified but we have files, set working_dir to mount path
        elif not self.runtime_env or "working_dir" not in self.runtime_env:
            if files:
                # Local files found - will be mounted at MOUNT_PATH
                processed_env["working_dir"] = MOUNT_PATH
                logger.info(
                    f"Local files will be packaged and mounted at: {MOUNT_PATH}"
                )
                self._adjust_entrypoint_for_mounted_files()

        # Convert to YAML string if we have any processed environment
        if processed_env:
            return yaml.dump(processed_env, default_flow_style=False)

        return None

    def _process_pip_dependencies(self, pip_spec) -> Optional[List[str]]:
        """
        Process pip dependencies from runtime_env.

        Args:
            pip_spec: Can be a list of packages, a string path to requirements.txt, or dict

        Returns:
            List of pip dependencies
        """
        if isinstance(pip_spec, list):
            # Already a list of dependencies
            logger.info(f"Using provided pip dependencies: {len(pip_spec)} packages")
            return pip_spec
        elif isinstance(pip_spec, str):
            # Assume it's a path to requirements.txt
            return self._parse_requirements_file(pip_spec)
        elif isinstance(pip_spec, dict):
            # Handle dict format (e.g., {"packages": [...], "pip_check": False})
            if "packages" in pip_spec:
                logger.info(
                    f"Using pip dependencies from dict: {len(pip_spec['packages'])} packages"
                )
                return pip_spec["packages"]

        logger.warning(f"Unsupported pip specification format: {type(pip_spec)}")
        return None

    def _parse_requirements_file(self, requirements_path: str) -> Optional[List[str]]:
        """
        Parse a requirements.txt file and return list of dependencies.

        Args:
            requirements_path: Path to requirements.txt file

        Returns:
            List of pip dependencies
        """
        if not os.path.isfile(requirements_path):
            logger.warning(f"Requirements file not found: {requirements_path}")
            return None

        try:
            with open(requirements_path, "r") as f:
                lines = f.readlines()

            # Parse requirements, filtering out comments and empty lines
            requirements = []
            for line in lines:
                line = line.strip()
                if line and not line.startswith("#"):
                    requirements.append(line)

            logger.info(
                f"Parsed {len(requirements)} dependencies from {requirements_path}"
            )
            return requirements

        except (IOError, OSError) as e:
            logger.warning(f"Could not read requirements file {requirements_path}: {e}")
            return None

    def _infer_working_dir_from_entrypoint(self) -> Optional[str]:
        """
        Infer working directory from entrypoint path when it contains directory components.
        Only useful for entrypoints with paths like 'python src/script.py'.

        Returns:
            Inferred working directory path, or None if just simple filenames
        """
        if not self.entrypoint:
            return None

        # Look for Python file patterns in entrypoint
        matches = re.findall(PYTHON_FILE_PATTERN, self.entrypoint)

        for script_path in matches:
            # Only infer working directory if the path has directory components
            if "/" in script_path or "\\" in script_path:
                if os.path.isfile(script_path):
                    working_dir = os.path.dirname(os.path.abspath(script_path))
                    logger.info(
                        f"Inferred working directory from entrypoint: {working_dir}"
                    )
                    return working_dir
                else:
                    # File doesn't exist locally, but path has directory components
                    working_dir = os.path.dirname(os.path.abspath(script_path))
                    logger.info(
                        f"Inferred working directory from entrypoint path: {working_dir}"
                    )
                    return working_dir

        # For simple filenames like "script.py" we don't need to infer the working directory
        return None

    def _adjust_entrypoint_for_mounted_files(self):
        """
        Adjust the entrypoint command to use just filenames since files are mounted at MOUNT_PATH.
        """
        if not self.entrypoint:
            return

        # Look for Python file patterns in entrypoint
        matches = re.findall(PYTHON_FILE_PATTERN, self.entrypoint)

        for script_path in matches:
            if os.path.isfile(script_path):
                # Use just the filename since files will be mounted at MOUNT_PATH
                filename = os.path.basename(script_path)
                self.entrypoint = self.entrypoint.replace(script_path, filename)
                logger.info(
                    f"Adjusted entrypoint for mounted files: {script_path} -> {filename}"
                )

    def _create_configmap_from_spec(
        self, configmap_spec: Dict[str, Any], rayjob_result: Dict[str, Any] = None
    ) -> str:
        """
        Create ConfigMap from specification via Kubernetes API.

        Args:
            configmap_spec: ConfigMap specification dictionary
            rayjob_result: The result from RayJob creation containing UID

        Returns:
            str: Name of the created ConfigMap
        """

        configmap_name = configmap_spec["metadata"]["name"]

        metadata = client.V1ObjectMeta(**configmap_spec["metadata"])

        # Add owner reference if we have the RayJob result
        if (
            rayjob_result
            and isinstance(rayjob_result, dict)
            and rayjob_result.get("metadata", {}).get("uid")
        ):
            logger.info(
                f"Adding owner reference to ConfigMap '{configmap_name}' with RayJob UID: {rayjob_result['metadata']['uid']}"
            )
            metadata.owner_references = [
                client.V1OwnerReference(
                    api_version="ray.io/v1",
                    kind="RayJob",
                    name=self.name,
                    uid=rayjob_result["metadata"]["uid"],
                    controller=True,
                    block_owner_deletion=True,
                )
            ]
        else:
            logger.warning(
                f"No valid RayJob result with UID found, ConfigMap '{configmap_name}' will not have owner reference. Result: {rayjob_result}"
            )

        # Convert dict spec to V1ConfigMap
        configmap = client.V1ConfigMap(
            metadata=metadata,
            data=configmap_spec["data"],
        )

        # Create ConfigMap via Kubernetes API
        k8s_api = client.CoreV1Api(get_api_client())
        try:
            k8s_api.create_namespaced_config_map(
                namespace=self.namespace, body=configmap
            )
            logger.info(
                f"Created ConfigMap '{configmap_name}' with {len(configmap_spec['data'])} files"
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

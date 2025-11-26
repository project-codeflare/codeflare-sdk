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
import os
import re
import warnings
from typing import Dict, Any, Optional, Tuple, Union

from ray.runtime_env import RuntimeEnv
from codeflare_sdk.common.kueue.kueue import get_default_kueue_name
from codeflare_sdk.common.utils.constants import MOUNT_PATH

from codeflare_sdk.common.utils.utils import get_ray_image_for_python_version
from codeflare_sdk.vendored.python_client.kuberay_job_api import RayjobApi
from codeflare_sdk.vendored.python_client.kuberay_cluster_api import RayClusterApi
from codeflare_sdk.ray.rayjobs.config import ManagedClusterConfig
from codeflare_sdk.ray.rayjobs.runtime_env import (
    create_file_secret,
    extract_all_local_files,
    process_runtime_env,
)

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
        runtime_env: Optional[Union[RuntimeEnv, Dict[str, Any]]] = None,
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
            runtime_env: Ray runtime environment configuration. Can be:
                - RuntimeEnv object from ray.runtime_env
                - Dict with keys like 'working_dir', 'pip', 'env_vars', etc.
                Example: {"working_dir": "./my-scripts", "pip": ["requests"]}
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

        # Convert dict to RuntimeEnv if needed for user convenience
        if isinstance(runtime_env, dict):
            self.runtime_env = RuntimeEnv(**runtime_env)
        else:
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

        # Validate configuration before submitting
        self._validate_ray_version_compatibility()
        self._validate_working_dir_entrypoint()

        # Extract files from entrypoint and runtime_env working_dir
        files = extract_all_local_files(self)

        rayjob_cr = self._build_rayjob_cr()

        logger.info(f"Submitting RayJob {self.name} to Kuberay operator")
        result = self._api.submit_job(k8s_namespace=self.namespace, job=rayjob_cr)

        if result:
            logger.info(f"Successfully submitted RayJob {self.name}")

            # Create Secret with owner reference after RayJob exists
            if files:
                create_file_secret(self, files, result)

            return self.name
        else:
            raise RuntimeError(f"Failed to submit RayJob {self.name}")

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

        # Extract files once and use for both runtime_env and submitter pod
        files = extract_all_local_files(self)

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

        # Add runtime environment (can be inferred even if not explicitly specified)
        processed_runtime_env = process_runtime_env(self, files)
        if processed_runtime_env:
            rayjob_cr["spec"]["runtimeEnvYAML"] = processed_runtime_env

        # Add submitterPodTemplate if we have files to mount
        if files:
            secret_name = f"{self.name}-files"
            rayjob_cr["spec"][
                "submitterPodTemplate"
            ] = self._build_submitter_pod_template(files, secret_name)

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
        self, files: Dict[str, str], secret_name: str
    ) -> Dict[str, Any]:
        """
        Build submitterPodTemplate with Secret volume mount for local files.

        If files contain working_dir.zip, an init container will unzip it before
        the main submitter container runs.

        Args:
            files: Dict of file_name -> file_content
            secret_name: Name of the Secret containing the files

        Returns:
            submitterPodTemplate specification
        """
        from codeflare_sdk.ray.rayjobs.runtime_env import UNZIP_PATH

        # Image has to be hard coded for the job submitter
        image = get_ray_image_for_python_version()
        if (
            self._cluster_config
            and hasattr(self._cluster_config, "image")
            and self._cluster_config.image
        ):
            image = self._cluster_config.image

        # Build Secret items for each file
        secret_items = []
        entrypoint_path = files.get(
            "__entrypoint_path__"
        )  # Metadata for single file case

        for file_name in files.keys():
            if file_name == "__entrypoint_path__":
                continue  # Skip metadata key

            # For single file case, use the preserved path structure
            if entrypoint_path:
                secret_items.append({"key": file_name, "path": entrypoint_path})
            else:
                secret_items.append({"key": file_name, "path": file_name})

        # Check if we need to unzip working_dir
        has_working_dir_zip = "working_dir.zip" in files

        # Base volume mounts for main container
        volume_mounts = [{"name": "ray-job-files", "mountPath": MOUNT_PATH}]

        # If we have a zip file, we need shared volume for unzipped content
        if has_working_dir_zip:
            volume_mounts.append(
                {"name": "unzipped-working-dir", "mountPath": UNZIP_PATH}
            )

        submitter_pod_template = {
            "spec": {
                "restartPolicy": "Never",
                "containers": [
                    {
                        "name": "ray-job-submitter",
                        "image": image,
                        "volumeMounts": volume_mounts,
                    }
                ],
                "volumes": [
                    {
                        "name": "ray-job-files",
                        "secret": {
                            "secretName": secret_name,
                            "items": secret_items,
                        },
                    }
                ],
            }
        }

        # Add init container and volume for unzipping if needed
        if has_working_dir_zip:
            # Add emptyDir volume for unzipped content
            submitter_pod_template["spec"]["volumes"].append(
                {"name": "unzipped-working-dir", "emptyDir": {}}
            )

            # Add init container to unzip before KubeRay's submitter runs
            submitter_pod_template["spec"]["initContainers"] = [
                {
                    "name": "unzip-working-dir",
                    "image": image,
                    "command": ["/bin/sh", "-c"],
                    "args": [
                        # Decode base64 zip, save to temp file, extract, cleanup
                        f"mkdir -p {UNZIP_PATH} && "
                        f"python3 -m base64 -d {MOUNT_PATH}/working_dir.zip > /tmp/working_dir.zip && "
                        f"python3 -m zipfile -e /tmp/working_dir.zip {UNZIP_PATH}/ && "
                        f"rm /tmp/working_dir.zip && "
                        f"echo 'Successfully unzipped working_dir to {UNZIP_PATH}' && "
                        f"ls -la {UNZIP_PATH}"
                    ],
                    "volumeMounts": volume_mounts,
                }
            ]
            logger.info(f"Added init container to unzip working_dir to {UNZIP_PATH}")

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

    def _validate_working_dir_entrypoint(self):
        """
        Validate entrypoint file configuration.

        Checks:
        1. Entrypoint doesn't redundantly reference working_dir
        2. Local files exist before submission

        Raises ValueError if validation fails.
        """
        # Skip validation for inline commands (python -c, etc.)
        if re.search(r"\s+-c\s+", self.entrypoint):
            return

        # Match Python file references only
        file_pattern = r"(?:python\d?\s+)?([./\w/-]+\.py)"
        matches = re.findall(file_pattern, self.entrypoint)

        if not matches:
            return

        entrypoint_path = matches[0]

        # Get working_dir from runtime_env
        runtime_env_dict = None
        working_dir = None

        if self.runtime_env:
            runtime_env_dict = (
                self.runtime_env.to_dict()
                if hasattr(self.runtime_env, "to_dict")
                else self.runtime_env
            )
            if runtime_env_dict and "working_dir" in runtime_env_dict:
                working_dir = runtime_env_dict["working_dir"]

        # Skip all validation for remote working_dir
        if working_dir and not os.path.isdir(working_dir):
            return

        # Case 1: Local working_dir - check redundancy and file existence
        if working_dir:
            normalized_working_dir = os.path.normpath(working_dir)
            normalized_entrypoint = os.path.normpath(entrypoint_path)

            # Check for redundant directory reference
            if normalized_entrypoint.startswith(normalized_working_dir + os.sep):
                relative_to_working_dir = os.path.relpath(
                    normalized_entrypoint, normalized_working_dir
                )
                working_dir_basename = os.path.basename(normalized_working_dir)
                redundant_nested_path = os.path.join(
                    normalized_working_dir,
                    working_dir_basename,
                    relative_to_working_dir,
                )

                if not os.path.exists(redundant_nested_path):
                    raise ValueError(
                        f"❌ Working directory conflict detected:\n"
                        f"   working_dir: '{working_dir}'\n"
                        f"   entrypoint references: '{entrypoint_path}'\n"
                        f"\n"
                        f"This will fail because the entrypoint runs from within working_dir.\n"
                        f"It would look for: '{redundant_nested_path}' (which doesn't exist)\n"
                        f"\n"
                        f"Fix: Remove the directory prefix from your entrypoint:\n"
                        f'   entrypoint = "python {relative_to_working_dir}"'
                    )

            # Check file exists within working_dir
            if not normalized_entrypoint.startswith(normalized_working_dir + os.sep):
                # Use normalized_working_dir (absolute path) for proper file existence check
                full_entrypoint_path = os.path.join(
                    normalized_working_dir, entrypoint_path
                )
                if not os.path.isfile(full_entrypoint_path):
                    raise ValueError(
                        f"❌ Entrypoint file not found:\n"
                        f"   Looking for: '{full_entrypoint_path}'\n"
                        f"   (working_dir: '{working_dir}', entrypoint file: '{entrypoint_path}')\n"
                        f"\n"
                        f"Please ensure the file exists at the expected location."
                    )

        # Case 2: No working_dir - validate local file exists
        else:
            if not os.path.isfile(entrypoint_path):
                raise ValueError(
                    f"❌ Entrypoint file not found: '{entrypoint_path}'\n"
                    f"\n"
                    f"Please ensure the file exists at the specified path."
                )

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

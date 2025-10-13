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
from kubernetes import client

from codeflare_sdk.common.kueue.kueue import get_default_kueue_name
from codeflare_sdk.common.utils.constants import MOUNT_PATH
from codeflare_sdk.common.utils.utils import get_ray_image_for_python_version
from codeflare_sdk.common.kubernetes_cluster.auth import get_api_client, config_check
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
    KueueWorkloadInfo,
)
from . import pretty_print

# Widget imports (optional, for Jupyter notebook support)
try:
    import ipywidgets as widgets
    from IPython.display import display
    WIDGETS_AVAILABLE = True
except ImportError:
    WIDGETS_AVAILABLE = False


logger = logging.getLogger(__name__)


def _get_kueue_workload_info(job_name: str, namespace: str, labels: dict) -> Optional[KueueWorkloadInfo]:
    """
    Get Kueue workload information for a RayJob if it's managed by Kueue.
    
    Args:
        job_name: Name of the RayJob
        namespace: Kubernetes namespace
        labels: Labels from the RayJob metadata
        
    Returns:
        KueueWorkloadInfo if the job is managed by Kueue, None otherwise
    """
    # Check if job has Kueue queue label
    queue_name = labels.get("kueue.x-k8s.io/queue-name")
    if not queue_name:
        return None
    
    try:
        # Check and load Kubernetes config (handles oc login, kubeconfig, etc.)
        config_check()
        # List all workloads in the namespace to find the one for this RayJob
        api_instance = client.CustomObjectsApi(get_api_client())
        workloads = api_instance.list_namespaced_custom_object(
            group="kueue.x-k8s.io",
            version="v1beta1",
            plural="workloads",
            namespace=namespace,
        )
        
        # Find workload with matching RayJob owner reference
        for workload in workloads.get("items", []):
            owner_refs = workload.get("metadata", {}).get("ownerReferences", [])
            
            for owner_ref in owner_refs:
                if (
                    owner_ref.get("kind") == "RayJob" 
                    and owner_ref.get("name") == job_name
                ):
                    # Found the workload for this RayJob
                    workload_metadata = workload.get("metadata", {})
                    workload_status = workload.get("status", {})
                    
                    # Extract workload information
                    workload_info = KueueWorkloadInfo(
                        name=workload_metadata.get("name", "unknown"),
                        queue_name=queue_name,
                        status=_get_workload_status_summary(workload_status),
                        priority=workload.get("spec", {}).get("priority"),
                        creation_time=workload_metadata.get("creationTimestamp"),
                        admission_time=_get_admission_time(workload_status),
                    )
                    
                    logger.debug(f"Found Kueue workload for RayJob {job_name}: {workload_info.name}")
                    return workload_info
        
        # No workload found for this RayJob
        logger.debug(f"No Kueue workload found for RayJob {job_name}")
        return None
        
    except Exception as e:
        logger.warning(f"Failed to get Kueue workload info for RayJob {job_name}: {e}")
        return None


def _get_workload_status_summary(workload_status: dict) -> str:
    """
    Get a summary status from Kueue workload status.
    
    Args:
        workload_status: The status section from a Kueue workload CR
        
    Returns:
        String summary of the workload status
    """
    conditions = workload_status.get("conditions", [])
    
    # Check conditions in priority order
    for condition_type in ["Finished", "Admitted", "QuotaReserved", "Pending"]:
        for condition in conditions:
            if (
                condition.get("type") == condition_type 
                and condition.get("status") == "True"
            ):
                return condition_type
    
    # If no clear status, return "Unknown"
    return "Unknown"


def _get_admission_time(workload_status: dict) -> Optional[str]:
    """
    Get the admission time from Kueue workload status.
    
    Args:
        workload_status: The status section from a Kueue workload CR
        
    Returns:
        Admission timestamp if available, None otherwise
    """
    conditions = workload_status.get("conditions", [])
    
    for condition in conditions:
        if (
            condition.get("type") == "Admitted" 
            and condition.get("status") == "True"
        ):
            return condition.get("lastTransitionTime")
    
    return None




class RayJob:
    """
    A client for managing Ray jobs using the KubeRay operator.

    This class provides a simplified interface for submitting and managing
    RayJob CRs (using the KubeRay RayJob python client).
    """
    
    # Global configuration for widget display preference
    _default_use_widgets = False

    @classmethod
    def set_widgets_default(cls, use_widgets: bool):
        """
        Set the global default for widget display in Status() and List() methods.
        
        Args:
            use_widgets (bool): Whether to use Jupyter widgets by default
            
        Example:
            >>> from codeflare_sdk import RayJob
            >>> RayJob.set_widgets_default(True)  # Enable widgets globally
            >>> RayJob.Status("my-job")  # Now uses widgets by default
            >>> RayJob.List()  # Now uses widgets by default
        """
        cls._default_use_widgets = use_widgets
        logger.info(f"Set global widget default to: {use_widgets}")

    @classmethod
    def get_widgets_default(cls) -> bool:
        """
        Get the current global default for widget display.
        
        Returns:
            bool: Current global widget setting
            
        Example:
            >>> from codeflare_sdk import RayJob
            >>> print(f"Widgets enabled: {RayJob.get_widgets_default()}")
        """
        return cls._default_use_widgets

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

        # Get Kueue workload information if available
        # We need to fetch the RayJob CR to get labels
        kueue_workload = None
        local_queue = None
        try:
            config_check()
            api_instance = client.CustomObjectsApi(get_api_client())
            rayjob_cr = api_instance.get_namespaced_custom_object(
                group="ray.io",
                version="v1",
                namespace=self.namespace,
                plural="rayjobs",
                name=self.name,
            )
            labels = rayjob_cr.get("metadata", {}).get("labels", {})
            local_queue = labels.get("kueue.x-k8s.io/queue-name")
            if local_queue:
                kueue_workload = _get_kueue_workload_info(self.name, self.namespace, labels)
        except Exception as e:
            logger.debug(f"Could not fetch Kueue workload info for {self.name}: {e}")

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
            kueue_workload=kueue_workload,
            local_queue=local_queue,
            is_managed_cluster=self._cluster_config is not None,
        )

        # Map to CodeFlare status and determine readiness
        codeflare_status, ready = self._map_to_codeflare_status(deployment_status)

        if print_to_console:
            pretty_print.print_job_status(job_info)

        return codeflare_status, ready

    @staticmethod
    def Status(
        job_name: str,
        namespace: Optional[str] = None,
        use_widgets: Optional[bool] = None
    ):
        """
        Get the status of a RayJob by name and display it with Rich console formatting.
        
        Args:
            job_name (str): The name of the RayJob
            namespace (Optional[str]): The Kubernetes namespace (auto-detected if not specified)
            use_widgets (Optional[bool]): Whether to display in Jupyter widgets (default: None, uses global setting)
        
        Returns:
            Tuple of (CodeflareRayJobStatus, ready: bool) when use_widgets=False (default), None when use_widgets=True
        
        Example:
            >>> from codeflare_sdk.ray import RayJob
            >>> status, ready = RayJob.Status("my-job")  # Rich console (default)
            >>> RayJob.set_widgets_default(True)  # Enable widgets globally
            >>> RayJob.Status("my-job")  # Now uses widgets by default
        """
        if namespace is None:
            namespace = get_current_namespace()
        
        # Use global default if not specified
        if use_widgets is None:
            use_widgets = RayJob._default_use_widgets
        
        # Initialize the API (no parameters needed)
        api = RayjobApi()
        
        try:
            # Check and load Kubernetes config (handles oc login, kubeconfig, etc.)
            config_check()
            status_data = api.get_job_status(name=job_name, k8s_namespace=namespace)
            
            if not status_data:
                if use_widgets:
                    RayJob._display_job_status_widget(None, job_name, namespace)
                    return None  # Don't return tuple to avoid Jupyter auto-display
                else:
                    pretty_print.print_no_job_found(job_name, namespace)
                    return CodeflareRayJobStatus.UNKNOWN, False
            
            # Map deployment status to our enums
            deployment_status_str = status_data.get("jobDeploymentStatus", "Unknown")
            
            try:
                deployment_status = RayJobDeploymentStatus(deployment_status_str)
            except ValueError:
                deployment_status = RayJobDeploymentStatus.UNKNOWN
            
            # Create RayJobInfo dataclass - we need to determine cluster_name
            cluster_name = status_data.get("rayClusterName", "unknown")
            
            # Get Kueue workload information and cluster management info
            # We need to fetch the RayJob CR to get labels and spec
            kueue_workload = None
            local_queue = None
            is_managed_cluster = False
            try:
                api_instance = client.CustomObjectsApi(get_api_client())
                rayjob_cr = api_instance.get_namespaced_custom_object(
                    group="ray.io",
                    version="v1",
                    namespace=namespace,
                    plural="rayjobs",
                    name=job_name,
                )
                labels = rayjob_cr.get("metadata", {}).get("labels", {})
                spec = rayjob_cr.get("spec", {})
                
                # Determine if this is a managed cluster
                is_managed_cluster = "rayClusterSpec" in spec
                
                local_queue = labels.get("kueue.x-k8s.io/queue-name")
                if local_queue:
                    kueue_workload = _get_kueue_workload_info(job_name, namespace, labels)
            except Exception as e:
                logger.debug(f"Could not fetch Kueue workload info for {job_name}: {e}")
            
            job_info = RayJobInfo(
                name=job_name,
                job_id=status_data.get("jobId", ""),
                status=deployment_status,
                namespace=namespace,
                cluster_name=cluster_name,
                start_time=status_data.get("startTime"),
                end_time=status_data.get("endTime"),
                failed_attempts=status_data.get("failed", 0),
                succeeded_attempts=status_data.get("succeeded", 0),
                kueue_workload=kueue_workload,
                local_queue=local_queue,
                is_managed_cluster=is_managed_cluster,
            )
            
            # Map to CodeFlare status and determine readiness using static method
            codeflare_status, ready = RayJob._map_to_codeflare_status_static(deployment_status)
            
            if use_widgets:
                RayJob._display_job_status_widget(job_info, job_name, namespace)
                return None  # Don't return tuple to avoid Jupyter auto-display
            else:
                pretty_print.print_job_status(job_info)
                return codeflare_status, ready
            
        except Exception as e:
            logger.error(f"Failed to get status for RayJob {job_name}: {e}")
            if use_widgets:
                RayJob._display_job_status_widget(None, job_name, namespace)
                return None  # Don't return tuple to avoid Jupyter auto-display
            else:
                pretty_print.print_no_job_found(job_name, namespace)
                return CodeflareRayJobStatus.UNKNOWN, False

    @staticmethod
    def List(
        namespace: Optional[str] = None,
        use_widgets: Optional[bool] = None,
        page_size: int = 10,
        page: int = 1
    ):
        """
        List all RayJobs in a namespace and display them with Rich console formatting.
        
        Args:
            namespace (Optional[str]): The Kubernetes namespace (auto-detected if not specified)
            use_widgets (Optional[bool]): Whether to display in Jupyter widgets (default: None, uses global setting)
            page_size (int): Number of jobs to display per page (default: 10)
            page (int): Page number to display (default: 1)
        
        Returns:
            list: List of RayJobInfo objects when use_widgets=False, None when use_widgets=True
        
        Example:
            >>> from codeflare_sdk.ray import RayJob
            >>> jobs = RayJob.List()  # First 10 jobs (default)
            >>> RayJob.List(page=2)  # Next 10 jobs
            >>> RayJob.List(page_size=5, page=1)  # First 5 jobs
            >>> RayJob.set_widgets_default(True)  # Enable widgets globally
        """
        if namespace is None:
            namespace = get_current_namespace()
        
        # Use global default if not specified
        if use_widgets is None:
            use_widgets = RayJob._default_use_widgets
        
        try:
            # Check and load Kubernetes config (handles oc login, kubeconfig, etc.)
            config_check()
            # Use Kubernetes API to list RayJob custom resources
            api_instance = client.CustomObjectsApi(get_api_client())
            rayjobs = api_instance.list_namespaced_custom_object(
                group="ray.io",
                version="v1",
                namespace=namespace,
                plural="rayjobs",
            )
            
            job_list = []
            for rayjob_cr in rayjobs["items"]:
                # Extract job information from the custom resource
                metadata = rayjob_cr.get("metadata", {})
                spec = rayjob_cr.get("spec", {})
                status = rayjob_cr.get("status", {})
                
                job_name = metadata.get("name", "unknown")
                job_id = status.get("jobId", "")
                deployment_status_str = status.get("jobDeploymentStatus", "Unknown")
                
                try:
                    deployment_status = RayJobDeploymentStatus(deployment_status_str)
                except ValueError:
                    deployment_status = RayJobDeploymentStatus.UNKNOWN
                
                # Get cluster name and determine if it's managed
                cluster_name = "unknown"
                is_managed_cluster = False
                if "rayClusterSpec" in spec:
                    cluster_name = f"{job_name}-cluster"  # Managed cluster
                    is_managed_cluster = True
                elif "clusterSelector" in spec:
                    cluster_selector = spec["clusterSelector"]
                    cluster_name = cluster_selector.get("ray.io/cluster", "unknown")
                    is_managed_cluster = False
                
                # Get Kueue workload information if available
                labels = metadata.get("labels", {})
                local_queue = labels.get("kueue.x-k8s.io/queue-name")
                kueue_workload = None
                if local_queue:
                    kueue_workload = _get_kueue_workload_info(job_name, namespace, labels)
                
                job_info = RayJobInfo(
                    name=job_name,
                    job_id=job_id,
                    status=deployment_status,
                    namespace=namespace,
                    cluster_name=cluster_name,
                    start_time=status.get("startTime"),
                    end_time=status.get("endTime"),
                    failed_attempts=status.get("failed", 0),
                    succeeded_attempts=status.get("succeeded", 0),
                    kueue_workload=kueue_workload,
                    local_queue=local_queue,
                    is_managed_cluster=is_managed_cluster,
                )
                job_list.append(job_info)
            
            # Apply pagination
            total_jobs = len(job_list)
            total_pages = (total_jobs + page_size - 1) // page_size  # Ceiling division
            
            # Validate page number
            if page < 1:
                page = 1
            elif page > total_pages and total_pages > 0:
                page = total_pages
            
            # Calculate pagination slice
            start_idx = (page - 1) * page_size
            end_idx = start_idx + page_size
            paginated_jobs = job_list[start_idx:end_idx]
            
            # Create pagination info
            pagination_info = {
                "current_page": page,
                "total_pages": total_pages,
                "page_size": page_size,
                "total_jobs": total_jobs,
                "showing_start": start_idx + 1 if paginated_jobs else 0,
                "showing_end": min(end_idx, total_jobs),
            }
            
            if use_widgets:
                RayJob._display_jobs_list_widget(paginated_jobs, namespace, pagination_info)
                return None  # Don't return job_list to avoid Jupyter auto-display
            else:
                pretty_print.print_jobs_list(paginated_jobs, namespace, pagination_info)
                return job_list  # Return full list for programmatic use
            
        except Exception as e:
            logger.error(f"Failed to list RayJobs in namespace {namespace}: {e}")
            empty_pagination_info = {
                "current_page": 1,
                "total_pages": 0,
                "page_size": page_size,
                "total_jobs": 0,
                "showing_start": 0,
                "showing_end": 0,
            }
            if use_widgets:
                RayJob._display_jobs_list_widget([], namespace, empty_pagination_info)
                return None  # Don't return empty list to avoid Jupyter auto-display
            else:
                pretty_print.print_jobs_list([], namespace, empty_pagination_info)
                return []

    @staticmethod
    def _map_to_codeflare_status_static(
        deployment_status: RayJobDeploymentStatus,
    ) -> Tuple[CodeflareRayJobStatus, bool]:
        """
        Static version of status mapping for use by the static status method.
        """
        status_mapping = {
            RayJobDeploymentStatus.COMPLETE: (CodeflareRayJobStatus.COMPLETE, True),
            RayJobDeploymentStatus.FAILED: (CodeflareRayJobStatus.FAILED, True),
            RayJobDeploymentStatus.RUNNING: (CodeflareRayJobStatus.RUNNING, False),
            RayJobDeploymentStatus.SUSPENDED: (CodeflareRayJobStatus.SUSPENDED, False),
            RayJobDeploymentStatus.UNKNOWN: (CodeflareRayJobStatus.UNKNOWN, False),
        }
        
        return status_mapping.get(
            deployment_status, (CodeflareRayJobStatus.UNKNOWN, False)
        )

    @staticmethod
    def _display_job_status_widget(job_info: Optional[RayJobInfo], job_name: str, namespace: str):
        """
        Display RayJob status in a Jupyter widget.
        
        Args:
            job_info: RayJobInfo object or None if job not found
            job_name: Name of the job
            namespace: Kubernetes namespace
        """
        if not WIDGETS_AVAILABLE:
            # Fall back to console output if widgets not available
            if job_info:
                pretty_print.print_job_status(job_info)
            else:
                pretty_print.print_no_job_found(job_name, namespace)
            return
        
        # Create the widget display
        if job_info is None:
            # Job not found - match the list widget styling
            status_widget = widgets.HTML(
                value=f"""
                <div style="border: 2px solid #dc3545; border-radius: 8px; padding: 15px; background-color: #f8f9fa;">
                    <h3 style="color: #dc3545; margin-top: 0;">❌ RayJob Not Found</h3>
                    <table style="width: 100%; border-collapse: collapse; margin-top: 10px;">
                        <tr>
                            <td style="border: 1px solid #dee2e6; padding: 8px; font-weight: bold;">Job Name:</td>
                            <td style="border: 1px solid #dee2e6; padding: 8px;">{job_name}</td>
                        </tr>
                        <tr>
                            <td style="border: 1px solid #dee2e6; padding: 8px; font-weight: bold;">Namespace:</td>
                            <td style="border: 1px solid #dee2e6; padding: 8px;">{namespace}</td>
                        </tr>
                        <tr>
                            <td style="border: 1px solid #dee2e6; padding: 8px; font-weight: bold;">Status:</td>
                            <td style="border: 1px solid #dee2e6; padding: 8px; color: #666; font-style: italic;">The RayJob may have been deleted or never existed.</td>
                        </tr>
                    </table>
                </div>
                """
            )
        else:
            # Job found - create status display matching list widget style
            status_color, status_icon = RayJob._get_status_color_and_icon(job_info.status)
            
            # Build main job information table
            job_table_rows = f"""
                <tr>
                    <td style="border: 1px solid #dee2e6; padding: 8px; font-weight: bold;">Name:</td>
                    <td style="border: 1px solid #dee2e6; padding: 8px; font-weight: bold; color: #0066cc;">{job_info.name}</td>
                </tr>
                <tr>
                    <td style="border: 1px solid #dee2e6; padding: 8px; font-weight: bold;">Job ID:</td>
                    <td style="border: 1px solid #dee2e6; padding: 8px; font-family: monospace; font-size: 0.9em;">{job_info.job_id}</td>
                </tr>
                <tr>
                    <td style="border: 1px solid #dee2e6; padding: 8px; font-weight: bold;">Status:</td>
                    <td style="border: 1px solid #dee2e6; padding: 8px;">
                        <span style="color: {status_color}; font-weight: bold;">{status_icon} {job_info.status.value}</span>
                    </td>
                </tr>
                <tr>
                    <td style="border: 1px solid #dee2e6; padding: 8px; font-weight: bold;">RayCluster:</td>
                    <td style="border: 1px solid #dee2e6; padding: 8px;">{job_info.cluster_name}</td>
                </tr>
                <tr>
                    <td style="border: 1px solid #dee2e6; padding: 8px; font-weight: bold;">Namespace:</td>
                    <td style="border: 1px solid #dee2e6; padding: 8px;">{job_info.namespace}</td>
                </tr>
                <tr>
                    <td style="border: 1px solid #dee2e6; padding: 8px; font-weight: bold;">Managed Cluster:</td>
                    <td style="border: 1px solid #dee2e6; padding: 8px;">
                        {'<span style="color: #28a745; font-weight: bold;">✅ Yes (Job-managed)</span>' if job_info.is_managed_cluster else '<span style="color: #6c757d;">❌ No (Existing cluster)</span>'}
                    </td>
                </tr>
            """
            
            # Add timing information if available
            if job_info.start_time:
                job_table_rows += f"""
                <tr>
                    <td style="border: 1px solid #dee2e6; padding: 8px; font-weight: bold;">Started:</td>
                    <td style="border: 1px solid #dee2e6; padding: 8px;">{job_info.start_time}</td>
                </tr>
                """
            
            if job_info.end_time:
                job_table_rows += f"""
                <tr>
                    <td style="border: 1px solid #dee2e6; padding: 8px; font-weight: bold;">Ended:</td>
                    <td style="border: 1px solid #dee2e6; padding: 8px;">{job_info.end_time}</td>
                </tr>
                """
            
            # Add failure info if available
            if job_info.failed_attempts > 0:
                job_table_rows += f"""
                <tr>
                    <td style="border: 1px solid #dee2e6; padding: 8px; font-weight: bold;">Failed Attempts:</td>
                    <td style="border: 1px solid #dee2e6; padding: 8px; color: #dc3545; font-weight: bold;">{job_info.failed_attempts}</td>
                </tr>
                """
            
            # Build Kueue section
            kueue_section = ""
            if job_info.kueue_workload:
                kueue_color = "#007bff"  # Blue for Kueue
                if job_info.kueue_workload.status == "Admitted":
                    kueue_color = "#28a745"  # Green for admitted
                elif job_info.kueue_workload.status == "Pending":
                    kueue_color = "#ffc107"  # Yellow for pending
                
                kueue_rows = f"""
                <tr style="background-color: #e7f3ff;">
                    <td style="border: 1px solid #dee2e6; padding: 8px; font-weight: bold; color: {kueue_color};">🎯 Local Queue:</td>
                    <td style="border: 1px solid #dee2e6; padding: 8px;">{job_info.local_queue}</td>
                </tr>
                <tr style="background-color: #e7f3ff;">
                    <td style="border: 1px solid #dee2e6; padding: 8px; font-weight: bold; color: {kueue_color};">🎯 Workload Status:</td>
                    <td style="border: 1px solid #dee2e6; padding: 8px;">
                        <span style="color: {kueue_color}; font-weight: bold;">{job_info.kueue_workload.status}</span>
                    </td>
                </tr>
                <tr style="background-color: #e7f3ff;">
                    <td style="border: 1px solid #dee2e6; padding: 8px; font-weight: bold; color: {kueue_color};">🎯 Workload Name:</td>
                    <td style="border: 1px solid #dee2e6; padding: 8px;">{job_info.kueue_workload.name}</td>
                </tr>
                """
                
                if job_info.kueue_workload.priority is not None:
                    kueue_rows += f"""
                <tr style="background-color: #e7f3ff;">
                    <td style="border: 1px solid #dee2e6; padding: 8px; font-weight: bold; color: {kueue_color};">🎯 Priority:</td>
                    <td style="border: 1px solid #dee2e6; padding: 8px;">{job_info.kueue_workload.priority}</td>
                </tr>
                    """
                
                if job_info.kueue_workload.admission_time:
                    kueue_rows += f"""
                <tr style="background-color: #e7f3ff;">
                    <td style="border: 1px solid #dee2e6; padding: 8px; font-weight: bold; color: {kueue_color};">🎯 Admitted:</td>
                    <td style="border: 1px solid #dee2e6; padding: 8px;">{job_info.kueue_workload.admission_time}</td>
                </tr>
                    """
                
                kueue_section = kueue_rows
                
            elif job_info.local_queue:
                kueue_section = f"""
                <tr style="background-color: #f8f9fa;">
                    <td style="border: 1px solid #dee2e6; padding: 8px; font-weight: bold; color: #6c757d;">🎯 Local Queue:</td>
                    <td style="border: 1px solid #dee2e6; padding: 8px;">{job_info.local_queue}</td>
                </tr>
                <tr style="background-color: #f8f9fa;">
                    <td style="border: 1px solid #dee2e6; padding: 8px; font-weight: bold; color: #6c757d;">🎯 Workload Info:</td>
                    <td style="border: 1px solid #dee2e6; padding: 8px; color: #666; font-style: italic;">Not available</td>
                </tr>
                """
            
            status_widget = widgets.HTML(
                value=f"""
                <div style="border: 2px solid {status_color}; border-radius: 8px; padding: 15px; background-color: #f8f9fa;">
                    <h3 style="color: {status_color}; margin-top: 0;">{status_icon} RayJob Status</h3>
                    <table style="width: 100%; border-collapse: collapse; margin-top: 10px;">
                        {job_table_rows}
                        {kueue_section}
                    </table>
                </div>
                """
            )
        
        # Display the widget
        display(status_widget)

    @staticmethod
    def _get_status_color_and_icon(status: RayJobDeploymentStatus) -> Tuple[str, str]:
        """
        Get color and icon for job status display.
        
        Returns:
            Tuple of (color, icon)
        """
        status_mapping = {
            RayJobDeploymentStatus.COMPLETE: ("#28a745", "✅"),
            RayJobDeploymentStatus.RUNNING: ("#007bff", "🔄"),
            RayJobDeploymentStatus.FAILED: ("#dc3545", "❌"),
            RayJobDeploymentStatus.SUSPENDED: ("#ffc107", "⏸️"),
            RayJobDeploymentStatus.UNKNOWN: ("#6c757d", "❓"),
        }
        return status_mapping.get(status, ("#6c757d", "❓"))

    @staticmethod
    def _display_jobs_list_widget(job_list, namespace: str, pagination_info: Optional[dict] = None):
        """
        Display a list of RayJobs in a Jupyter widget table with pagination.
        
        Args:
            job_list: List of RayJobInfo objects (for current page)
            namespace: Kubernetes namespace
            pagination_info: Optional pagination information dict
        """
        if not WIDGETS_AVAILABLE:
            # Fall back to console output if widgets not available
            pretty_print.print_jobs_list(job_list, namespace, pagination_info)
            return
        
        if not job_list:
            # No jobs found
            no_jobs_widget = widgets.HTML(
                value=f"""
                <div style="border: 2px solid #ffc107; border-radius: 8px; padding: 15px; background-color: #fff9e6;">
                    <h3 style="color: #856404; margin-top: 0;">📋 No RayJobs Found</h3>
                    <p><strong>Namespace:</strong> {namespace}</p>
                    <p style="color: #666;">No RayJobs found in this namespace. Jobs may have been deleted or completed with TTL cleanup.</p>
                </div>
                """
            )
            display(no_jobs_widget)
            return
        
        # Create table header with pagination info
        title = f"📋 RayJobs in namespace: {namespace}"
        if pagination_info and pagination_info["total_pages"] > 1:
            title += f" (Page {pagination_info['current_page']} of {pagination_info['total_pages']})"
        
        table_html = f"""
        <div style="border: 2px solid #007bff; border-radius: 8px; padding: 15px; background-color: #f8f9fa;">
            <h3 style="color: #007bff; margin-top: 0;">{title}</h3>
            <table style="width: 100%; border-collapse: collapse; margin-top: 10px;">
                <thead>
                    <tr style="background-color: #e9ecef;">
                        <th style="border: 1px solid #dee2e6; padding: 8px; text-align: left;">Status</th>
                        <th style="border: 1px solid #dee2e6; padding: 8px; text-align: left;">Job Name</th>
                        <th style="border: 1px solid #dee2e6; padding: 8px; text-align: left;">Job ID</th>
                        <th style="border: 1px solid #dee2e6; padding: 8px; text-align: left;">Cluster</th>
                        <th style="border: 1px solid #dee2e6; padding: 8px; text-align: left;">Managed</th>
                        <th style="border: 1px solid #dee2e6; padding: 8px; text-align: left;">Queue</th>
                        <th style="border: 1px solid #dee2e6; padding: 8px; text-align: left;">Kueue Status</th>
                        <th style="border: 1px solid #dee2e6; padding: 8px; text-align: left;">Start Time</th>
                    </tr>
                </thead>
                <tbody>
        """
        
        # Add rows for each job
        for job_info in job_list:
            status_color, status_icon = RayJob._get_status_color_and_icon(job_info.status)
            start_time = job_info.start_time or "N/A"
            
            # Cluster management info
            managed_display = "✅ Yes" if job_info.is_managed_cluster else "❌ No"
            managed_color = "#28a745" if job_info.is_managed_cluster else "#6c757d"
            
            # Kueue information
            queue_display = job_info.local_queue or "N/A"
            kueue_status_display = "N/A"
            kueue_status_color = "#6c757d"
            
            if job_info.kueue_workload:
                kueue_status_display = job_info.kueue_workload.status
                if job_info.kueue_workload.status == "Admitted":
                    kueue_status_color = "#28a745"  # Green
                elif job_info.kueue_workload.status == "Pending":
                    kueue_status_color = "#ffc107"  # Yellow
                elif job_info.kueue_workload.status == "Finished":
                    kueue_status_color = "#007bff"  # Blue
            
            table_html += f"""
                    <tr>
                        <td style="border: 1px solid #dee2e6; padding: 8px;">
                            <span style="color: {status_color}; font-weight: bold;">
                                {status_icon} {job_info.status.value}
                            </span>
                        </td>
                        <td style="border: 1px solid #dee2e6; padding: 8px; font-weight: bold;">{job_info.name}</td>
                        <td style="border: 1px solid #dee2e6; padding: 8px; font-family: monospace; font-size: 0.9em;">{job_info.job_id}</td>
                        <td style="border: 1px solid #dee2e6; padding: 8px;">{job_info.cluster_name}</td>
                        <td style="border: 1px solid #dee2e6; padding: 8px;">
                            <span style="color: {managed_color}; font-weight: bold;">{managed_display}</span>
                        </td>
                        <td style="border: 1px solid #dee2e6; padding: 8px;">{queue_display}</td>
                        <td style="border: 1px solid #dee2e6; padding: 8px;">
                            <span style="color: {kueue_status_color}; font-weight: bold;">{kueue_status_display}</span>
                        </td>
                        <td style="border: 1px solid #dee2e6; padding: 8px; font-size: 0.9em;">{start_time}</td>
                    </tr>
            """
        
        table_html += """
                </tbody>
            </table>
        """
        
        # Add pagination navigation info
        if pagination_info and pagination_info["total_pages"] > 1:
            table_html += f"""
            <div style="margin-top: 10px; padding: 10px; background-color: #e9ecef; border-radius: 4px;">
                <p style="margin: 0; color: #6c757d; font-size: 0.9em;">
                    Showing {pagination_info['showing_start']}-{pagination_info['showing_end']} 
                    of {pagination_info['total_jobs']} jobs
                </p>
                <p style="margin: 5px 0 0 0; color: #007bff; font-size: 0.9em;">
                    <strong>Navigation:</strong>
            """
            
            if pagination_info['current_page'] > 1:
                table_html += f" RayJob.List(page={pagination_info['current_page'] - 1}) [Previous]"
            if pagination_info['current_page'] < pagination_info['total_pages']:
                if pagination_info['current_page'] > 1:
                    table_html += " |"
                table_html += f" RayJob.List(page={pagination_info['current_page'] + 1}) [Next]"
            
            table_html += """
                </p>
            </div>
            """
        
        table_html += "</div>"
        
        # Display the widget
        jobs_widget = widgets.HTML(value=table_html)
        display(jobs_widget)


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

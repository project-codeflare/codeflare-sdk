# Copyright 2024 IBM, Red Hat
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

import warnings
from dataclasses import dataclass, field, fields
from typing import Dict, List, Optional, Union, get_args, get_origin

from kubernetes.client import V1Toleration, V1Volume, V1VolumeMount

from ...common.widgets.raycluster_widgets import raycluster_apply_down_buttons
from ...common.widgets.widgets import is_notebook
from .builders import RayClusterBuildersMixin
from .constants import DEFAULT_ACCELERATORS
from .kubernetes_helpers import RayClusterKubernetesHelpersMixin
from .lifecycle import RayClusterLifecycleMixin
from .utils import get_cluster, list_all_clusters, list_all_queued


@dataclass
class RayCluster(
    RayClusterBuildersMixin,
    RayClusterKubernetesHelpersMixin,
    RayClusterLifecycleMixin,
):
    """
    Unified Ray cluster class supporting both standalone clusters and RayJob-managed clusters.

    This class consolidates functionality from ClusterConfiguration and ManagedClusterConfig,
    providing a single interface for defining and managing Ray clusters.

    For standalone clusters: name is required, use apply()/down()/status()/wait_ready().
    For RayJob-managed clusters: name is optional (auto-generated from job name).

    Args:
        name:
            The name of the cluster. Required for standalone clusters,
            optional for RayJob-managed clusters.
        namespace:
            The Kubernetes namespace for the cluster.
        head_cpu_requests:
            CPU requests for the head node.
        head_cpu_limits:
            CPU limits for the head node.
        head_memory_requests:
            Memory requests for the head node. Integer values are treated as GB.
        head_memory_limits:
            Memory limits for the head node. Integer values are treated as GB.
        head_accelerators:
            Extended resource requests for the head node. ex: {"nvidia.com/gpu": 1}
        head_tolerations:
            List of Kubernetes tolerations for head nodes.
        worker_cpu_requests:
            CPU requests for each worker node.
        worker_cpu_limits:
            CPU limits for each worker node.
        num_workers:
            The number of worker nodes to create.
        worker_memory_requests:
            Memory requests for each worker. Integer values are treated as GB.
        worker_memory_limits:
            Memory limits for each worker. Integer values are treated as GB.
        worker_accelerators:
            Extended resource requests for each worker. ex: {"nvidia.com/gpu": 1}
        worker_tolerations:
            List of Kubernetes tolerations for worker nodes.
        envs:
            Environment variables to set for all cluster pods.
        image:
            Container image for the Ray cluster.
        image_pull_secrets:
            List of Kubernetes secret names for pulling container images.
        labels:
            Labels to apply to the cluster resources.
        annotations:
            Annotations to apply to the cluster pods.
        volumes:
            List of V1Volume objects to add to the cluster.
        volume_mounts:
            List of V1VolumeMount objects to add to the cluster.
        accelerator_configs:
            A dictionary of custom resource mappings to map extended resource requests to RayCluster resource names
        overwrite_default_accelerator_configs:
            A boolean whether to allow overwriting default accelerator configs.
        write_to_file:
            Whether to write cluster configuration to a file (standalone only).
        verify_tls:
            Whether to verify TLS when connecting to the cluster (standalone only).
        local_queue:
            The Kueue LocalQueue name for the cluster.
        enable_gcs_ft:
            Whether to enable GCS fault tolerance (standalone only).
        redis_address:
            Redis address for GCS fault tolerance (required when enable_gcs_ft=True).
        redis_password_secret:
            Kubernetes secret reference for Redis password.
            ex: {"name": "secret-name", "key": "password-key"}
        external_storage_namespace:
            Storage namespace for GCS fault tolerance.
        enable_usage_stats:
            Whether to enable Ray usage statistics collection.
    """

    # Core identification
    name: Optional[str] = None
    namespace: Optional[str] = None

    # Head node resources
    head_cpu_requests: Union[int, str] = 2
    head_cpu_limits: Union[int, str] = 2
    head_memory_requests: Union[int, str] = 8
    head_memory_limits: Union[int, str] = 8
    head_accelerators: Dict[str, Union[str, int]] = field(default_factory=dict)
    head_tolerations: Optional[List[V1Toleration]] = None

    # Worker node resources
    # Defaults match ManagedClusterConfig for consistency
    worker_cpu_requests: Union[int, str] = 1
    worker_cpu_limits: Union[int, str] = 1
    num_workers: int = 1
    worker_memory_requests: Union[int, str] = 2
    worker_memory_limits: Union[int, str] = 2
    worker_accelerators: Dict[str, Union[str, int]] = field(default_factory=dict)
    worker_tolerations: Optional[List[V1Toleration]] = None

    # Shared configuration
    envs: Dict[str, str] = field(default_factory=dict)
    image: str = ""
    image_pull_secrets: List[str] = field(default_factory=list)
    labels: Dict[str, str] = field(default_factory=dict)
    annotations: Dict[str, str] = field(default_factory=dict)
    volumes: List[V1Volume] = field(default_factory=list)
    volume_mounts: List[V1VolumeMount] = field(default_factory=list)

    # Accelerator configuration
    accelerator_configs: Dict[str, str] = field(default_factory=dict)
    overwrite_default_accelerator_configs: bool = False

    # Standalone cluster specific options
    write_to_file: bool = False
    verify_tls: bool = True
    local_queue: Optional[str] = None

    # GCS fault tolerance options (standalone only)
    enable_gcs_ft: bool = False
    redis_address: Optional[str] = None
    redis_password_secret: Optional[Dict[str, str]] = None
    external_storage_namespace: Optional[str] = None

    # Usage statistics
    enable_usage_stats: bool = False

    def __post_init__(self):
        """
        Post-initialization validation and processing.

        This method runs after dataclass initialization and performs:
        - Internal state initialization
        - Configuration validation
        - Memory unit conversion
        - Accelerator config merging
        - Environment variable setup

        Validation ensures all required fields are properly configured before
        the cluster can be used. This happens before any mixin methods are called,
        so mixins can safely assume validated state.
        """
        # Internal state for standalone cluster lifecycle.
        self._resource_yaml = None
        self._job_submission_client = None

        # TLS verification warning.
        if not self.verify_tls:
            print(
                "Warning: TLS verification has been disabled - Endpoint checks will be bypassed"
            )

        # Set usage stats environment variable.
        if self.enable_usage_stats:
            self.envs["RAY_USAGE_STATS_ENABLED"] = "1"
        else:
            self.envs["RAY_USAGE_STATS_ENABLED"] = "0"

        # Validate GCS fault tolerance configuration.
        if self.enable_gcs_ft:
            if not self.redis_address:
                raise ValueError(
                    "redis_address must be provided when enable_gcs_ft is True"
                )

            if self.redis_password_secret and not isinstance(
                self.redis_password_secret, dict
            ):
                raise ValueError(
                    "redis_password_secret must be a dictionary with 'name' and 'key' fields"
                )

            if self.redis_password_secret and (
                "name" not in self.redis_password_secret
                or "key" not in self.redis_password_secret
            ):
                raise ValueError(
                    "redis_password_secret must contain both 'name' and 'key' fields"
                )

        # Run validation and processing.
        # These methods ensure the cluster is in a valid state before use.
        self._validate_types()
        self._memory_to_string()
        self._str_mem_no_unit_add_GB()
        self._combine_accelerator_configs()
        self._validate_accelerator_config(self.head_accelerators)
        self._validate_accelerator_config(self.worker_accelerators)

        # Display widget if in notebook environment.
        if is_notebook():
            raycluster_apply_down_buttons(self)

    # -------------------------------------------------------------------------
    # Validation Methods
    # -------------------------------------------------------------------------

    def _validate_types(self):
        """
        Validate the types of all fields in the RayCluster dataclass.

        This ensures that all field values match their declared types,
        catching configuration errors early.
        """
        errors = []
        for field_info in fields(self):
            value = getattr(self, field_info.name)
            expected_type = field_info.type
            if not self._is_type(value, expected_type):
                errors.append(f"'{field_info.name}' should be of type {expected_type}.")

        if errors:
            raise TypeError("Type validation failed:\n" + "\n".join(errors))

    @staticmethod
    def _is_type(value, expected_type) -> bool:
        """
        Check if the value matches the expected type.

        Handles complex types like Union, List, Dict, and Optional.
        """

        def check_type(value, expected_type):
            origin_type = get_origin(expected_type)
            args = get_args(expected_type)
            if origin_type is Union:
                return any(check_type(value, union_type) for union_type in args)
            if origin_type is list:
                if value is not None:
                    return all(check_type(elem, args[0]) for elem in (value or []))
                return True
            if origin_type is dict:
                if value is not None:
                    return all(
                        check_type(k, args[0]) and check_type(v, args[1])
                        for k, v in value.items()
                    )
                return True
            if origin_type is tuple:
                return all(check_type(elem, etype) for elem, etype in zip(value, args))
            if expected_type is int:
                return isinstance(value, int) and not isinstance(value, bool)
            if expected_type is bool:
                return isinstance(value, bool)
            return isinstance(value, expected_type)

        return check_type(value, expected_type)

    def _memory_to_string(self):
        """
        Convert integer memory values to string with 'Gi' suffix (Kubernetes standard).

        This ensures memory values are in the format Kubernetes expects.
        Integer values represent GB and are converted to Gi format.
        """
        if isinstance(self.head_memory_requests, int):
            self.head_memory_requests = f"{self.head_memory_requests}Gi"
        if isinstance(self.head_memory_limits, int):
            self.head_memory_limits = f"{self.head_memory_limits}Gi"
        if isinstance(self.worker_memory_requests, int):
            self.worker_memory_requests = f"{self.worker_memory_requests}Gi"
        if isinstance(self.worker_memory_limits, int):
            self.worker_memory_limits = f"{self.worker_memory_limits}Gi"

    def _str_mem_no_unit_add_GB(self):
        """
        Add 'Gi' suffix to string memory values that are just numbers.

        This handles cases where memory is provided as a string number without units.
        Processes both head and worker memory values for consistency.
        """
        # Handle head memory values.
        if (
            isinstance(self.head_memory_requests, str)
            and self.head_memory_requests.isdecimal()
        ):
            self.head_memory_requests = f"{self.head_memory_requests}Gi"
        if (
            isinstance(self.head_memory_limits, str)
            and self.head_memory_limits.isdecimal()
        ):
            self.head_memory_limits = f"{self.head_memory_limits}Gi"

        # Handle worker memory values.
        if (
            isinstance(self.worker_memory_requests, str)
            and self.worker_memory_requests.isdecimal()
        ):
            self.worker_memory_requests = f"{self.worker_memory_requests}Gi"
        if (
            isinstance(self.worker_memory_limits, str)
            and self.worker_memory_limits.isdecimal()
        ):
            self.worker_memory_limits = f"{self.worker_memory_limits}Gi"

    def _combine_accelerator_configs(self):
        """
        Merge defaults with custom accelerator configs.

        This keeps the default map intact unless the caller explicitly allows
        overriding entries. Default accelerator mappings are always included.
        """
        if overwritten := set(self.accelerator_configs.keys()).intersection(
            DEFAULT_ACCELERATORS.keys()
        ):
            if self.overwrite_default_accelerator_configs:
                warnings.warn(
                    f"Overwriting default accelerator configs for {overwritten}",
                    UserWarning,
                )
            else:
                raise ValueError(
                    "Accelerator config already exists for "
                    f"{overwritten}, set overwrite_default_accelerator_configs to True to overwrite"
                )
        self.accelerator_configs = {
            **DEFAULT_ACCELERATORS,
            **self.accelerator_configs,
        }

    def _validate_accelerator_config(self, accelerators: Dict[str, int]):
        """
        Validate that accelerator resources are in the config mapping.

        This ensures that all specified accelerators have corresponding
        mappings in accelerator_configs.
        """
        for k in accelerators.keys():
            if k not in self.accelerator_configs.keys():
                raise ValueError(
                    f"Accelerator '{k}' not found in accelerator_configs, "
                    f"available resources are {list(self.accelerator_configs.keys())}, "
                    f"to add more supported resources use accelerator_configs. "
                    f"i.e. accelerator_configs = {{'{k}': 'FOO_BAR'}}"
                )

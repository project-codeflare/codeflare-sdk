# Copyright 2022 IBM, Red Hat
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
The config sub-module contains the definition of the ClusterConfiguration dataclass,
which is used to specify resource requirements and other details when creating a
Cluster object.
"""

import pathlib
import warnings
from dataclasses import dataclass, field, fields
from typing import Dict, List, Optional, Union, get_args, get_origin, Any
from typing_extensions import deprecated
from kubernetes.client import (
    V1Toleration,
    V1Volume,
    V1VolumeMount,
    V1LocalObjectReference,
    V1SecretVolumeSource,
    V1ObjectMeta,
    V1Container,
    V1ContainerPort,
    V1Lifecycle,
    V1ExecAction,
    V1LifecycleHandler,
    V1EnvVar,
    V1PodTemplateSpec,
    V1PodSpec,
    V1ResourceRequirements,
)

from ...common.utils.constants import RAY_VERSION
from ...common.utils.utils import update_image

dir = pathlib.Path(__file__).parent.parent.resolve()

# https://docs.ray.io/en/latest/ray-core/scheduling/accelerators.html
DEFAULT_RESOURCE_MAPPING = {
    "nvidia.com/gpu": "GPU",
    "intel.com/gpu": "GPU",
    "amd.com/gpu": "GPU",
    "aws.amazon.com/neuroncore": "neuron_cores",
    "google.com/tpu": "TPU",
    "habana.ai/gaudi": "HPU",
    "huawei.com/Ascend910": "NPU",
    "huawei.com/Ascend310": "NPU",
}

# Alias for the new unified naming
DEFAULT_ACCELERATORS = DEFAULT_RESOURCE_MAPPING


@deprecated(
    "Use RayCluster instead. See: https://github.com/project-codeflare/codeflare-sdk"
)
@dataclass
class ClusterConfiguration:
    """
    [DEPRECATED] Use RayCluster instead.

    This dataclass is used to specify resource requirements and other details, and
    is passed in as an argument when creating a Cluster object.

    Args:
        name:
            The name of the cluster.
        namespace:
            The namespace in which the cluster should be created.
        head_extended_resource_requests:
            A dictionary of extended resource requests for the head node. ex: {"nvidia.com/gpu": 1}
        head_tolerations:
            List of tolerations for head nodes.
        num_workers:
            The number of workers to create.
        worker_tolerations:
            List of tolerations for worker nodes.
        appwrapper:
            A boolean indicating whether to use an AppWrapper.
        envs:
            A dictionary of environment variables to set for the cluster.
        image:
            The image to use for the cluster.
        image_pull_secrets:
            A list of image pull secrets to use for the cluster.
        write_to_file:
            A boolean indicating whether to write the cluster configuration to a file.
        verify_tls:
            A boolean indicating whether to verify TLS when connecting to the cluster.
        labels:
            A dictionary of labels to apply to the cluster.
        worker_extended_resource_requests:
            A dictionary of extended resource requests for each worker. ex: {"nvidia.com/gpu": 1}
        extended_resource_mapping:
            A dictionary of custom resource mappings to map extended resource requests to RayCluster resource names
        overwrite_default_resource_mapping:
            A boolean indicating whether to overwrite the default resource mapping.
        annotations:
            A dictionary of annotations to apply to the cluster.
        volumes:
            A list of V1Volume objects to add to the Cluster
        volume_mounts:
            A list of V1VolumeMount objects to add to the Cluster
        enable_gcs_ft:
            A boolean indicating whether to enable GCS fault tolerance.
        enable_usage_stats:
            A boolean indicating whether to capture and send Ray usage stats externally.
        redis_address:
            The address of the Redis server to use for GCS fault tolerance, required when enable_gcs_ft is True.
        redis_password_secret:
            Kubernetes secret reference containing Redis password. ex: {"name": "secret-name", "key": "password-key"}
        external_storage_namespace:
            The storage namespace to use for GCS fault tolerance. By default, KubeRay sets it to the UID of RayCluster.
    """

    name: str
    namespace: Optional[str] = None
    head_cpu_requests: Union[int, str] = 1
    head_cpu_limits: Union[int, str] = 2
    head_memory_requests: Union[int, str] = 5
    head_memory_limits: Union[int, str] = 8
    head_extended_resource_requests: Dict[str, Union[str, int]] = field(
        default_factory=dict
    )
    head_tolerations: Optional[List[V1Toleration]] = None
    worker_cpu_requests: Union[int, str] = 1
    worker_cpu_limits: Union[int, str] = 1
    num_workers: int = 1
    worker_memory_requests: Union[int, str] = 3
    worker_memory_limits: Union[int, str] = 6
    worker_tolerations: Optional[List[V1Toleration]] = None
    appwrapper: bool = False
    envs: Dict[str, str] = field(default_factory=dict)
    image: str = ""
    image_pull_secrets: List[str] = field(default_factory=list)
    write_to_file: bool = False
    verify_tls: bool = True
    labels: Dict[str, str] = field(default_factory=dict)
    worker_extended_resource_requests: Dict[str, Union[str, int]] = field(
        default_factory=dict
    )
    extended_resource_mapping: Dict[str, str] = field(default_factory=dict)
    overwrite_default_resource_mapping: bool = False
    local_queue: Optional[str] = None
    annotations: Dict[str, str] = field(default_factory=dict)
    volumes: list[V1Volume] = field(default_factory=list)
    volume_mounts: list[V1VolumeMount] = field(default_factory=list)
    enable_gcs_ft: bool = False
    enable_usage_stats: bool = False
    redis_address: Optional[str] = None
    redis_password_secret: Optional[Dict[str, str]] = None
    external_storage_namespace: Optional[str] = None

    def __post_init__(self):
        if not self.verify_tls:
            print(
                "Warning: TLS verification has been disabled - Endpoint checks will be bypassed"
            )

        if self.enable_usage_stats:
            self.envs["RAY_USAGE_STATS_ENABLED"] = "1"
        else:
            self.envs["RAY_USAGE_STATS_ENABLED"] = "0"

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

        self._validate_types()
        self._memory_to_string()
        self._str_mem_no_unit_add_GB()
        self._combine_extended_resource_mapping()
        self._validate_extended_resource_requests(self.head_extended_resource_requests)
        self._validate_extended_resource_requests(
            self.worker_extended_resource_requests
        )

    def _combine_extended_resource_mapping(self):
        if overwritten := set(self.extended_resource_mapping.keys()).intersection(
            DEFAULT_RESOURCE_MAPPING.keys()
        ):
            if self.overwrite_default_resource_mapping:
                warnings.warn(
                    f"Overwriting default resource mapping for {overwritten}",
                    UserWarning,
                )
            else:
                raise ValueError(
                    f"Resource mapping already exists for {overwritten}, set overwrite_default_resource_mapping to True to overwrite"
                )
        self.extended_resource_mapping = {
            **DEFAULT_RESOURCE_MAPPING,
            **self.extended_resource_mapping,
        }

    def _validate_extended_resource_requests(self, extended_resources: Dict[str, int]):
        for k in extended_resources.keys():
            if k not in self.extended_resource_mapping.keys():
                raise ValueError(
                    f"extended resource '{k}' not found in extended_resource_mapping, available resources are {list(self.extended_resource_mapping.keys())}, to add more supported resources use extended_resource_mapping. i.e. extended_resource_mapping = {{'{k}': 'FOO_BAR'}}"
                )

    def _str_mem_no_unit_add_GB(self):
        if (
            isinstance(self.worker_memory_requests, str)
            and self.worker_memory_requests.isdecimal()
        ):
            self.worker_memory_requests = f"{self.worker_memory_requests}G"
        if (
            isinstance(self.worker_memory_limits, str)
            and self.worker_memory_limits.isdecimal()
        ):
            self.worker_memory_limits = f"{self.worker_memory_limits}G"

    def _memory_to_string(self):
        if isinstance(self.head_memory_requests, int):
            self.head_memory_requests = f"{self.head_memory_requests}G"
        if isinstance(self.head_memory_limits, int):
            self.head_memory_limits = f"{self.head_memory_limits}G"
        if isinstance(self.worker_memory_requests, int):
            self.worker_memory_requests = f"{self.worker_memory_requests}G"
        if isinstance(self.worker_memory_limits, int):
            self.worker_memory_limits = f"{self.worker_memory_limits}G"

    def _validate_types(self):
        """Validate the types of all fields in the ClusterConfiguration dataclass."""
        errors = []
        for field_info in fields(self):
            if field_info.name == "appwrapper":
                continue
            value = getattr(self, field_info.name)
            expected_type = field_info.type
            if not self._is_type(value, expected_type):
                errors.append(f"'{field_info.name}' should be of type {expected_type}.")

        if errors:
            raise TypeError("Type validation failed:\n" + "\n".join(errors))

    @staticmethod
    def _is_type(value, expected_type):
        """Check if the value matches the expected type."""

        def check_type(value, expected_type):
            origin_type = get_origin(expected_type)
            args = get_args(expected_type)
            if origin_type is Union:
                return any(check_type(value, union_type) for union_type in args)
            if origin_type is list:
                if value is not None:
                    return all(check_type(elem, args[0]) for elem in (value or []))
                else:
                    return True
            if origin_type is dict:
                if value is not None:
                    return all(
                        check_type(k, args[0]) and check_type(v, args[1])
                        for k, v in value.items()
                    )
                else:
                    return True
            if origin_type is tuple:
                return all(check_type(elem, etype) for elem, etype in zip(value, args))
            if expected_type is int:
                return isinstance(value, int) and not isinstance(value, bool)
            if expected_type is bool:
                return isinstance(value, bool)
            return isinstance(value, expected_type)

        return check_type(value, expected_type)


@dataclass
class RayClusterConfig:
    """
    [INTERNAL] Configuration dataclass for Ray clusters.

    Note: This is an internal configuration class. Users should use the new RayCluster
    class from codeflare_sdk.ray.cluster.raycluster instead, which combines configuration
    and operational methods in a single object.

    Args:
        name:
            The name of the cluster. Required for Cluster, optional for RayJob.
        namespace:
            The namespace in which the cluster should be created.
        head_accelerators:
            A dictionary of accelerator requests for the head node. ex: {"nvidia.com/gpu": 1}
        head_tolerations:
            List of tolerations for head nodes.
        num_workers:
            The number of workers to create.
        worker_tolerations:
            List of tolerations for worker nodes.
        envs:
            A dictionary of environment variables to set for the cluster.
        image:
            The image to use for the cluster.
        image_pull_secrets:
            A list of image pull secrets to use for the cluster.
        write_to_file:
            A boolean indicating whether to write the cluster configuration to a file (Cluster only).
        verify_tls:
            A boolean indicating whether to verify TLS when connecting to the cluster (Cluster only).
        labels:
            A dictionary of labels to apply to the cluster.
        worker_accelerators:
            A dictionary of accelerator requests for each worker. ex: {"nvidia.com/gpu": 1}
        accelerator_configs:
            A dictionary mapping accelerator resource names to Ray resource names.
            Defaults to DEFAULT_ACCELERATORS but can be extended with custom mappings.
        overwrite_default_accelerator_configs:
            A boolean indicating whether to overwrite the default accelerator configs.
        annotations:
            A dictionary of annotations to apply to the cluster.
        volumes:
            A list of V1Volume objects to add to the Cluster.
        volume_mounts:
            A list of V1VolumeMount objects to add to the Cluster.
        enable_gcs_ft:
            A boolean indicating whether to enable GCS fault tolerance.
        enable_usage_stats:
            A boolean indicating whether to capture and send Ray usage stats externally.
        redis_address:
            The address of the Redis server for GCS fault tolerance.
        redis_password_secret:
            Kubernetes secret reference for Redis password.
        external_storage_namespace:
            The storage namespace for GCS fault tolerance.
        local_queue:
            The Kueue local queue to use for scheduling.
    """

    name: Optional[str] = None
    namespace: Optional[str] = None
    head_cpu_requests: Union[int, str] = 2
    head_cpu_limits: Union[int, str] = 2
    head_memory_requests: Union[int, str] = 8
    head_memory_limits: Union[int, str] = 8
    head_accelerators: Dict[str, Union[str, int]] = field(default_factory=dict)
    head_tolerations: Optional[List[V1Toleration]] = None
    worker_cpu_requests: Union[int, str] = 1
    worker_cpu_limits: Union[int, str] = 1
    num_workers: int = 1
    worker_memory_requests: Union[int, str] = 2
    worker_memory_limits: Union[int, str] = 2
    worker_tolerations: Optional[List[V1Toleration]] = None
    envs: Dict[str, str] = field(default_factory=dict)
    image: str = ""
    image_pull_secrets: List[str] = field(default_factory=list)
    write_to_file: bool = False
    appwrapper: bool = False
    verify_tls: bool = True
    labels: Dict[str, str] = field(default_factory=dict)
    worker_accelerators: Dict[str, Union[str, int]] = field(default_factory=dict)
    accelerator_configs: Dict[str, str] = field(
        default_factory=lambda: DEFAULT_ACCELERATORS.copy()
    )
    overwrite_default_accelerator_configs: bool = False
    local_queue: Optional[str] = None
    annotations: Dict[str, str] = field(default_factory=dict)
    volumes: list[V1Volume] = field(default_factory=list)
    volume_mounts: list[V1VolumeMount] = field(default_factory=list)
    enable_gcs_ft: bool = False
    enable_usage_stats: bool = False
    redis_address: Optional[str] = None
    redis_password_secret: Optional[Dict[str, str]] = None
    external_storage_namespace: Optional[str] = None

    def __post_init__(self):
        if not self.verify_tls:
            print(
                "Warning: TLS verification has been disabled - Endpoint checks will be bypassed"
            )

        if self.enable_usage_stats:
            self.envs["RAY_USAGE_STATS_ENABLED"] = "1"
        else:
            self.envs["RAY_USAGE_STATS_ENABLED"] = "0"

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

        self._validate_types()
        self._memory_to_string()
        self._str_mem_no_unit_add_GB()
        self._combine_accelerator_configs()
        self._validate_accelerators(self.head_accelerators)
        self._validate_accelerators(self.worker_accelerators)

    def _combine_accelerator_configs(self):
        if overwritten := set(self.accelerator_configs.keys()).intersection(
            DEFAULT_ACCELERATORS.keys()
        ):
            if self.overwrite_default_accelerator_configs:
                warnings.warn(
                    f"Overwriting default accelerator configs for {overwritten}",
                    UserWarning,
                )
            # No error if not overwriting - just merge defaults with user configs
        self.accelerator_configs = {
            **DEFAULT_ACCELERATORS,
            **self.accelerator_configs,
        }

    def _validate_accelerators(self, accelerators: Dict[str, int]):
        for k in accelerators.keys():
            if k not in self.accelerator_configs.keys():
                raise ValueError(
                    f"Accelerator '{k}' not found in accelerator_configs, available resources are {list(self.accelerator_configs.keys())}, to add more supported resources use accelerator_configs. i.e. accelerator_configs = {{'{k}': 'FOO_BAR'}}"
                )

    def _str_mem_no_unit_add_GB(self):
        if (
            isinstance(self.worker_memory_requests, str)
            and self.worker_memory_requests.isdecimal()
        ):
            self.worker_memory_requests = f"{self.worker_memory_requests}G"
        if (
            isinstance(self.worker_memory_limits, str)
            and self.worker_memory_limits.isdecimal()
        ):
            self.worker_memory_limits = f"{self.worker_memory_limits}G"

    def _memory_to_string(self):
        if isinstance(self.head_memory_requests, int):
            self.head_memory_requests = f"{self.head_memory_requests}G"
        if isinstance(self.head_memory_limits, int):
            self.head_memory_limits = f"{self.head_memory_limits}G"
        if isinstance(self.worker_memory_requests, int):
            self.worker_memory_requests = f"{self.worker_memory_requests}G"
        if isinstance(self.worker_memory_limits, int):
            self.worker_memory_limits = f"{self.worker_memory_limits}G"

    def _validate_types(self):
        """Validate the types of all fields in the RayCluster dataclass."""
        errors = []
        for field_info in fields(self):
            value = getattr(self, field_info.name)
            expected_type = field_info.type
            if not self._is_type(value, expected_type):
                errors.append(f"'{field_info.name}' should be of type {expected_type}.")

        if errors:
            raise TypeError("Type validation failed:\n" + "\n".join(errors))

    @staticmethod
    def _is_type(value, expected_type):
        """Check if the value matches the expected type."""

        def check_type(value, expected_type):
            origin_type = get_origin(expected_type)
            args = get_args(expected_type)
            if origin_type is Union:
                return any(check_type(value, union_type) for union_type in args)
            if origin_type is list:
                if value is not None:
                    return all(check_type(elem, args[0]) for elem in (value or []))
                else:
                    return True
            if origin_type is dict:
                if value is not None:
                    return all(
                        check_type(k, args[0]) and check_type(v, args[1])
                        for k, v in value.items()
                    )
                else:
                    return True
            if origin_type is tuple:
                return all(check_type(elem, etype) for elem, etype in zip(value, args))
            if expected_type is int:
                return isinstance(value, int) and not isinstance(value, bool)
            if expected_type is bool:
                return isinstance(value, bool)
            return isinstance(value, expected_type)

        return check_type(value, expected_type)

    # Properties for backward compatibility with ClusterConfiguration field names
    @property
    def head_extended_resource_requests(self) -> Dict[str, Union[str, int]]:
        """Backward compatibility alias for head_accelerators."""
        return self.head_accelerators

    @property
    def worker_extended_resource_requests(self) -> Dict[str, Union[str, int]]:
        """Backward compatibility alias for worker_accelerators."""
        return self.worker_accelerators

    @property
    def extended_resource_mapping(self) -> Dict[str, str]:
        """Backward compatibility alias for accelerator_configs."""
        return self.accelerator_configs

    # Methods for RayJob integration
    def build_ray_cluster_spec(self, cluster_name: str) -> Dict[str, Any]:
        """
        Build the RayCluster spec for embedding in RayJob.

        Args:
            cluster_name: The name for the cluster (derived from RayJob name)

        Returns:
            Dict containing the RayCluster spec for embedding in RayJob
        """
        ray_cluster_spec = {
            "rayVersion": RAY_VERSION,
            "enableInTreeAutoscaling": False,
            "headGroupSpec": self._build_head_group_spec(),
            "workerGroupSpecs": [self._build_worker_group_spec(cluster_name)],
        }

        return ray_cluster_spec

    def _build_head_group_spec(self) -> Dict[str, Any]:
        """Build the head group specification."""
        return {
            "serviceType": "ClusterIP",
            "enableIngress": False,
            "rayStartParams": self._build_head_ray_params(),
            "template": V1PodTemplateSpec(
                metadata=V1ObjectMeta(annotations=self.annotations),
                spec=self._build_pod_spec(self._build_head_container(), is_head=True),
            ),
        }

    def _build_worker_group_spec(self, cluster_name: str) -> Dict[str, Any]:
        """Build the worker group specification."""
        return {
            "replicas": self.num_workers,
            "minReplicas": self.num_workers,
            "maxReplicas": self.num_workers,
            "groupName": f"worker-group-{cluster_name}",
            "rayStartParams": self._build_worker_ray_params(),
            "template": V1PodTemplateSpec(
                metadata=V1ObjectMeta(annotations=self.annotations),
                spec=self._build_pod_spec(
                    self._build_worker_container(),
                    is_head=False,
                ),
            ),
        }

    def _build_head_ray_params(self) -> Dict[str, str]:
        """Build Ray start parameters for head node."""
        params = {
            "dashboard-host": "0.0.0.0",
            "block": "true",
        }

        if self.head_accelerators:
            gpu_count = sum(
                count
                for resource_type, count in self.head_accelerators.items()
                if "gpu" in resource_type.lower()
            )
            if gpu_count > 0:
                params["num-gpus"] = str(gpu_count)

        return params

    def _build_worker_ray_params(self) -> Dict[str, str]:
        """Build Ray start parameters for worker nodes."""
        params = {
            "block": "true",
        }

        if self.worker_accelerators:
            gpu_count = sum(
                count
                for resource_type, count in self.worker_accelerators.items()
                if "gpu" in resource_type.lower()
            )
            if gpu_count > 0:
                params["num-gpus"] = str(gpu_count)

        return params

    def _build_head_container(self) -> V1Container:
        """Build the head container specification."""
        container = V1Container(
            name="ray-head",
            image=update_image(self.image),
            image_pull_policy="IfNotPresent",
            ports=[
                V1ContainerPort(name="gcs", container_port=6379),
                V1ContainerPort(name="dashboard", container_port=8265),
                V1ContainerPort(name="client", container_port=10001),
            ],
            lifecycle=V1Lifecycle(
                pre_stop=V1LifecycleHandler(
                    _exec=V1ExecAction(command=["/bin/sh", "-c", "ray stop"])
                )
            ),
            resources=self._build_resource_requirements(
                self.head_cpu_requests,
                self.head_cpu_limits,
                self.head_memory_requests,
                self.head_memory_limits,
                self.head_accelerators,
            ),
            volume_mounts=self._generate_volume_mounts(),
            env=self._build_env_vars() if self.envs else None,
        )

        return container

    def _build_worker_container(self) -> V1Container:
        """Build the worker container specification."""
        container = V1Container(
            name="ray-worker",
            image=update_image(self.image),
            image_pull_policy="IfNotPresent",
            lifecycle=V1Lifecycle(
                pre_stop=V1LifecycleHandler(
                    _exec=V1ExecAction(command=["/bin/sh", "-c", "ray stop"])
                )
            ),
            resources=self._build_resource_requirements(
                self.worker_cpu_requests,
                self.worker_cpu_limits,
                self.worker_memory_requests,
                self.worker_memory_limits,
                self.worker_accelerators,
            ),
            volume_mounts=self._generate_volume_mounts(),
            env=self._build_env_vars() if self.envs else None,
        )

        return container

    def _build_resource_requirements(
        self,
        cpu_requests: Union[int, str],
        cpu_limits: Union[int, str],
        memory_requests: Union[int, str],
        memory_limits: Union[int, str],
        accelerators: Dict[str, Union[int, str]] = None,
    ) -> V1ResourceRequirements:
        """Build Kubernetes resource requirements."""
        resource_requirements = V1ResourceRequirements(
            requests={"cpu": cpu_requests, "memory": memory_requests},
            limits={"cpu": cpu_limits, "memory": memory_limits},
        )

        if accelerators:
            for resource_type, amount in accelerators.items():
                resource_requirements.limits[resource_type] = amount
                resource_requirements.requests[resource_type] = amount

        return resource_requirements

    def _build_pod_spec(self, container: V1Container, is_head: bool) -> V1PodSpec:
        """Build the pod specification."""
        pod_spec = V1PodSpec(
            containers=[container],
            volumes=self._generate_volumes(),
            restart_policy="Never",
        )

        if is_head and self.head_tolerations:
            pod_spec.tolerations = self.head_tolerations
        elif not is_head and self.worker_tolerations:
            pod_spec.tolerations = self.worker_tolerations

        if self.image_pull_secrets:
            pod_spec.image_pull_secrets = [
                V1LocalObjectReference(name=secret)
                for secret in self.image_pull_secrets
            ]

        return pod_spec

    def _generate_volume_mounts(self) -> list:
        """Generate volume mounts for the container."""
        volume_mounts = []
        if self.volume_mounts:
            volume_mounts.extend(self.volume_mounts)
        return volume_mounts

    def _generate_volumes(self) -> list:
        """Generate volumes for the pod."""
        volumes = []
        if self.volumes:
            volumes.extend(self.volumes)
        return volumes

    def _build_env_vars(self) -> list:
        """Build environment variables list."""
        return [V1EnvVar(name=key, value=value) for key, value in self.envs.items()]

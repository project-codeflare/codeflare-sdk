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
from typing import Dict, List, Optional, Union, get_args, get_origin
from kubernetes.client import V1Toleration, V1Volume, V1VolumeMount

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


@dataclass
class ClusterConfiguration:
    """
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
    head_cpu_requests: Union[int, str] = 2
    head_cpu_limits: Union[int, str] = 2
    head_memory_requests: Union[int, str] = 8
    head_memory_limits: Union[int, str] = 8
    head_extended_resource_requests: Dict[str, Union[str, int]] = field(
        default_factory=dict
    )
    head_tolerations: Optional[List[V1Toleration]] = None
    worker_cpu_requests: Union[int, str] = 1
    worker_cpu_limits: Union[int, str] = 1
    num_workers: int = 1
    worker_memory_requests: Union[int, str] = 2
    worker_memory_limits: Union[int, str] = 2
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

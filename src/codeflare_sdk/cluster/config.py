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

from dataclasses import dataclass, field
import pathlib
import typing
import warnings

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

    Attributes:
    - name: The name of the cluster.
    - namespace: The namespace in which the cluster should be created.
    - head_info: A list of strings containing information about the head node.
    - head_cpus: The number of CPUs to allocate to the head node.
    - head_memory: The amount of memory to allocate to the head node.
    - head_gpus: The number of GPUs to allocate to the head node. (Deprecated, use head_extended_resource_requests)
    - head_extended_resource_requests: A dictionary of extended resource requests for the head node. ex: {"nvidia.com/gpu": 1}
    - machine_types: A list of machine types to use for the cluster.
    - min_cpus: The minimum number of CPUs to allocate to each worker.
    - max_cpus: The maximum number of CPUs to allocate to each worker.
    - num_workers: The number of workers to create.
    - min_memory: The minimum amount of memory to allocate to each worker.
    - max_memory: The maximum amount of memory to allocate to each worker.
    - num_gpus: The number of GPUs to allocate to each worker. (Deprecated, use worker_extended_resource_requests)
    - template: The path to the template file to use for the cluster.
    - appwrapper: A boolean indicating whether to use an AppWrapper.
    - envs: A dictionary of environment variables to set for the cluster.
    - image: The image to use for the cluster.
    - image_pull_secrets: A list of image pull secrets to use for the cluster.
    - write_to_file: A boolean indicating whether to write the cluster configuration to a file.
    - verify_tls: A boolean indicating whether to verify TLS when connecting to the cluster.
    - labels: A dictionary of labels to apply to the cluster.
    - worker_extended_resource_requests: A dictionary of extended resource requests for each worker. ex: {"nvidia.com/gpu": 1}
    - custom_resource_mapping: A dictionary of custom resource mappings to map extended resource requests to RayCluster resource names
    - overwrite_default_resource_mapping: A boolean indicating whether to overwrite the default resource mapping.
    """

    name: str
    namespace: str = None
    head_info: list = field(default_factory=list)
    head_cpus: typing.Union[int, str] = 2
    head_memory: typing.Union[int, str] = 8
    head_gpus: int = 0
    head_extended_resource_requests: typing.Dict[str, int] = field(default_factory=dict)
    machine_types: list = field(default_factory=list)  # ["m4.xlarge", "g4dn.xlarge"]
    min_cpus: typing.Union[int, str] = 1
    max_cpus: typing.Union[int, str] = 1
    num_workers: int = 1
    min_memory: typing.Union[int, str] = 2
    max_memory: typing.Union[int, str] = 2
    num_gpus: int = 0
    template: str = f"{dir}/templates/base-template.yaml"
    appwrapper: bool = False
    envs: dict = field(default_factory=dict)
    image: str = ""
    image_pull_secrets: list = field(default_factory=list)
    write_to_file: bool = False
    verify_tls: bool = True
    labels: dict = field(default_factory=dict)
    worker_extended_resource_requests: typing.Dict[str, int] = field(
        default_factory=dict
    )
    custom_resource_mapping: typing.Dict[str, str] = field(default_factory=dict)
    overwrite_default_resource_mapping: bool = False

    def __post_init__(self):
        if not self.verify_tls:
            print(
                "Warning: TLS verification has been disabled - Endpoint checks will be bypassed"
            )
        self._memory_to_string()
        self._str_mem_no_unit_add_GB()
        self._gpu_to_resource()
        self._combine_custom_resource_mapping()

    def _combine_custom_resource_mapping(self):
        if overwritten := set(self.custom_resource_mapping.keys()).intersection(
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
        self.custom_resource_mapping = {
            **DEFAULT_RESOURCE_MAPPING,
            **self.custom_resource_mapping,
        }

    def _gpu_to_resource(self):
        if self.head_gpus:
            warnings.warn(
                'head_gpus is being deprecated, use head_custom_resource_requests={"nvidia.com/gpu": <num_gpus>}'
            )
            if "nvidia.com/gpu" in self.head_extended_resource_requests:
                raise ValueError(
                    "nvidia.com/gpu already exists in head_custom_resource_requests"
                )
            self.head_extended_resource_requests["nvidia.com/gpu"] = self.head_gpus
        if self.num_gpus:
            warnings.warn(
                'num_gpus is being deprecated, use worker_custom_resource_requests={"nvidia.com/gpu": <num_gpus>}'
            )
            if "nvidia.com/gpu" in self.worker_extended_resource_requests:
                raise ValueError(
                    "nvidia.com/gpu already exists in worker_custom_resource_requests"
                )
            self.worker_extended_resource_requests["nvidia.com/gpu"] = self.num_gpus

    def _str_mem_no_unit_add_GB(self):
        if isinstance(self.head_memory, str) and self.head_memory.isdecimal():
            self.head_memory = f"{self.head_memory}G"
        if isinstance(self.min_memory, str) and self.min_memory.isdecimal():
            self.min_memory = f"{self.min_memory}G"
        if isinstance(self.max_memory, str) and self.max_memory.isdecimal():
            self.max_memory = f"{self.max_memory}G"

    def _memory_to_string(self):
        if isinstance(self.head_memory, int):
            self.head_memory = f"{self.head_memory}G"
        if isinstance(self.min_memory, int):
            self.min_memory = f"{self.min_memory}G"
        if isinstance(self.max_memory, int):
            self.max_memory = f"{self.max_memory}G"

    local_queue: str = None

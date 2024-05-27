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


@dataclass
class ClusterConfiguration:
    """
    This dataclass is used to specify resource requirements and other details, and
    is passed in as an argument when creating a Cluster object.
    """

    name: str
    namespace: str = None
    head_info: list = field(default_factory=list)
    head_cpus: typing.Union[int, str] = 2
    head_memory: typing.Union[int, str] = 8
    head_gpus: int = None  # Deprecating
    num_head_gpus: int = 0
    machine_types: list = field(default_factory=list)  # ["m4.xlarge", "g4dn.xlarge"]
    worker_cpu_requests: typing.Union[int, str] = 1
    worker_cpu_limits: typing.Union[int, str] = 1
    min_cpus: typing.Union[int, str] = None  # Deprecating
    max_cpus: typing.Union[int, str] = None  # Deprecating
    num_workers: int = 1
    worker_memory_requests: typing.Union[int, str] = 2
    worker_memory_limits: typing.Union[int, str] = 2
    min_memory: typing.Union[int, str] = None  # Deprecating
    max_memory: typing.Union[int, str] = None  # Deprecating
    num_worker_gpus: int = 0
    num_gpus: int = None  # Deprecating
    template: str = f"{dir}/templates/base-template.yaml"
    appwrapper: bool = False
    envs: dict = field(default_factory=dict)
    image: str = ""
    image_pull_secrets: list = field(default_factory=list)
    write_to_file: bool = False
    verify_tls: bool = True
    labels: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.verify_tls:
            print(
                "Warning: TLS verification has been disabled - Endpoint checks will be bypassed"
            )

        self._memory_to_string()
        self._str_mem_no_unit_add_GB()
        self._memory_to_resource()
        self._gpu_to_resource()
        self._cpu_to_resource()

    def _str_mem_no_unit_add_GB(self):
        if isinstance(self.head_memory, str) and self.head_memory.isdecimal():
            self.head_memory = f"{self.head_memory}G"
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
        if isinstance(self.head_memory, int):
            self.head_memory = f"{self.head_memory}G"
        if isinstance(self.worker_memory_requests, int):
            self.worker_memory_requests = f"{self.worker_memory_requests}G"
        if isinstance(self.worker_memory_limits, int):
            self.worker_memory_limits = f"{self.worker_memory_limits}G"

    def _gpu_to_resource(self):
        if self.head_gpus:
            warnings.warn("head_gpus is being deprecated, use num_head_gpus")
            self.num_head_gpus = self.head_gpus
        if self.num_gpus:
            warnings.warn("num_gpus is being deprecated, use num_worker_gpus")
            self.num_worker_gpus = self.num_gpus

    def _cpu_to_resource(self):
        if self.min_cpus:
            warnings.warn("min_cpus is being deprecated, use worker_cpu_requests")
            self.worker_cpu_requests = self.min_cpus
        if self.max_cpus:
            warnings.warn("max_cpus is being deprecated, use worker_cpu_limits")
            self.worker_cpu_limits = self.max_cpus

    def _memory_to_resource(self):
        if self.min_memory:
            warnings.warn("min_memory is being deprecated, use worker_memory_requests")
            self.worker_memory_requests = f"{self.min_memory}G"
        if self.max_memory:
            warnings.warn("max_memory is being deprecated, use worker_memory_limits")
            self.worker_memory_limits = f"{self.max_memory}G"

    local_queue: str = None

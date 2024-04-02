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

dir = pathlib.Path(__file__).parent.parent.resolve()


VALID_MEMORY_SUFFIXES = ["m", "k", "M", "G", "T", "P", "E"]
VALID_CPU_SUFFIXES = ["m"]


@dataclass
class ClusterConfiguration:
    """
    This dataclass is used to specify resource requirements and other details, and
    is passed in as an argument when creating a Cluster object.
    """

    name: str
    namespace: str = None
    head_info: list = field(default_factory=list)
    head_cpus: typing.Union[float, str] = 2
    head_memory: typing.Union[float, str] = 8
    head_gpus: int = 0
    machine_types: list = field(default_factory=list)  # ["m4.xlarge", "g4dn.xlarge"]
    min_cpus: typing.Union[float, str] = 1
    max_cpus: typing.Union[float, str] = 1
    num_workers: int = 1
    min_memory: typing.Union[float, str] = 2
    max_memory: typing.Union[float, str] = 2
    num_gpus: int = 0
    template: str = f"{dir}/templates/base-template.yaml"
    instascale: bool = False
    mcad: bool = True
    envs: dict = field(default_factory=dict)
    image: str = ""
    local_interactive: bool = False
    image_pull_secrets: list = field(default_factory=list)
    dispatch_priority: str = None
    openshift_oauth: bool = False  # NOTE: to use the user must have permission to create a RoleBinding for system:auth-delegator
    ingress_options: dict = field(default_factory=dict)
    ingress_domain: str = None
    write_to_file: bool = False

    def __post_init__(self):
        self._validate_cpu(self.head_cpus)
        self._validate_memory(self.head_memory)
        self._validate_cpu(self.min_cpus)
        self._validate_cpu(self.max_cpus)
        self._validate_memory(self.min_memory)
        self._validate_memory(self.max_memory)

    def _validate_cpu(self, cpu):
        if isinstance(cpu, str):
            if cpu[-1] not in VALID_CPU_SUFFIXES:
                raise ValueError(f"Invalid CPU value: {cpu}")

    def _validate_memory(self, memory):
        if isinstance(memory, str):
            if memory[-1] not in VALID_MEMORY_SUFFIXES:
                raise ValueError(f"Invalid memory value: {memory}")

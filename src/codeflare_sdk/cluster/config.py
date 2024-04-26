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
    head_gpus: int = 0
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

    def __post_init__(self):
        if not self.verify_tls:
            print(
                "Warning: TLS verification has been disabled - Endpoint checks will be bypassed"
            )
        self._memory_to_string()
        self._str_mem_no_unit_add_GB()

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

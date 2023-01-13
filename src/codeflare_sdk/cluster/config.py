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
from .auth import Authentication
import pathlib

dir = pathlib.Path(__file__).parent.parent.resolve()


@dataclass
class ClusterConfiguration:
    """
    This dataclass is used to specify resource requirements and other details, and
    is passed in as an argument when creating a Cluster object.
    """

    name: str
    namespace: str = "default"
    head_info: list = field(default_factory=list)
    machine_types: list = field(default_factory=list)  # ["m4.xlarge", "g4dn.xlarge"]
    min_cpus: int = 1
    max_cpus: int = 1
    min_worker: int = 1
    max_worker: int = 1
    min_memory: int = 2
    max_memory: int = 2
    gpu: int = 0
    template: str = f"{dir}/templates/new-template.yaml"
    instascale: bool = False
    envs: dict = field(default_factory=dict)
    image: str = "ghcr.io/foundation-model-stack/base:ray2.1.0-py38-gpu-pytorch1.12.0cu116-20221213-193103"
    auth: Authentication = Authentication()

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
    head_cpus: int = 2
    head_memory: int = 8
    head_gpus: int = 0
    machine_types: list = field(default_factory=list)  # ["m4.xlarge", "g4dn.xlarge"]
    min_cpus: int = 1
    max_cpus: int = 1
    num_workers: int = 1
    min_memory: int = 2
    max_memory: int = 2
    num_gpus: int = 0
    template: str = f"{dir}/templates/base-template.yaml"
    instascale: bool = False
    mcad: bool = True
    envs: dict = field(default_factory=dict)
    image: str = "quay.io/project-codeflare/ray@sha256:1ddf39c1bbb182bc9f9c477fa0003902506013f8721f7e203673f965156f5559"
    local_interactive: bool = False
    image_pull_secrets: list = field(default_factory=list)
    dispatch_priority: str = None
    openshift_oauth: bool = False  # NOTE: to use the user must have permission to create a RoleBinding for system:auth-delegator
    ingress_options: dict = field(default_factory=dict)
    ingress_domain: str = None

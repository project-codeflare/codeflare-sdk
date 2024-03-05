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
import warnings

dir = pathlib.Path(__file__).parent.parent.resolve()

# NOTE: this isn't an enum because the values for ray custom resources can be arbitrary strings
DEFAULT_CUSTOM_RESOURCE_MAPPING = {
    "nvidia.com/gpu": "GPU",
    "gpu.intel.com/i915": "GPU",
    "habana.ai/gaudi": "HPU",
    "google.com/tpu": "TPU",
}


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
    image: str = ""
    local_interactive: bool = False
    image_pull_secrets: list = field(default_factory=list)
    dispatch_priority: str = None
    openshift_oauth: bool = False  # NOTE: to use the user must have permission to create a RoleBinding for system:auth-delegator
    ingress_options: dict = field(default_factory=dict)
    ingress_domain: str = None
    head_custom_resources: dict = field(default_factory=dict)
    worker_custom_resources: dict = field(default_factory=dict)
    custom_resource_mapping: dict = field(
        default_factory=dict
    )  # for custom resources not in the default mapping

    def __post_init__(self):
        if (
            self.head_gpus
            and self.head_custom_resources
            or self.num_gpus
            and self.worker_custom_resources
        ):
            raise ValueError(
                "Cannot set both head_gpus and head_custom_resources or num_gpus and worker_custom_resources"
            )
        if self.head_gpus != 0:
            warnings.warn(
                "head_gpus being deprecated, use gpu_custom_resources with resource 'nvidia.com/gpu'",
                PendingDeprecationWarning,
            )
            self.head_custom_resources["nvidia.com/gpu"] = self.head_gpus
        if self.num_gpus != 0:
            warnings.warn(
                "num_gpus being deprecated use worker_custom_resources with resource 'nvidia.com/gpu'",
                PendingDeprecationWarning,
            )
            self.worker_custom_resources["nvidia.com/gpu"] = self.num_gpus
            pass

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

"""
The status sub-module defines Enums containing information for Ray cluster
states states, and CodeFlare cluster states, as well as
dataclasses to store information for Ray clusters.
"""

from dataclasses import dataclass, field
from enum import Enum
import typing
from typing import Union, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..rayjobs.status import KueueWorkloadInfo


class RayClusterStatus(Enum):
    """
    Defines the possible reportable states of a Ray cluster.
    """

    # https://github.com/ray-project/kuberay/blob/master/ray-operator/apis/ray/v1/raycluster_types.go#L112-L117
    READY = "ready"
    UNHEALTHY = "unhealthy"
    FAILED = "failed"
    UNKNOWN = "unknown"
    SUSPENDED = "suspended"


class CodeFlareClusterStatus(Enum):
    """
    Defines the possible reportable states of a Codeflare cluster.
    """

    READY = 1
    STARTING = 2
    QUEUED = 3
    QUEUEING = 4
    FAILED = 5
    UNKNOWN = 6
    SUSPENDED = 7


@dataclass
class RayCluster:
    """
    For storing information about a Ray cluster.
    
    Attributes:
        name: Name of the RayCluster
        status: Current status of the cluster
        head_cpu_requests: CPU requests for head node
        head_cpu_limits: CPU limits for head node
        head_mem_requests: Memory requests for head node
        head_mem_limits: Memory limits for head node
        num_workers: Number of worker nodes
        worker_mem_requests: Memory requests per worker
        worker_mem_limits: Memory limits per worker
        worker_cpu_requests: CPU requests per worker
        worker_cpu_limits: CPU limits per worker
        namespace: Kubernetes namespace
        dashboard: Dashboard URL
        worker_extended_resources: Extended resources for workers (e.g., GPUs)
        head_extended_resources: Extended resources for head node
        local_queue: Kueue LocalQueue name (if managed by Kueue)
        kueue_workload: Kueue workload information (if managed by Kueue)
        is_appwrapper: Whether cluster is managed by AppWrapper
    """

    name: str
    status: RayClusterStatus
    head_cpu_requests: int
    head_cpu_limits: int
    head_mem_requests: str
    head_mem_limits: str
    num_workers: int
    worker_mem_requests: str
    worker_mem_limits: str
    worker_cpu_requests: Union[int, str]
    worker_cpu_limits: Union[int, str]
    namespace: str
    dashboard: str
    worker_extended_resources: typing.Dict[str, int] = field(default_factory=dict)
    head_extended_resources: typing.Dict[str, int] = field(default_factory=dict)
    local_queue: Optional[str] = None
    kueue_workload: Optional["KueueWorkloadInfo"] = None
    is_appwrapper: bool = False

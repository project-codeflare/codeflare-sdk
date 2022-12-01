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
The model sub-module defines Enums containing information for Ray cluster
states and AppWrapper states, and CodeFlare cluster states, as well as
dataclasses to store information for Ray clusters and AppWrappers.
"""

from dataclasses import dataclass
from enum import Enum


class RayClusterStatus(Enum):
    """
    Defines the possible reportable states of a Ray cluster.
    """

    # https://github.com/ray-project/kuberay/blob/master/ray-operator/apis/ray/v1alpha1/raycluster_types.go#L95
    READY = "ready"
    UNHEALTHY = "unhealthy"
    FAILED = "failed"
    UNKNOWN = "unknown"


class AppWrapperStatus(Enum):
    """
    Defines the possible reportable states of an AppWrapper.
    """

    PENDING = "pending"
    RUNNING = "running"
    FAILED = "failed"
    DELETED = "deleted"
    COMPLETED = "completed"
    RUNNING_HOLD_COMPLETION = "runningholdcompletion"


class CodeFlareClusterStatus(Enum):
    """
    Defines the possible reportable states of a Codeflare cluster.
    """

    READY = 1
    QUEUED = 2
    FAILED = 3
    UNKNOWN = 4


@dataclass
class RayCluster:
    """
    For storing information about a Ray cluster.
    """

    name: str
    status: RayClusterStatus
    min_workers: int
    max_workers: int
    worker_mem_min: str
    worker_mem_max: str
    worker_cpu: int
    worker_gpu: int
    namespace: str
    dashboard: str


@dataclass
class AppWrapper:
    """
    For storing information about an AppWrapper.
    """

    name: str
    status: AppWrapperStatus
    can_run: bool
    job_state: str

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

from dataclasses import dataclass, field
from enum import Enum
import typing


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


class AppWrapperStatus(Enum):
    """
    Defines the possible reportable phases of an AppWrapper.
    """

    SUSPENDED = "suspended"
    RESUMING = "resuming"
    RUNNING = "running"
    RESETTING = "resetting"
    SUSPENDING = "suspending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TERMINATING = "terminating"


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
    """

    name: str
    status: RayClusterStatus
    head_cpus: int
    head_mem: str
    workers: int
    worker_mem_min: str
    worker_mem_max: str
    worker_cpu: int
    namespace: str
    dashboard: str
    worker_extended_resources: typing.Dict[str, int] = field(default_factory=dict)
    head_extended_resources: typing.Dict[str, int] = field(default_factory=dict)


@dataclass
class AppWrapper:
    """
    For storing information about an AppWrapper.
    """

    name: str
    status: AppWrapperStatus

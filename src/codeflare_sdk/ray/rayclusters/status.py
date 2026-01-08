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
Status enums and info classes for RayCluster.

This module defines:
- RayClusterStatus: Enum of possible cluster states from KubeRay
- CodeFlareClusterStatus: Enum of higher-level SDK states
- RayClusterInfo: Dataclass combining RayCluster with runtime status/dashboard
"""

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .raycluster import RayCluster


class RayClusterStatus(Enum):
    """
    Defines the possible reportable states of a Ray cluster.

    These values correspond to the states reported by the KubeRay operator.
    """

    # https://github.com/ray-project/kuberay/blob/master/ray-operator/apis/ray/v1/raycluster_types.go#L112-L117
    READY = "ready"
    UNHEALTHY = "unhealthy"
    FAILED = "failed"
    UNKNOWN = "unknown"
    SUSPENDED = "suspended"


class CodeFlareClusterStatus(Enum):
    """
    Defines the possible reportable states of a CodeFlare-managed cluster.

    These are higher-level states used by the CodeFlare SDK to represent
    the cluster lifecycle from the user's perspective.
    """

    READY = 1
    STARTING = 2
    QUEUED = 3
    QUEUEING = 4
    FAILED = 5
    UNKNOWN = 6
    SUSPENDED = 7


@dataclass
class RayClusterInfo:
    """
    Runtime information about a Ray cluster.

    Combines a RayCluster configuration with its current runtime state
    (status and dashboard URL) obtained from Kubernetes.
    """

    cluster: "RayCluster"
    status: RayClusterStatus
    dashboard: str

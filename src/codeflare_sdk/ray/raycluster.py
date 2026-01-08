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
Alias module for backwards compatibility.
Re-exports everything from the rayclusters package.
"""

from .rayclusters import (
    RayCluster,
    RayClusterStatus,
    CodeFlareClusterStatus,
    RayClusterInfo,
    get_cluster,
    list_all_clusters,
    list_all_queued,
)

from .rayclusters.raycluster import DEFAULT_ACCELERATOR_CONFIGS

__all__ = [
    "RayCluster",
    "RayClusterStatus",
    "CodeFlareClusterStatus",
    "RayClusterInfo",
    "DEFAULT_ACCELERATOR_CONFIGS",
    "get_cluster",
    "list_all_clusters",
    "list_all_queued",
]

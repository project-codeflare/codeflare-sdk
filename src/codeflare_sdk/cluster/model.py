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

from dataclasses import dataclass
from enum import Enum

class RayClusterStatus(Enum):
    #https://github.com/ray-project/kuberay/blob/master/ray-operator/apis/ray/v1alpha1/raycluster_types.go#L95
    READY = "ready"
    UNHEALTHY = "unhealthy"
    FAILED = "failed"
    UNKNOWN = "unknown"

class AppWrapperStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    FAILED = "failed"
    DELETED = "deleted"
    COMPLETED = "completed"
    RUNNING_HOLD_COMPLETION = "runningholdcompletion"

class CodeFlareClusterStatus(Enum):
    READY = 1
    QUEUED = 2
    FAILED = 3
    UNKNOWN = 4
@dataclass
class RayCluster:
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
    name: str
    status:AppWrapperStatus
    can_run: bool
    job_state: str


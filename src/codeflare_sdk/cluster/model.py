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

@dataclass
class AppWrapper:
    name: str
    status:AppWrapperStatus
    can_run: bool
    job_state: str


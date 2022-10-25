from dataclasses import dataclass

@dataclass
class RayCluster:
    name: str
    status: str
    min_workers: int
    max_workers: int
    worker_mem_min: str
    worker_mem_max: str
    worker_cpu: int
    worker_gpu: int

@dataclass
class AppWrapper:
    name: str
    status:str
    can_run: bool
    job_state: str

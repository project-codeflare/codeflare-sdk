from dataclasses import dataclass

@dataclass
class ClusterConfiguration:
    name: str
    min_cpus: int = 1
    max_cpus: int = 1
    min_worker: int = 0
    max_worker: int = 1

from dataclasses import dataclass

@dataclass
class ClusterConfiguration:
    min_cpus: int
    max_cpus: int
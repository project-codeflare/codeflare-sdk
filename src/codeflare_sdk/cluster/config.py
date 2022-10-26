from dataclasses import dataclass, field
import pathlib

dir = pathlib.Path(__file__).parent.parent.resolve()

@dataclass
class ClusterConfiguration:
    name: str
    head_info: list = field(default_factory=list)
    machine_types: list = field(default_factory=list) #["m4.xlarge", "g4dn.xlarge"]
    min_cpus: int = 1
    max_cpus: int = 1
    min_worker: int = 1
    max_worker: int = 1
    min_memory: int = 2
    max_memory: int = 2
    gpu: int = 0
    template: str = f"{dir}/templates/new-template.yaml"
    instascale: bool = False
    envs: dict = field(default_factory=dict)
    image: str = "ghcr.io/ibm-ai-foundation/base:ray1.13.0-py38-gpu-pytorch1.12.0cu116-20220826-202124"

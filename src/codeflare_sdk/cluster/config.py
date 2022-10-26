from dataclasses import dataclass

@dataclass
class ClusterConfiguration:
    name: str
    head_info: list = []
    machine_types: list = ["m4.xlarge", "g4dn.xlarge"]
    min_cpus: int = 1
    max_cpus: int = 1
    min_worker: int = 1
    max_worker: int = 1
    min_memory: int = 2
    max_memory: int = 2
    gpu: int = 0
    template: str = "src/codeflare_sdk/templates/new-template.yaml"
    instascale: bool = False
    envs: dict = {}
    image: str = "rayproject/ray:latest"

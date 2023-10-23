# Copyright 2023 IBM, Red Hat
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


import abc
from typing import TYPE_CHECKING, Optional, Dict, List
from pathlib import Path

from torchx.components.dist import ddp
from torchx.runner import get_runner, Runner
from torchx.schedulers.ray_scheduler import RayScheduler
from torchx.specs import AppHandle, parse_app_handle, AppDryRunInfo


if TYPE_CHECKING:
    from ..cluster.cluster import Cluster
from ..cluster.cluster import get_current_namespace

all_jobs: List["Job"] = []


class JobDefinition(metaclass=abc.ABCMeta):
    def _dry_run(self, cluster: "Cluster"):
        pass

    def submit(self, cluster: "Cluster"):
        pass


class Job(metaclass=abc.ABCMeta):
    def status(self):
        pass

    def logs(self):
        pass


class DDPJobDefinition(JobDefinition):
    def __init__(
        self,
        script: Optional[str] = None,
        m: Optional[str] = None,
        script_args: Optional[List[str]] = None,
        name: Optional[str] = None,
        cpu: Optional[int] = None,
        gpu: Optional[int] = None,
        memMB: Optional[int] = None,
        h: Optional[str] = None,
        j: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        max_retries: int = 0,
        mounts: Optional[List[str]] = None,
        rdzv_port: int = 29500,
        rdzv_backend: str = None,
        scheduler_args: Optional[Dict[str, str]] = None,
        image: Optional[str] = None,
        workspace: Optional[str] = f"file://{Path.cwd()}",
    ):
        if bool(script) == bool(m):  # logical XOR
            raise ValueError(
                "Exactly one of the following arguments must be defined: [script, m]."
            )
        self.script = script
        self.m = m
        self.script_args: List[str] = script_args if script_args is not None else []
        self.name = name
        self.cpu = cpu
        self.gpu = gpu
        self.memMB = memMB
        self.h = h
        self.j = j
        self.env: Dict[str, str] = env if env is not None else dict()
        self.max_retries = max_retries
        self.mounts: List[str] = mounts if mounts is not None else []
        self.rdzv_port = rdzv_port
        self.rdzv_backend = rdzv_backend
        self.scheduler_args: Dict[str, str] = (
            scheduler_args if scheduler_args is not None else dict()
        )
        self.image = image
        self.workspace = workspace

    def _dry_run(self, cluster: "Cluster"):
        j = f"{cluster.config.num_workers}x{max(cluster.config.num_gpus, 1)}"  # # of proc. = # of gpus
        runner = get_runner(ray_client=cluster.job_client)
        runner._scheduler_instances["ray"] = RayScheduler(
            session_name=runner._name, ray_client=cluster.job_client
        )
        return (
            runner.dryrun(
                app=ddp(
                    *self.script_args,
                    script=self.script,
                    m=self.m,
                    name=self.name,
                    h=self.h,
                    cpu=self.cpu if self.cpu is not None else cluster.config.max_cpus,
                    gpu=self.gpu if self.gpu is not None else cluster.config.num_gpus,
                    memMB=self.memMB
                    if self.memMB is not None
                    else cluster.config.max_memory * 1024,
                    j=self.j if self.j is not None else j,
                    env=self.env,
                    max_retries=self.max_retries,
                    rdzv_port=self.rdzv_port,
                    rdzv_backend=self.rdzv_backend
                    if self.rdzv_backend is not None
                    else "static",
                    mounts=self.mounts,
                ),
                scheduler=cluster.torchx_scheduler,
                cfg=cluster.torchx_config(**self.scheduler_args),
                workspace=self.workspace,
            ),
            runner,
        )

    def _missing_spec(self, spec: str):
        raise ValueError(f"Job definition missing arg: {spec}")

    def _dry_run_no_cluster(self):
        if self.scheduler_args is not None:
            if self.scheduler_args.get("namespace") is None:
                self.scheduler_args["namespace"] = get_current_namespace()
        runner = get_runner()
        return (
            runner.dryrun(
                app=ddp(
                    *self.script_args,
                    script=self.script,
                    m=self.m,
                    name=self.name
                    if self.name is not None
                    else self._missing_spec("name"),
                    h=self.h,
                    cpu=self.cpu
                    if self.cpu is not None
                    else self._missing_spec("cpu (# cpus per worker)"),
                    gpu=self.gpu
                    if self.gpu is not None
                    else self._missing_spec("gpu (# gpus per worker)"),
                    memMB=self.memMB
                    if self.memMB is not None
                    else self._missing_spec("memMB (memory in MB)"),
                    j=self.j
                    if self.j is not None
                    else self._missing_spec(
                        "j (`workers`x`procs`)"
                    ),  # # of proc. = # of gpus,
                    env=self.env,  # should this still exist?
                    max_retries=self.max_retries,
                    rdzv_port=self.rdzv_port,  # should this still exist?
                    rdzv_backend=self.rdzv_backend
                    if self.rdzv_backend is not None
                    else "c10d",
                    mounts=self.mounts,
                    image=self.image
                    if self.image is not None
                    else self._missing_spec("image"),
                ),
                scheduler="kubernetes_mcad",
                cfg=self.scheduler_args,
                workspace="",
            ),
            runner,
        )

    def submit(self, cluster: "Cluster" = None) -> "Job":
        return DDPJob(self, cluster)


class DDPJob(Job):
    def __init__(self, job_definition: "DDPJobDefinition", cluster: "Cluster" = None):
        self.job_definition = job_definition
        self.cluster = cluster
        if self.cluster:
            definition, runner = job_definition._dry_run(cluster)
            self._app_handle = runner.schedule(definition)
            self._runner = runner
        else:
            definition, runner = job_definition._dry_run_no_cluster()
            self._app_handle = runner.schedule(definition)
            self._runner = runner
        all_jobs.append(self)

    def status(self) -> str:
        return self._runner.status(self._app_handle)

    def logs(self) -> str:
        return "".join(self._runner.log_lines(self._app_handle, None))

    def cancel(self):
        self._runner.cancel(self._app_handle)

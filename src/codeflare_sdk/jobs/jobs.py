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

"""
The jobs sub-module contains the definitions for the Job objects, which represent
the methods by which a user can submit a job to a cluster, check the jobs status and 
access the jobs logs. 
"""

import abc
from typing import List
from pathlib import Path

from ray.job_submission import JobSubmissionClient
from torchx.components.dist import ddp
from torchx.runner import get_runner, Runner
from torchx.specs import AppHandle, parse_app_handle, AppDryRunInfo

from .config import JobConfiguration

import typing
if typing.TYPE_CHECKING:
    from ..cluster.cluster import Cluster

all_jobs: List["Job"] = []
torchx_runner: Runner = get_runner()

class JobDefinition(metaclass=abc.ABCMeta):
    """
    A job definition to be submitted to a generic backend cluster.
    """

    def _dry_run(self, cluster) -> str:
        """
        Create job definition, but do not submit.

        The primary purpose of this function is to facilitate unit testing.
        """

    def submit(self, cluster: "Cluster"):
        """
        Method for creating a job on a specific cluster
        """
        pass

class Job(metaclass=abc.ABCMeta):
    """
    An abstract class that defines the necessary methods for authenticating to a remote environment.
    Specifically, this class `status` and a `logs` function.
    """

    def status(self):
        """
        Method for retrieving the job's current status.
        """
        pass

    def logs(self):
        """
        Method for retrieving the job's logs.
        """


class TorchXJobDefinition(JobDefinition):
    def __init__(self, config: JobConfiguration):
        """
        Create the TorchXJob object by passing in a JobConfiguration
        (defined in the config sub-module).
        """
        self.config = config

    def _dry_run(self, cluster: "Cluster", *script_args) -> AppDryRunInfo:
        """
        Create job definition, but do not submit.

        The primary purpose of this function is to facilitate unit testing.
        """
        j = f"{cluster.config.max_worker}x{max(cluster.config.gpu, 1)}"  # # of proc. = # of gpus
        dashboard_address = f"{cluster.cluster_dashboard_uri(cluster.config.namespace).lstrip('http://')}"
        return torchx_runner.dryrun(
            app=ddp(
                *script_args,
                script = self.config.script,
                m=self.config.m,
                name=self.config.name,
                h=None,  # for custom resource types
                cpu=cluster.config.max_cpus,
                gpu = cluster.config.gpu,
                memMB = 1024 * cluster.config.max_memory,  # cluster memory is in GB
                j=j,
                env=self.config.env,
                # max_retries=0,  # default
                # mounts=None,  # default
            ),
            scheduler="ray",  # can be determined by type of cluster if more are introduced
            cfg={
                "cluster_name": cluster.config.name,
                "dashboard_address": dashboard_address,
                "working_dir": self.config.working_dir,
                "requirements": self.config.requirements,
            },
            workspace=f"file://{Path.cwd()}"
        )

    def submit(self, cluster: "Cluster") -> "TorchXRayJob":
        """
        Submit the job definition to a specific cluster, resulting in a Job object.
        """
        return TorchXRayJob(self, cluster)


class TorchXRayJob(Job):
    """
    Active submission of a dist.ddp job to a Ray cluster which can be used to get logs and status.
    """
    def __init__(self, job_definition: TorchXJobDefinition, cluster: "Cluster", *script_args):
        """
        Creates job which maximizes resource usage on the passed cluster.
        """
        self.job_definition: TorchXJobDefinition = job_definition
        self.cluster: "Cluster" = cluster
        self._app_handle = torchx_runner.schedule(job_definition._dry_run(cluster, *script_args))
        all_jobs.append(self)

    @property
    def job_id(self):
        if hasattr(self, "_job_id"):
            return self._job_id
        dashboard_address = f"{self.cluster.cluster_dashboard_uri(self.cluster.config.namespace).lstrip('http://')}:8265"
        _, _, job_id = parse_app_handle(self._app_handle)
        self._job_id = job_id.lstrip(f"{dashboard_address}-")

    def status(self) -> str:
        """
        Get running job status.
        """
        return torchx_runner.status(self._app_handle)

    def logs(self) -> str:
        """
        Get job logs.
        """
        return "".join(torchx_runner.log_lines(self._app_handle, None))

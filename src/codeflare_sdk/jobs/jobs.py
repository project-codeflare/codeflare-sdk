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

from ray.job_submission import JobSubmissionClient
from torchx.components.dist import ddp
from torchx.runner import get_runner, Runner
from torchx.specs import AppHandle, parse_app_handle

from .config import JobConfiguration

import typing
if typing.TYPE_CHECKING:
    from ..cluster.cluster import Cluster

all_jobs: List["Job"] = []
torchx_runner: Runner = get_runner()

torchx_runner.run(app, scheduler, cfg, workspace)

torchx_runner.run_component(component, component_args, scheduler, cfg, workspace)

class JobDefinition(metaclass=abc.ABCMeta):
    """
    A job definition to be submitted to a generic backend cluster.
    """

    def submit(self, cluster: Cluster):
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

    def submit(self, cluster: Cluster) -> "TorchXRayJob":
        """
        Submit the job definition to a specific cluster, resulting in a Job object.
        """
        return TorchXRayJob(self, cluster)


class TorchXRayJob(Job):
    """
    Active submission of a dist.ddp job to a Ray cluster which can be used to get logs and status.
    """
    def __init__(self, job_definition: TorchXJobDefinition, cluster: Cluster, *script_args):
        """
        TODO
        """
        self.job_definition: TorchXJobDefinition = job_definition
        self.cluster: Cluster = cluster
        j = f"{cluster.config.max_worker}x{max(cluster.config.gpu, 1)}"  # # of proc. = # of gpus
        # TODO: allow user to override resource allocation for job
        _app_handle: AppHandle = torchx_runner.run(
            app=ddp(
                *script_args,
                script = job_definition.config.script,
                m=None,  # python module to run (might be worth exposing)
                name = job_definition.config.name,
                h=None,  # for custom resource types
                cpu=cluster.config.max_cpus,  # TODO: get from cluster config
                gpu = cluster.config.gpu,
                memMB = 1024 * cluster.config.max_memory,  # cluster memory is in GB
                j=j,
                env=None,  # TODO: should definitely expose Dict[str, str]
                max_retries = 0,  # TODO: maybe expose
                mounts=None,  # TODO: maybe expose
                debug=False  # TODO: expose
            ),
            scheduler="ray", cfg="fo",
        )

        _, _, self.job_id = parse_app_handle(_app_handle)
        all_jobs.append(self)

    def status(self):
        """
        TODO
        """
        dashboard_route = self.cluster.cluster_dashboard_uri()
        client = JobSubmissionClient(dashboard_route)
        return client.get_job_status(self.job_id)

    def logs(self):
        """
        TODO
        """
        dashboard_route = self.cluster_dashboard_uri(namespace=self.config.namespace)
        client = JobSubmissionClient(dashboard_route)
        return client.get_job_logs(job_id)
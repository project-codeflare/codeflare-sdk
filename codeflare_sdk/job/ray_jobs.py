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
The ray_jobs sub-module contains methods needed to submit jobs and connect to Ray Clusters that were not created by CodeFlare.
The SDK acts as a wrapper for the Ray Job Submission Client.
"""
from ray.job_submission import JobSubmissionClient
from ray.dashboard.modules.job.pydantic_models import JobDetails
from typing import Iterator, Optional, Dict, Any, Union, List


class RayJobClient:
    """
    A class that functions as a wrapper for the Ray Job Submission Client.

    parameters:
    address -- Either (1) the address of the Ray cluster, or (2) the HTTP address of the dashboard server on the head node, e.g. “http://<head-node-ip>:8265”. In case (1) it must be specified as an address that can be passed to ray.init(),
    e.g. a Ray Client address (ray://<head_node_host>:10001), or “auto”, or “localhost:<port>”. If unspecified, will try to connect to a running local Ray cluster. This argument is always overridden by the RAY_ADDRESS environment variable.
    create_cluster_if_needed -- Indicates whether the cluster at the specified address needs to already be running. Ray doesn't start a cluster before interacting with jobs, but third-party job managers may do so.
    cookies -- Cookies to use when sending requests to the HTTP job server.
    metadata -- Arbitrary metadata to store along with all jobs. New metadata specified per job will be merged with the global metadata provided here via a simple dict update.
    headers -- Headers to use when sending requests to the HTTP job server, used for cases like authentication to a remote cluster.
    verify -- Boolean indication to verify the server's TLS certificate or a path to a file or directory of trusted certificates. Default: True.
    """

    def __init__(
        self,
        address: Optional[str] = None,
        create_cluster_if_needed: bool = False,
        cookies: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, Any]] = None,
        verify: Optional[Union[str, bool]] = True,
    ):
        self.rayJobClient = JobSubmissionClient(
            address=address,
            create_cluster_if_needed=create_cluster_if_needed,
            cookies=cookies,
            metadata=metadata,
            headers=headers,
            verify=verify,
        )

    def submit_job(
        self,
        entrypoint: str,
        job_id: Optional[str] = None,
        runtime_env: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, str]] = None,
        submission_id: Optional[str] = None,
        entrypoint_num_cpus: Optional[Union[int, float]] = None,
        entrypoint_num_gpus: Optional[Union[int, float]] = None,
        entrypoint_resources: Optional[Dict[str, float]] = None,
    ) -> str:
        """
        Method for submitting jobs to a Ray Cluster and returning the job id with entrypoint being a mandatory field.

        Parameters:
        entrypoint -- The shell command to run for this job.
        submission_id -- A unique ID for this job.
        runtime_env -- The runtime environment to install and run this job in.
        metadata -- Arbitrary data to store along with this job.
        job_id -- DEPRECATED. This has been renamed to submission_id
        entrypoint_num_cpus -- The quantity of CPU cores to reserve for the execution of the entrypoint command, separately from any tasks or actors launched by it. Defaults to 0.
        entrypoint_num_gpus -- The quantity of GPUs to reserve for the execution of the entrypoint command, separately from any tasks or actors launched by it. Defaults to 0.
        entrypoint_resources -- The quantity of custom resources to reserve for the execution of the entrypoint command, separately from any tasks or actors launched by it.
        """
        return self.rayJobClient.submit_job(
            entrypoint=entrypoint,
            job_id=job_id,
            runtime_env=runtime_env,
            metadata=metadata,
            submission_id=submission_id,
            entrypoint_num_cpus=entrypoint_num_cpus,
            entrypoint_num_gpus=entrypoint_num_gpus,
            entrypoint_resources=entrypoint_resources,
        )

    def delete_job(self, job_id: str) -> (bool, str):
        """
        Method for deleting jobs with the job id being a mandatory field.
        """
        deletion_status = self.rayJobClient.delete_job(job_id=job_id)

        if deletion_status:
            message = f"Successfully deleted Job {job_id}"
        else:
            message = f"Failed to delete Job {job_id}"

        return deletion_status, message

    def get_address(self) -> str:
        """
        Method for getting the address from the RayJobClient
        """
        return self.rayJobClient.get_address()

    def get_job_info(self, job_id: str):
        """
        Method for getting the job info with the job id being a mandatory field.
        """
        return self.rayJobClient.get_job_info(job_id=job_id)

    def get_job_logs(self, job_id: str) -> str:
        """
        Method for getting the job logs with the job id being a mandatory field.
        """
        return self.rayJobClient.get_job_logs(job_id=job_id)

    def get_job_status(self, job_id: str) -> str:
        """
        Method for getting the job's status with the job id being a mandatory field.
        """
        return self.rayJobClient.get_job_status(job_id=job_id)

    def list_jobs(self) -> List[JobDetails]:
        """
        Method for getting a list of current jobs in the Ray Cluster.
        """
        return self.rayJobClient.list_jobs()

    def stop_job(self, job_id: str) -> (bool, str):
        """
        Method for stopping a job with the job id being a mandatory field.
        """
        stop_job_status = self.rayJobClient.stop_job(job_id=job_id)
        if stop_job_status:
            message = f"Successfully stopped Job {job_id}"
        else:
            message = f"Failed to stop Job, {job_id} could have already completed."
        return stop_job_status, message

    def tail_job_logs(self, job_id: str) -> Iterator[str]:
        """
        Method for getting an iterator that follows the logs of a job with the job id being a mandatory field.
        """
        return self.rayJobClient.tail_job_logs(job_id=job_id)

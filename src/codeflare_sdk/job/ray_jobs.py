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
from typing import Iterator, Optional, Dict, Any, Union


class RayJobClient:
    """
    An object for that acts as the Ray Job Submission Client.
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

    def delete_job(self, job_id: str) -> bool:
        """
        Method for deleting jobs with the job id being a mandatory field.
        """
        return self.rayJobClient.delete_job(job_id=job_id)

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
        Method for getting the job info with the job id being a mandatory field.
        """
        return self.rayJobClient.get_job_logs(job_id=job_id)

    def get_job_status(self, job_id: str) -> str:
        """
        Method for getting the job's status with the job id being a mandatory field.
        """
        return self.rayJobClient.get_job_status(job_id=job_id)

    def list_jobs(self):
        """
        Method for getting a list of current jobs in the Ray Cluster.
        """
        return self.rayJobClient.list_jobs()

    def stop_job(self, job_id: str) -> bool:
        """
        Method for stopping a job with the job id being a mandatory field.
        """
        return self.rayJobClient.stop_job(job_id=job_id)

    def tail_job_logs(self, job_id: str) -> Iterator[str]:
        """
        Method for getting an iterator that follows the logs of a job with the job id being a mandatory field.
        """
        return self.rayJobClient.tail_job_logs(job_id=job_id)

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
    A wrapper class for the Ray Job Submission Client, used for interacting with Ray clusters to manage job
    submissions, deletions, and other job-related information.

    Args:
        address (Optional[str]):
            The Ray cluster's address, which may be either the Ray Client address, HTTP address
            of the dashboard server on the head node, or "auto" / "localhost:<port>" for a local cluster.
            This is overridden by the RAY_ADDRESS environment variable if set.
        create_cluster_if_needed (bool):
            If True, a new cluster will be created if not already running at the
            specified address. By default, Ray requires an existing cluster.
        cookies (Optional[Dict[str, Any]]):
            HTTP cookies to send with requests to the job server.
        metadata (Optional[Dict[str, Any]]):
            Global metadata to store with all jobs, merged with job-specific
            metadata during job submission.
        headers (Optional[Dict[str, Any]]):
            HTTP headers to send with requests to the job server, can be used for
            authentication.
        verify (Optional[Union[str, bool]]):
            If True, verifies the server's TLS certificate. Can also be a path
            to trusted certificates. Default is True.
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
        entrypoint_memory: Optional[int] = None,
        entrypoint_resources: Optional[Dict[str, float]] = None,
    ) -> str:
        """
        Submits a job to the Ray cluster with specified resources and returns the job ID.

        Args:
            entrypoint (str):
                The command to execute for this job.
            job_id (Optional[str]):
                Deprecated, use `submission_id`. A unique job identifier.
            runtime_env (Optional[Dict[str, Any]]):
                The runtime environment for this job.
            metadata (Optional[Dict[str, str]]):
                Metadata associated with the job, merged with global metadata.
            submission_id (Optional[str]):
                Unique ID for the job submission.
            entrypoint_num_cpus (Optional[Union[int, float]]):
                The quantity of CPU cores to reserve for the execution of the entrypoint command,
                separately from any tasks or actors launched by it. Defaults to 0.
            entrypoint_num_gpus (Optional[Union[int, float]]):
                The quantity of GPUs to reserve for the execution of the entrypoint command,
                separately from any tasks or actors launched by it. Defaults to 0.
            entrypoint_memory (Optional[int]):
                The quantity of memory to reserve for the execution of the entrypoint command,
                separately from any tasks or actors launched by it. Defaults to 0.
            entrypoint_resources (Optional[Dict[str, float]]):
                The quantity of custom resources to reserve for the execution of the entrypoint command,
                separately from any tasks or actors launched by it.

        Returns:
            str:
                The unique identifier for the submitted job.
        """
        return self.rayJobClient.submit_job(
            entrypoint=entrypoint,
            job_id=job_id,
            runtime_env=runtime_env,
            metadata=metadata,
            submission_id=submission_id,
            entrypoint_num_cpus=entrypoint_num_cpus,
            entrypoint_num_gpus=entrypoint_num_gpus,
            entrypoint_memory=entrypoint_memory,
            entrypoint_resources=entrypoint_resources,
        )

    def delete_job(self, job_id: str) -> (bool, str):
        """
        Deletes a job by job ID.

        Args:
            job_id (str):
                The unique identifier of the job to delete.

        Returns:
            tuple(bool, str):
                A tuple with deletion status and a message.
        """
        deletion_status = self.rayJobClient.delete_job(job_id=job_id)

        if deletion_status:
            message = f"Successfully deleted Job {job_id}"
        else:
            message = f"Failed to delete Job {job_id}"

        return deletion_status, message

    def get_address(self) -> str:
        """
        Retrieves the address of the connected Ray cluster.

        Returns:
            str:
                The Ray cluster's address.
        """
        return self.rayJobClient.get_address()

    def get_job_info(self, job_id: str):
        """
        Fetches information about a job by job ID.

        Args:
            job_id (str):
                The unique identifier of the job.

        Returns:
            JobInfo:
                Information about the job's status, progress, and other details.
        """
        return self.rayJobClient.get_job_info(job_id=job_id)

    def get_job_logs(self, job_id: str) -> str:
        """
        Retrieves the logs for a specific job by job ID.

        Args:
            job_id (str):
                The unique identifier of the job.

        Returns:
            str:
                Logs output from the job.
        """
        return self.rayJobClient.get_job_logs(job_id=job_id)

    def get_job_status(self, job_id: str) -> str:
        """
        Fetches the current status of a job by job ID.

        Args:
            job_id (str):
                The unique identifier of the job.

        Returns:
            str:
                The job's status.
        """
        return self.rayJobClient.get_job_status(job_id=job_id)

    def list_jobs(self) -> List[JobDetails]:
        """
        Lists all current jobs in the Ray cluster.

        Returns:
            List[JobDetails]:
                A list of job details for each current job in the cluster.
        """
        return self.rayJobClient.list_jobs()

    def stop_job(self, job_id: str) -> (bool, str):
        """
        Stops a running job by job ID.

        Args:
            job_id (str):
                The unique identifier of the job to stop.

        Returns:
            tuple(bool, str):
                A tuple with the stop status and a message.
        """
        stop_job_status = self.rayJobClient.stop_job(job_id=job_id)
        if stop_job_status:
            message = f"Successfully stopped Job {job_id}"
        else:
            message = f"Failed to stop Job, {job_id} could have already completed."
        return stop_job_status, message

    def tail_job_logs(self, job_id: str) -> Iterator[str]:
        """
        Continuously streams the logs of a job.

        Args:
            job_id (str):
                The unique identifier of the job.

        Returns:
            Iterator[str]:
                An iterator that yields log entries in real-time.
        """
        return self.rayJobClient.tail_job_logs(job_id=job_id)

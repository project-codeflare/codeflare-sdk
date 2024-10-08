# Copyright 2024 IBM, Red Hat
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

from ray.job_submission import JobSubmissionClient
from codeflare_sdk.ray.client.ray_jobs import RayJobClient
from codeflare_sdk.common.utils.unit_test_support import get_package_and_version
import pytest


# rjc == RayJobClient
@pytest.fixture
def ray_job_client(mocker):
    # Creating a fixture to instantiate RayJobClient with a mocked JobSubmissionClient
    mocker.patch.object(JobSubmissionClient, "__init__", return_value=None)
    return RayJobClient(
        "https://ray-dashboard-unit-test-cluster-ns.apps.cluster.awsroute.org"
    )


def test_rjc_submit_job(ray_job_client, mocker):
    mocked_submit_job = mocker.patch.object(
        JobSubmissionClient, "submit_job", return_value="mocked_submission_id"
    )
    submission_id = ray_job_client.submit_job(entrypoint={"pip": ["numpy"]})

    mocked_submit_job.assert_called_once_with(
        entrypoint={"pip": ["numpy"]},
        job_id=None,
        runtime_env=None,
        metadata=None,
        submission_id=None,
        entrypoint_num_cpus=None,
        entrypoint_num_gpus=None,
        entrypoint_memory=None,
        entrypoint_resources=None,
    )

    assert submission_id == "mocked_submission_id"


def test_rjc_delete_job(ray_job_client, mocker):
    # Case return True
    mocked_delete_job_True = mocker.patch.object(
        JobSubmissionClient, "delete_job", return_value=True
    )
    result = ray_job_client.delete_job(job_id="mocked_job_id")

    mocked_delete_job_True.assert_called_once_with(job_id="mocked_job_id")
    assert result == (True, "Successfully deleted Job mocked_job_id")

    # Case return False
    mocked_delete_job_False = mocker.patch.object(
        JobSubmissionClient, "delete_job", return_value=(False)
    )
    result = ray_job_client.delete_job(job_id="mocked_job_id")

    mocked_delete_job_False.assert_called_once_with(job_id="mocked_job_id")
    assert result == (False, "Failed to delete Job mocked_job_id")


def test_rjc_stop_job(ray_job_client, mocker):
    # Case return True
    mocked_stop_job_True = mocker.patch.object(
        JobSubmissionClient, "stop_job", return_value=(True)
    )
    result = ray_job_client.stop_job(job_id="mocked_job_id")

    mocked_stop_job_True.assert_called_once_with(job_id="mocked_job_id")
    assert result == (True, "Successfully stopped Job mocked_job_id")

    # Case return False
    mocked_stop_job_False = mocker.patch.object(
        JobSubmissionClient, "stop_job", return_value=(False)
    )
    result = ray_job_client.stop_job(job_id="mocked_job_id")

    mocked_stop_job_False.assert_called_once_with(job_id="mocked_job_id")
    assert result == (
        False,
        "Failed to stop Job, mocked_job_id could have already completed.",
    )


def test_rjc_address(ray_job_client, mocker):
    mocked_rjc_address = mocker.patch.object(
        JobSubmissionClient,
        "get_address",
        return_value="https://ray-dashboard-unit-test-cluster-ns.apps.cluster.awsroute.org",
    )
    address = ray_job_client.get_address()

    mocked_rjc_address.assert_called_once()
    assert (
        address
        == "https://ray-dashboard-unit-test-cluster-ns.apps.cluster.awsroute.org"
    )


def test_rjc_get_job_logs(ray_job_client, mocker):
    mocked_rjc_get_job_logs = mocker.patch.object(
        JobSubmissionClient, "get_job_logs", return_value="Logs"
    )
    logs = ray_job_client.get_job_logs(job_id="mocked_job_id")

    mocked_rjc_get_job_logs.assert_called_once_with(job_id="mocked_job_id")
    assert logs == "Logs"


def test_rjc_get_job_info(ray_job_client, mocker):
    job_details_example = "JobDetails(type=<JobType.SUBMISSION: 'SUBMISSION'>, job_id=None, submission_id='mocked_submission_id', driver_info=None, status=<JobStatus.PENDING: 'PENDING'>, entrypoint='python test.py', message='Job has not started yet. It may be waiting for the runtime environment to be set up.', error_type=None, start_time=1701271760641, end_time=None, metadata={}, runtime_env={'working_dir': 'gcs://_ray_pkg_67de6f0e60d43b19.zip', 'pip': {'packages': ['numpy'], 'pip_check': False}, '_ray_commit': 'b4bba4717f5ba04ee25580fe8f88eed63ef0c5dc'}, driver_agent_http_address=None, driver_node_id=None)"
    mocked_rjc_get_job_info = mocker.patch.object(
        JobSubmissionClient, "get_job_info", return_value=job_details_example
    )
    job_details = ray_job_client.get_job_info(job_id="mocked_job_id")

    mocked_rjc_get_job_info.assert_called_once_with(job_id="mocked_job_id")
    assert job_details == job_details_example


def test_rjc_get_job_status(ray_job_client, mocker):
    job_status_example = "<JobStatus.PENDING: 'PENDING'>"
    mocked_rjc_get_job_status = mocker.patch.object(
        JobSubmissionClient, "get_job_status", return_value=job_status_example
    )
    job_status = ray_job_client.get_job_status(job_id="mocked_job_id")

    mocked_rjc_get_job_status.assert_called_once_with(job_id="mocked_job_id")
    assert job_status == job_status_example


def test_rjc_tail_job_logs(ray_job_client, mocker):
    logs_example = [
        "Job started...",
        "Processing input data...",
        "Finalizing results...",
        "Job completed successfully.",
    ]
    mocked_rjc_tail_job_logs = mocker.patch.object(
        JobSubmissionClient, "tail_job_logs", return_value=logs_example
    )
    job_tail_job_logs = ray_job_client.tail_job_logs(job_id="mocked_job_id")

    mocked_rjc_tail_job_logs.assert_called_once_with(job_id="mocked_job_id")
    assert job_tail_job_logs == logs_example


def test_rjc_list_jobs(ray_job_client, mocker):
    requirements_path = "tests/e2e/mnist_pip_requirements.txt"
    pytorch_lightning = get_package_and_version("pytorch_lightning", requirements_path)
    torchmetrics = get_package_and_version("torchmetrics", requirements_path)
    torchvision = get_package_and_version("torchvision", requirements_path)
    jobs_list = [
        f"JobDetails(type=<JobType.SUBMISSION: 'SUBMISSION'>, job_id=None, submission_id='raysubmit_4k2NYS1YbRXYPZCM', driver_info=None, status=<JobStatus.SUCCEEDED: 'SUCCEEDED'>, entrypoint='python mnist.py', message='Job finished successfully.', error_type=None, start_time=1701352132585, end_time=1701352192002, metadata={{}}, runtime_env={{'working_dir': 'gcs://_ray_pkg_6200b93a110e8033.zip', 'pip': {{'packages': ['{pytorch_lightning}', 'ray_lightning', '{torchmetrics}', '{torchvision}'], 'pip_check': False}}, '_ray_commit': 'b4bba4717f5ba04ee25580fe8f88eed63ef0c5dc'}}, driver_agent_http_address='http://10.131.0.18:52365', driver_node_id='9fb515995f5fb13ad4db239ceea378333bebf0a2d45b6aa09d02e691')",
        f"JobDetails(type=<JobType.SUBMISSION: 'SUBMISSION'>, job_id=None, submission_id='raysubmit_iRuwU8vdkbUZZGvT', driver_info=None, status=<JobStatus.STOPPED: 'STOPPED'>, entrypoint='python mnist.py', message='Job was intentionally stopped.', error_type=None, start_time=1701353096163, end_time=1701353097733, metadata={{}}, runtime_env={{'working_dir': 'gcs://_ray_pkg_6200b93a110e8033.zip', 'pip': {{'packages': ['{pytorch_lightning}', 'ray_lightning', '{torchmetrics}', '{torchvision}'], 'pip_check': False}}, '_ray_commit': 'b4bba4717f5ba04ee25580fe8f88eed63ef0c5dc'}}, driver_agent_http_address='http://10.131.0.18:52365', driver_node_id='9fb515995f5fb13ad4db239ceea378333bebf0a2d45b6aa09d02e691')",
    ]
    mocked_rjc_list_jobs = mocker.patch.object(
        JobSubmissionClient, "list_jobs", return_value=jobs_list
    )
    job_list_jobs = ray_job_client.list_jobs()

    mocked_rjc_list_jobs.assert_called_once()
    assert job_list_jobs == jobs_list

# Copyright 2025 IBM, Red Hat
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

from codeflare_sdk.ray.rayjobs.rayjob import RayJob
from codeflare_sdk.ray.rayjobs.status import (
    CodeflareRayJobStatus,
    RayJobDeploymentStatus,
    RayJobInfo,
)


def test_rayjob_status(mocker):
    """
    Test the RayJob status method with different deployment statuses.
    """
    # Mock kubernetes config loading
    mocker.patch("kubernetes.config.load_kube_config")
    # Mock the RayjobApi to avoid actual Kubernetes calls
    mock_api_class = mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")
    mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayClusterApi")
    mock_api_instance = mock_api_class.return_value

    # Create a RayJob instance
    rayjob = RayJob(
        job_name="test-job",
        cluster_name="test-cluster",
        namespace="test-ns",
        entrypoint="python test.py",
    )

    # Test case 1: No job found
    mock_api_instance.get_job_status.return_value = None
    status, ready = rayjob.status(print_to_console=False)
    assert status == CodeflareRayJobStatus.UNKNOWN
    assert ready == False

    # Test case 2: Running job
    mock_api_instance.get_job_status.return_value = {
        "jobId": "test-job-abc123",
        "jobDeploymentStatus": "Running",
        "startTime": "2025-07-28T11:37:07Z",
        "failed": 0,
        "succeeded": 0,
        "rayClusterName": "test-cluster",
    }
    status, ready = rayjob.status(print_to_console=False)
    assert status == CodeflareRayJobStatus.RUNNING
    assert ready == False

    # Test case 3: Complete job
    mock_api_instance.get_job_status.return_value = {
        "jobId": "test-job-abc123",
        "jobDeploymentStatus": "Complete",
        "startTime": "2025-07-28T11:37:07Z",
        "endTime": "2025-07-28T11:42:30Z",
        "failed": 0,
        "succeeded": 1,
        "rayClusterName": "test-cluster",
    }
    status, ready = rayjob.status(print_to_console=False)
    assert status == CodeflareRayJobStatus.COMPLETE
    assert ready == True

    # Test case 4: Failed job
    mock_api_instance.get_job_status.return_value = {
        "jobId": "test-job-abc123",
        "jobDeploymentStatus": "Failed",
        "startTime": "2025-07-28T11:37:07Z",
        "endTime": "2025-07-28T11:42:30Z",
        "failed": 1,
        "succeeded": 0,
        "rayClusterName": "test-cluster",
    }
    status, ready = rayjob.status(print_to_console=False)
    assert status == CodeflareRayJobStatus.FAILED
    assert ready == False

    # Test case 5: Suspended job
    mock_api_instance.get_job_status.return_value = {
        "jobId": "test-job-abc123",
        "jobDeploymentStatus": "Suspended",
        "startTime": "2025-07-28T11:37:07Z",
        "failed": 0,
        "succeeded": 0,
        "rayClusterName": "test-cluster",
    }
    status, ready = rayjob.status(print_to_console=False)
    assert status == CodeflareRayJobStatus.SUSPENDED
    assert ready == False


def test_rayjob_status_unknown_deployment_status(mocker):
    """
    Test handling of unknown deployment status from the API.
    """
    mocker.patch("kubernetes.config.load_kube_config")
    mock_api_class = mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")
    mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayClusterApi")
    mock_api_instance = mock_api_class.return_value

    rayjob = RayJob(
        job_name="test-job",
        cluster_name="test-cluster",
        namespace="test-ns",
        entrypoint="python test.py",
    )

    # Test with unrecognized deployment status
    mock_api_instance.get_job_status.return_value = {
        "jobId": "test-job-abc123",
        "jobDeploymentStatus": "SomeNewStatus",  # Unknown status
        "startTime": "2025-07-28T11:37:07Z",
        "failed": 0,
        "succeeded": 0,
    }

    status, ready = rayjob.status(print_to_console=False)
    assert status == CodeflareRayJobStatus.UNKNOWN
    assert ready == False


def test_rayjob_status_missing_fields(mocker):
    """
    Test handling of API response with missing fields.
    """
    mocker.patch("kubernetes.config.load_kube_config")
    mock_api_class = mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")
    mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayClusterApi")
    mock_api_instance = mock_api_class.return_value

    rayjob = RayJob(
        job_name="test-job",
        cluster_name="test-cluster",
        namespace="test-ns",
        entrypoint="python test.py",
    )

    # Test with minimal API response (missing some fields)
    mock_api_instance.get_job_status.return_value = {
        # Missing jobId, failed, succeeded, etc.
        "jobDeploymentStatus": "Running",
    }

    status, ready = rayjob.status(print_to_console=False)
    assert status == CodeflareRayJobStatus.RUNNING
    assert ready == False


def test_map_to_codeflare_status(mocker):
    """
    Test the _map_to_codeflare_status helper method directly.
    """
    # Mock kubernetes config loading
    mocker.patch("kubernetes.config.load_kube_config")
    # Mock the RayjobApi constructor to avoid authentication issues
    mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")
    mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayClusterApi")

    rayjob = RayJob(
        job_name="test-job",
        cluster_name="test-cluster",
        namespace="test-ns",
        entrypoint="python test.py",
    )

    # Test all deployment status mappings
    status, ready = rayjob._map_to_codeflare_status(RayJobDeploymentStatus.COMPLETE)
    assert status == CodeflareRayJobStatus.COMPLETE
    assert ready == True

    status, ready = rayjob._map_to_codeflare_status(RayJobDeploymentStatus.RUNNING)
    assert status == CodeflareRayJobStatus.RUNNING
    assert ready == False

    status, ready = rayjob._map_to_codeflare_status(RayJobDeploymentStatus.FAILED)
    assert status == CodeflareRayJobStatus.FAILED
    assert ready == False

    status, ready = rayjob._map_to_codeflare_status(RayJobDeploymentStatus.SUSPENDED)
    assert status == CodeflareRayJobStatus.SUSPENDED
    assert ready == False

    status, ready = rayjob._map_to_codeflare_status(RayJobDeploymentStatus.UNKNOWN)
    assert status == CodeflareRayJobStatus.UNKNOWN
    assert ready == False


def test_rayjob_info_dataclass():
    """
    Test the RayJobInfo dataclass creation and field access.
    """
    job_info = RayJobInfo(
        name="test-job",
        job_id="test-job-abc123",
        status=RayJobDeploymentStatus.RUNNING,
        namespace="test-ns",
        cluster_name="test-cluster",
        start_time="2025-07-28T11:37:07Z",
        failed_attempts=0,
        succeeded_attempts=0,
    )

    # Test all fields are accessible
    assert job_info.name == "test-job"
    assert job_info.job_id == "test-job-abc123"
    assert job_info.status == RayJobDeploymentStatus.RUNNING
    assert job_info.namespace == "test-ns"
    assert job_info.cluster_name == "test-cluster"
    assert job_info.start_time == "2025-07-28T11:37:07Z"
    assert job_info.end_time is None  # Default value
    assert job_info.failed_attempts == 0
    assert job_info.succeeded_attempts == 0


def test_rayjob_status_print_no_job_found(mocker):
    """
    Test that pretty_print.print_no_job_found is called when no job is found and print_to_console=True.
    """
    mocker.patch("kubernetes.config.load_kube_config")
    # Mock the RayjobApi and pretty_print
    mock_api_class = mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")
    mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayClusterApi")
    mock_api_instance = mock_api_class.return_value
    mock_print_no_job_found = mocker.patch(
        "codeflare_sdk.ray.rayjobs.pretty_print.print_no_job_found"
    )

    # Create a RayJob instance
    rayjob = RayJob(
        job_name="test-job",
        cluster_name="test-cluster",
        namespace="test-ns",
        entrypoint="python test.py",
    )

    # No job found scenario
    mock_api_instance.get_job_status.return_value = None

    # Call status with print_to_console=True
    status, ready = rayjob.status(print_to_console=True)

    # Verify the pretty print function was called
    mock_print_no_job_found.assert_called_once_with("test-job", "test-ns")
    assert status == CodeflareRayJobStatus.UNKNOWN
    assert ready == False


def test_rayjob_status_print_job_found(mocker):
    """
    Test that pretty_print.print_job_status is called when job is found and print_to_console=True.
    """
    mocker.patch("kubernetes.config.load_kube_config")
    # Mock the RayjobApi and pretty_print
    mock_api_class = mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")
    mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayClusterApi")
    mock_api_instance = mock_api_class.return_value
    mock_print_job_status = mocker.patch(
        "codeflare_sdk.ray.rayjobs.pretty_print.print_job_status"
    )

    # Create a RayJob instance
    rayjob = RayJob(
        job_name="test-job",
        cluster_name="test-cluster",
        namespace="test-ns",
        entrypoint="python test.py",
    )

    # Job found scenario
    mock_api_instance.get_job_status.return_value = {
        "jobId": "test-job-abc123",
        "jobDeploymentStatus": "Running",
        "startTime": "2025-07-28T11:37:07Z",
        "failed": 0,
        "succeeded": 0,
        "rayClusterName": "test-cluster",
    }

    # Call status with print_to_console=True
    status, ready = rayjob.status(print_to_console=True)

    # Verify the pretty print function was called
    mock_print_job_status.assert_called_once()
    # Verify the RayJobInfo object passed to print_job_status
    call_args = mock_print_job_status.call_args[0][0]  # First positional argument
    assert call_args.name == "test-job"
    assert call_args.job_id == "test-job-abc123"
    assert call_args.status == RayJobDeploymentStatus.RUNNING
    assert call_args.namespace == "test-ns"
    assert call_args.cluster_name == "test-cluster"

    assert status == CodeflareRayJobStatus.RUNNING
    assert ready == False


def test_rayjob_status_all_deployment_states(mocker):
    """Test RayJob status method with all deployment states."""
    mocker.patch("kubernetes.config.load_kube_config")
    mock_api_class = mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")
    mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayClusterApi")
    mock_api_instance = mock_api_class.return_value

    rayjob = RayJob(
        job_name="test-job",
        cluster_name="test-cluster",
        namespace="test-ns",
        entrypoint="python test.py",
    )

    # Test mapping of deployment statuses to CodeflareRayJobStatus
    test_cases = [
        # (deployment_status_str, expected CodeflareRayJobStatus, expected ready)
        ("Complete", CodeflareRayJobStatus.COMPLETE, True),
        ("Running", CodeflareRayJobStatus.RUNNING, False),
        ("Failed", CodeflareRayJobStatus.FAILED, False),
        ("Suspended", CodeflareRayJobStatus.SUSPENDED, False),
    ]

    for deployment_status_str, expected_status, expected_ready in test_cases:
        mock_api_instance.get_job_status.return_value = {
            "jobId": "test-job-abc123",
            "jobDeploymentStatus": deployment_status_str,
            "startTime": "2025-07-28T11:37:07Z",
            "failed": 0,
            "succeeded": 0,
            "rayClusterName": "test-cluster",
        }
        status, ready = rayjob.status(print_to_console=False)
        assert status == expected_status, f"Failed for {deployment_status_str}"
        assert (
            ready == expected_ready
        ), f"Failed ready check for {deployment_status_str}"


def test_rayjob_status_with_end_time(mocker):
    """Test RayJob status with end time field."""
    mocker.patch("kubernetes.config.load_kube_config")
    mock_api_class = mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")
    mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayClusterApi")
    mock_api_instance = mock_api_class.return_value

    rayjob = RayJob(
        job_name="test-job",
        cluster_name="test-cluster",
        namespace="test-ns",
        entrypoint="python test.py",
    )

    # Test with end time field
    mock_api_instance.get_job_status.return_value = {
        "jobId": "test-job-abc123",
        "jobDeploymentStatus": "Complete",
        "startTime": "2025-07-28T11:37:07Z",
        "endTime": "2025-07-28T11:47:07Z",
        "failed": 0,
        "succeeded": 1,
        "rayClusterName": "test-cluster",
    }

    status, ready = rayjob.status(print_to_console=False)
    assert status == CodeflareRayJobStatus.COMPLETE
    assert ready == True

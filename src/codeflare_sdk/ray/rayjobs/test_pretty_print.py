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

from codeflare_sdk.ray.rayjobs.pretty_print import (
    _get_status_display,
    print_job_status,
    print_no_job_found,
)
from codeflare_sdk.ray.rayjobs.status import RayJobDeploymentStatus, RayJobInfo
from unittest.mock import MagicMock, call


def test_get_status_display():
    """
    Test the _get_status_display function.
    """
    # Test Complete status
    display, color = _get_status_display(RayJobDeploymentStatus.COMPLETE)
    assert display == "Complete :white_heavy_check_mark:"
    assert color == "[white on green][bold]Name"

    # Test Running status
    display, color = _get_status_display(RayJobDeploymentStatus.RUNNING)
    assert display == "Running :gear:"
    assert color == "[white on blue][bold]Name"

    # Test Failed status
    display, color = _get_status_display(RayJobDeploymentStatus.FAILED)
    assert display == "Failed :x:"
    assert color == "[white on red][bold]Name"

    # Test Suspended status
    display, color = _get_status_display(RayJobDeploymentStatus.SUSPENDED)
    assert display == "Suspended :pause_button:"
    assert color == "[white on yellow][bold]Name"

    # Test Unknown status
    display, color = _get_status_display(RayJobDeploymentStatus.UNKNOWN)
    assert display == "Unknown :question:"
    assert color == "[white on red][bold]Name"


def test_print_job_status_running_format(mocker):
    """
    Test the print_job_status function format for a running job.
    """
    # Mock Rich components to verify format
    mock_console = MagicMock()
    mock_inner_table = MagicMock()
    mock_main_table = MagicMock()
    mock_panel = MagicMock()

    # Mock Table to return different instances for inner and main tables
    table_instances = [mock_inner_table, mock_main_table]
    mock_table_class = MagicMock(side_effect=table_instances)

    mocker.patch(
        "codeflare_sdk.ray.rayjobs.pretty_print.Console", return_value=mock_console
    )
    mocker.patch("codeflare_sdk.ray.rayjobs.pretty_print.Table", mock_table_class)
    mocker.patch("codeflare_sdk.ray.rayjobs.pretty_print.Panel", mock_panel)

    # Create test job info for running job
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

    # Call the function
    print_job_status(job_info)

    # Verify both Table calls
    expected_table_calls = [
        call(box=None, show_header=False),  # Inner content table
        call(
            box=None, title="[bold] :package: CodeFlare RayJob Status :package:"
        ),  # Main wrapper table
    ]
    mock_table_class.assert_has_calls(expected_table_calls)

    # Verify inner table rows are added in correct order and format (versus our hard-coded version of this for cluster)
    expected_calls = [
        call("[white on blue][bold]Name"),  # Header with blue color for running
        call(
            "[bold underline]test-job", "Running :gear:"
        ),  # Name and status with gear emoji
        call(),  # Empty separator row
        call("[bold]Job ID:[/bold] test-job-abc123"),
        call("[bold]Status:[/bold] Running"),
        call("[bold]RayCluster:[/bold] test-cluster"),
        call("[bold]Namespace:[/bold] test-ns"),
        call(),  # Empty row before timing info
        call("[bold]Started:[/bold] 2025-07-28T11:37:07Z"),
    ]
    mock_inner_table.add_row.assert_has_calls(expected_calls)

    # Verify Panel is created with inner table
    mock_panel.fit.assert_called_once_with(mock_inner_table)

    # Verify main table gets the panel
    mock_main_table.add_row.assert_called_once_with(mock_panel.fit.return_value)

    # Verify console prints the main table
    mock_console.print.assert_called_once_with(mock_main_table)


def test_print_job_status_complete_format(mocker):
    """
    Test the print_job_status function format for a completed job.
    """
    # Mock Rich components
    mock_console = MagicMock()
    mock_inner_table = MagicMock()
    mock_main_table = MagicMock()
    mock_panel = MagicMock()

    # Mock Table to return different instances
    table_instances = [mock_inner_table, mock_main_table]
    mock_table_class = MagicMock(side_effect=table_instances)

    mocker.patch(
        "codeflare_sdk.ray.rayjobs.pretty_print.Console", return_value=mock_console
    )
    mocker.patch("codeflare_sdk.ray.rayjobs.pretty_print.Table", mock_table_class)
    mocker.patch("codeflare_sdk.ray.rayjobs.pretty_print.Panel", mock_panel)

    # Create test job info for completed job
    job_info = RayJobInfo(
        name="completed-job",
        job_id="completed-job-xyz789",
        status=RayJobDeploymentStatus.COMPLETE,
        namespace="prod-ns",
        cluster_name="prod-cluster",
        start_time="2025-07-28T11:37:07Z",
        failed_attempts=0,
        succeeded_attempts=1,
    )

    # Call the function
    print_job_status(job_info)

    # Verify correct header color for completed job (green) (versus our hard-coded version of this for cluster)
    expected_calls = [
        call("[white on green][bold]Name"),  # Green header for complete
        call(
            "[bold underline]completed-job", "Complete :white_heavy_check_mark:"
        ),  # Checkmark emoji
        call(),  # Empty separator
        call("[bold]Job ID:[/bold] completed-job-xyz789"),
        call("[bold]Status:[/bold] Complete"),
        call("[bold]RayCluster:[/bold] prod-cluster"),
        call("[bold]Namespace:[/bold] prod-ns"),
        call(),  # Empty row before timing info
        call("[bold]Started:[/bold] 2025-07-28T11:37:07Z"),
    ]
    mock_inner_table.add_row.assert_has_calls(expected_calls)


def test_print_job_status_failed_with_attempts_format(mocker):
    """
    Test the print_job_status function format for a failed job with attempts.
    """
    # Mock Rich components
    mock_console = MagicMock()
    mock_inner_table = MagicMock()
    mock_main_table = MagicMock()
    mock_panel = MagicMock()

    # Mock Table to return different instances
    table_instances = [mock_inner_table, mock_main_table]
    mock_table_class = MagicMock(side_effect=table_instances)

    mocker.patch(
        "codeflare_sdk.ray.rayjobs.pretty_print.Console", return_value=mock_console
    )
    mocker.patch("codeflare_sdk.ray.rayjobs.pretty_print.Table", mock_table_class)
    mocker.patch("codeflare_sdk.ray.rayjobs.pretty_print.Panel", mock_panel)

    # Create test job info with failures
    job_info = RayJobInfo(
        name="failing-job",
        job_id="failing-job-fail123",
        status=RayJobDeploymentStatus.FAILED,
        namespace="test-ns",
        cluster_name="test-cluster",
        start_time="2025-07-28T11:37:07Z",
        failed_attempts=3,  # Has failures
        succeeded_attempts=0,
    )

    # Call the function
    print_job_status(job_info)

    # Verify correct formatting including failure attempts (versus our hard-coded version of this for cluster)
    expected_calls = [
        call("[white on red][bold]Name"),  # Red header for failed
        call("[bold underline]failing-job", "Failed :x:"),  # X emoji for failed
        call(),  # Empty separator
        call("[bold]Job ID:[/bold] failing-job-fail123"),
        call("[bold]Status:[/bold] Failed"),
        call("[bold]RayCluster:[/bold] test-cluster"),
        call("[bold]Namespace:[/bold] test-ns"),
        call(),  # Empty row before timing info
        call("[bold]Started:[/bold] 2025-07-28T11:37:07Z"),
        call("[bold]Failed Attempts:[/bold] 3"),  # Failed attempts should be shown
    ]
    mock_inner_table.add_row.assert_has_calls(expected_calls)


def test_print_no_job_found_format(mocker):
    """
    Test the print_no_job_found function format.
    """
    # Mock Rich components
    mock_console = MagicMock()
    mock_inner_table = MagicMock()
    mock_main_table = MagicMock()
    mock_panel = MagicMock()

    # Mock Table to return different instances
    table_instances = [mock_inner_table, mock_main_table]
    mock_table_class = MagicMock(side_effect=table_instances)

    mocker.patch(
        "codeflare_sdk.ray.rayjobs.pretty_print.Console", return_value=mock_console
    )
    mocker.patch("codeflare_sdk.ray.rayjobs.pretty_print.Table", mock_table_class)
    mocker.patch("codeflare_sdk.ray.rayjobs.pretty_print.Panel", mock_panel)

    # Call the function
    print_no_job_found("missing-job", "test-namespace")

    # Verify error message format (versus our hard-coded version of this for cluster)
    expected_calls = [
        call("[white on red][bold]Name"),  # Red header for error
        call(
            "[bold underline]missing-job", "[bold red]No RayJob found"
        ),  # Error message in red
        call(),  # Empty separator
        call(),  # Another empty row
        call("Please run rayjob.submit() to submit a job."),  # Helpful hint
        call(),  # Empty separator
        call("[bold]Namespace:[/bold] test-namespace"),
    ]
    mock_inner_table.add_row.assert_has_calls(expected_calls)

    # Verify Panel is used
    mock_panel.fit.assert_called_once_with(mock_inner_table)

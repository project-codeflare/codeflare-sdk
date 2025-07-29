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

"""
This sub-module exists primarily to be used internally by the RayJob object
(in the rayjob sub-module) for pretty-printing job status and details.
"""

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from typing import Tuple, Optional

from .status import RayJobDeploymentStatus, RayJobInfo


def print_job_status(job_info: RayJobInfo):
    """
    Pretty print the job status in a format similar to cluster status.
    """
    status_display, header_color = _get_status_display(job_info.status)

    # Create main info table
    table = _create_info_table(header_color, job_info.name, status_display)
    table.add_row(f"[bold]Job ID:[/bold] {job_info.job_id}")
    table.add_row(f"[bold]Status:[/bold] {job_info.status.value}")
    table.add_row(f"[bold]RayCluster:[/bold] {job_info.cluster_name}")
    table.add_row(f"[bold]Namespace:[/bold] {job_info.namespace}")

    # Add timing information if available
    if job_info.start_time:
        table.add_row()
        table.add_row(f"[bold]Started:[/bold] {job_info.start_time}")

    # Add attempt counts if there are failures
    if job_info.failed_attempts > 0:
        table.add_row(f"[bold]Failed Attempts:[/bold] {job_info.failed_attempts}")

    _print_table_in_panel(table)


def print_no_job_found(job_name: str, namespace: str):
    """
    Print a message when no job is found.
    """
    # Create table with error message
    table = _create_info_table(
        "[white on red][bold]Name", job_name, "[bold red]No RayJob found"
    )
    table.add_row()
    table.add_row("Please run rayjob.submit() to submit a job.")
    table.add_row()
    table.add_row(f"[bold]Namespace:[/bold] {namespace}")

    _print_table_in_panel(table)


def _get_status_display(status: RayJobDeploymentStatus) -> Tuple[str, str]:
    """
    Get the display string and header color for a given status.

    Returns:
        Tuple of (status_display, header_color)
    """
    status_mapping = {
        RayJobDeploymentStatus.COMPLETE: (
            "Complete :white_heavy_check_mark:",
            "[white on green][bold]Name",
        ),
        RayJobDeploymentStatus.RUNNING: ("Running :gear:", "[white on blue][bold]Name"),
        RayJobDeploymentStatus.FAILED: ("Failed :x:", "[white on red][bold]Name"),
        RayJobDeploymentStatus.SUSPENDED: (
            "Suspended :pause_button:",
            "[white on yellow][bold]Name",
        ),
    }

    return status_mapping.get(
        status, ("Unknown :question:", "[white on red][bold]Name")
    )


def _create_info_table(header_color: str, name: str, status_display: str) -> Table:
    """
    Create a standardized info table with header and status.

    Returns:
        Table with header row, name/status row, and empty separator row
    """
    table = Table(box=None, show_header=False)
    table.add_row(header_color)
    table.add_row("[bold underline]" + name, status_display)
    table.add_row()  # Empty separator row
    return table


def _print_table_in_panel(table: Table):
    """
    Print a table wrapped in a consistent panel format.
    """
    console = Console()
    main_table = Table(
        box=None, title="[bold] :package: CodeFlare RayJob Status :package:"
    )
    main_table.add_row(Panel.fit(table))
    console.print(main_table)

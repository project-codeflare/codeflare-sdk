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
from typing import Tuple, Optional, List

from .status import RayJobDeploymentStatus, RayJobInfo, KueueWorkloadInfo


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
    
    # Add cluster management info
    managed_text = "[bold green]Yes (Job-managed)[/bold green]" if job_info.is_managed_cluster else "[dim]No (Existing cluster)[/dim]"
    table.add_row(f"[bold]Managed Cluster:[/bold] {managed_text}")

    # Add timing information if available
    if job_info.start_time:
        table.add_row()
        table.add_row(f"[bold]Started:[/bold] {job_info.start_time}")

    # Add attempt counts if there are failures
    if job_info.failed_attempts > 0:
        table.add_row(f"[bold]Failed Attempts:[/bold] {job_info.failed_attempts}")

    # Add Kueue information if available
    if job_info.kueue_workload:
        table.add_row()
        table.add_row("[bold blue]🎯 Kueue Integration[/bold blue]")
        table.add_row(f"[bold]Local Queue:[/bold] {job_info.local_queue}")
        table.add_row(f"[bold]Workload Status:[/bold] [bold green]{job_info.kueue_workload.status}[/bold green]")
        table.add_row(f"[bold]Workload Name:[/bold] {job_info.kueue_workload.name}")
        if job_info.kueue_workload.priority is not None:
            table.add_row(f"[bold]Priority:[/bold] {job_info.kueue_workload.priority}")
        if job_info.kueue_workload.admission_time:
            table.add_row(f"[bold]Admitted:[/bold] {job_info.kueue_workload.admission_time}")
    elif job_info.local_queue:
        table.add_row()
        table.add_row("[bold blue]🎯 Kueue Integration[/bold blue]")
        table.add_row(f"[bold]Local Queue:[/bold] {job_info.local_queue}")
        table.add_row("[dim]Workload information not available[/dim]")

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


def print_jobs_list(job_list: List[RayJobInfo], namespace: str, pagination_info: Optional[dict] = None):
    """
    Pretty print a list of RayJobs using Rich formatting with pagination support.
    
    Args:
        job_list: List of RayJobInfo objects (for current page)
        namespace: Kubernetes namespace
        pagination_info: Optional pagination information dict
    """
    if not job_list:
        # Create table for no jobs found
        table = _create_info_table(
            "[white on yellow][bold]Namespace", namespace, "[bold yellow]No RayJobs found"
        )
        table.add_row()
        table.add_row("No RayJobs found in this namespace.")
        table.add_row("Jobs may have been deleted or completed with TTL cleanup.")
        _print_table_in_panel(table)
        return
    
    # Create main table for job list
    console = Console()
    
    # Create title with pagination info
    title = f"[bold blue]🚀 RayJobs in namespace: {namespace}[/bold blue]"
    if pagination_info and pagination_info["total_pages"] > 1:
        title += f" [dim](Page {pagination_info['current_page']} of {pagination_info['total_pages']})[/dim]"
    
    # Create jobs table with responsive width
    jobs_table = Table(
        title=title,
        show_header=True,
        header_style="bold magenta",
        border_style="blue",
        expand=True,  # Allow table to expand to terminal width
        min_width=120,  # Minimum width for readability
    )
    
    # Add columns with flexible width allocation and wrapping
    jobs_table.add_column("Status", style="bold", min_width=12, max_width=16)
    jobs_table.add_column("Job Name", style="bold cyan", min_width=15, max_width=30)
    jobs_table.add_column("Job ID", style="dim", min_width=12, max_width=25)
    jobs_table.add_column("Cluster", min_width=12, max_width=25)
    jobs_table.add_column("Managed", min_width=8, max_width=12)
    jobs_table.add_column("Queue", min_width=10, max_width=18)
    jobs_table.add_column("Kueue Status", min_width=8, max_width=15)
    jobs_table.add_column("Start Time", style="dim", min_width=8, max_width=12)
    
    # Add rows for each job
    for job_info in job_list:
        status_display, _ = _get_status_display(job_info.status)
        
        # Format start time more compactly
        if job_info.start_time:
            try:
                # Extract just time portion and make it compact
                start_time = job_info.start_time.split('T')[1][:8]  # HH:MM:SS
            except (IndexError, AttributeError):
                start_time = "N/A"
        else:
            start_time = "N/A"
        
        # Truncate long values intelligently (Rich will handle further truncation if needed)
        job_name = _truncate_text(job_info.name, 28)
        job_id = _truncate_text(job_info.job_id, 23)
        cluster_name = _truncate_text(job_info.cluster_name, 23)
        
        # Cluster management info
        managed_display = "✅ Yes" if job_info.is_managed_cluster else "❌ No"
        managed_style = "bold green" if job_info.is_managed_cluster else "dim"
        
        # Kueue information
        queue_display = _truncate_text(job_info.local_queue or "N/A", 16)
        kueue_status_display = "N/A"
        kueue_status_style = "dim"
        
        if job_info.kueue_workload:
            kueue_status_display = job_info.kueue_workload.status
            if job_info.kueue_workload.status == "Admitted":
                kueue_status_style = "bold green"
            elif job_info.kueue_workload.status == "Pending":
                kueue_status_style = "bold yellow"
            elif job_info.kueue_workload.status == "Finished":
                kueue_status_style = "bold blue"
        
        jobs_table.add_row(
            status_display,
            job_name,
            job_id,
            cluster_name,
            f"[{managed_style}]{managed_display}[/{managed_style}]",
            queue_display,
            f"[{kueue_status_style}]{kueue_status_display}[/{kueue_status_style}]",
            start_time,
        )
    
    # Print the table
    console.print(jobs_table)
    
    # Add pagination information
    if pagination_info:
        console.print()  # Add spacing
        if pagination_info["total_pages"] > 1:
            console.print(
                f"[dim]Showing {pagination_info['showing_start']}-{pagination_info['showing_end']} "
                f"of {pagination_info['total_jobs']} jobs "
                f"(Page {pagination_info['current_page']} of {pagination_info['total_pages']})[/dim]"
            )
            
            # Navigation hints
            nav_hints = []
            if pagination_info['current_page'] > 1:
                nav_hints.append(f"Previous: RayJob.List(page={pagination_info['current_page'] - 1})")
            if pagination_info['current_page'] < pagination_info['total_pages']:
                nav_hints.append(f"Next: RayJob.List(page={pagination_info['current_page'] + 1})")
            
            if nav_hints:
                console.print(f"[dim]Navigation: {' | '.join(nav_hints)}[/dim]")
    
    # Add summary information
    kueue_jobs = [job for job in job_list if job.local_queue]
    managed_jobs = [job for job in job_list if job.is_managed_cluster]
    
    if kueue_jobs or managed_jobs:
        console.print()  # Add spacing
        if managed_jobs:
            total_managed = len(managed_jobs)
            total_jobs = pagination_info["total_jobs"] if pagination_info else len(job_list)
            console.print(f"[bold green]🏗️  {total_managed} of {total_jobs} jobs use job-managed clusters[/bold green]")
        if kueue_jobs:
            total_kueue = len(kueue_jobs)
            total_jobs = pagination_info["total_jobs"] if pagination_info else len(job_list)
            console.print(f"[bold blue]🎯 {total_kueue} of {total_jobs} jobs are managed by Kueue[/bold blue]")


def _truncate_text(text: str, max_length: int) -> str:
    """
    Truncate text intelligently with ellipsis if needed.
    
    Args:
        text: Text to truncate
        max_length: Maximum length including ellipsis
        
    Returns:
        Truncated text with ellipsis if needed
    """
    if len(text) <= max_length:
        return text
    
    # Leave room for ellipsis
    if max_length <= 3:
        return text[:max_length]
    
    return text[:max_length-3] + "..."


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

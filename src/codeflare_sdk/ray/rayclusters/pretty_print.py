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
This sub-module exists primarily to be used internally by the RayCluster object
for pretty-printing cluster status and details.
"""

from rich.table import Table
from rich.console import Console
from rich.panel import Panel
from rich import box
from typing import List, TYPE_CHECKING
from .status import RayClusterStatus

if TYPE_CHECKING:
    from .raycluster import RayCluster


def _is_valid_url(url: str) -> bool:
    """Check if a string is a valid URL (starts with http:// or https://)."""
    if not url or not isinstance(url, str):
        return False
    return url.startswith("http://") or url.startswith("https://")


def _get_cluster_status(cluster: "RayCluster") -> RayClusterStatus:
    """
    Get the current status of the RayCluster.

    Args:
        cluster: A RayCluster object.

    Returns:
        RayClusterStatus enum value.
    """
    return cluster._get_current_status()


def print_no_resources_found():
    console = Console()
    console.print(
        Panel(
            "[red]No resources found, have you run cluster.apply() yet? Run cluster.details() to check if it's ready."
        )
    )


def print_ray_clusters_status(clusters: List["RayCluster"], starting: bool = False):
    """
    Print a summary table of cluster statuses.

    Args:
        clusters: List of RayCluster objects.
        starting: Whether to append "(starting)" to status.
    """
    if not clusters:
        print_no_resources_found()
        return  # shortcircuit

    console = Console()
    table = Table(
        box=box.ASCII_DOUBLE_HEAD,
        title="[bold] :rocket: Cluster Queue Status :rocket:",
    )
    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("Status", style="magenta")

    for cluster in clusters:
        name = cluster.name
        cluster_status = _get_cluster_status(cluster)
        status = cluster_status.value
        if starting:
            status += " (starting)"
        table.add_row(name, status)
        table.add_row("")  # empty row for spacing

    console.print(Panel.fit(table))


def print_cluster_status(cluster: "RayCluster"):
    """
    Pretty prints the status of a passed-in cluster.

    Args:
        cluster: A RayCluster object.
    """
    if not cluster:
        print_no_resources_found()
        return

    console = Console()
    cluster_status = _get_cluster_status(cluster)
    status = (
        "Active :white_heavy_check_mark:"
        if cluster_status == RayClusterStatus.READY
        else "Inactive :x:"
    )
    name = cluster.name
    dashboard = cluster.dashboard

    #'table0' to display the cluster name, status, url, and dashboard link
    table0 = Table(box=None, show_header=False)

    table0.add_row("[white on green][bold]Name")
    table0.add_row("[bold underline]" + name, status)
    table0.add_row()
    # fixme harcded to default for now
    table0.add_row(
        f"[bold]URI:[/bold] ray://{cluster.name}-head-svc.{cluster.namespace}.svc:10001"
    )  # format that is used to generate the name of the service
    table0.add_row()
    # Only create clickable link if dashboard is a valid URL
    if _is_valid_url(dashboard):
        table0.add_row(
            f"[link={dashboard}][blue underline]Dashboard🔗[/blue underline][/link]"
        )
    else:
        table0.add_row("[blue]Dashboard🔗[/blue]")
    table0.add_row("")  # empty row for spacing

    # table4 to display table0 and table3, one below the other
    table4 = Table(box=None, show_header=False)
    table4.add_row(table0)

    # Encompass all details of the cluster in a single panel
    table5 = Table(box=None, title="[bold] :rocket: CodeFlare Cluster Status :rocket:")
    table5.add_row(Panel.fit(table4))
    console.print(table5)


def print_clusters(clusters: List["RayCluster"]):
    """
    Print detailed information about clusters.

    Args:
        clusters: List of RayCluster objects.
    """
    if not clusters:
        print_no_resources_found()
        return  # shortcircuit

    console = Console()
    title_printed = False

    for cluster in clusters:
        cluster_status = _get_cluster_status(cluster)
        status = (
            "Active :white_heavy_check_mark:"
            if cluster_status == RayClusterStatus.READY
            else "Inactive :x:"
        )
        name = cluster.name
        dashboard = cluster.dashboard
        workers = str(cluster.num_workers)
        memory = f"{cluster.worker_memory_requests}~{cluster.worker_memory_limits}"
        cpu = f"{cluster.worker_cpu_requests}~{cluster.worker_cpu_limits}"
        gpu = str(cluster.worker_accelerators.get("nvidia.com/gpu", 0))

        #'table0' to display the cluster name, status, url, and dashboard link
        table0 = Table(box=None, show_header=False)

        table0.add_row("[white on green][bold]Name")
        table0.add_row("[bold underline]" + name, status)
        table0.add_row()
        # fixme harcded to default for now
        table0.add_row(
            f"[bold]URI:[/bold] ray://{cluster.name}-head-svc.{cluster.namespace}.svc:10001"
        )  # format that is used to generate the name of the service
        table0.add_row()
        # Only create clickable link if dashboard is a valid URL
        if _is_valid_url(dashboard):
            table0.add_row(
                f"[link={dashboard}][blue underline]Dashboard🔗[/blue underline][/link]"
            )
        else:
            table0.add_row("[blue]Dashboard🔗[/blue]")
        table0.add_row("")  # empty row for spacing

        #'table1' to display the worker counts
        table1 = Table(box=None)
        table1.add_row()
        table1.add_column("# Workers", style="magenta")
        table1.add_row()
        table1.add_row(workers)
        table1.add_row()

        #'table2' to display the worker resources
        table2 = Table(box=None)
        table2.add_column("Memory", style="cyan", no_wrap=True, min_width=10)
        table2.add_column("CPU", style="magenta", min_width=10)
        table2.add_column("GPU", style="magenta", min_width=10)
        table2.add_row()
        table2.add_row(memory, cpu, gpu)
        table2.add_row()

        # panels to encompass table1 and table2 into separate cards
        panel_1 = Panel.fit(table1, title="Workers")
        panel_2 = Panel.fit(table2, title="Worker specs(each)")

        # table3 to display panel_1 and panel_2 side-by-side in a single row
        table3 = Table(box=None, show_header=False, title="Cluster Resources")
        table3.add_row(panel_1, panel_2)

        # table4 to display table0 and table3, one below the other
        table4 = Table(box=None, show_header=False)
        table4.add_row(table0)
        table4.add_row(table3)

        # Encompass all details of the cluster in a single panel
        if not title_printed:
            # If first cluster in the list, then create a table with title "Codeflare clusters".
            # This is done to ensure the title is center aligned on the cluster display tables, rather
            # than being center aligned on the console/terminal if we simply use console.print(title)

            table5 = Table(
                box=None, title="[bold] :rocket: CodeFlare Cluster Details :rocket:"
            )
            table5.add_row(Panel.fit(table4))
            console.print(table5)
            title_printed = True
        else:
            console.print(Panel.fit(table4))

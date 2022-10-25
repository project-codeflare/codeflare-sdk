from rich import print
from rich.table import Table
from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich import box
from typing import List
from ..cluster.model import RayCluster, AppWrapper

def _print_no_cluster_found():
    pass

def print_clusters(clusters:List[RayCluster], verbose=True):
    console = Console()
    title_printed = False
    #FIXME handle case where no clusters are found
    if len(clusters) == 0:
        _print_no_cluster_found()
        return #exit early

    for cluster in clusters:
        status = "Active :white_heavy_check_mark:" if cluster.status.lower() == 'ready' else "InActive :x:"
        name = cluster.name
        dashboard = f"https://codeflare-raydashboard.research.ibm.com?rayclustername={name}"
        mincount = str(cluster.min_workers)
        maxcount = str(cluster.max_workers)
        memory = cluster.worker_mem_min+"~"+cluster.worker_mem_max
        cpu = str(cluster.worker_cpu)
        gpu = str(cluster.worker_mem_max)
        #owned = bool(cluster["userOwned"])
        owned = True

        #'table0' to display the cluster name, status, url, and dashboard link
        table0 = Table(box=None, show_header=False)
        if owned:
            table0.add_row("[white on green][bold]Owner")
        else:
            table0.add_row("")
        table0.add_row("[bold underline]"+name,status)
        table0.add_row()
        table0.add_row(f"[bold]URI:[/bold] ray://{name}-head.codeflare.svc:1001")
        table0.add_row()
        table0.add_row(f"[link={dashboard} blue underline]Dashboard:link:[/link]")
        table0.add_row("") #empty row for spacing


        #'table1' to display the worker counts
        table1 = Table(box=None)
        table1.add_row()
        table1.add_column("Min", style="cyan", no_wrap=True)
        table1.add_column("Max", style="magenta")
        table1.add_row()
        table1.add_row(mincount,maxcount)
        table1.add_row()

        #'table2' to display the worker resources
        table2 = Table(box=None)
        table2.add_column("Memory", style="cyan", no_wrap=True, min_width=10)
        table2.add_column("CPU", style="magenta", min_width=10)
        table2.add_column("GPU", style="magenta", min_width=10)
        table2.add_row()
        table2.add_row(memory, cpu, gpu)
        table2.add_row()

        #panels to encompass table1 and table2 into separate cards
        panel_1 = Panel.fit(table1,title="Workers")
        panel_2 = Panel.fit(table2, title="Worker specs(each)")

        #table3 to display panel_1 and panel_2 side-by-side in a single row
        table3 = Table(box=None, show_header=False, title="Cluster Resources")
        table3.add_row(panel_1,panel_2)

        #table4 to display table0 and table3, one below the other
        table4 = Table(box=None, show_header=False)
        table4.add_row(table0)
        table4.add_row(table3)

        # Encompass all details of the cluster in a single panel
        if not title_printed:
            #If first cluster in the list, then create a table with title "Codeflare clusters".
            #This is done to ensure the title is center aligned on the cluster display tables, rather
            #than being center aligned on the console/terminal if we simply use console.print(title)

            table5 = Table(box=None, title="[bold] :rocket: List of CodeFlare clusters :rocket:")
            table5.add_row(Panel.fit(table4))
            console.print(table5)
            title_printed = True
        else:
            console.print(Panel.fit(table4))

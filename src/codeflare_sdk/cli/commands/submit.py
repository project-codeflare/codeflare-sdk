import click
import yaml
import time

from codeflare_sdk.cluster.cluster import Cluster
from codeflare_sdk.cli.cli_utils import load_auth
import codeflare_sdk.cluster.auth as sdk_auth


@click.group()
def cli():
    """
    Submit a defined resource to the Kubernetes cluster
    """
    pass


@cli.command()
@click.argument("name", type=str)
@click.option("--wait", is_flag=True)
def raycluster(name, wait):
    """
    Submit a defined RayCluster to the Kubernetes cluster
    """
    cluster = Cluster.from_definition_yaml(name + ".yaml")
    if not cluster:
        click.echo(
            "Error submitting RayCluster. Make sure the RayCluster is defined before submitting it"
        )
        return
    if not wait:
        cluster.up()
        click.echo("Cluster submitted successfully")
        return
    cluster.up()
    cluster.wait_ready()

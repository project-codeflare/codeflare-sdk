import click

from codeflare_sdk.cluster.cluster import get_cluster
from codeflare_sdk.cli.cli_utils import load_auth


@click.group()
def cli():
    """
    Delete a specified resource from the Kubernetes cluster
    """
    pass


@cli.command()
@click.argument("name", type=str)
@click.option("--namespace", type=str, default="default")
def raycluster(name, namespace):
    """
    Delete a specified RayCluster from the Kubernetes cluster
    """
    cluster = get_cluster(name, namespace)
    cluster.down()
    click.echo(f"Cluster deleted successfully")

import click

from codeflare_sdk.cluster.cluster import get_cluster
from codeflare_sdk.cli.cli_utils import load_auth


@click.group()
def cli():
    pass


@cli.command()
@click.option("--name", type=str)
@click.option("--namespace", type=str, default="default")
def raycluster(name, namespace):
    load_auth()
    cluster = get_cluster(name, namespace)
    cluster.down()
    click.echo(f"Cluster deleted successfully")

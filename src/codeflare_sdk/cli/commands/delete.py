import click

from codeflare_sdk.cluster.cluster import get_cluster
from codeflare_sdk.cli.cli_utils import load_auth


@click.group()
def cli():
    pass


@cli.command()
@click.argument("name", type=str)
@click.option("--namespace", type=str, required=True)
def raycluster(name, namespace):
    cluster = get_cluster(name, namespace)
    cluster.down()
    click.echo(f"Cluster deleted successfully")

import click

from codeflare_sdk.cluster.cluster import get_cluster


@click.group()
def cli():
    pass


@cli.command()
@click.option("--name", type=str)
@click.option("--namespace", type=str, default="default")
def raycluster(name, namespace):
    cluster = get_cluster(name, namespace)
    cluster.down()
    click.echo(f"Cluster deleted successfully")

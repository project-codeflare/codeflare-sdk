import click

from codeflare_sdk.cluster.cluster import get_cluster


@click.group()
def cli():
    """Get the status of a specified resource"""
    pass


@cli.command()
@click.argument("name", type=str)
@click.option("--namespace", type=str)
@click.pass_context
def raycluster(ctx, name, namespace):
    """Get the status of a specified RayCluster"""
    namespace = namespace or "default"
    cluster = get_cluster(name, namespace)
    cluster.status()

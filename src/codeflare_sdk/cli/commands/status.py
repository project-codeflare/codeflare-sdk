import click

from codeflare_sdk.cluster.cluster import get_cluster


@click.group()
def cli():
    """Get the status of a specified resource"""
    pass


@cli.command()
@click.argument("name", type=str)
@click.option("--namespace", type=str, required=True)
@click.pass_context
def raycluster(ctx, name, namespace):
    """Get the status of a specified RayCluster"""
    try:
        cluster = get_cluster(name, namespace)
    except FileNotFoundError:
        click.echo(f"Cluster {name} not found in {namespace} namespace")
        return
    cluster.status()

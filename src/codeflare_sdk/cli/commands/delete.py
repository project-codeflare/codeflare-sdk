import click

from codeflare_sdk.cluster.cluster import get_cluster


@click.group()
def cli():
    """
    Delete a specified resource from the Kubernetes cluster
    """
    pass


@cli.command()
@click.argument("name", type=str)
@click.option("--namespace", type=str, required=True)
def raycluster(name, namespace):
    """
    Delete a specified RayCluster from the Kubernetes cluster
    """
    try:
        cluster = get_cluster(name, namespace)
    except FileNotFoundError:
        click.echo(f"Cluster {name} not found in {namespace} namespace")
        return
    cluster.down()
    click.echo(f"Cluster deleted successfully")

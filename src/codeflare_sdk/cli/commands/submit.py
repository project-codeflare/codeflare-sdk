import click
import yaml
import time

from codeflare_sdk.cluster.cluster import Cluster
from codeflare_sdk.cli.cli_utils import load_auth
import codeflare_sdk.cluster.auth as sdk_auth


@click.group()
def cli():
    pass


@cli.command()
@click.argument("cluster_name")
@click.option("--wait", type=bool, default=False)
def raycluster(cluster_name, wait):
    load_auth()
    cluster = Cluster.from_definition_yaml(cluster_name + ".yaml")
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

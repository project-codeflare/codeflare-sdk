import click
from kubernetes import client, config

from codeflare_sdk.cluster.cluster import (
    list_clusters_all_namespaces,
    list_all_clusters,
    get_current_namespace,
)
from codeflare_sdk.cli.cli_utils import load_auth


@click.group()
def cli():
    """List a specified resource"""
    pass


@cli.command()
@click.option("--namespace")
@click.option("--all", is_flag=True)
@click.pass_context
def rayclusters(ctx, namespace, all):
    """List all rayclusters in a specified namespace"""
    if all and namespace:
        click.echo("--all and --namespace are mutually exclusive")
        return
    namespace = namespace or "default"
    if not all:
        list_all_clusters(namespace)
        return
    list_clusters_all_namespaces()

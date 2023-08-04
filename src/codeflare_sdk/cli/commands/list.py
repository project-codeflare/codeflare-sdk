import click
from kubernetes import client, config

from codeflare_sdk.cluster.cluster import (
    list_clusters_all_namespaces,
    list_all_clusters,
)
from codeflare_sdk.cli.cli_utils import PluralAlias


@click.group(cls=PluralAlias)
def cli():
    """List a specified resource"""
    pass


@cli.command()
@click.option("--namespace", type=str)
@click.option("--all", is_flag=True)
@click.pass_context
def raycluster(ctx, namespace, all):
    """List all rayclusters in a specified namespace"""
    if all and namespace:
        click.echo("--all and --namespace are mutually exclusive")
        return
    namespace = namespace or ctx.obj.current_namespace
    if not all:
        list_all_clusters(namespace)
        return
    list_clusters_all_namespaces()

import click

from codeflare_sdk.cluster.cluster import (
    list_clusters_all_namespaces,
    list_all_clusters,
)
from codeflare_sdk.cli.cli_utils import PluralAlias
from codeflare_sdk.cluster.cluster import get_cluster
from codeflare_sdk.cluster.cluster import _copy_to_ray
from codeflare_sdk.cli.cli_utils import list_all_jobs
from codeflare_sdk.cli.cli_utils import list_all_kubernetes_jobs
from codeflare_sdk.cli.cli_utils import list_raycluster_jobs


@click.group(cls=PluralAlias)
def cli():
    """List a specified resource"""
    pass


@cli.command()
@click.option("--namespace", type=str)
@click.pass_context
def raycluster(ctx, namespace):
    """
    List all rayclusters
    """
    if namespace:
        list_all_clusters(namespace)
        return
    list_clusters_all_namespaces()


@cli.command()
@click.pass_context
@click.option("--cluster-name", "-c", type=str)
@click.option("--namespace", "-n", type=str)
@click.option("--kube-mcad-scheduler-only", is_flag=True)
def job(ctx, cluster_name, namespace, kube_mcad_scheduler_only):
    """
    List all jobs submitted
    """
    if cluster_name:
        cluster = get_cluster(cluster_name, namespace or ctx.obj.current_namespace)
        list_raycluster_jobs(_copy_to_ray(cluster), True)
        return
    if kube_mcad_scheduler_only:
        list_all_kubernetes_jobs(True)
        return
    list_all_jobs(True)

import click
import os

from codeflare_sdk.cluster.cluster import Cluster
import pickle
from torchx.runner import get_runner

from codeflare_sdk.cluster.cluster import get_cluster


@click.group()
def cli():
    """
    Submit a defined resource to the Kubernetes cluster
    """
    pass


@cli.command()
@click.argument("name", type=str)
@click.option("--wait", is_flag=True)
def raycluster(name, wait):
    """
    Submit a defined RayCluster to the Kubernetes cluster
    """
    cluster = Cluster.from_definition_yaml(name + ".yaml")
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


@cli.command()
@click.pass_context
@click.argument("name", type=str)
@click.option("--cluster-name", type=str)
@click.option("--namespace", type=str)
def job(ctx, name, cluster_name, namespace):
    """
    Submit a defined job to the Kubernetes cluster or a RayCluster
    """
    runner = get_runner()
    job_path = ctx.obj.codeflare_path + f"/{name}"
    if not os.path.isfile(job_path):
        click.echo(
            f"Error submitting job. Make sure the job is defined before submitting it"
        )
        return
    with open(job_path, "rb") as file:
        job_def = pickle.load(file)
    if not cluster_name:
        job = job_def.submit()
        submission_id = runner.describe(job._app_handle).name.split(":")[1]
        click.echo(f"Job {submission_id} submitted successfully")
        return
    namespace = namespace or ctx.obj.current_namespace
    try:
        cluster = get_cluster(cluster_name, namespace)
    except FileNotFoundError:
        click.echo(f"Cluster {name} not found in {namespace} namespace")
        return
    job = job_def.submit(cluster)
    full_name = runner.describe(job._app_handle).name
    submission_id = full_name[full_name.rfind(name) :]
    click.echo(
        f"Job {submission_id} submitted onto {cluster_name} RayCluster successfully\nView dashboard: {cluster.cluster_dashboard_uri()}"
    )

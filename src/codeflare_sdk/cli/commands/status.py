import click
from torchx.runner import get_runner

from codeflare_sdk.cluster.cluster import get_cluster
from codeflare_sdk.cli.cli_utils import get_job_app_handle


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
    namespace = namespace or ctx.obj.current_namespace
    try:
        cluster = get_cluster(name, namespace)
    except FileNotFoundError:
        click.echo(f"Cluster {name} not found in {namespace} namespace")
        return
    cluster.status()


@cli.command()
@click.pass_context
@click.argument("submission-id", type=str)
def job(ctx, submission_id):
    """Get the status of a specified job"""
    runner = get_runner()
    try:
        app_handle = get_job_app_handle(submission_id)
        click.echo(runner.status(app_handle=app_handle))
    except FileNotFoundError:
        click.echo(f"Submission ID {submission_id} not found in Kubernetes Cluster")
    except Exception as e:
        click.echo("Error getting job status: " + str(e))

import click
from torchx.runner import get_runner

from codeflare_sdk.cli.cli_utils import get_job_app_handle


@click.group()
def cli():
    """Get the logs of a specified resource"""
    pass


@cli.command()
@click.pass_context
@click.argument("submission-id", type=str)
def job(ctx, submission_id):
    """Get the logs of a specified job"""
    runner = get_runner()
    try:
        app_handle = get_job_app_handle(submission_id)
        click.echo("".join(runner.log_lines(app_handle, None)))
    except FileNotFoundError:
        click.echo(f"Submission ID {submission_id} not found in Kubernetes Cluster")
    except Exception as e:
        click.echo("Error getting job logs: " + str(e))

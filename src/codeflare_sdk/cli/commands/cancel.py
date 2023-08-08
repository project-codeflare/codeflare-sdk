import click
from torchx.runner import get_runner


from codeflare_sdk.cli.cli_utils import get_job_app_handle


@click.group()
def cli():
    """Cancel a resource"""
    pass


@cli.command()
@click.pass_context
@click.argument("submission-id", type=str)
def job(ctx, submission_id):
    """Cancel a job"""
    runner = get_runner()
    try:
        app_handle = get_job_app_handle(submission_id)
        runner.cancel(app_handle=app_handle)
        click.echo(f"{submission_id} cancelled successfully")
    except FileNotFoundError:
        click.echo(f"Submission ID {submission_id} not found in Kubernetes Cluster")
    except Exception as e:
        click.echo("Error cancelling job: " + str(e))

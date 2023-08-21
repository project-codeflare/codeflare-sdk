import click
import pickle

from codeflare_sdk.cluster.cluster import Cluster
from codeflare_sdk.cluster.config import ClusterConfiguration
from codeflare_sdk.cli.cli_utils import PythonLiteralOption
from codeflare_sdk.job.jobs import DDPJobDefinition


@click.group()
def cli():
    """Define a resource with parameter specifications"""
    pass


@cli.command()
@click.pass_context
@click.option("--name", type=str, required=True)
@click.option("--namespace", "-n", type=str)
@click.option("--head-info", cls=PythonLiteralOption, type=list)
@click.option("--machine-types", cls=PythonLiteralOption, type=list)
@click.option("--min-cpus", type=int)
@click.option("--max-cpus", type=int)
@click.option("--num-workers", type=int)
@click.option("--min-memory", type=int)
@click.option("--max-memory", type=int)
@click.option("--num-gpus", type=int)
@click.option("--template", type=str)
@click.option("--instascale", type=bool)
@click.option("--envs", cls=PythonLiteralOption, type=dict)
@click.option("--image", type=str)
@click.option("--local-interactive", type=bool)
@click.option("--image-pull-secrets", cls=PythonLiteralOption, type=list)
def raycluster(ctx, **kwargs):
    """Define a RayCluster with parameter specifications"""
    filtered_kwargs = {k: v for k, v in kwargs.items() if v is not None}
    if "namespace" not in filtered_kwargs.keys():
        filtered_kwargs["namespace"] = ctx.obj.current_namespace
    clusterConfig = ClusterConfiguration(**filtered_kwargs)
    Cluster(clusterConfig)  # Creates yaml file


@cli.command()
@click.pass_context
@click.option("--script", type=str, required=True)
@click.option("--m", type=str)
@click.option("--script-args", cls=PythonLiteralOption, type=list)
@click.option("--name", type=str, required=True)
@click.option("--cpu", type=int)
@click.option("--gpu", type=int)
@click.option("--memMB", type=int)
@click.option("--h", type=str)
@click.option("--j", type=str)
@click.option("--env", cls=PythonLiteralOption, type=dict)
@click.option("--max-retries", type=int)
@click.option("--mounts", cls=PythonLiteralOption, type=list)
@click.option("--rdzv-port", type=int)
@click.option("--rdzv-backend", type=str)
@click.option("--scheduler-args", cls=PythonLiteralOption, type=dict)
@click.option("--image", type=str)
@click.option("--workspace", type=str)
def job(ctx, **kwargs):
    """Define a job with specified resources"""
    filtered_kwargs = {k: v for k, v in kwargs.items() if v is not None}
    if "memmb" in filtered_kwargs:
        filtered_kwargs["memMB"] = filtered_kwargs["memmb"]
        del filtered_kwargs["memmb"]
    job_def = DDPJobDefinition(**filtered_kwargs)
    job_file_path = ctx.obj.codeflare_path + f"/{job_def.name}"
    with open(job_file_path, "wb") as file:
        pickle.dump(job_def, file)
    click.echo("Job definition saved to " + job_file_path)

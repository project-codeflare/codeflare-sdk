import click

from codeflare_sdk.cluster.cluster import Cluster
from codeflare_sdk.cluster.config import ClusterConfiguration
from codeflare_sdk.cli.cli_utils import PythonLiteralOption


@click.group()
def cli():
    """Define a resource with parameter specifications"""
    pass


@cli.command()
@click.option("--name", type=str, required=True)
@click.option("--namespace", "-n", type=str, required=True)
@click.option("--head_info", cls=PythonLiteralOption, type=list)
@click.option("--machine_types", cls=PythonLiteralOption, type=list)
@click.option("--min_cpus", type=int)
@click.option("--max_cpus", type=int)
@click.option("--min_worker", type=int)
@click.option("--max_worker", type=int)
@click.option("--min_memory", type=int)
@click.option("--max_memory", type=int)
@click.option("--gpu", type=int)
@click.option("--template", type=str)
@click.option("--instascale", type=bool)
@click.option("--envs", cls=PythonLiteralOption, type=dict)
@click.option("--image", type=str)
@click.option("--local_interactive", type=bool)
@click.option("--image_pull_secrets", cls=PythonLiteralOption, type=list)
def raycluster(**kwargs):
    """Define a RayCluster with parameter specifications"""
    filtered_kwargs = {k: v for k, v in kwargs.items() if v is not None}
    clusterConfig = ClusterConfiguration(**filtered_kwargs)
    Cluster(clusterConfig)  # Creates yaml file

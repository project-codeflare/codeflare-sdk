import ast
import click
from kubernetes import client, config
import pickle
import os
from ray.job_submission import JobSubmissionClient
from torchx.runner import get_runner
from rich.table import Table
from rich import print

from codeflare_sdk.cluster.cluster import list_clusters_all_namespaces, get_cluster
from codeflare_sdk.cluster.model import RayCluster
from codeflare_sdk.cluster.auth import _create_api_client_config, config_check
from codeflare_sdk.utils.kube_api_helpers import _kube_api_error_handling
import codeflare_sdk.cluster.auth as sdk_auth


class PythonLiteralOption(click.Option):
    def type_cast_value(self, ctx, value):
        try:
            if not value:
                return None
            return ast.literal_eval(value)
        except:
            raise click.BadParameter(value)


class AuthenticationConfig:
    """
    Authentication configuration that will be stored in a file once
    the user logs in using `codeflare login`
    """

    def __init__(
        self,
        token: str,
        server: str,
        skip_tls: bool,
        ca_cert_path: str,
    ):
        self.api_client_config = _create_api_client_config(
            token, server, skip_tls, ca_cert_path
        )
        self.server = server
        self.token = token

    def create_client(self):
        return client.ApiClient(self.api_client_config)


def load_auth():
    """
    Loads AuthenticationConfiguration and stores it in global variables
    which can be used by the SDK for authentication
    """
    try:
        auth_file_path = os.path.expanduser("~/.codeflare/auth")
        with open(auth_file_path, "rb") as file:
            auth = pickle.load(file)
            sdk_auth.api_client = auth.create_client()
            return auth
    except (IOError, EOFError):
        click.echo("No authentication found, trying default kubeconfig")
    except client.ApiException:
        click.echo("Invalid authentication, trying default kubeconfig")


class PluralAlias(click.Group):
    def get_command(self, ctx, cmd_name):
        rv = click.Group.get_command(self, ctx, cmd_name)
        if rv is not None:
            return rv
        for x in self.list_commands(ctx):
            if x + "s" == cmd_name:
                return click.Group.get_command(self, ctx, x)
        return None

    def resolve_command(self, ctx, args):
        # always return the full command name
        _, cmd, args = super().resolve_command(ctx, args)
        return cmd.name, cmd, args


def print_jobs(jobs):
    headers = ["Submission ID", "Job ID", "RayCluster", "Namespace", "Status"]
    table = Table(show_header=True)
    for header in headers:
        table.add_column(header)
    for job in jobs:
        table.add_row(*[job[header] for header in headers])
    print(table)


def list_all_kubernetes_jobs(print_to_console=True):
    k8s_jobs = []
    runner = get_runner()
    jobs = runner.list(scheduler="kubernetes_mcad")
    rayclusters = {
        raycluster.name for raycluster in list_clusters_all_namespaces(False)
    }
    for job in jobs:
        namespace, name = job.app_id.split(":")
        status = job.state
        if name not in rayclusters:
            k8s_jobs.append(
                {
                    "Submission ID": name,
                    "Job ID": "N/A",
                    "RayCluster": "N/A",
                    "Namespace": namespace,
                    "Status": str(status),
                    "App Handle": job.app_handle,
                }
            )
    if print_to_console:
        print_jobs(k8s_jobs)
    return k8s_jobs


def list_all_jobs(print_to_console=True):
    k8s_jobs = list_all_kubernetes_jobs(False)
    rc_jobs = list_all_raycluster_jobs(False)
    all_jobs = rc_jobs + k8s_jobs
    if print_to_console:
        print_jobs(all_jobs)
    return all_jobs


def list_raycluster_jobs(cluster: RayCluster, print_to_console=True):
    rc_jobs = []
    client = JobSubmissionClient(cluster.dashboard)
    jobs = client.list_jobs()
    for job in jobs:
        job_obj = {
            "Submission ID": job.submission_id,
            "Job ID": job.job_id,
            "RayCluster": cluster.name,
            "Namespace": cluster.namespace,
            "Status": str(job.status),
            "App Handle": "ray://torchx/" + cluster.dashboard + "-" + job.submission_id,
        }
        rc_jobs.append(job_obj)
    if print_to_console:
        print_jobs(rc_jobs)
    return rc_jobs


def list_all_raycluster_jobs(print_to_console=True):
    rc_jobs = []
    clusters = list_clusters_all_namespaces(False)
    for cluster in clusters:
        cluster.dashboard = "http://" + cluster.dashboard
        rc_jobs += list_raycluster_jobs(cluster, False)
    if print_to_console:
        print_jobs(rc_jobs)
    return rc_jobs


def get_job_app_handle(job_submission):
    job = get_job_object(job_submission)
    return job["App Handle"]


def get_job_object(job_submission):
    all_jobs = list_all_jobs(False)
    for job in all_jobs:
        if job["Submission ID"] == job_submission:
            return job
    raise (
        FileNotFoundError(
            f"Job {job_submission} not found. Try using 'codeflare list --all' to see all jobs"
        )
    )

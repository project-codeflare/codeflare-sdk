import click
import pickle
from kubernetes import client
import os

from codeflare_sdk.cluster.auth import TokenAuthentication
from codeflare_sdk.cli.cli_utils import AuthenticationConfig
import codeflare_sdk.cluster.auth as sdk_auth


@click.command()
@click.pass_context
@click.option("--server", "-s", type=str, required=True, help="Cluster API address")
@click.option("--token", "-t", type=str, required=True, help="Authentication token")
@click.option(
    "--insecure-skip-tls-verify",
    type=bool,
    help="If true, server's certificate won't be checked for validity",
    default=False,
)
@click.option(
    "--certificate-authority",
    type=str,
    help="Path to cert file for certificate authority",
)
def cli(ctx, server, token, insecure_skip_tls_verify, certificate_authority):
    """
    Login to your Kubernetes cluster and save login for subsequent use
    """
    auth = TokenAuthentication(
        token, server, insecure_skip_tls_verify, certificate_authority
    )
    auth.login()
    if not sdk_auth.api_client:  # TokenAuthentication failed
        return

    auth_config = AuthenticationConfig(
        token,
        server,
        insecure_skip_tls_verify,
        certificate_authority,
    )
    auth_file_path = ctx.obj.codeflare_path + "/auth"
    with open(auth_file_path, "wb") as file:
        pickle.dump(auth_config, file)
    click.echo(f"Logged into '{server}'")

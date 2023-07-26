import click
import pickle
from kubernetes import client

from codeflare_sdk.cluster.auth import TokenAuthentication
from codeflare_sdk.cli.cli_utils import AuthenticationConfig
import codeflare_sdk.cluster.auth as sdk_auth


@click.command()
@click.option("--server", "-s", type=str, required=True, help="Cluster API address")
@click.option("--token", "-t", type=str, required=True, help="Authentication token")
@click.option(
    "--insecure-skip-tls-verify",
    type=bool,
    help="If true, server's certificate won't be checked for validity",
)
@click.option(
    "--certificate-authority",
    type=str,
    help="Path to cert file for certificate authority",
)
def cli(server, token, insecure_skip_tls_verify, certificate_authority):
    """
    Login to your Kubernetes cluster and save login for subsequent use
    """
    auth = TokenAuthentication(
        token, server, insecure_skip_tls_verify, certificate_authority
    )
    auth.login()
    if not sdk_auth.api_client:  # TokenAuthentication failed
        return

    authConfig = AuthenticationConfig(
        token,
        server,
        insecure_skip_tls_verify,
        certificate_authority,
    )
    with open("auth", "wb") as file:
        pickle.dump(authConfig, file)
    click.echo(f"Logged into '{server}'")

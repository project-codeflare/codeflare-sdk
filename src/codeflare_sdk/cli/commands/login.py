import click
import pickle

from codeflare_sdk.cluster.auth import TokenAuthentication
from codeflare_sdk.cli.cli_utils import AuthenticationConfig, load_auth
import codeflare_sdk.cluster.auth as sdk_auth


@click.command()
@click.option("--server", type=str, required=True, help="Cluster API address")
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
    try:
        auth = TokenAuthentication(
            token, server, insecure_skip_tls_verify, certificate_authority
        )
        auth.login()

        # Store auth config for later use
        authConfig = AuthenticationConfig(
            token,
            server,
            insecure_skip_tls_verify,
            certificate_authority,
            sdk_auth.config_path,
        )
        with open("auth", "wb") as file:
            pickle.dump(authConfig, file)
        click.echo(f"Logged into {server}")
    except Exception as e:
        click.echo(e)

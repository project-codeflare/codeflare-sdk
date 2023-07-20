import click
import pickle

from codeflare_sdk.cluster.auth import TokenAuthentication
from codeflare_sdk.cli.cli_utils import AuthenticationConfig
import codeflare_sdk.cluster.auth as sdk_auth


@click.command()
@click.argument("server")
@click.option("--token", "-t", type=str, required=True)
@click.option("--skip-tls", type=bool)
@click.option("--ca-cert-path", type=str)
def cli(server, token, skip_tls, ca_cert_path):
    """
    Login to your Kubernetes cluster by specifying server and token
    """
    try:
        auth = TokenAuthentication(token, server, skip_tls, ca_cert_path)
        auth.login()
        authConfig = AuthenticationConfig(
            token, server, skip_tls, ca_cert_path, sdk_auth.config_path
        )
        with open("auth", "wb") as file:
            pickle.dump(authConfig, file)
        click.echo(f"Logged into {server}")
    except Exception as e:
        click.echo(e)

import click
import os

from codeflare_sdk.cli.cli_utils import load_auth


@click.command()
def cli():
    """
    Log out of current Kubernetes cluster
    """
    auth = load_auth()
    if not auth:
        click.echo("Not logged in")
        return
    os.remove("auth")
    click.echo(f"Successfully logged out of '{auth.server}'")

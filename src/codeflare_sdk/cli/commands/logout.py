import click
import os
import pickle


@click.command()
@click.pass_context
def cli(ctx):
    """
    Log out of current Kubernetes cluster
    """
    try:
        auth_file_path = ctx.obj.codeflare_path + "/auth"
        with open(auth_file_path, "rb") as file:
            auth = pickle.load(file)
        os.remove(auth_file_path)
        click.echo(f"Successfully logged out of '{auth.server}'")
    except:
        click.echo("Not logged in")

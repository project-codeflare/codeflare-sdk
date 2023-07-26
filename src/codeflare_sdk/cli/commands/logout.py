import click
import os
import pickle


@click.command()
def cli():
    """
    Log out of current Kubernetes cluster
    """
    try:
        with open("auth", "rb") as file:
            auth = pickle.load(file)
        os.remove("auth")
        click.echo(f"Successfully logged out of '{auth.server}'")
    except:
        click.echo("Not logged in")

import click
import os

from codeflare_sdk.cli.cli_utils import load_auth
from codeflare_sdk.cluster.cluster import get_current_namespace

cmd_folder = os.path.abspath(os.path.join(os.path.dirname(__file__), "commands"))


class CodeflareContext:
    def __init__(self):
        self.codeflare_path = _initialize_codeflare_folder()
        self.current_namespace = get_current_namespace()


def _initialize_codeflare_folder():
    codeflare_folder = os.path.expanduser("~/.codeflare")
    if not os.path.exists(codeflare_folder):
        os.makedirs(codeflare_folder)
    return codeflare_folder


class CodeflareCLI(click.MultiCommand):
    def list_commands(self, ctx):
        rv = []
        for filename in os.listdir(cmd_folder):
            if filename.endswith(".py") and filename != "__init__.py":
                rv.append(filename[:-3])
        rv.sort()
        return rv

    def get_command(self, ctx, name):
        ns = {}
        fn = os.path.join(cmd_folder, name + ".py")
        try:
            with open(fn) as f:
                code = compile(f.read(), fn, "exec")
                eval(code, ns, ns)
            return ns["cli"]
        except FileNotFoundError:
            return


@click.command(cls=CodeflareCLI)
@click.pass_context
def cli(ctx):
    load_auth()
    ctx.obj = CodeflareContext()  # Ran on every command
    pass


if __name__ == "__main__":
    cli()

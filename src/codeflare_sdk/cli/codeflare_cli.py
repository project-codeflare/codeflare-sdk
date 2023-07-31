import click
import sys
import os

cmd_folder = os.path.abspath(os.path.join(os.path.dirname(__file__), "commands"))


class CodeflareContext:
    def __init__(self, codeflare_path):
        self.codeflare_path = codeflare_path


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


def initialize_cli(ctx):
    # Make .codeflare folder
    codeflare_folder = os.path.expanduser("~/.codeflare")
    if not os.path.exists(codeflare_folder):
        os.makedirs(codeflare_folder)
    ctx.obj = CodeflareContext(codeflare_folder)


@click.command(cls=CodeflareCLI)
@click.pass_context
def cli(ctx):
    initialize_cli(ctx)  # Ran on every command
    pass


if __name__ == "__main__":
    cli()

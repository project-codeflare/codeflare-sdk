import click
import sys
import os

cmd_folder = os.path.abspath(os.path.join(os.path.dirname(__file__), "commands"))


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
        with open(fn) as f:
            code = compile(f.read(), fn, "exec")
            eval(code, ns, ns)
        return ns["cli"]


@click.command(cls=CodeflareCLI)
@click.pass_context
def cli(ctx):
    pass


if __name__ == "__main__":
    cli()

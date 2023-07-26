import ast
import click


class PythonLiteralOption(click.Option):
    def type_cast_value(self, ctx, value):
        try:
            if not value:
                return None
            return ast.literal_eval(value)
        except:
            raise click.BadParameter(value)

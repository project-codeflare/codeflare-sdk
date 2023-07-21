import ast
import click
from kubernetes import client
import pickle

from codeflare_sdk.cluster.auth import _create_api_client_config
import codeflare_sdk.cluster.auth as sdk_auth


class PythonLiteralOption(click.Option):
    def type_cast_value(self, ctx, value):
        try:
            if not value:
                return None
            return ast.literal_eval(value)
        except:
            raise click.BadParameter(value)


class AuthenticationConfig:
    """
    Authentication configuration that will be stored in a file once
    the user logs in using `codeflare login`
    """

    def __init__(
        self,
        token: str,
        server: str,
        skip_tls: bool,
        ca_cert_path: str,
        k8_config_path: str,
    ):
        self.api_client_config = _create_api_client_config(
            token, server, skip_tls, ca_cert_path
        )
        self.k8_config_path = k8_config_path

    def create_client(self):
        return client.ApiClient(self.api_client_config)


def load_auth():
    """
    Loads AuthenticationConfiguration and stores it in global variables
    which can be used by the SDK for authentication
    """
    try:
        with open("auth", "rb") as file:
            auth = pickle.load(file)
            sdk_auth.api_client = auth.create_client()
            sdk_auth.config_path = auth.k8_config_path
            return auth
    except IOError:
        return None
    except EOFError:
        return None

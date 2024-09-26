# Copyright 2022 IBM, Red Hat
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
The auth sub-module contains the definitions for the Authentication objects, which represent
the methods by which a user can authenticate to their cluster(s). The abstract class, `Authentication`,
contains two required methods `login()` and `logout()`. Users can use one of the existing concrete classes to
authenticate to their cluster or add their own custom concrete classes here.
"""

import abc
from kubernetes import client, config
import os
import urllib3
from ..utils.kube_api_helpers import _kube_api_error_handling

from typing import Optional

global api_client
api_client = None
global config_path
config_path = None

WORKBENCH_CA_CERT_PATH = "/etc/pki/tls/custom-certs/ca-bundle.crt"


class Authentication(metaclass=abc.ABCMeta):
    """
    An abstract class that defines the necessary methods for authenticating to a remote environment.
    Specifically, this class defines the need for a `login()` and a `logout()` function.
    """

    def login(self):
        """
        Method for logging in to a remote cluster.
        """
        pass

    def logout(self):
        """
        Method for logging out of the remote cluster.
        """
        pass


class KubeConfiguration(metaclass=abc.ABCMeta):
    """
    An abstract class that defines the method for loading a user defined config file using the `load_kube_config()` function
    """

    def load_kube_config(self):
        """
        Method for setting your Kubernetes configuration to a certain file
        """
        pass

    def logout(self):
        """
        Method for logging out of the remote cluster
        """
        pass


class TokenAuthentication(Authentication):
    """
    `TokenAuthentication` is a subclass of `Authentication`. It can be used to authenticate to a Kubernetes
    cluster when the user has an API token and the API server address.
    """

    def __init__(
        self,
        token: str,
        server: str,
        skip_tls: bool = False,
        ca_cert_path: str = None,
    ):
        """
        Initialize a TokenAuthentication object that requires a value for `token`, the API Token
        and `server`, the API server address for authenticating to a Kubernetes cluster.
        """

        self.token = token
        self.server = server
        self.skip_tls = skip_tls
        self.ca_cert_path = self._gen_ca_cert_path(ca_cert_path)

    def _gen_ca_cert_path(self, ca_cert_path: str):
        if ca_cert_path is not None:
            return ca_cert_path
        elif "CF_SDK_CA_CERT_PATH" in os.environ:
            return os.environ.get("CF_SDK_CA_CERT_PATH")
        elif os.path.exists(WORKBENCH_CA_CERT_PATH):
            return WORKBENCH_CA_CERT_PATH
        else:
            return None

    def login(self) -> str:
        """
        This function is used to log in to a Kubernetes cluster using the user's API token and API server address.
        Depending on the cluster, a user can choose to login in with `--insecure-skip-tls-verify` by setting `skip_tls`
        to `True` or `--certificate-authority` by setting `skip_tls` to False and providing a path to a ca bundle with `ca_cert_path`.
        """
        global config_path
        global api_client
        try:
            configuration = client.Configuration()
            configuration.api_key_prefix["authorization"] = "Bearer"
            configuration.host = self.server
            configuration.api_key["authorization"] = self.token

            if not self.skip_tls:
                if self.ca_cert_path is None:
                    configuration.ssl_ca_cert = None
                elif os.path.isfile(self.ca_cert_path):
                    print(
                        f"Authenticated with certificate located at {self.ca_cert_path}"
                    )
                    configuration.ssl_ca_cert = self.ca_cert_path
                else:
                    raise FileNotFoundError(
                        f"Certificate file not found at {self.ca_cert_path}"
                    )
                configuration.verify_ssl = True
            else:
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                print("Insecure request warnings have been disabled")
                configuration.verify_ssl = False

            api_client = client.ApiClient(configuration)
            client.AuthenticationApi(api_client).get_api_group()
            config_path = None
            return "Logged into %s" % self.server
        except client.ApiException as e:
            _kube_api_error_handling(e)

    def logout(self) -> str:
        """
        This function is used to logout of a Kubernetes cluster.
        """
        global config_path
        config_path = None
        global api_client
        api_client = None
        return "Successfully logged out of %s" % self.server


class KubeConfigFileAuthentication(KubeConfiguration):
    """
    A class that defines the necessary methods for passing a user's own Kubernetes config file.
    Specifically this class defines the `load_kube_config()` and `config_check()` functions.
    """

    def __init__(self, kube_config_path: str = None):
        self.kube_config_path = kube_config_path

    def load_kube_config(self):
        """
        Function for loading a user's own predefined Kubernetes config file.
        """
        global config_path
        global api_client
        try:
            if self.kube_config_path == None:
                return "Please specify a config file path"
            config_path = self.kube_config_path
            api_client = None
            config.load_kube_config(config_path)
            response = "Loaded user config file at path %s" % self.kube_config_path
        except config.ConfigException:  # pragma: no cover
            config_path = None
            raise Exception("Please specify a config file path")
        return response


def config_check() -> str:
    """
    Function for loading the config file at the default config location ~/.kube/config if the user has not
    specified their own config file or has logged in with their token and server.
    """
    global config_path
    global api_client
    home_directory = os.path.expanduser("~")
    if config_path == None and api_client == None:
        if os.path.isfile("%s/.kube/config" % home_directory):
            try:
                config.load_kube_config()
            except Exception as e:  # pragma: no cover
                _kube_api_error_handling(e)
        elif "KUBERNETES_PORT" in os.environ:
            try:
                config.load_incluster_config()
            except Exception as e:  # pragma: no cover
                _kube_api_error_handling(e)
        else:
            raise PermissionError(
                "Action not permitted, have you put in correct/up-to-date auth credentials?"
            )

    if config_path != None and api_client == None:
        return config_path


def api_config_handler() -> Optional[client.ApiClient]:
    """
    This function is used to load the api client if the user has logged in
    """
    if api_client != None and config_path == None:
        return api_client
    else:
        return None


def get_current_namespace():  # pragma: no cover
    config_check()
    if os.path.isfile("/var/run/secrets/kubernetes.io/serviceaccount/namespace"):
        try:
            file = open("/var/run/secrets/kubernetes.io/serviceaccount/namespace", "r")
            active_context = file.readline().strip("\n")
            return active_context
        except Exception as e:
            print("Unable to find current namespace")
    if api_config_handler() is not None:
        return None
    print("trying to gather from current context")
    try:
        _, active_context = config.list_kube_config_contexts(config_check())
    except Exception as e:
        return _kube_api_error_handling(e)
    try:
        return active_context["context"]["namespace"]
    except KeyError:
        return None

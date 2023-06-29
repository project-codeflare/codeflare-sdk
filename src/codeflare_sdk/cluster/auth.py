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
import os
from kubernetes import client, config

global path_set
path_set = False


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

    def config_check(self):
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
        token: str = None,
        server: str = None,
        skip_tls: bool = False,
        ca_cert_path: str = "/etc/pki/tls/certs/ca-bundle.crt",
    ):
        """
        Initialize a TokenAuthentication object that requires a value for `token`, the API Token
        and `server`, the API server address for authenticating to a Kubernetes cluster.
        """

        self.token = token
        self.server = server
        self.skip_tls = skip_tls
        self.ca_cert_path = ca_cert_path

    def login(self) -> str:
        """
        This function is used to log in to a Kubernetes cluster using the user's API token and API server address.
        Depending on the cluster, a user can choose to login in with `--insecure-skip-tls-verify` by setting `skip_tls`
        to `True` or `--certificate-authority` by setting `skip_tls` to false and providing a path to a ca bundle with `ca_cert_path`.
        """
        global path_set
        global api_client
        try:
            configuration = client.Configuration()
            configuration.api_key_prefix["authorization"] = "Bearer"
            configuration.host = self.server
            configuration.api_key["authorization"] = self.token
            if self.skip_tls == False:
                configuration.ssl_ca_cert = self.ca_cert_path
            else:
                configuration.verify_ssl = False
            api_client = client.ApiClient(configuration)
            path_set = False
            return "Logged into %s" % self.server
        except client.ApiException as exception:
            return exception

    def api_config_handler():
        """
        This function is used to load the api client if the user has logged in
        """
        if api_client != None and path_set == False:
            return api_client
        else:
            return None

    def logout(self) -> str:
        """
        This function is used to logout of a Kubernetes cluster.
        """
        global path_set
        path_set = False
        global api_client
        api_client = None


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
        global path_set
        global api_client
        try:
            path_set = True
            api_client = None
            config.load_kube_config(self.kube_config_path)
            response = "Loaded user config file at path %s" % self.kube_config_path
        except config.ConfigException:
            path_set = False
            raise Exception("Please specify a config file path")
        return response

    def config_check():
        """
        Function for loading the config file at the default config location ~/.kube/config if the user has not
        specified their own config file or has logged in with their token and server.
        """
        if path_set == False and api_client == None:
            config.load_kube_config()

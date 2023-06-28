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
import pathlib
from kubernetes import config
from jinja2 import Environment, FileSystemLoader
import os

global path_set
path_set = False

"""
auth = KubeConfigFileAuthentication(
            kube_config_path="config"
        )
auth.load_kube_config()


"""


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
    `TokenAuthentication` is a subclass of `Authentication`. It can be used to authenticate to an OpenShift
    cluster when the user has an API token and the API server address.
    """

    def __init__(
        self,
        token: str = None,
        server: str = None,
        skip_tls: bool = False,
        ca_cert_path: str = "/etc/pki/tls/certs/ca-bundle.crt",
        username: str = "user",
    ):
        """
        Initialize a TokenAuthentication object that requires a value for `token`, the API Token
        and `server`, the API server address for authenticating to an OpenShift cluster.
        """

        self.token = token
        self.server = server
        self.skip_tls = skip_tls
        self.ca_cert_path = ca_cert_path
        self.username = username

    def login(self) -> str:
        """
        This function is used to login to a Kubernetes cluster using the user's API token and API server address.
        Depending on the cluster, a user can choose to login in with `--insecure-skip-tls-verify` by setting `skip_tls`
        to `True` or `--certificate-authority` by setting `skip_tls` to false and providing a path to a ca bundle with `ca_cert_path`.

        If a user does not have a Kubernetes config file one is created from a template with the appropriate user functionality
        and if they do it is updated with new credentials.
        """
        dir = pathlib.Path(__file__).parent.parent.resolve()
        home = os.path.expanduser("~")
        try:
            security = "insecure-skip-tls-verify: false"
            if self.skip_tls == False:
                security = "certificate-authority: %s" % self.ca_cert_path
            else:
                security = "insecure-skip-tls-verify: true"

            env = Environment(
                loader=FileSystemLoader(f"{dir}/templates"),
                trim_blocks=True,
                lstrip_blocks=True,
            )
            template = env.get_template("config.yaml")
            server = self.server
            cluster_name = server[8:].replace(".", "-")
            # If there is no .kube folder it is created.
            if not os.path.isdir("%s/.kube" % home):
                os.mkdir("%s/.kube" % home)

            # If a config file exists then it will be updated with new fields and values.
            if os.path.isfile("%s/.kube/config" % home):
                file = open(r"%s/.kube/config" % home, "r").readlines()
                write_file = open(r"%s/.kube/config" % home, "w")
                existing = False
                # Check for existing config
                for line in file:
                    if self.server in line:
                        existing = True

                if existing == False:
                    for line in file:
                        # All of these fields are given new lines underneath with credentials info.
                        if "clusters:" in line:
                            write_file.write(line)
                            write_file.write(
                                "- cluster:\n    %(security)s\n    server: %(server)s\n  name: %(cluster)s\n"
                                % {
                                    "security": security,
                                    "server": self.server,
                                    "cluster": cluster_name,
                                }
                            )
                            continue
                        if "contexts:" in line:
                            write_file.write(line)
                            write_file.write(
                                "- context:\n    cluster: %(cluster)s\n    namespace: default\n    user: %(user)s/%(cluster)s\n  name: default/%(cluster)s/%(user)s\n"
                                % {"cluster": cluster_name, "user": self.username}
                            )
                            continue
                        if "current-context:" in line:
                            write_file.write(
                                "current-context: default/{}/{}\n".format(
                                    cluster_name, self.username
                                )
                            )
                            continue
                        if "users:" in line:
                            write_file.write(line)
                            write_file.write(
                                "- name: {}/{}\n  user:\n    token: {}\n".format(
                                    self.username, cluster_name, self.token
                                )
                            )
                            continue

                        write_file.write(line)
                else:
                    # If there is an existing config just update the token and username
                    for line in file:
                        if "users:" in line:
                            write_file.write(line)
                            write_file.write(
                                "- name: {}/{}\n  user:\n    token: {}\n".format(
                                    self.username, cluster_name, self.token
                                )
                            )
                            continue
                        write_file.write(line)

                response = "Updated config file at %s/.kube/config" % home
            else:
                # Create a new config file from the config template and store it in HOME/.kube
                file = open("%s/.kube/config" % home, "w")
                file.write(
                    template.render(
                        security=security,
                        server=server,
                        cluster=cluster_name,
                        context_name="default/{}/{}".format(
                            cluster_name, self.username
                        ),
                        current_context="default/{}/{}".format(
                            cluster_name, self.username
                        ),
                        username="{}/{}".format(self.username, cluster_name),
                        token=self.token,
                    )
                )
                response = (
                    "Logged in and created new config file at %s/.kube/config" % home
                )
        except:
            response = "Error logging in. Have you inputted correct credentials?"
        return response

    def logout(self) -> str:
        """
        This function is used to logout of a Kubernetes cluster.
        """
        home = os.path.expanduser("~")
        file = open(r"%s/.kube/config" % home, "r")
        lines = file.readlines()
        line_count = 0
        for line in lines:
            if (
                "- name: {}/{}".format(self.username, self.server[8:].replace(".", "-"))
                not in line.strip()
            ):
                line_count = line_count + 1
            else:
                break
        # The name, user and token are removed from the config file
        with open(r"%s/.kube/config" % home, "w") as file:
            for number, line in enumerate(lines):
                if number not in [line_count, line_count + 1, line_count + 2]:
                    file.write(line)
        print("logged out of user %s" % self.username)


class KubeConfigFileAuthentication(KubeConfiguration):
    """
    An abstract class that defines the necessary methods for passing a user's own Kubernetes config file.
    Specifically this class defines the `load_kube_config()`, `config_check()` and `remove_config()` functions.
    """

    def __init__(self, kube_config_path: str = None):
        self.kube_config_path = kube_config_path

    def load_kube_config(self):
        global path_set
        try:
            path_set = True
            print("Loaded user config file at path %s" % self.kube_config_path)
            response = config.load_kube_config(self.kube_config_path)
        except config.ConfigException:
            path_set = False
            raise Exception("Please specify a config file path")
        return response

    def config_check():
        if path_set == False:
            config.load_kube_config()

    def remove_config(self) -> str:
        global path_set
        path_set = False
        os.remove(self.kube_config_path)
        print("Removed config file")

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
import openshift as oc
from openshift import OpenShiftPythonException


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


class TokenAuthentication(Authentication):
    """
    `TokenAuthentication` is a subclass of `Authentication`. It can be used to authenticate to an OpenShift
    cluster when the user has an API token and the API server address.
    """

    def __init__(self, token: str = None, server: str = None, skip_tls: bool = False):
        """
        Initialize a TokenAuthentication object that requires a value for `token`, the API Token
        and `server`, the API server address for authenticating to an OpenShift cluster.
        """

        self.token = token
        self.server = server
        self.skip_tls = skip_tls

    def login(self):
        """
        This function is used to login to an OpenShift cluster using the user's API token and API server address.
        Depending on the cluster, a user can choose to login in with "--insecure-skip-tls-verify` by setting `skip_tls`
        to `True`.
        """
        args = [f"--token={self.token}", f"--server={self.server}:6443"]
        if self.skip_tls:
            args.append("--insecure-skip-tls-verify")
        try:
            response = oc.invoke("login", args)
        except OpenShiftPythonException as osp:
            error_msg = osp.result.err()
            if "The server uses a certificate signed by unknown authority" in error_msg:
                return "Error: certificate auth failure, please set `skip_tls=True` in TokenAuthentication"
            else:
                return error_msg
        return response.out()

    def logout(self):
        """
        This function is used to logout of an OpenShift cluster.
        """
        response = oc.invoke("logout")
        return response.out()


class PasswordUserAuthentication(Authentication):
    """
    `PasswordUserAuthentication` is a subclass of `Authentication`. It can be used to authenticate to an OpenShift
    cluster when the user has a username and password.
    """

    def __init__(
        self,
        username: str = None,
        password: str = None,
    ):
        """
        Initialize a PasswordUserAuthentication object that requires a value for `username`
        and `password` for authenticating to an OpenShift cluster.
        """
        self.username = username
        self.password = password

    def login(self):
        """
        This function is used to login to an OpenShift cluster using the user's `username` and `password`.
        """
        response = oc.login(self.username, self.password)
        return response.out()

    def logout(self):
        """
        This function is used to logout of an OpenShift cluster.
        """
        response = oc.invoke("logout")
        return response.out()

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
The awload sub-module contains the definition of the AWManager object, which handles
submission and deletion of existing AppWrappers from a user's file system.
"""

from os.path import isfile
import errno
import os
import yaml

from kubernetes import client, config
from ..utils.kube_api_helpers import _kube_api_error_handling
from .auth import config_check, api_config_handler


class AWManager:
    """
    An object for submitting and removing existing AppWrapper yamls
    to be added to the Kueue localqueue.
    """

    def __init__(self, filename: str) -> None:
        """
        Create the AppWrapper Manager object by passing in an
        AppWrapper yaml file
        """
        if not isfile(filename):
            raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), filename)
        self.filename = filename
        try:
            with open(self.filename) as f:
                self.awyaml = yaml.load(f, Loader=yaml.FullLoader)
            assert self.awyaml["kind"] == "AppWrapper"
            self.name = self.awyaml["metadata"]["name"]
            self.namespace = self.awyaml["metadata"]["namespace"]
        except:
            raise ValueError(
                f"{filename } is not a correctly formatted AppWrapper yaml"
            )
        self.submitted = False

    def submit(self) -> None:
        """
        Attempts to create the AppWrapper custom resource using the yaml file
        """
        try:
            config_check()
            api_instance = client.CustomObjectsApi(api_config_handler())
            api_instance.create_namespaced_custom_object(
                group="workload.codeflare.dev",
                version="v1beta2",
                namespace=self.namespace,
                plural="appwrappers",
                body=self.awyaml,
            )
        except Exception as e:
            return _kube_api_error_handling(e)

        self.submitted = True
        print(f"AppWrapper {self.filename} submitted!")

    def remove(self) -> None:
        """
        Attempts to delete the AppWrapper custom resource matching the name in the yaml,
        if submitted by this manager.
        """
        if not self.submitted:
            print("AppWrapper not submitted by this manager yet, nothing to remove")
            return

        try:
            config_check()
            api_instance = client.CustomObjectsApi(api_config_handler())
            api_instance.delete_namespaced_custom_object(
                group="workload.codeflare.dev",
                version="v1beta2",
                namespace=self.namespace,
                plural="appwrappers",
                name=self.name,
            )
        except Exception as e:
            return _kube_api_error_handling(e)

        self.submitted = False
        print(f"AppWrapper {self.name} removed!")

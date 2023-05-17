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
import openshift as oc
import yaml


class AWManager:
    """
    An object for submitting and removing existing AppWrapper yamls
    to be added to the MCAD queue.
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
                awyaml = yaml.load(f, Loader=yaml.FullLoader)
            assert awyaml["kind"] == "AppWrapper"
            self.name = awyaml["metadata"]["name"]
            self.namespace = awyaml["metadata"]["namespace"]
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
            with oc.project(self.namespace):
                oc.invoke("create", ["-f", self.filename])
        except oc.OpenShiftPythonException as osp:  # pragma: no cover
            error_msg = osp.result.err()
            if "Unauthorized" in error_msg or "Forbidden" in error_msg:
                raise PermissionError(
                    "Action not permitted, have you put in correct/up-to-date auth credentials?"
                )
            elif "AlreadyExists" in error_msg:
                raise FileExistsError(
                    f"An AppWrapper of the name {self.name} already exists in namespace {self.namespace}"
                )
            raise osp

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
            with oc.project(self.namespace):
                oc.invoke("delete", ["AppWrapper", self.name])
        except oc.OpenShiftPythonException as osp:  # pragma: no cover
            error_msg = osp.result.err()
            if (
                'the server doesn\'t have a resource type "AppWrapper"' in error_msg
                or "forbidden" in error_msg
                or "Unauthorized" in error_msg
                or "Missing or incomplete configuration" in error_msg
            ):
                raise PermissionError(
                    "Action not permitted, have you put in correct/up-to-date auth credentials?"
                )
            elif "not found" in error_msg:
                self.submitted = False
                print("AppWrapper not found, was deleted in another manner")
                return
            else:
                raise osp

        self.submitted = False
        print(f"AppWrapper {self.name} removed!")

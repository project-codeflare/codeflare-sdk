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
This sub-module exists primarily to be used internally for any Kubernetes
API error handling or wrapping.
"""

import executing
from kubernetes import client, config
from urllib3.util import parse_url


# private methods
def _kube_api_error_handling(
    e: Exception, print_error: bool = True
):  # pragma: no cover
    perm_msg = (
        "Action not permitted, have you put in correct/up-to-date auth credentials?"
    )
    nf_msg = "No instances found, nothing to be done."
    exists_msg = "Resource with this name already exists."
    if type(e) == config.ConfigException:
        raise PermissionError(perm_msg)
    if type(e) == executing.executing.NotOneValueFound:
        if print_error:
            print(nf_msg)
        return
    if type(e) == client.ApiException:
        if e.reason == "Not Found":
            if print_error:
                print(nf_msg)
            return
        elif e.reason == "Unauthorized" or e.reason == "Forbidden":
            if print_error:
                print(perm_msg)
            return
        elif e.reason == "Conflict":
            raise FileExistsError(exists_msg)
    raise e

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

ERROR_MESSAGES = {
    "Not Found": "The requested resource could not be located.\n"
    "Please verify the resource name and namespace.",
    "Unauthorized": "Access to the API is unauthorized.\n"
    "Check your credentials or permissions.",
    "Forbidden": "Access denied to the Kubernetes resource.\n"
    "Ensure your role has sufficient permissions for this operation.",
    "Conflict": "A conflict occurred with the RayCluster resource.\n"
    "Only one RayCluster with the same name is allowed. "
    "Please delete or rename the existing RayCluster before creating a new one with the desired name.",
}


# private methods
def _kube_api_error_handling(
    e: Exception, print_error: bool = True
):  # pragma: no cover
    def print_message(message: str):
        if print_error:
            print(message)

    if isinstance(e, client.ApiException):
        # Retrieve message based on reason, defaulting if reason is not known
        message = ERROR_MESSAGES.get(
            e.reason, f"Unexpected API error encountered (Reason: {e.reason})"
        )
        full_message = f"{message}\nResponse: {e.body}"
        print_message(full_message)

    elif isinstance(e, config.ConfigException):
        message = "Configuration error: Unable to load Kubernetes configuration. Verify the config file path and format."
        print_message(message)

    elif isinstance(e, executing.executing.NotOneValueFound):
        message = "Execution error: Expected exactly one value in the operation but found none or multiple."
        print_message(message)

    else:
        message = f"Unexpected error:\n{str(e)}"
        print_message(message)
        raise e

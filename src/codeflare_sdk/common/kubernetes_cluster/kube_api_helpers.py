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

import json
import executing
from kubernetes import client, config


ERROR_MESSAGES = {
    401: "Access to the API is unauthorized.\n"
    "Check your credentials or permissions.",
    403: "Access denied:\n"
    "Ensure your role has sufficient permissions and that you are logged in to the correct cluster.",
    404: "The requested resource could not be located.\n"
    "Please verify the resource name and namespace.",
    409: "A conflict occurred with the RayCluster resource.\n"
    "Only one RayCluster with the same name is allowed. "
    "Please delete or rename the existing RayCluster before creating a new one with the desired name.",
    422: "The request was rejected because something in your cluster configuration is invalid. Fix the value and try again.",
}

ERROR_MESSAGES_FALLBACK = (
    "An error occurred while communicating with the cluster.\n"
    "Check the details below; if the problem persists, contact your administrator."
)


def _format_api_error_body(body) -> str:
    """
    Extract a short, readable detail from a Kubernetes Status API response body.
    Returns a single line like "Details: <message>" instead of raw JSON.
    For cluster name validation errors, returns a brief, data-scientist-friendly line.
    """
    if not body:
        return ""
    try:
        raw = body.decode() if isinstance(body, bytes) else body
        data = json.loads(raw)
        msg = data.get("message")
        if not msg:
            return ""

        # Short, friendly line for cluster name (metadata.name) validation errors
        if (
            "metadata.name" in msg
            and "Invalid value" in msg
            and ("lowercase" in msg or "RFC 1123" in msg or "subdomain" in msg)
        ):
            return (
                "Details: Cluster name is invalid. Use only lowercase letters, "
                "numbers, and hyphens; it must start and end with a letter or number.\n"
                "(e.g. 'mycluster' or 'my-cluster')."
            )

        return f"Details: {msg}"
    except (json.JSONDecodeError, AttributeError, TypeError):
        return f"Response: {body}"


# private methods
def _kube_api_error_handling(
    e: Exception, print_error: bool = True
):  # pragma: no cover
    def print_message(message: str):
        if print_error:
            print(message)

    if isinstance(e, client.ApiException):
        detail = _format_api_error_body(e.body)
        status_code = getattr(e, "status", None)

        if status_code == 422 and detail and "Cluster name is invalid" in detail:
            print_message(detail)
        else:
            message = ERROR_MESSAGES.get(status_code, ERROR_MESSAGES_FALLBACK)
            if detail:
                full_message = f"{message}\n{detail}"
            else:
                # Ensure we always show something (reason and status) when no body detail
                status_info = f"Reason: {e.reason}"
                if status_code is not None:
                    status_info += f" (HTTP {status_code})"
                full_message = f"{message}\n{status_info}."
            print_message(full_message)

    elif isinstance(e, config.ConfigException):
        message = "Configuration error: Unable to load Kubernetes configuration. Verify the config file path and format."
        print_message(message)

    elif isinstance(e, executing.executing.NotOneValueFound):
        message = "Execution error: Expected exactly one value in the operation but found none or multiple."
        print_message(message)

    else:
        message = "An unexpected error occurred.\n" f"{str(e)}"
        print_message(message)
        raise e

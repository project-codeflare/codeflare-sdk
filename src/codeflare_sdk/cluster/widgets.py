# Copyright 2024 IBM, Red Hat
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
The widgets sub-module contains the ui widgets created using the ipywidgets package.
"""
import os
from time import sleep
import codeflare_sdk
from kubernetes import client
import ipywidgets as widgets
from IPython.display import display, HTML, Javascript
import pandas as pd
from .config import ClusterConfiguration
from .model import RayClusterStatus
from ..utils.kube_api_helpers import _kube_api_error_handling
from .auth import config_check, api_config_handler


def cluster_up_down_buttons(cluster: "codeflare_sdk.cluster.Cluster") -> widgets.Button:
    """
    The cluster_up_down_buttons function returns two button widgets for a create and delete button.
    The function uses the appwrapper bool to distinguish between resource type for the tool tip.
    """
    resource = "Ray Cluster"
    if cluster.config.appwrapper:
        resource = "AppWrapper"

    up_button = widgets.Button(
        description="Cluster Up",
        tooltip=f"Create the {resource}",
        icon="play",
    )

    delete_button = widgets.Button(
        description="Cluster Down",
        tooltip=f"Delete the {resource}",
        icon="trash",
    )

    wait_ready_check = wait_ready_check_box()
    output = widgets.Output()

    # Display the buttons in an HBox wrapped in a VBox which includes the wait_ready Checkbox
    button_display = widgets.HBox([up_button, delete_button])
    display(widgets.VBox([button_display, wait_ready_check]), output)

    def on_up_button_clicked(b):  # Handle the up button click event
        with output:
            output.clear_output()
            cluster.up()

            # If the wait_ready Checkbox is clicked(value == True) trigger the wait_ready function
            if wait_ready_check.value:
                cluster.wait_ready()

    def on_down_button_clicked(b):  # Handle the down button click event
        with output:
            output.clear_output()
            cluster.down()

    up_button.on_click(on_up_button_clicked)
    delete_button.on_click(on_down_button_clicked)


def wait_ready_check_box():
    """
    The wait_ready_check_box function will return a checkbox widget used for waiting for the resource to be in the state READY.
    """
    wait_ready_check_box = widgets.Checkbox(
        False,
        description="Wait for Cluster?",
    )
    return wait_ready_check_box


def is_notebook() -> bool:
    """
    The is_notebook function checks if Jupyter Notebook environment variables exist in the given environment and return True/False based on that.
    """
    if (
        "PYDEVD_IPYTHON_COMPATIBLE_DEBUGGING" in os.environ
        or "JPY_SESSION_NAME" in os.environ
    ):  # If running Jupyter NBs in VsCode or RHOAI/ODH display UI buttons
        return True
    else:
        return False


def view_clusters(namespace: str = None):
    """view_clusters function will display existing clusters with their specs, and handle user interactions."""
    from .cluster import get_current_namespace
    if not namespace:
        namespace = get_current_namespace()

    user_output = widgets.Output()
    raycluster_data_output = widgets.Output()
    url_output = widgets.Output()

    df = _fetch_cluster_data(namespace)
    if df.empty:
        print(f"No clusters found in the {namespace} namespace.")
    else:
        classification_widget = widgets.ToggleButtons(
            options=df["Name"].tolist(), value=None,
            description='Select an existing cluster:',
        )

        classification_widget.observe(lambda selection_change: _on_cluster_click(selection_change, raycluster_data_output, namespace, classification_widget), names="value")

        delete_button = widgets.Button(
                    description='Delete Cluster',
                    icon='trash',
                    tooltip="Delete the selected cluster"
                )
        delete_button.on_click(lambda b: _on_delete_button_click(b, classification_widget, df, raycluster_data_output, user_output, delete_button, list_jobs_button, ray_dashboard_button))

        list_jobs_button = widgets.Button(
                    description='View Jobs',
                    icon='suitcase',
                    tooltip="Open the Ray Job Dashboard"
                )
        list_jobs_button.on_click(lambda b: _on_list_jobs_button_click(b, classification_widget, df, user_output, url_output))

        ray_dashboard_button = widgets.Button(
                    description='Open Ray Dashboard',
                    icon='dashboard',
                    tooltip="Open the Ray Dashboard in a new tab",
                    layout=widgets.Layout(width='auto'),
                )
        ray_dashboard_button.on_click(lambda b: _on_ray_dashboard_button_click(b, classification_widget, df, user_output, url_output))

        display(widgets.VBox([classification_widget, raycluster_data_output]))
        display(widgets.HBox([delete_button, list_jobs_button, ray_dashboard_button]), url_output, user_output)

# Handles the event when a cluster is selected from the toggle buttons, updating the output with cluster details.
def _on_cluster_click(selection_change, raycluster_data_output: widgets.Output, namespace: str, classification_widget: widgets.ToggleButtons):
    new_value = selection_change["new"]
    raycluster_data_output.clear_output()
    df = _fetch_cluster_data(namespace)
    classification_widget.options = df["Name"].tolist()
    with raycluster_data_output:
        display(HTML(df[df["Name"]==new_value][["Name", "Namespace", "Head GPUs", "Head CPU Req~Lim", "Head Memory Req~Lim", "Worker GPUs", "Worker CPU Req~Lim", "Worker Memory Req~Lim", "status"]].to_html(escape=False, index=False, border=2)))


def _on_delete_button_click(b, classification_widget: widgets.ToggleButtons, df: pd.DataFrame, raycluster_data_output: widgets.Output, user_output: widgets.Output, delete_button: widgets.Button, list_jobs_button: widgets.Button, ray_dashboard_button: widgets.Button):
    cluster_name = classification_widget.value
    namespace = df[df["Name"]==classification_widget.value]["Namespace"].values[0]

    _delete_cluster(cluster_name, namespace)

    sleep(2) # TODO: wait for the cluster to be deleted instead
    with user_output:
        user_output.clear_output()
        print(f"Cluster {cluster_name} in the {namespace} namespace was deleted successfully.")

    # Refresh the dataframe
    new_df = _fetch_cluster_data(namespace)
    if new_df.empty:
        classification_widget.close()
        delete_button.close()
        list_jobs_button.close()
        ray_dashboard_button.close()
        with raycluster_data_output:
            raycluster_data_output.clear_output()
            print(f"No clusters found in the {namespace} namespace.")
    else:
        classification_widget.options = new_df["Name"].tolist()

def _on_ray_dashboard_button_click(b, classification_widget: widgets.ToggleButtons, df: pd.DataFrame, user_output: widgets.Output, url_output: widgets.Output):
    from codeflare_sdk.cluster import Cluster
    cluster_name = classification_widget.value
    namespace = df[df["Name"]==classification_widget.value]["Namespace"].values[0]

    cluster = Cluster(ClusterConfiguration(cluster_name, namespace))
    dashboard_url = cluster.cluster_dashboard_uri()

    with user_output:
        user_output.clear_output()
        print(f"Opening Ray Dashboard for {cluster_name} cluster:\n{dashboard_url}")
    with url_output:
        display(Javascript(f'window.open("{dashboard_url}", "_blank");'))

def _on_list_jobs_button_click(b, classification_widget: widgets.ToggleButtons, df: pd.DataFrame, user_output: widgets.Output, url_output: widgets.Output):
    from codeflare_sdk.cluster import Cluster
    cluster_name = classification_widget.value
    namespace = df[df["Name"]==classification_widget.value]["Namespace"].values[0]

    cluster = Cluster(ClusterConfiguration(cluster_name, namespace))
    dashboard_url = cluster.cluster_dashboard_uri()

    with user_output:
        user_output.clear_output()
        print(f"Opening Ray Jobs Dashboard for {cluster_name} cluster:\n{dashboard_url}/#/jobs")
    with url_output:
        display(Javascript(f'window.open("{dashboard_url}/#/jobs", "_blank");'))

def _delete_cluster(
    cluster_name: str,
    namespace: str,
):
    from .cluster import _check_aw_exists
    if _check_aw_exists(cluster_name, namespace):
        try:
            config_check()
            api_instance = client.CustomObjectsApi(api_config_handler())
            api_instance.delete_namespaced_custom_object(
                group="workload.codeflare.dev",
                version="v1beta2",
                namespace=namespace,
                plural="appwrappers",
                name=cluster_name,
            )
        except Exception as e:
            return _kube_api_error_handling(e)
    else:
        try:
            config_check()
            api_instance = client.CustomObjectsApi(api_config_handler())
            api_instance.delete_namespaced_custom_object(
                group="ray.io",
                version="v1",
                namespace=namespace,
                plural="rayclusters",
                name=cluster_name,
            )
        except Exception as e:
            return _kube_api_error_handling(e)


def _fetch_cluster_data(namespace):
    from .cluster import list_all_clusters
    rayclusters = list_all_clusters(namespace, False)
    if not rayclusters:
        return pd.DataFrame()
    names = [item.name for item in rayclusters]
    namespaces = [item.namespace for item in rayclusters]
    head_extended_resources = [
        f"{list(item.head_extended_resources.keys())[0]}: {list(item.head_extended_resources.values())[0]}"
        if item.head_extended_resources else "0"
        for item in rayclusters
    ]
    worker_extended_resources = [
        f"{list(item.worker_extended_resources.keys())[0]}: {list(item.worker_extended_resources.values())[0]}"
        if item.worker_extended_resources else "0"
        for item in rayclusters
    ]
    head_cpu_requests = [item.head_cpu_requests if item.head_cpu_requests else 0 for item in rayclusters]
    head_cpu_limits = [item.head_cpu_limits if item.head_cpu_limits else 0 for item in rayclusters]
    head_cpu_rl = [f"{requests}~{limits}" for requests, limits in zip(head_cpu_requests, head_cpu_limits)]
    head_mem_requests = [item.head_mem_requests if item.head_mem_requests else 0 for item in rayclusters]
    head_mem_limits = [item.head_mem_limits if item.head_mem_limits else 0 for item in rayclusters]
    head_mem_rl = [f"{requests}~{limits}" for requests, limits in zip(head_mem_requests, head_mem_limits)]
    worker_cpu_requests = [item.worker_cpu_requests if item.worker_cpu_requests else 0 for item in rayclusters]
    worker_cpu_limits = [item.worker_cpu_limits if item.worker_cpu_limits else 0 for item in rayclusters]
    worker_cpu_rl = [f"{requests}~{limits}" for requests, limits in zip(worker_cpu_requests, worker_cpu_limits)]
    worker_mem_requests = [item.worker_mem_requests if item.worker_mem_requests else 0 for item in rayclusters]
    worker_mem_limits = [item.worker_mem_limits if item.worker_mem_limits else 0 for item in rayclusters]
    worker_mem_rl = [f"{requests}~{limits}" for requests, limits in zip(worker_mem_requests, worker_mem_limits)]
    status = [item.status.name for item in rayclusters]

    status = [_format_status(item.status) for item in rayclusters]

    data = {
        "Name": names,
        "Namespace": namespaces,
        "Head GPUs": head_extended_resources,
        "Worker GPUs": worker_extended_resources,
        "Head CPU Req~Lim": head_cpu_rl,
        "Head Memory Req~Lim": head_mem_rl,
        "Worker CPU Req~Lim": worker_cpu_rl,
        "Worker Memory Req~Lim": worker_mem_rl,
        "status": status
    }
    return pd.DataFrame(data)

# format_status takes a RayCluster status and applies colors and icons based on the status.
def _format_status(status):
    if status == RayClusterStatus.READY:
        return '<span style="color: green;">Ready ✓</span>'
    elif status == RayClusterStatus.SUSPENDED:
        return '<span style="color: #007BFF;">Suspended ❄️</span>'
    elif status == RayClusterStatus.FAILED:
        return '<span style="color: red;">Failed ✗</span>'
    elif status == RayClusterStatus.UNHEALTHY:
        return '<span style="color: purple;">Unhealthy</span>'
    elif status == RayClusterStatus.UNKNOWN:
        return '<span style="color: purple;">Unknown</span>'
    else:
        return status

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
import contextlib
import io
import os
import warnings
import time
import codeflare_sdk
from kubernetes import client
from kubernetes.client.rest import ApiException
import ipywidgets as widgets
from IPython.display import display, HTML, Javascript
import pandas as pd
from ...ray.cluster.config import ClusterConfiguration
from ...ray.cluster.status import RayClusterStatus
from ..kubernetes_cluster import _kube_api_error_handling
from ..kubernetes_cluster.auth import (
    config_check,
    get_api_client,
)


class RayClusterManagerWidgets:
    """
    The RayClusterManagerWidgets class is responsible for initialising the ToggleButtons, Button, and Output widgets.
    It also handles the user interactions and displays the cluster details.
    Used when calling the view_clusters function.
    """

    def __init__(self, ray_clusters_df: pd.DataFrame, namespace: str = None):
        from ...ray.cluster.cluster import get_current_namespace

        # Data
        self.ray_clusters_df = ray_clusters_df
        self.namespace = get_current_namespace() if not namespace else namespace
        self.raycluster_data_output = widgets.Output()
        self.user_output = widgets.Output()
        self.url_output = widgets.Output()

        # Widgets
        self.classification_widget = widgets.ToggleButtons(
            options=ray_clusters_df["Name"].tolist(),
            value=ray_clusters_df["Name"].tolist()[0],
            description="Select an existing cluster:",
        )
        self.delete_button = widgets.Button(
            description="Delete Cluster",
            icon="trash",
            tooltip="Delete the selected cluster",
        )
        self.list_jobs_button = widgets.Button(
            description="View Jobs",
            icon="suitcase",
            tooltip="Open the Ray Job Dashboard",
        )
        self.ray_dashboard_button = widgets.Button(
            description="Open Ray Dashboard",
            icon="dashboard",
            tooltip="Open the Ray Dashboard in a new tab",
            layout=widgets.Layout(width="auto"),
        )
        self.refresh_data_button = widgets.Button(
            description="Refresh Data",
            icon="refresh",
            tooltip="Refresh the list of Ray Clusters",
            layout=widgets.Layout(width="auto", left="1em"),
        )

        # Set up interactions
        self._initialize_callbacks()
        self._trigger_initial_display()

    def _initialize_callbacks(self):
        """
        Called upon RayClusterManagerWidgets initialisation.
        Sets up event handlers and callbacks for UI interactions.
        """
        # Observe cluster selection
        self.classification_widget.observe(
            lambda selection_change: self._on_cluster_click(selection_change),
            names="value",
        )
        # Set up button clicks
        self.delete_button.on_click(lambda b: self._on_delete_button_click(b))
        self.list_jobs_button.on_click(lambda b: self._on_list_jobs_button_click(b))
        self.ray_dashboard_button.on_click(
            lambda b: self._on_ray_dashboard_button_click(b)
        )
        self.refresh_data_button.on_click(
            lambda b: self._on_refresh_data_button_click(b)
        )

    def _trigger_initial_display(self):
        """
        Called upon RayClusterManagerWidgets initialisation.
        Triggers an initial display update with the current cluster value.
        """
        # Trigger display with initial cluster value
        initial_value = self.classification_widget.value
        self._on_cluster_click({"new": initial_value})

    def _on_cluster_click(self, selection_change):
        """
        _on_cluster_click handles the event when a cluster is selected from the toggle buttons, updating the output with cluster details.
        """
        new_value = selection_change["new"]
        self.classification_widget.value = new_value
        self._refresh_dataframe()

    def _on_delete_button_click(self, b):
        """
        _on_delete_button_click handles the event when the Delete Button is clicked, deleting the selected cluster.
        """
        cluster_name = self.classification_widget.value

        _delete_cluster(cluster_name, self.namespace)

        with self.user_output:
            self.user_output.clear_output()
            print(
                f"Cluster {cluster_name} in the {self.namespace} namespace was deleted successfully."
            )

        # Refresh the dataframe
        self._refresh_dataframe()

    def _on_list_jobs_button_click(self, b):
        """
        _on_list_jobs_button_click handles the event when the View Jobs button is clicked, opening the Ray Jobs Dashboard in a new tab
        """
        from codeflare_sdk import Cluster

        cluster_name = self.classification_widget.value

        # Suppress from Cluster Object initialisation widgets and outputs
        with widgets.Output(), contextlib.redirect_stdout(
            io.StringIO()
        ), contextlib.redirect_stderr(io.StringIO()):
            cluster = Cluster(ClusterConfiguration(cluster_name, self.namespace))
        dashboard_url = cluster.cluster_dashboard_uri()

        with self.user_output:
            self.user_output.clear_output()
            print(
                f"Opening Ray Jobs Dashboard for {cluster_name} cluster:\n{dashboard_url}/#/jobs"
            )
        with self.url_output:
            display(Javascript(f'window.open("{dashboard_url}/#/jobs", "_blank");'))

    def _on_ray_dashboard_button_click(self, b):
        """
        _on_ray_dashboard_button_click handles the event when the Open Ray Dashboard button is clicked, opening the Ray Dashboard in a new tab
        """
        from codeflare_sdk import Cluster

        cluster_name = self.classification_widget.value

        # Suppress from Cluster Object initialisation widgets and outputs
        with widgets.Output(), contextlib.redirect_stdout(
            io.StringIO()
        ), contextlib.redirect_stderr(io.StringIO()):
            cluster = Cluster(ClusterConfiguration(cluster_name, self.namespace))
        dashboard_url = cluster.cluster_dashboard_uri()

        with self.user_output:
            self.user_output.clear_output()
            print(f"Opening Ray Dashboard for {cluster_name} cluster:\n{dashboard_url}")
        with self.url_output:
            display(Javascript(f'window.open("{dashboard_url}", "_blank");'))

    def _on_refresh_data_button_click(self, b):
        """
        _on_refresh_button_click handles the event when the Refresh Data button is clicked, refreshing the list of Ray Clusters.
        """
        self.refresh_data_button.disabled = True
        self._refresh_dataframe()
        self.refresh_data_button.disabled = False

    def _refresh_dataframe(self):
        """
        _refresh_data function refreshes the list of Ray Clusters.
        """
        self.ray_clusters_df = _fetch_cluster_data(self.namespace)
        if self.ray_clusters_df.empty:
            self.classification_widget.close()
            self.delete_button.close()
            self.list_jobs_button.close()
            self.ray_dashboard_button.close()
            self.refresh_data_button.close()
            with self.raycluster_data_output:
                self.raycluster_data_output.clear_output()
                print(f"No clusters found in the {self.namespace} namespace.")
        else:
            # Store the current selection if it still exists (Was not previously deleted).
            selected_cluster = (
                self.classification_widget.value
                if self.classification_widget.value
                in self.ray_clusters_df["Name"].tolist()
                else None
            )

            # Update list of Ray Clusters.
            self.classification_widget.options = self.ray_clusters_df["Name"].tolist()

            # If the selected cluster exists, preserve the selection to remain viewing the currently selected cluster.
            # If it does not exist, default to the first available cluster.
            if selected_cluster:
                self.classification_widget.value = selected_cluster
            else:
                self.classification_widget.value = self.ray_clusters_df["Name"].iloc[0]

            # Update the output with the current Ray Cluster details.
            self._display_cluster_details()

    def _display_cluster_details(self):
        """
        _display_cluster_details function displays the selected cluster details in the output widget.
        """
        self.raycluster_data_output.clear_output()
        selected_cluster = self.ray_clusters_df[
            self.ray_clusters_df["Name"] == self.classification_widget.value
        ]
        with self.raycluster_data_output:
            display(
                HTML(
                    selected_cluster[
                        [
                            "Name",
                            "Namespace",
                            "Num Workers",
                            "Head GPUs",
                            "Head CPU Req~Lim",
                            "Head Memory Req~Lim",
                            "Worker GPUs",
                            "Worker CPU Req~Lim",
                            "Worker Memory Req~Lim",
                            "status",
                        ]
                    ].to_html(escape=False, index=False, border=2)
                )
            )

    def display_widgets(self):
        display(widgets.VBox([self.classification_widget, self.raycluster_data_output]))
        display(
            widgets.HBox(
                [
                    self.delete_button,
                    self.list_jobs_button,
                    self.ray_dashboard_button,
                    self.refresh_data_button,
                ]
            ),
            self.url_output,
            self.user_output,
        )


def cluster_up_down_buttons(
    cluster: "codeflare_sdk.ray.cluster.cluster.Cluster",
) -> widgets.Button:
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

    wait_ready_check = _wait_ready_check_box()
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


def _wait_ready_check_box():
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
    """
    view_clusters function will display existing clusters with their specs, and handle user interactions.
    """
    if not is_notebook():
        warnings.warn(
            "view_clusters can only be used in a Jupyter Notebook environment."
        )
        return  # Exit function if not in Jupyter Notebook

    from ...ray.cluster.cluster import get_current_namespace

    if not namespace:
        namespace = get_current_namespace()

    ray_clusters_df = _fetch_cluster_data(namespace)
    if ray_clusters_df.empty:
        print(f"No clusters found in the {namespace} namespace.")
        return

    # Initialize the RayClusterManagerWidgets class
    ray_cluster_manager = RayClusterManagerWidgets(
        ray_clusters_df=ray_clusters_df, namespace=namespace
    )

    # Display the UI components
    ray_cluster_manager.display_widgets()


def _delete_cluster(
    cluster_name: str,
    namespace: str,
    timeout: int = 5,
    interval: int = 1,
):
    """
    _delete_cluster function deletes the cluster with the given name and namespace.
    It optionally waits for the cluster to be deleted.
    """
    from ...ray.cluster.cluster import _check_aw_exists

    try:
        config_check()
        api_instance = client.CustomObjectsApi(get_api_client())

        if _check_aw_exists(cluster_name, namespace):
            api_instance.delete_namespaced_custom_object(
                group="workload.codeflare.dev",
                version="v1beta2",
                namespace=namespace,
                plural="appwrappers",
                name=cluster_name,
            )
            group = "workload.codeflare.dev"
            version = "v1beta2"
            plural = "appwrappers"
        else:
            api_instance.delete_namespaced_custom_object(
                group="ray.io",
                version="v1",
                namespace=namespace,
                plural="rayclusters",
                name=cluster_name,
            )
            group = "ray.io"
            version = "v1"
            plural = "rayclusters"

        # Wait for the resource to be deleted
        while timeout > 0:
            try:
                api_instance.get_namespaced_custom_object(
                    group=group,
                    version=version,
                    namespace=namespace,
                    plural=plural,
                    name=cluster_name,
                )
                # Retry if resource still exists
                time.sleep(interval)
                timeout -= interval
                if timeout <= 0:
                    raise TimeoutError(
                        f"Timeout waiting for {cluster_name} to be deleted."
                    )
            except ApiException as e:
                # Resource is deleted
                if e.status == 404:
                    break
    except Exception as e:  # pragma: no cover
        return _kube_api_error_handling(e)


def _fetch_cluster_data(namespace):
    """
    _fetch_cluster_data function fetches all clusters and their spec in a given namespace and returns a DataFrame.
    """
    from ...ray.cluster.cluster import list_all_clusters

    rayclusters = list_all_clusters(namespace, False)
    if not rayclusters:
        return pd.DataFrame()
    names = [item.name for item in rayclusters]
    namespaces = [item.namespace for item in rayclusters]
    num_workers = [item.num_workers for item in rayclusters]
    head_extended_resources = [
        (
            f"{list(item.head_extended_resources.keys())[0]}: {list(item.head_extended_resources.values())[0]}"
            if item.head_extended_resources
            else "0"
        )
        for item in rayclusters
    ]
    worker_extended_resources = [
        (
            f"{list(item.worker_extended_resources.keys())[0]}: {list(item.worker_extended_resources.values())[0]}"
            if item.worker_extended_resources
            else "0"
        )
        for item in rayclusters
    ]
    head_cpu_requests = [
        item.head_cpu_requests if item.head_cpu_requests else 0 for item in rayclusters
    ]
    head_cpu_limits = [
        item.head_cpu_limits if item.head_cpu_limits else 0 for item in rayclusters
    ]
    head_cpu_rl = [
        f"{requests}~{limits}"
        for requests, limits in zip(head_cpu_requests, head_cpu_limits)
    ]
    head_mem_requests = [
        item.head_mem_requests if item.head_mem_requests else 0 for item in rayclusters
    ]
    head_mem_limits = [
        item.head_mem_limits if item.head_mem_limits else 0 for item in rayclusters
    ]
    head_mem_rl = [
        f"{requests}~{limits}"
        for requests, limits in zip(head_mem_requests, head_mem_limits)
    ]
    worker_cpu_requests = [
        item.worker_cpu_requests if item.worker_cpu_requests else 0
        for item in rayclusters
    ]
    worker_cpu_limits = [
        item.worker_cpu_limits if item.worker_cpu_limits else 0 for item in rayclusters
    ]
    worker_cpu_rl = [
        f"{requests}~{limits}"
        for requests, limits in zip(worker_cpu_requests, worker_cpu_limits)
    ]
    worker_mem_requests = [
        item.worker_mem_requests if item.worker_mem_requests else 0
        for item in rayclusters
    ]
    worker_mem_limits = [
        item.worker_mem_limits if item.worker_mem_limits else 0 for item in rayclusters
    ]
    worker_mem_rl = [
        f"{requests}~{limits}"
        for requests, limits in zip(worker_mem_requests, worker_mem_limits)
    ]
    status = [item.status.name for item in rayclusters]

    status = [_format_status(item.status) for item in rayclusters]

    data = {
        "Name": names,
        "Namespace": namespaces,
        "Num Workers": num_workers,
        "Head GPUs": head_extended_resources,
        "Worker GPUs": worker_extended_resources,
        "Head CPU Req~Lim": head_cpu_rl,
        "Head Memory Req~Lim": head_mem_rl,
        "Worker CPU Req~Lim": worker_cpu_rl,
        "Worker Memory Req~Lim": worker_mem_rl,
        "status": status,
    }
    return pd.DataFrame(data)


def _format_status(status):
    """
    _format_status function formats the status enum.
    """
    status_map = {
        RayClusterStatus.READY: '<span style="color: green;">Ready ✓</span>',
        RayClusterStatus.SUSPENDED: '<span style="color: #007BFF;">Suspended ❄️</span>',
        RayClusterStatus.FAILED: '<span style="color: red;">Failed ✗</span>',
        RayClusterStatus.UNHEALTHY: '<span style="color: purple;">Unhealthy</span>',
        RayClusterStatus.UNKNOWN: '<span style="color: purple;">Unknown</span>',
    }
    return status_map.get(status, status)

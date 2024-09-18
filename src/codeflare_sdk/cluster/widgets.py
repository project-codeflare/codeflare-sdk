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
import ipywidgets as widgets
from IPython.display import display
import os
import codeflare_sdk


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

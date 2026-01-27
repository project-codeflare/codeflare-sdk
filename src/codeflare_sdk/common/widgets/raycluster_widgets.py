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
Widgets for RayCluster objects.

This module provides Jupyter notebook widgets specifically for the new RayCluster API.
It provides clean separation from the legacy Cluster API widgets.
"""
import contextlib
import io
import sys
from typing import TYPE_CHECKING

import ipywidgets as widgets
from IPython.display import display

if TYPE_CHECKING:
    from ...ray.rayclusters.raycluster import RayCluster


def raycluster_apply_down_buttons(
    cluster: "RayCluster",
) -> widgets.Button:
    """
    Create button widgets for applying and deleting a RayCluster.

    This function creates two button widgets (Apply and Down) along with a
    checkbox for waiting until the cluster is ready. All output from cluster
    operations is captured in the widget output area to prevent duplicate
    logging in the notebook.

    Args:
        cluster: The RayCluster object to create widgets for.

    Returns:
        widgets.Button: The apply button (for consistency with old API).
    """
    apply_button = widgets.Button(
        description="Cluster Apply",
        tooltip="Create the Ray Cluster",
        icon="play",
    )

    delete_button = widgets.Button(
        description="Cluster Down",
        tooltip="Delete the Ray Cluster",
        icon="trash",
    )

    wait_ready_check = _wait_ready_check_box()
    output = widgets.Output()

    # Create informational message about widget usage
    info_message = widgets.HTML(
        value='<div style="font-size: 0.85em; color: #666; text-align: left;">'
        "For standalone clusters only (not RayJob-managed)."
        "</div>",
    )

    # Layout with left alignment
    button_display = widgets.HBox([apply_button, delete_button])
    container = widgets.VBox(
        [info_message, button_display, wait_ready_check],
        layout=widgets.Layout(align_items="flex-start"),
    )
    display(container, output)

    def on_apply_button_clicked(b):  # Handle the apply button click event
        # Capture output in StringIO to prevent duplicate logging in notebook stdout
        # Then display it only in the widget output
        stdout_capture = io.StringIO()
        stderr_capture = io.StringIO()

        with output:
            output.clear_output()
            # Redirect stdout and stderr to capture output without displaying in notebook
            with contextlib.redirect_stdout(stdout_capture), contextlib.redirect_stderr(
                stderr_capture
            ):
                cluster.apply()

            # Display captured output in the widget
            stdout_text = stdout_capture.getvalue()
            stderr_text = stderr_capture.getvalue()
            if stdout_text:
                print(stdout_text, end="")
            if stderr_text:
                print(stderr_text, file=sys.stderr, end="")

            # If the wait_ready Checkbox is clicked(value == True) trigger the wait_ready function
            if wait_ready_check.value:
                stdout_capture = io.StringIO()
                stderr_capture = io.StringIO()
                with contextlib.redirect_stdout(
                    stdout_capture
                ), contextlib.redirect_stderr(stderr_capture):
                    cluster.wait_ready()
                stdout_text = stdout_capture.getvalue()
                stderr_text = stderr_capture.getvalue()
                if stdout_text:
                    print(stdout_text, end="")
                if stderr_text:
                    print(stderr_text, file=sys.stderr, end="")

    def on_down_button_clicked(b):  # Handle the down button click event
        # Capture output to prevent duplicate logging
        stdout_capture = io.StringIO()
        stderr_capture = io.StringIO()

        with output:
            output.clear_output()
            with contextlib.redirect_stdout(stdout_capture), contextlib.redirect_stderr(
                stderr_capture
            ):
                cluster.down()

            # Display captured output in the widget
            stdout_text = stdout_capture.getvalue()
            stderr_text = stderr_capture.getvalue()
            if stdout_text:
                print(stdout_text, end="")
            if stderr_text:
                print(stderr_text, file=sys.stderr, end="")

    apply_button.on_click(on_apply_button_clicked)
    delete_button.on_click(on_down_button_clicked)

    return apply_button


def _wait_ready_check_box():
    """
    Create a checkbox widget for waiting until the cluster is ready.

    Returns:
        widgets.Checkbox: A checkbox with description "Wait for Cluster?"
    """
    wait_ready_check_box = widgets.Checkbox(
        False,
        description="Wait for Cluster?",
    )
    return wait_ready_check_box

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
Tests for RayCluster widgets.

This module tests the widget functionality specifically for the new RayCluster API.
"""
import codeflare_sdk.common.widgets.raycluster_widgets as raycluster_widgets
from unittest.mock import MagicMock, patch
from codeflare_sdk.ray.rayclusters.raycluster import RayCluster
import pytest


@patch.dict(
    "os.environ", {"JPY_SESSION_NAME": "example-test"}
)  # Mock Jupyter environment variable
def test_raycluster_apply_down_buttons(mocker):
    """
    Test that raycluster_apply_down_buttons creates widgets and handles button clicks correctly.
    """
    # Create a mock RayCluster object
    cluster = RayCluster(
        name="test-cluster",
        namespace="default",
        num_workers=1,
        head_cpu_requests=1,
        head_cpu_limits=2,
        head_memory_requests=4,
        head_memory_limits=8,
        worker_cpu_requests=1,
        worker_cpu_limits=2,
        worker_memory_requests=4,
        worker_memory_limits=8,
    )

    # Mock the widget components
    with patch("ipywidgets.Button") as MockButton, patch(
        "ipywidgets.Checkbox"
    ) as MockCheckbox, patch("ipywidgets.Output"), patch("ipywidgets.HBox"), patch(
        "ipywidgets.VBox"
    ), patch(
        "IPython.display.display"
    ), patch.object(
        cluster, "apply"
    ) as mock_apply, patch.object(
        cluster, "down"
    ) as mock_down, patch.object(
        cluster, "wait_ready"
    ) as mock_wait_ready:
        # Create mock button & CheckBox instances
        mock_apply_button = MagicMock()
        mock_down_button = MagicMock()
        mock_wait_ready_check_box = MagicMock()

        # Ensure the mock Button class returns the mock button instances in sequence
        MockCheckbox.side_effect = [mock_wait_ready_check_box]
        MockButton.side_effect = [mock_apply_button, mock_down_button]

        # Call the method under test
        result = raycluster_widgets.raycluster_apply_down_buttons(cluster)

        # Verify the function returns the apply button
        assert result == mock_apply_button

        # Simulate checkbox being checked
        mock_wait_ready_check_box.value = True

        # Simulate clicking "Cluster Apply" button
        mock_apply_button.on_click.call_args[0][0](None)

        # Verify apply() was called
        mock_apply.assert_called_once()

        # Verify wait_ready() was called since checkbox is checked
        mock_wait_ready.assert_called_once()

        # Simulate clicking "Cluster Down" button
        mock_down_button.on_click.call_args[0][0](None)

        # Verify down() was called
        mock_down.assert_called_once()


@patch.dict(
    "os.environ", {"JPY_SESSION_NAME": "example-test"}
)  # Mock Jupyter environment variable
def test_raycluster_apply_down_buttons_without_wait_ready(mocker):
    """
    Test that wait_ready is not called when checkbox is unchecked.
    """
    # Create a mock RayCluster object
    cluster = RayCluster(
        name="test-cluster",
        namespace="default",
        num_workers=1,
    )

    # Mock the widget components
    with patch("ipywidgets.Button") as MockButton, patch(
        "ipywidgets.Checkbox"
    ) as MockCheckbox, patch("ipywidgets.Output"), patch("ipywidgets.HBox"), patch(
        "ipywidgets.VBox"
    ), patch(
        "IPython.display.display"
    ), patch.object(
        cluster, "apply"
    ) as mock_apply, patch.object(
        cluster, "wait_ready"
    ) as mock_wait_ready:
        # Create mock button & CheckBox instances
        mock_apply_button = MagicMock()
        mock_down_button = MagicMock()
        mock_wait_ready_check_box = MagicMock()

        # Checkbox is unchecked (default value)
        mock_wait_ready_check_box.value = False

        MockCheckbox.side_effect = [mock_wait_ready_check_box]
        MockButton.side_effect = [mock_apply_button, mock_down_button]

        # Call the method under test
        raycluster_widgets.raycluster_apply_down_buttons(cluster)

        # Simulate clicking "Cluster Apply" button
        mock_apply_button.on_click.call_args[0][0](None)

        # Verify apply() was called
        mock_apply.assert_called_once()

        # Verify wait_ready() was NOT called since checkbox is unchecked
        mock_wait_ready.assert_not_called()


def test_wait_ready_check_box():
    """
    Test that _wait_ready_check_box creates a checkbox widget with correct properties.
    """
    checkbox = raycluster_widgets._wait_ready_check_box()

    # Verify it's a Checkbox widget
    assert hasattr(checkbox, "value")
    assert hasattr(checkbox, "description")

    # Verify default value is False
    assert checkbox.value is False

    # Verify description
    assert checkbox.description == "Wait for Cluster?"


@patch.dict(
    "os.environ", {"JPY_SESSION_NAME": "example-test"}
)  # Mock Jupyter environment variable
def test_raycluster_apply_down_buttons_output_capture(mocker):
    """
    Test that output is properly captured and redirected to prevent duplicate logging.
    """
    import io
    import contextlib

    # Create a mock RayCluster object
    cluster = RayCluster(
        name="test-cluster",
        namespace="default",
        num_workers=1,
    )

    # Mock the widget components
    with patch("ipywidgets.Button") as MockButton, patch(
        "ipywidgets.Checkbox"
    ) as MockCheckbox, patch("ipywidgets.Output") as MockOutput, patch(
        "ipywidgets.HBox"
    ), patch(
        "ipywidgets.VBox"
    ), patch(
        "IPython.display.display"
    ), patch.object(
        cluster, "apply"
    ) as mock_apply:
        # Create mock instances
        mock_apply_button = MagicMock()
        mock_down_button = MagicMock()
        mock_wait_ready_check_box = MagicMock()
        mock_output = MagicMock()

        mock_wait_ready_check_box.value = False
        MockCheckbox.side_effect = [mock_wait_ready_check_box]
        MockButton.side_effect = [mock_apply_button, mock_down_button]
        MockOutput.return_value = mock_output

        # Call the method under test
        raycluster_widgets.raycluster_apply_down_buttons(cluster)

        # Simulate clicking "Cluster Apply" button
        mock_apply_button.on_click.call_args[0][0](None)

        # Verify output.clear_output() was called
        mock_output.clear_output.assert_called()

        # Verify apply() was called
        mock_apply.assert_called_once()

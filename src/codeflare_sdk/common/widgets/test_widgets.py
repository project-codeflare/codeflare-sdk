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

import codeflare_sdk.common.widgets.widgets as cf_widgets
import pandas as pd
from unittest.mock import MagicMock, patch
from ..utils.unit_test_support import get_local_queue, createClusterConfig
from codeflare_sdk.ray.cluster.cluster import Cluster
from codeflare_sdk.ray.cluster.status import (
    RayCluster,
    RayClusterStatus,
)
import pytest
from kubernetes import client


@patch.dict(
    "os.environ", {"JPY_SESSION_NAME": "example-test"}
)  # Mock Jupyter environment variable
def test_cluster_up_down_buttons(mocker):
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.get_cluster_custom_object",
        return_value={"spec": {"domain": "apps.cluster.awsroute.org"}},
    )
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        return_value=get_local_queue("kueue.x-k8s.io", "v1beta1", "ns", "localqueues"),
    )
    cluster = Cluster(createClusterConfig())

    with patch("ipywidgets.Button") as MockButton, patch(
        "ipywidgets.Checkbox"
    ) as MockCheckbox, patch("ipywidgets.Output"), patch("ipywidgets.HBox"), patch(
        "ipywidgets.VBox"
    ), patch.object(
        cluster, "up"
    ) as mock_up, patch.object(
        cluster, "down"
    ) as mock_down, patch.object(
        cluster, "wait_ready"
    ) as mock_wait_ready:
        # Create mock button & CheckBox instances
        mock_up_button = MagicMock()
        mock_down_button = MagicMock()
        mock_wait_ready_check_box = MagicMock()

        # Ensure the mock Button class returns the mock button instances in sequence
        MockCheckbox.side_effect = [mock_wait_ready_check_box]
        MockButton.side_effect = [mock_up_button, mock_down_button]

        # Call the method under test
        cf_widgets.cluster_up_down_buttons(cluster)

        # Simulate checkbox being checked or unchecked
        mock_wait_ready_check_box.value = True  # Simulate checkbox being checked

        # Simulate the button clicks by calling the mock on_click handlers
        mock_up_button.on_click.call_args[0][0](None)  # Simulate clicking "Cluster Up"
        mock_down_button.on_click.call_args[0][0](
            None
        )  # Simulate clicking "Cluster Down"

        # Check if the `up` and `down` methods were called
        mock_wait_ready.assert_called_once()
        mock_up.assert_called_once()
        mock_down.assert_called_once()


@patch.dict("os.environ", {}, clear=True)  # Mock environment with no variables
def test_is_notebook_false():
    assert cf_widgets.is_notebook() is False


@patch.dict(
    "os.environ", {"JPY_SESSION_NAME": "example-test"}
)  # Mock Jupyter environment variable
def test_is_notebook_true():
    assert cf_widgets.is_notebook() is True


def test_view_clusters(mocker, capsys):
    # If is not a notebook environment, a warning should be raised
    with pytest.warns(
        UserWarning,
        match="view_clusters can only be used in a Jupyter Notebook environment.",
    ):
        result = cf_widgets.view_clusters("default")

        # Assert the function returns None when not in a notebook environment
        assert result is None

    # Prepare to run view_clusters when notebook environment is detected
    mocker.patch("codeflare_sdk.common.widgets.widgets.is_notebook", return_value=True)
    mock_get_current_namespace = mocker.patch(
        "codeflare_sdk.ray.cluster.cluster.get_current_namespace",
        return_value="default",
    )
    namespace = mock_get_current_namespace.return_value

    # Assert the function returns None when no clusters are found
    mock_fetch_cluster_data = mocker.patch(
        "codeflare_sdk.common.widgets.widgets._fetch_cluster_data",
        return_value=pd.DataFrame(),
    )
    result = cf_widgets.view_clusters()
    captured = capsys.readouterr()
    assert mock_fetch_cluster_data.return_value.empty
    assert "No clusters found in the default namespace." in captured.out
    assert result is None

    # Prepare to run view_clusters with a test DataFrame
    mock_fetch_cluster_data = mocker.patch(
        "codeflare_sdk.common.widgets.widgets._fetch_cluster_data",
        return_value=pd.DataFrame(
            {
                "Name": ["test-cluster"],
                "Namespace": ["default"],
                "Num Workers": ["1"],
                "Head GPUs": ["0"],
                "Worker GPUs": ["0"],
                "Head CPU Req~Lim": ["1~1"],
                "Head Memory Req~Lim": ["1Gi~1Gi"],
                "Worker CPU Req~Lim": ["1~1"],
                "Worker Memory Req~Lim": ["1Gi~1Gi"],
                "status": ['<span style="color: green;">Ready ✓</span>'],
            }
        ),
    )
    # Create a RayClusterManagerWidgets instance
    ray_cluster_manager_instance = cf_widgets.RayClusterManagerWidgets(
        ray_clusters_df=mock_fetch_cluster_data.return_value, namespace=namespace
    )
    # Patch the constructor of RayClusterManagerWidgets to return our initialized instance
    mock_constructor = mocker.patch(
        "codeflare_sdk.common.widgets.widgets.RayClusterManagerWidgets",
        return_value=ray_cluster_manager_instance,
    )

    # Use a spy to track calls to display_widgets without replacing it
    spy_display_widgets = mocker.spy(ray_cluster_manager_instance, "display_widgets")

    cf_widgets.view_clusters()

    mock_constructor.assert_called_once_with(
        ray_clusters_df=mock_fetch_cluster_data.return_value, namespace=namespace
    )

    spy_display_widgets.assert_called_once()


def test_delete_cluster(mocker, capsys):
    name = "test-cluster"
    namespace = "default"

    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")

    mock_ray_cluster = MagicMock()
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.get_namespaced_custom_object",
        side_effect=[
            mock_ray_cluster,
            client.ApiException(status=404),
            client.ApiException(status=404),
            mock_ray_cluster,
        ],
    )

    # In this scenario, the RayCluster exists and the AppWrapper does not.
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster._check_aw_exists", return_value=False
    )
    mock_delete_rc = mocker.patch(
        "kubernetes.client.CustomObjectsApi.delete_namespaced_custom_object"
    )
    cf_widgets._delete_cluster(name, namespace)

    mock_delete_rc.assert_called_once_with(
        group="ray.io",
        version="v1",
        namespace=namespace,
        plural="rayclusters",
        name=name,
    )

    # In this scenario, the AppWrapper exists and the RayCluster does not
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster._check_aw_exists", return_value=True
    )
    mock_delete_aw = mocker.patch(
        "kubernetes.client.CustomObjectsApi.delete_namespaced_custom_object"
    )
    cf_widgets._delete_cluster(name, namespace)

    mock_delete_aw.assert_called_once_with(
        group="workload.codeflare.dev",
        version="v1beta2",
        namespace=namespace,
        plural="appwrappers",
        name=name,
    )

    # In this scenario, the deletion of the resource times out.
    with pytest.raises(
        TimeoutError, match=f"Timeout waiting for {name} to be deleted."
    ):
        cf_widgets._delete_cluster(name, namespace, 1)


def test_ray_cluster_manager_widgets_init(mocker, capsys):
    namespace = "default"
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        return_value=get_local_queue("kueue.x-k8s.io", "v1beta1", "ns", "localqueues"),
    )
    test_ray_clusters_df = pd.DataFrame(
        {
            "Name": ["test-cluster-1", "test-cluster-2"],
            "Namespace": [namespace, namespace],
            "Num Workers": ["1", "2"],
            "Head GPUs": ["0", "0"],
            "Worker GPUs": ["0", "0"],
            "Head CPU Req~Lim": ["1~1", "1~1"],
            "Head Memory Req~Lim": ["1Gi~1Gi", "1Gi~1Gi"],
            "Worker CPU Req~Lim": ["1~1", "1~1"],
            "Worker Memory Req~Lim": ["1Gi~1Gi", "1Gi~1Gi"],
            "status": [
                '<span style="color: green;">Ready ✓</span>',
                '<span style="color: green;">Ready ✓</span>',
            ],
        }
    )
    mock_fetch_cluster_data = mocker.patch(
        "codeflare_sdk.common.widgets.widgets._fetch_cluster_data",
        return_value=test_ray_clusters_df,
    )
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster.get_current_namespace",
        return_value=namespace,
    )
    mock_delete_cluster = mocker.patch(
        "codeflare_sdk.common.widgets.widgets._delete_cluster"
    )

    # # Mock ToggleButtons
    mock_toggle_buttons = mocker.patch("ipywidgets.ToggleButtons")
    mock_button = mocker.patch("ipywidgets.Button")
    mock_output = mocker.patch("ipywidgets.Output")

    # Initialize the RayClusterManagerWidgets instance
    ray_cluster_manager_instance = cf_widgets.RayClusterManagerWidgets(
        ray_clusters_df=test_ray_clusters_df, namespace=namespace
    )

    # Assertions for DataFrame and attributes
    assert ray_cluster_manager_instance.ray_clusters_df.equals(
        test_ray_clusters_df
    ), "ray_clusters_df attribute does not match the input DataFrame"
    assert (
        ray_cluster_manager_instance.namespace == namespace
    ), f"Expected namespace to be '{namespace}', but got '{ray_cluster_manager_instance.namespace}'"
    assert (
        ray_cluster_manager_instance.classification_widget.options
        == test_ray_clusters_df["Name"].tolist()
    ), "classification_widget options do not match the input DataFrame"

    # Assertions for widgets
    mock_toggle_buttons.assert_called_once_with(
        options=test_ray_clusters_df["Name"].tolist(),
        value=test_ray_clusters_df["Name"].tolist()[0],
        description="Select an existing cluster:",
    )
    assert (
        ray_cluster_manager_instance.classification_widget
        == mock_toggle_buttons.return_value
    ), "classification_widget is not set correctly"
    assert (
        ray_cluster_manager_instance.delete_button == mock_button.return_value
    ), "delete_button is not set correctly"
    assert (
        ray_cluster_manager_instance.list_jobs_button == mock_button.return_value
    ), "list_jobs_button is not set correctly"
    assert (
        ray_cluster_manager_instance.ray_dashboard_button == mock_button.return_value
    ), "ray_dashboard_button is not set correctly"
    assert (
        ray_cluster_manager_instance.refresh_data_button == mock_button.return_value
    ), "refresh_data_button is not set correctly"
    assert (
        ray_cluster_manager_instance.raycluster_data_output == mock_output.return_value
    ), "raycluster_data_output is not set correctly"
    assert (
        ray_cluster_manager_instance.user_output == mock_output.return_value
    ), "user_output is not set correctly"
    assert (
        ray_cluster_manager_instance.url_output == mock_output.return_value
    ), "url_output is not set correctly"

    ### Test button click events
    mock_delete_button = MagicMock()
    mock_list_jobs_button = MagicMock()
    mock_ray_dashboard_button = MagicMock()
    mock_refresh_dataframe_button = MagicMock()

    mock_javascript = mocker.patch("codeflare_sdk.common.widgets.widgets.Javascript")
    ray_cluster_manager_instance.url_output = MagicMock()

    mock_dashboard_uri = mocker.patch(
        "codeflare_sdk.ray.cluster.cluster.Cluster.cluster_dashboard_uri",
        return_value="https://ray-dashboard-test-cluster-1-ns.apps.cluster.awsroute.org",
    )

    # Simulate clicking the list jobs button
    ray_cluster_manager_instance.classification_widget.value = "test-cluster-1"
    ray_cluster_manager_instance._on_list_jobs_button_click(mock_list_jobs_button)

    captured = capsys.readouterr()
    assert (
        f"Opening Ray Jobs Dashboard for test-cluster-1 cluster:\n{mock_dashboard_uri.return_value}/#/jobs"
        in captured.out
    )
    mock_javascript.assert_called_with(
        f'window.open("{mock_dashboard_uri.return_value}/#/jobs", "_blank");'
    )

    # Simulate clicking the refresh data button
    ray_cluster_manager_instance._on_refresh_data_button_click(
        mock_refresh_dataframe_button
    )
    mock_fetch_cluster_data.assert_called_with(namespace)

    # Simulate clicking the Ray dashboard button
    ray_cluster_manager_instance.classification_widget.value = "test-cluster-1"
    ray_cluster_manager_instance._on_ray_dashboard_button_click(
        mock_ray_dashboard_button
    )

    captured = capsys.readouterr()
    assert (
        f"Opening Ray Dashboard for test-cluster-1 cluster:\n{mock_dashboard_uri.return_value}"
        in captured.out
    )
    mock_javascript.assert_called_with(
        f'window.open("{mock_dashboard_uri.return_value}", "_blank");'
    )

    # Simulate clicking the delete button
    ray_cluster_manager_instance.classification_widget.value = "test-cluster-1"
    ray_cluster_manager_instance._on_delete_button_click(mock_delete_button)
    mock_delete_cluster.assert_called_with("test-cluster-1", namespace)

    mock_fetch_cluster_data.return_value = pd.DataFrame()
    ray_cluster_manager_instance.classification_widget.value = "test-cluster-2"
    ray_cluster_manager_instance._on_delete_button_click(mock_delete_button)
    mock_delete_cluster.assert_called_with("test-cluster-2", namespace)

    # Assert on deletion that the dataframe is empty
    assert (
        ray_cluster_manager_instance.ray_clusters_df.empty
    ), "Expected DataFrame to be empty after deletion"

    captured = capsys.readouterr()
    assert (
        f"Cluster test-cluster-1 in the {namespace} namespace was deleted successfully."
        in captured.out
    )


def test_fetch_cluster_data(mocker):
    # Return empty dataframe when no clusters are found
    mocker.patch("codeflare_sdk.ray.cluster.cluster.list_all_clusters", return_value=[])
    df = cf_widgets._fetch_cluster_data(namespace="default")
    assert df.empty

    # Create mock RayCluster objects
    mock_raycluster1 = MagicMock(spec=RayCluster)
    mock_raycluster1.name = "test-cluster-1"
    mock_raycluster1.namespace = "default"
    mock_raycluster1.num_workers = 1
    mock_raycluster1.head_extended_resources = {"nvidia.com/gpu": "1"}
    mock_raycluster1.worker_extended_resources = {"nvidia.com/gpu": "2"}
    mock_raycluster1.head_cpu_requests = "500m"
    mock_raycluster1.head_cpu_limits = "1000m"
    mock_raycluster1.head_mem_requests = "1Gi"
    mock_raycluster1.head_mem_limits = "2Gi"
    mock_raycluster1.worker_cpu_requests = "1000m"
    mock_raycluster1.worker_cpu_limits = "2000m"
    mock_raycluster1.worker_mem_requests = "2Gi"
    mock_raycluster1.worker_mem_limits = "4Gi"
    mock_raycluster1.status = MagicMock()
    mock_raycluster1.status.name = "READY"
    mock_raycluster1.status = RayClusterStatus.READY

    mock_raycluster2 = MagicMock(spec=RayCluster)
    mock_raycluster2.name = "test-cluster-2"
    mock_raycluster2.namespace = "default"
    mock_raycluster2.num_workers = 2
    mock_raycluster2.head_extended_resources = {}
    mock_raycluster2.worker_extended_resources = {}
    mock_raycluster2.head_cpu_requests = None
    mock_raycluster2.head_cpu_limits = None
    mock_raycluster2.head_mem_requests = None
    mock_raycluster2.head_mem_limits = None
    mock_raycluster2.worker_cpu_requests = None
    mock_raycluster2.worker_cpu_limits = None
    mock_raycluster2.worker_mem_requests = None
    mock_raycluster2.worker_mem_limits = None
    mock_raycluster2.status = MagicMock()
    mock_raycluster2.status.name = "SUSPENDED"
    mock_raycluster2.status = RayClusterStatus.SUSPENDED

    with patch(
        "codeflare_sdk.ray.cluster.cluster.list_all_clusters",
        return_value=[mock_raycluster1, mock_raycluster2],
    ):
        # Call the function under test
        df = cf_widgets._fetch_cluster_data(namespace="default")

    # Expected DataFrame
    expected_data = {
        "Name": ["test-cluster-1", "test-cluster-2"],
        "Namespace": ["default", "default"],
        "Num Workers": [1, 2],
        "Head GPUs": ["nvidia.com/gpu: 1", "0"],
        "Worker GPUs": ["nvidia.com/gpu: 2", "0"],
        "Head CPU Req~Lim": ["500m~1000m", "0~0"],
        "Head Memory Req~Lim": ["1Gi~2Gi", "0~0"],
        "Worker CPU Req~Lim": ["1000m~2000m", "0~0"],
        "Worker Memory Req~Lim": ["2Gi~4Gi", "0~0"],
        "status": [
            '<span style="color: green;">Ready ✓</span>',
            '<span style="color: #007BFF;">Suspended ❄️</span>',
        ],
    }

    expected_df = pd.DataFrame(expected_data)

    # Assert that the DataFrame matches expected
    pd.testing.assert_frame_equal(
        df.reset_index(drop=True), expected_df.reset_index(drop=True)
    )


def test_format_status():
    # Test each possible status
    test_cases = [
        (RayClusterStatus.READY, '<span style="color: green;">Ready ✓</span>'),
        (
            RayClusterStatus.SUSPENDED,
            '<span style="color: #007BFF;">Suspended ❄️</span>',
        ),
        (RayClusterStatus.FAILED, '<span style="color: red;">Failed ✗</span>'),
        (RayClusterStatus.UNHEALTHY, '<span style="color: purple;">Unhealthy</span>'),
        (RayClusterStatus.UNKNOWN, '<span style="color: purple;">Unknown</span>'),
    ]

    for status, expected_output in test_cases:
        assert (
            cf_widgets._format_status(status) == expected_output
        ), f"Failed for status: {status}"

    # Test an unrecognized status
    unrecognized_status = "NotAStatus"
    assert (
        cf_widgets._format_status(unrecognized_status) == "NotAStatus"
    ), "Failed for unrecognized status"

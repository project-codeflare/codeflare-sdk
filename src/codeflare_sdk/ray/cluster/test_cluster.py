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

from codeflare_sdk.ray.cluster.cluster import (
    Cluster,
    ClusterConfiguration,
    get_cluster,
    list_all_queued,
)
from codeflare_sdk.common.utils.unit_test_support import (
    create_cluster,
    arg_check_del_effect,
    ingress_retrieval,
    arg_check_apply_effect,
    get_local_queue,
    create_cluster_config,
    get_ray_obj,
    get_obj_none,
    get_ray_obj_with_status,
    patch_cluster_with_dynamic_client,
    route_list_retrieval,
)
from codeflare_sdk.ray.cluster.cluster import _is_openshift_cluster
from pathlib import Path
from unittest.mock import MagicMock
from kubernetes import client
import yaml
import pytest
import filecmp
import os
import ray
import tempfile

parent = Path(__file__).resolve().parents[4]  # project directory
expected_clusters_dir = f"{parent}/tests/test_cluster_yamls"
cluster_dir = os.path.expanduser("~/.codeflare/resources/")


def test_cluster_apply_down(mocker):
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch("codeflare_sdk.ray.cluster.cluster.Cluster._throw_for_no_raycluster")
    mocker.patch("codeflare_sdk.ray.cluster.cluster.Cluster.get_dynamic_client")
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.get_cluster_custom_object",
        return_value={"spec": {"domain": ""}},
    )
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.create_namespaced_custom_object",
        side_effect=arg_check_apply_effect,
    )
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.delete_namespaced_custom_object",
        side_effect=arg_check_del_effect,
    )
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_cluster_custom_object",
        return_value={"items": []},
    )
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        return_value=get_local_queue("kueue.x-k8s.io", "v1beta1", "ns", "localqueues"),
    )
    # Mock certificate cleanup (automatic in cluster.down())
    mock_cleanup = mocker.patch(
        "codeflare_sdk.common.utils.generate_cert.cleanup_tls_cert", return_value=True
    )
    # Mock TLS cert generation for this test
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster.Cluster._generate_tls_certs_with_wait"
    )

    cluster = create_cluster(mocker)
    cluster.apply()
    cluster.down()

    # Verify cleanup was called
    mock_cleanup.assert_called_once_with("unit-test-cluster", "ns")


def test_cluster_apply_scale_up_scale_down(mocker):
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mock_dynamic_client = mocker.Mock()
    mocker.patch(
        "kubernetes.dynamic.DynamicClient.resources", new_callable=mocker.PropertyMock
    )
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster.Cluster.create_resource",
        return_value="./tests/test_cluster_yamls/ray/default-ray-cluster.yaml",
    )
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.get_cluster_custom_object",
        return_value={"spec": {"domain": "apps.cluster.awsroute.org"}},
    )

    # Initialize test
    initial_num_workers = 1
    scaled_up_num_workers = 2

    # Step 1: Create cluster with initial workers
    cluster = create_cluster(mocker, initial_num_workers)
    patch_cluster_with_dynamic_client(mocker, cluster, mock_dynamic_client)
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        return_value=get_obj_none("ray.io", "v1", "ns", "rayclusters"),
    )
    # Mock TLS cert generation for this test
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster.Cluster._generate_tls_certs_with_wait"
    )
    cluster.apply()

    # Step 2: Scale up the cluster
    cluster = create_cluster(mocker, scaled_up_num_workers)
    patch_cluster_with_dynamic_client(mocker, cluster, mock_dynamic_client)
    cluster.apply()

    # Step 3: Scale down the cluster
    cluster = create_cluster(mocker, initial_num_workers)
    patch_cluster_with_dynamic_client(mocker, cluster, mock_dynamic_client)
    cluster.apply()

    # Mock certificate cleanup (automatic in cluster.down())
    mocker.patch(
        "codeflare_sdk.common.utils.generate_cert.cleanup_tls_cert", return_value=True
    )

    # Tear down
    cluster.down()


def test_cluster_apply_with_file(mocker):
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mock_dynamic_client = mocker.Mock()
    mocker.patch("codeflare_sdk.ray.cluster.cluster.Cluster._throw_for_no_raycluster")
    mocker.patch(
        "kubernetes.dynamic.DynamicClient.resources", new_callable=mocker.PropertyMock
    )
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster.Cluster.create_resource",
        return_value="./tests/test_cluster_yamls/ray/default-ray-cluster.yaml",
    )
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.get_cluster_custom_object",
        return_value={"spec": {"domain": "apps.cluster.awsroute.org"}},
    )

    # Step 1: Create cluster with initial workers
    cluster = create_cluster(mocker, 1, write_to_file=True)
    patch_cluster_with_dynamic_client(mocker, cluster, mock_dynamic_client)
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        return_value=get_obj_none("ray.io", "v1", "ns", "rayclusters"),
    )
    # Mock certificate cleanup (automatic in cluster.down())
    mocker.patch(
        "codeflare_sdk.common.utils.generate_cert.cleanup_tls_cert", return_value=True
    )
    # Mock TLS cert generation for this test
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster.Cluster._generate_tls_certs_with_wait"
    )

    cluster.apply()
    # Tear down
    cluster.down()


def test_cluster_apply_write_to_file(mocker):
    # Mock Kubernetes client and dynamic client methods
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mock_dynamic_client = mocker.Mock()
    mocker.patch("codeflare_sdk.ray.cluster.cluster.Cluster._throw_for_no_raycluster")
    mocker.patch(
        "kubernetes.dynamic.DynamicClient.resources", new_callable=mocker.PropertyMock
    )
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster.Cluster.create_resource",
        return_value="./tests/test_cluster_yamls/ray/default-ray-cluster.yaml",
    )
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")

    # Create a cluster configuration
    cluster = create_cluster(mocker, 1, write_to_file=True)
    patch_cluster_with_dynamic_client(mocker, cluster, mock_dynamic_client)

    # Mock listing RayCluster to simulate it doesn't exist
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        return_value=get_obj_none("ray.io", "v1", "ns", "rayclusters"),
    )
    # Mock TLS cert generation for this test
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster.Cluster._generate_tls_certs_with_wait"
    )
    # Call the apply method
    cluster.apply()

    # Assertions
    print("Cluster applied.")


def test_cluster_apply_basic(mocker):
    # Mock Kubernetes client and dynamic client methods
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mock_dynamic_client = mocker.Mock()
    mocker.patch("codeflare_sdk.ray.cluster.cluster.Cluster._throw_for_no_raycluster")
    mocker.patch(
        "kubernetes.dynamic.DynamicClient.resources", new_callable=mocker.PropertyMock
    )
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster.Cluster.create_resource",
        return_value="./tests/test_cluster_yamls/ray/default-ray-cluster.yaml",
    )
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")

    # Create a cluster configuration
    cluster = create_cluster(mocker, 1, write_to_file=False)
    patch_cluster_with_dynamic_client(mocker, cluster, mock_dynamic_client)

    # Mock listing RayCluster to simulate it doesn't exist
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        return_value=get_obj_none("ray.io", "v1", "ns", "rayclusters"),
    )
    # Mock TLS cert generation for this test
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster.Cluster._generate_tls_certs_with_wait"
    )

    # Call the apply method
    cluster.apply()

    # Assertions
    print("Cluster applied.")


def test_cluster_apply_down_no_mcad(mocker):
    mocker.patch("codeflare_sdk.ray.cluster.cluster.Cluster._throw_for_no_raycluster")
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch("codeflare_sdk.ray.cluster.cluster.Cluster.get_dynamic_client")
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        return_value=get_local_queue("kueue.x-k8s.io", "v1beta1", "ns", "localqueues"),
    )
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.create_namespaced_custom_object",
        side_effect=arg_check_apply_effect,
    )
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.delete_namespaced_custom_object",
        side_effect=arg_check_del_effect,
    )
    mocker.patch(
        "kubernetes.client.CoreV1Api.create_namespaced_secret",
    )
    mocker.patch(
        "kubernetes.client.CoreV1Api.delete_namespaced_secret",
    )
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_cluster_custom_object",
        return_value={"items": []},
    )
    # Mock certificate cleanup (automatic in cluster.down())
    mocker.patch(
        "codeflare_sdk.common.utils.generate_cert.cleanup_tls_cert", return_value=True
    )
    # Mock TLS cert generation for this test
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster.Cluster._generate_tls_certs_with_wait"
    )

    config = create_cluster_config()
    config.name = "unit-test-cluster-ray"
    cluster = Cluster(config)
    cluster.apply()
    cluster.down()


def test_cluster_uris(mocker):
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster._get_ingress_domain",
        return_value="apps.cluster.awsroute.org",
    )
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        return_value=get_local_queue("kueue.x-k8s.io", "v1beta1", "ns", "localqueues"),
    )

    # Mock the TLS cert check to avoid warnings in test output
    mocker.patch("codeflare_sdk.ray.cluster.cluster.Cluster._check_tls_certs_exist")

    cluster = create_cluster(mocker)
    mocker.patch(
        "kubernetes.client.NetworkingV1Api.list_namespaced_ingress",
        return_value=ingress_retrieval(
            cluster_name="unit-test-cluster",
            annotations={"route.openshift.io/termination": "passthrough"},
        ),
    )
    assert (
        cluster.cluster_dashboard_uri()
        == "https://ray-dashboard-unit-test-cluster-ns.apps.cluster.awsroute.org"
    )
    mocker.patch(
        "kubernetes.client.NetworkingV1Api.list_namespaced_ingress",
        return_value=ingress_retrieval(),
    )
    assert cluster.cluster_uri() == "ray://unit-test-cluster-head-svc.ns.svc:10001"
    assert (
        cluster.cluster_dashboard_uri()
        == "http://ray-dashboard-unit-test-cluster-ns.apps.cluster.awsroute.org"
    )
    cluster.config.name = "fake"
    mocker.patch(
        "kubernetes.client.NetworkingV1Api.list_namespaced_ingress",
    )
    assert (
        cluster.cluster_dashboard_uri()
        == "Dashboard not available yet, have you run cluster.apply()? Run cluster.details() to check if it's ready."
    )

    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster._is_openshift_cluster", return_value=True
    )
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        return_value={
            "items": [
                {
                    "metadata": {
                        "name": "ray-dashboard-unit-test-cluster",
                    },
                    "spec": {
                        "host": "ray-dashboard-unit-test-cluster-ns.apps.cluster.awsroute.org",
                        "tls": {},  # Indicating HTTPS
                    },
                }
            ]
        },
    )
    cluster = create_cluster(mocker)
    assert (
        cluster.cluster_dashboard_uri()
        == "http://ray-dashboard-unit-test-cluster-ns.apps.cluster.awsroute.org"
    )
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        return_value={
            "items": [
                {
                    "metadata": {
                        "name": "ray-dashboard-unit-test-cluster",
                    },
                    "spec": {
                        "host": "ray-dashboard-unit-test-cluster-ns.apps.cluster.awsroute.org",
                        "tls": {"termination": "passthrough"},  # Indicating HTTPS
                    },
                }
            ]
        },
    )
    cluster = create_cluster(mocker)
    assert (
        cluster.cluster_dashboard_uri()
        == "https://ray-dashboard-unit-test-cluster-ns.apps.cluster.awsroute.org"
    )


def test_ray_job_wrapping(mocker):
    def ray_addr(self, *args):
        return self._address

    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        return_value=get_local_queue("kueue.x-k8s.io", "v1beta1", "ns", "localqueues"),
    )
    # Mock the TLS cert check to avoid warnings in test output
    mocker.patch("codeflare_sdk.ray.cluster.cluster.Cluster._check_tls_certs_exist")
    cluster = create_cluster(mocker)
    mocker.patch(
        "ray.job_submission.JobSubmissionClient._check_connection_and_version_with_url",
        return_value="None",
    )
    mock_res = mocker.patch.object(
        ray.job_submission.JobSubmissionClient, "list_jobs", autospec=True
    )
    mock_res.side_effect = ray_addr
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.get_cluster_custom_object",
        return_value={"spec": {"domain": ""}},
    )
    mocker.patch(
        "kubernetes.client.NetworkingV1Api.list_namespaced_ingress",
        return_value=ingress_retrieval(),
    )
    assert cluster.list_jobs() == cluster.cluster_dashboard_uri()

    mock_res = mocker.patch.object(
        ray.job_submission.JobSubmissionClient, "get_job_status", autospec=True
    )
    mock_res.side_effect = ray_addr
    assert cluster.job_status("fake_id") == cluster.cluster_dashboard_uri()

    mock_res = mocker.patch.object(
        ray.job_submission.JobSubmissionClient, "get_job_logs", autospec=True
    )
    mock_res.side_effect = ray_addr
    assert cluster.job_logs("fake_id") == cluster.cluster_dashboard_uri()


def test_local_client_url(mocker):
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.get_cluster_custom_object",
        return_value={"spec": {"domain": ""}},
    )
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster._get_ingress_domain",
        return_value="rayclient-unit-test-cluster-localinter-ns.apps.cluster.awsroute.org",
    )
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster.Cluster.create_resource",
        return_value="unit-test-cluster-localinter.yaml",
    )
    # Mock the TLS cert check to avoid warnings in test output
    mocker.patch("codeflare_sdk.ray.cluster.cluster.Cluster._check_tls_certs_exist")

    cluster_config = ClusterConfiguration(
        name="unit-test-cluster-localinter",
        namespace="ns",
    )
    cluster = Cluster(cluster_config)
    assert (
        cluster.local_client_url()
        == "ray://rayclient-unit-test-cluster-localinter-ns.apps.cluster.awsroute.org"
    )


"""
get_cluster tests
"""


def test_get_cluster(mocker):
    """
    This test uses the "test all params" unit test file as a comparison
    """
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")

    with open(f"{expected_clusters_dir}/ray/unit-test-all-params.yaml") as f:
        expected_rc = yaml.load(f, Loader=yaml.FullLoader)
        mocker.patch(
            "kubernetes.client.CustomObjectsApi.get_namespaced_custom_object",
            return_value=expected_rc,
        )
        get_cluster("test-all-params", "ns", write_to_file=True)

        with open(f"{cluster_dir}test-all-params.yaml") as f:
            generated_rc = yaml.load(f, Loader=yaml.FullLoader)
        assert generated_rc == expected_rc


def test_wait_ready(mocker, capsys):
    from codeflare_sdk.ray.cluster.status import CodeFlareClusterStatus

    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch(
        "kubernetes.client.NetworkingV1Api.list_namespaced_ingress",
        return_value=ingress_retrieval(),
    )
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster._ray_cluster_status", return_value=None
    )
    mocker.patch.object(
        client.CustomObjectsApi,
        "list_namespaced_custom_object",
        return_value={
            "items": [
                {
                    "metadata": {"name": "ray-dashboard-test"},
                    "spec": {"host": "mocked-host"},
                }
            ]
        },
    )
    mock_response = mocker.Mock()
    mock_response.status_code = 200
    mocker.patch("requests.get", return_value=mock_response)

    # Mock certificate generation (automatic in wait_ready)
    mocker.patch("codeflare_sdk.common.utils.generate_cert.generate_tls_cert")
    mocker.patch("codeflare_sdk.common.utils.generate_cert.export_env")

    cf = Cluster(
        ClusterConfiguration(
            name="test",
            namespace="ns",
            write_to_file=False,
        )
    )
    try:
        cf.wait_ready(timeout=5)
        assert 1 == 0
    except Exception as e:
        assert type(e) == TimeoutError

    captured = capsys.readouterr()
    assert (
        "WARNING: Current cluster status is unknown, have you run cluster.apply() yet? Run cluster.details() to check if it's ready."
        in captured.out
    )
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster.Cluster.status",
        return_value=(True, CodeFlareClusterStatus.READY),
    )
    cf.wait_ready()
    captured = capsys.readouterr()
    # Note: "TLS certificates generated" message is not shown when generate_tls_cert is mocked
    assert (
        captured.out
        == "Waiting for requested resources to be set up...\nRequested cluster is up and running!\nDashboard is ready!\n"
    )
    cf.wait_ready(dashboard_check=False)
    captured = capsys.readouterr()
    assert (
        captured.out
        == "Waiting for requested resources to be set up...\nRequested cluster is up and running!\n"
    )

    # Test dashboard waiting message when dashboard_uri is not a valid URL (error message)
    call_count = 0

    def mock_is_dashboard_ready_eventually():
        nonlocal call_count
        call_count += 1
        return call_count >= 2  # Return False first, then True

    mocker.patch.object(
        cf, "is_dashboard_ready", side_effect=mock_is_dashboard_ready_eventually
    )
    mocker.patch.object(
        cf,
        "cluster_dashboard_uri",
        return_value="Dashboard not available yet, have you run cluster.apply()?",
    )

    call_count = 0  # Reset counter
    cf.wait_ready()
    captured = capsys.readouterr()
    assert "Waiting for dashboard route/HTTPRoute to be created..." in captured.out

    # Test dashboard waiting message when dashboard_uri is a valid URL
    call_count = 0  # Reset counter
    mocker.patch.object(
        cf,
        "cluster_dashboard_uri",
        return_value="https://dashboard.example.com",
    )
    cf.wait_ready()
    captured = capsys.readouterr()
    assert (
        "Waiting for dashboard to become accessible: https://dashboard.example.com"
        in captured.out
    )


def test_is_dashboard_ready_url_validation(mocker):
    """Test that is_dashboard_ready returns False for invalid URLs (error messages)"""
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        return_value=get_local_queue("kueue.x-k8s.io", "v1beta1", "ns", "localqueues"),
    )

    cluster = create_cluster(mocker)

    # Test with error message string (not a valid URL)
    mocker.patch.object(
        cluster,
        "cluster_dashboard_uri",
        return_value="Dashboard not available yet, have you run cluster.apply()?",
    )
    assert (
        cluster.is_dashboard_ready() is False
    ), "Should return False when dashboard_uri is an error message"

    # Test with None
    mocker.patch.object(cluster, "cluster_dashboard_uri", return_value=None)
    assert (
        cluster.is_dashboard_ready() is False
    ), "Should return False when dashboard_uri is None"

    # Test with valid HTTP URL that returns 200
    mocker.patch.object(
        cluster,
        "cluster_dashboard_uri",
        return_value="http://dashboard.example.com",
    )
    mock_response = mocker.Mock()
    mock_response.status_code = 200
    mocker.patch("requests.get", return_value=mock_response)
    assert (
        cluster.is_dashboard_ready() is True
    ), "Should return True when dashboard returns 200"

    # Test with valid HTTPS URL that returns 302 (OAuth redirect)
    mocker.patch.object(
        cluster,
        "cluster_dashboard_uri",
        return_value="https://dashboard.example.com",
    )
    mock_response.status_code = 302
    assert (
        cluster.is_dashboard_ready() is True
    ), "Should return True when dashboard returns 302 (OAuth redirect)"

    # Test with valid URL that returns 401/403 (auth required)
    mock_response.status_code = 401
    assert (
        cluster.is_dashboard_ready() is True
    ), "Should return True when dashboard returns 401"
    mock_response.status_code = 403
    assert (
        cluster.is_dashboard_ready() is True
    ), "Should return True when dashboard returns 403"

    # Test with valid URL that returns 500 (server error)
    mock_response.status_code = 500
    assert (
        cluster.is_dashboard_ready() is False
    ), "Should return False when dashboard returns 500"


def test_list_queue_rayclusters(mocker, capsys):
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mock_api = MagicMock()
    mock_api.get_api_versions.return_value.groups = [
        MagicMock(versions=[MagicMock(group_version="route.openshift.io/v1")])
    ]
    mocker.patch("kubernetes.client.ApisApi", return_value=mock_api)

    assert _is_openshift_cluster() == True
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        return_value=get_obj_none("ray.io", "v1", "ns", "rayclusters"),
    )

    list_all_queued("ns")
    captured = capsys.readouterr()
    # The Rich library's console width detection varies between test contexts
    # Accept either the two-line format (individual tests) or single-line format (full test suite)
    # Check for key parts of the message instead of the full text
    assert "No resources found" in captured.out
    assert "cluster.apply()" in captured.out
    assert "cluster.details()" in captured.out
    assert "check if it's ready" in captured.out
    assert "╭" in captured.out and "╮" in captured.out  # Check for box characters
    assert "│" in captured.out  # Check for vertical lines
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        return_value=get_ray_obj_with_status("ray.io", "v1", "ns", "rayclusters"),
    )

    list_all_queued("ns")
    captured = capsys.readouterr()
    # print(captured.out) -> useful for updating the test
    assert captured.out == (
        "╭────────────────────────────────╮\n"
        "│   🚀 Cluster Queue Status 🚀   │\n"
        "│ +----------------+-----------+ │\n"
        "│ | Name           | Status    | │\n"
        "│ +================+===========+ │\n"
        "│ | test-cluster-a | ready     | │\n"
        "│ |                |           | │\n"
        "│ | test-rc-b      | suspended | │\n"
        "│ |                |           | │\n"
        "│ +----------------+-----------+ │\n"
        "╰────────────────────────────────╯\n"
    )


def test_list_clusters(mocker, capsys):
    from codeflare_sdk.ray.cluster.cluster import list_all_clusters

    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        side_effect=get_obj_none,
    )
    mocker.patch(
        "kubernetes.client.NetworkingV1Api.list_namespaced_ingress",
    )
    list_all_clusters("ns")
    captured = capsys.readouterr()
    # The Rich library's console width detection varies between test contexts
    # Accept either the two-line format (individual tests) or single-line format (full test suite)
    # Check for key parts of the message instead of the full text
    assert "No resources found" in captured.out
    assert "cluster.apply()" in captured.out
    assert "cluster.details()" in captured.out
    assert "check if it's ready" in captured.out
    assert "╭" in captured.out and "╮" in captured.out  # Check for box characters
    assert "│" in captured.out  # Check for vertical lines
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        side_effect=get_ray_obj,
    )
    list_all_clusters("ns")
    captured = capsys.readouterr()
    # print(captured.out) -> useful for updating the test
    assert captured.out == (
        "                    🚀 CodeFlare Cluster Details 🚀                   \n"
        "                                                                      \n"
        " ╭──────────────────────────────────────────────────────────────────╮ \n"
        " │   Name                                                           │ \n"
        " │   test-cluster-a                                   Inactive ❌   │ \n"
        " │                                                                  │ \n"
        " │   URI: ray://test-cluster-a-head-svc.ns.svc:10001                │ \n"
        " │                                                                  │ \n"
        " │   Dashboard🔗                                                    │ \n"
        " │                                                                  │ \n"
        " │                       Cluster Resources                          │ \n"
        " │   ╭── Workers ──╮  ╭───────── Worker specs(each) ─────────╮      │ \n"
        " │   │  # Workers  │  │  Memory      CPU         GPU         │      │ \n"
        " │   │             │  │                                      │      │ \n"
        " │   │  1          │  │  2G~2G       1~1         0           │      │ \n"
        " │   │             │  │                                      │      │ \n"
        " │   ╰─────────────╯  ╰──────────────────────────────────────╯      │ \n"
        " ╰──────────────────────────────────────────────────────────────────╯ \n"
        "╭───────────────────────────────────────────────────────────────╮\n"
        "│   Name                                                        │\n"
        "│   test-rc-b                                   Inactive ❌     │\n"
        "│                                                               │\n"
        "│   URI: ray://test-rc-b-head-svc.ns.svc:10001                  │\n"
        "│                                                               │\n"
        "│   Dashboard🔗                                                 │\n"
        "│                                                               │\n"
        "│                       Cluster Resources                       │\n"
        "│   ╭── Workers ──╮  ╭───────── Worker specs(each) ─────────╮   │\n"
        "│   │  # Workers  │  │  Memory      CPU         GPU         │   │\n"
        "│   │             │  │                                      │   │\n"
        "│   │  1          │  │  2G~2G       1~1         0           │   │\n"
        "│   │             │  │                                      │   │\n"
        "│   ╰─────────────╯  ╰──────────────────────────────────────╯   │\n"
        "╰───────────────────────────────────────────────────────────────╯\n"
    )


def test_map_to_ray_cluster(mocker):
    from codeflare_sdk.ray.cluster.cluster import _map_to_ray_cluster

    mocker.patch("kubernetes.config.load_kube_config")

    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster._is_openshift_cluster", return_value=True
    )

    mock_api_client = mocker.MagicMock(spec=client.ApiClient)
    mocker.patch(
        "codeflare_sdk.common.kubernetes_cluster.auth.get_api_client",
        return_value=mock_api_client,
    )

    mock_routes = {
        "items": [
            {
                "apiVersion": "route.openshift.io/v1",
                "kind": "Route",
                "metadata": {
                    "name": "ray-dashboard-test-cluster-a",
                    "namespace": "ns",
                },
                "spec": {"host": "ray-dashboard-test-cluster-a"},
            },
        ]
    }

    def custom_side_effect(group, version, namespace, plural, **kwargs):
        if plural == "routes":
            return mock_routes
        elif plural == "rayclusters":
            return get_ray_obj("ray.io", "v1", "ns", "rayclusters")

    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        side_effect=custom_side_effect,
    )

    rc = get_ray_obj("ray.io", "v1", "ns", "rayclusters")["items"][0]
    rc_name = rc["metadata"]["name"]
    rc_dashboard = f"http://ray-dashboard-{rc_name}"

    result = _map_to_ray_cluster(rc)

    assert result is not None
    assert result.dashboard == rc_dashboard


def test_throw_for_no_raycluster_crd_errors(mocker):
    """Test RayCluster CRD error handling"""
    from kubernetes.client.rest import ApiException

    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")

    # Test 404 error - CRD not found
    mock_api_404 = MagicMock()
    mock_api_404.list_namespaced_custom_object.side_effect = ApiException(status=404)
    mocker.patch("kubernetes.client.CustomObjectsApi", return_value=mock_api_404)

    cluster = create_cluster(mocker)
    with pytest.raises(
        RuntimeError, match="RayCluster CustomResourceDefinition unavailable"
    ):
        cluster._throw_for_no_raycluster()

    # Test other API error
    mock_api_500 = MagicMock()
    mock_api_500.list_namespaced_custom_object.side_effect = ApiException(status=500)
    mocker.patch("kubernetes.client.CustomObjectsApi", return_value=mock_api_500)

    cluster2 = create_cluster(mocker)
    with pytest.raises(
        RuntimeError, match="Failed to get RayCluster CustomResourceDefinition"
    ):
        cluster2._throw_for_no_raycluster()


def test_cluster_apply_attribute_error_handling(mocker):
    """Test AttributeError handling when DynamicClient fails"""
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch("codeflare_sdk.ray.cluster.cluster.Cluster._throw_for_no_raycluster")
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        return_value=get_local_queue("kueue.x-k8s.io", "v1beta1", "ns", "localqueues"),
    )

    # Mock get_dynamic_client to raise AttributeError
    def raise_attribute_error():
        raise AttributeError("DynamicClient initialization failed")

    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster.Cluster.get_dynamic_client",
        side_effect=raise_attribute_error,
    )

    cluster = create_cluster(mocker)

    with pytest.raises(RuntimeError, match="Failed to initialize DynamicClient"):
        cluster.apply()


def test_cluster_namespace_handling(mocker, capsys):
    """Test namespace validation in create_resource"""
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        return_value=get_local_queue("kueue.x-k8s.io", "v1beta1", "ns", "localqueues"),
    )

    # Test with None namespace that gets set
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster.get_current_namespace", return_value=None
    )

    config = ClusterConfiguration(
        name="test-cluster-ns",
        namespace=None,  # Will trigger namespace check
        num_workers=1,
        worker_cpu_requests=1,
        worker_cpu_limits=1,
        worker_memory_requests=2,
        worker_memory_limits=2,
    )

    cluster = Cluster(config)
    captured = capsys.readouterr()
    # Verify the warning message was printed
    assert "Please specify with namespace=<your_current_namespace>" in captured.out
    assert cluster.config.namespace is None


def test_component_resources_with_write_to_file(mocker):
    """Test _component_resources_up with write_to_file enabled"""
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        return_value=get_local_queue("kueue.x-k8s.io", "v1beta1", "ns", "localqueues"),
    )

    # Mock the _create_resources function
    mocker.patch("codeflare_sdk.ray.cluster.cluster._create_resources")

    # Create cluster with write_to_file=True
    config = ClusterConfiguration(
        name="test-cluster-component",
        namespace="ns",
        num_workers=1,
        worker_cpu_requests=1,
        worker_cpu_limits=1,
        worker_memory_requests=2,
        worker_memory_limits=2,
        write_to_file=True,
    )

    cluster = Cluster(config)

    # Mock file reading and test _component_resources_up

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write("apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: test")
        temp_file = f.name

    try:
        mock_api = MagicMock()
        cluster.resource_yaml = temp_file
        cluster._component_resources_up("ns", mock_api)
        # If we got here without error, the write_to_file path was executed
        assert True
    finally:
        os.unlink(temp_file)


def test_get_cluster_status_functions(mocker):
    """Test _ray_cluster_status functions"""
    from codeflare_sdk.ray.cluster.cluster import (
        _ray_cluster_status,
    )

    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch("codeflare_sdk.ray.cluster.cluster.config_check")

    # Test _ray_cluster_status when cluster not found
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        return_value={"items": []},
    )
    result = _ray_cluster_status("non-existent-cluster", "ns")
    assert result is None


def test_cluster_namespace_type_error(mocker):
    """Test TypeError when namespace is not a string"""
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        return_value=get_local_queue("kueue.x-k8s.io", "v1beta1", "ns", "localqueues"),
    )

    # Mock get_current_namespace to return a non-string value (e.g., int)
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster.get_current_namespace", return_value=12345
    )

    config = ClusterConfiguration(
        name="test-cluster-type-error",
        namespace=None,  # Will trigger namespace check
        num_workers=1,
        worker_cpu_requests=1,
        worker_cpu_limits=1,
        worker_memory_requests=2,
        worker_memory_limits=2,
    )

    # This should raise TypeError because get_current_namespace returns int
    with pytest.raises(
        TypeError,
        match="Namespace 12345 is of type.*Check your Kubernetes Authentication",
    ):
        Cluster(config)


def test_get_dashboard_url_from_httproute(mocker):
    """
    Test the HTTPRoute dashboard URL generation for RHOAI v3.0+
    """
    from codeflare_sdk.ray.cluster.cluster import _get_dashboard_url_from_httproute

    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")

    # Test successful HTTPRoute and Gateway lookup
    mock_httproute = {
        "metadata": {"name": "test-cluster", "namespace": "test-ns"},
        "spec": {
            "parentRefs": [
                {
                    "group": "gateway.networking.k8s.io",
                    "kind": "Gateway",
                    "name": "data-science-gateway",
                    "namespace": "openshift-ingress",
                }
            ]
        },
    }

    mock_gateway = {
        "metadata": {"name": "data-science-gateway", "namespace": "openshift-ingress"},
        "spec": {
            "listeners": [
                {
                    "name": "https",
                    "hostname": "data-science-gateway.apps.example.com",
                    "port": 443,
                    "protocol": "HTTPS",
                }
            ]
        },
    }

    # Mock list_cluster_custom_object to return HTTPRoute (cluster-wide search)
    def mock_list_cluster_custom_object(group, version, plural, label_selector):
        if plural == "httproutes":
            return {"items": [mock_httproute]}
        raise Exception("Unexpected plural")

    # Mock get_namespaced_custom_object to return Gateway
    def mock_get_namespaced_custom_object(group, version, namespace, plural, name):
        if plural == "gateways":
            return mock_gateway
        raise Exception("Unexpected plural")

    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_cluster_custom_object",
        side_effect=mock_list_cluster_custom_object,
    )
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.get_namespaced_custom_object",
        side_effect=mock_get_namespaced_custom_object,
    )

    # Test successful URL generation
    result = _get_dashboard_url_from_httproute("test-cluster", "test-ns")
    expected_url = (
        "https://data-science-gateway.apps.example.com/ray/test-ns/test-cluster"
    )
    assert result == expected_url, f"Expected {expected_url}, got {result}"

    # Test HTTPRoute not found - should return None
    def mock_list_cluster_empty(group, version, plural, label_selector):
        if plural == "httproutes":
            return {"items": []}
        raise Exception("Unexpected plural")

    def mock_list_namespaced_empty(group, version, namespace, plural, label_selector):
        if plural == "httproutes":
            return {"items": []}
        raise Exception("Unexpected plural")

    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_cluster_custom_object",
        side_effect=mock_list_cluster_empty,
    )
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        side_effect=mock_list_namespaced_empty,
    )

    result = _get_dashboard_url_from_httproute("nonexistent-cluster", "test-ns")
    assert result is None, "Should return None when HTTPRoute not found"

    # Test HTTPRoute with empty parentRefs - should return None
    mock_httproute_no_parents = {
        "metadata": {"name": "test-cluster", "namespace": "test-ns"},
        "spec": {"parentRefs": []},  # Empty parentRefs
    }

    def mock_list_cluster_no_parents(group, version, plural, label_selector):
        if plural == "httproutes":
            return {"items": [mock_httproute_no_parents]}
        raise Exception("Unexpected plural")

    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_cluster_custom_object",
        side_effect=mock_list_cluster_no_parents,
    )

    result = _get_dashboard_url_from_httproute("test-cluster", "test-ns")
    assert result is None, "Should return None when HTTPRoute has empty parentRefs"

    # Test HTTPRoute with missing gateway name - should return None
    mock_httproute_no_name = {
        "metadata": {"name": "test-cluster", "namespace": "test-ns"},
        "spec": {
            "parentRefs": [
                {
                    "group": "gateway.networking.k8s.io",
                    "kind": "Gateway",
                    # Missing "name" field
                    "namespace": "openshift-ingress",
                }
            ]
        },
    }

    def mock_list_cluster_no_name(group, version, plural, label_selector):
        if plural == "httproutes":
            return {"items": [mock_httproute_no_name]}
        raise Exception("Unexpected plural")

    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_cluster_custom_object",
        side_effect=mock_list_cluster_no_name,
    )

    result = _get_dashboard_url_from_httproute("test-cluster", "test-ns")
    assert result is None, "Should return None when gateway reference missing name"

    # Test HTTPRoute with missing gateway namespace - should return None
    mock_httproute_no_namespace = {
        "metadata": {"name": "test-cluster", "namespace": "test-ns"},
        "spec": {
            "parentRefs": [
                {
                    "group": "gateway.networking.k8s.io",
                    "kind": "Gateway",
                    "name": "data-science-gateway",
                    # Missing "namespace" field
                }
            ]
        },
    }

    def mock_list_cluster_no_namespace(group, version, plural, label_selector):
        if plural == "httproutes":
            return {"items": [mock_httproute_no_namespace]}
        raise Exception("Unexpected plural")

    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_cluster_custom_object",
        side_effect=mock_list_cluster_no_namespace,
    )

    result = _get_dashboard_url_from_httproute("test-cluster", "test-ns")
    assert result is None, "Should return None when gateway reference missing namespace"

    # Define valid HTTPRoute for reuse in subsequent tests
    mock_httproute_valid = {
        "metadata": {"name": "test-cluster", "namespace": "test-ns"},
        "spec": {
            "parentRefs": [
                {
                    "group": "gateway.networking.k8s.io",
                    "kind": "Gateway",
                    "name": "data-science-gateway",
                    "namespace": "openshift-ingress",
                }
            ]
        },
    }

    # Test Gateway with empty listeners - should try Route fallback, then return None
    mock_gateway_no_listeners = {
        "metadata": {"name": "data-science-gateway", "namespace": "openshift-ingress"},
        "spec": {"listeners": []},  # Empty listeners
    }

    def mock_gateway_no_listeners_fn(group, version, namespace, plural, name=None):
        if plural == "gateways":
            return mock_gateway_no_listeners
        raise Exception(f"Unexpected plural: {plural}")

    def mock_list_empty_routes(group, version, namespace, plural, label_selector=None):
        if plural == "httproutes":
            return {"items": [mock_httproute_valid]}
        elif plural == "routes":
            return {"items": []}  # No routes found
        raise Exception(f"Unexpected plural: {plural}")

    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_cluster_custom_object",
        side_effect=lambda g, v, p, label_selector: {"items": [mock_httproute_valid]},
    )
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.get_namespaced_custom_object",
        side_effect=mock_gateway_no_listeners_fn,
    )
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        side_effect=mock_list_empty_routes,
    )

    result = _get_dashboard_url_from_httproute("test-cluster", "test-ns")
    assert (
        result is None
    ), "Should return None when Gateway has empty listeners and no Route/addresses"

    # Test Gateway listener with missing hostname - should try OpenShift Route fallback
    mock_gateway_no_hostname = {
        "metadata": {"name": "data-science-gateway", "namespace": "openshift-ingress"},
        "spec": {
            "listeners": [
                {
                    "name": "https",
                    # Missing "hostname" field
                    "port": 443,
                    "protocol": "HTTPS",
                }
            ]
        },
    }

    # Test case: No OpenShift Route found, no valid status.addresses - should return None
    def mock_gateway_no_hostname_fn(group, version, namespace, plural, name=None):
        if plural == "gateways":
            return mock_gateway_no_hostname
        raise Exception(f"Unexpected plural: {plural}")

    def mock_list_no_routes(group, version, namespace, plural, label_selector=None):
        if plural == "httproutes":
            return {"items": [mock_httproute_valid]}
        elif plural == "routes":
            return {"items": []}  # No OpenShift Route found
        raise Exception(f"Unexpected plural: {plural}")

    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_cluster_custom_object",
        side_effect=lambda g, v, p, label_selector: {"items": [mock_httproute_valid]},
    )
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.get_namespaced_custom_object",
        side_effect=mock_gateway_no_hostname_fn,
    )
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        side_effect=mock_list_no_routes,
    )

    result = _get_dashboard_url_from_httproute("test-cluster", "test-ns")
    assert (
        result is None
    ), "Should return None when listener missing hostname and no Route/addresses found"

    # Test case: OpenShift Route found exposing the Gateway - should use Route hostname
    mock_openshift_route = {
        "metadata": {"name": "data-science-gateway", "namespace": "openshift-ingress"},
        "spec": {"host": "data-science-gateway.apps.example.com"},
    }

    def mock_list_with_route(group, version, namespace, plural, label_selector=None):
        if plural == "httproutes":
            return {"items": [mock_httproute_valid]}
        elif plural == "routes":
            return {"items": [mock_openshift_route]}
        raise Exception(f"Unexpected plural: {plural}")

    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        side_effect=mock_list_with_route,
    )

    result = _get_dashboard_url_from_httproute("test-cluster", "test-ns")
    expected_url = (
        "https://data-science-gateway.apps.example.com/ray/test-ns/test-cluster"
    )
    assert (
        result == expected_url
    ), f"Should use OpenShift Route hostname when listener missing hostname. Expected {expected_url}, got {result}"

    # Test case: No listener hostname, no Route, but valid status.addresses - should use address
    mock_gateway_with_address = {
        "metadata": {"name": "data-science-gateway", "namespace": "openshift-ingress"},
        "spec": {"listeners": [{"name": "https", "port": 443, "protocol": "HTTPS"}]},
        "status": {
            "addresses": [{"type": "Hostname", "value": "gateway.external.example.com"}]
        },
    }

    def mock_gateway_with_address_fn(group, version, namespace, plural, name=None):
        if plural == "gateways":
            return mock_gateway_with_address
        raise Exception(f"Unexpected plural: {plural}")

    mocker.patch(
        "kubernetes.client.CustomObjectsApi.get_namespaced_custom_object",
        side_effect=mock_gateway_with_address_fn,
    )
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        side_effect=mock_list_no_routes,
    )

    result = _get_dashboard_url_from_httproute("test-cluster", "test-ns")
    expected_url = "https://gateway.external.example.com/ray/test-ns/test-cluster"
    assert (
        result == expected_url
    ), f"Should use status.addresses when no listener hostname or Route. Expected {expected_url}, got {result}"

    # Test case: status.addresses with internal cluster DNS - should skip and return None
    mock_gateway_internal_address = {
        "metadata": {"name": "data-science-gateway", "namespace": "openshift-ingress"},
        "spec": {"listeners": [{"name": "https", "port": 443, "protocol": "HTTPS"}]},
        "status": {
            "addresses": [
                {
                    "type": "Hostname",
                    "value": "gateway.openshift-ingress.svc.cluster.local",
                }
            ]
        },
    }

    def mock_gateway_internal_address_fn(group, version, namespace, plural, name=None):
        if plural == "gateways":
            return mock_gateway_internal_address
        raise Exception(f"Unexpected plural: {plural}")

    mocker.patch(
        "kubernetes.client.CustomObjectsApi.get_namespaced_custom_object",
        side_effect=mock_gateway_internal_address_fn,
    )

    result = _get_dashboard_url_from_httproute("test-cluster", "test-ns")
    assert (
        result is None
    ), "Should return None when status.addresses contains only internal cluster DNS"

    # Test case: OpenShift Route lookup throws exception - should continue to status.addresses fallback
    mock_gateway_no_hostname_with_address = {
        "metadata": {"name": "data-science-gateway", "namespace": "openshift-ingress"},
        "spec": {"listeners": [{"name": "https", "port": 443, "protocol": "HTTPS"}]},
        "status": {
            "addresses": [{"type": "Hostname", "value": "gateway.fallback.example.com"}]
        },
    }

    def mock_gateway_for_route_exception(group, version, namespace, plural, name=None):
        if plural == "gateways":
            return mock_gateway_no_hostname_with_address
        raise Exception(f"Unexpected plural: {plural}")

    def mock_list_routes_exception(
        group, version, namespace, plural, label_selector=None
    ):
        if plural == "httproutes":
            return {"items": [mock_httproute_valid]}
        elif plural == "routes":
            raise Exception("Simulated route lookup failure")
        raise Exception(f"Unexpected plural: {plural}")

    mocker.patch(
        "kubernetes.client.CustomObjectsApi.get_namespaced_custom_object",
        side_effect=mock_gateway_for_route_exception,
    )
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        side_effect=mock_list_routes_exception,
    )

    result = _get_dashboard_url_from_httproute("test-cluster", "test-ns")
    expected_url = "https://gateway.fallback.example.com/ray/test-ns/test-cluster"
    assert (
        result == expected_url
    ), f"Should fallback to status.addresses when Route lookup fails. Expected {expected_url}, got {result}"

    # Test non-404 ApiException - should be re-raised then caught by outer handler
    # The function is designed to return None for any unexpected errors via outer try-catch
    def mock_403_error(group, version, namespace, plural, name):
        error = client.exceptions.ApiException(status=403)
        error.status = 403
        raise error

    mocker.patch(
        "kubernetes.client.CustomObjectsApi.get_namespaced_custom_object",
        side_effect=mock_403_error,
    )

    # Should return None (the inner handler re-raises, outer handler catches and returns None)
    result = _get_dashboard_url_from_httproute("test-cluster", "test-ns")
    assert (
        result is None
    ), "Should return None when non-404 exception occurs (caught by outer handler)"

    # Real-world scenario: Cluster-wide permissions denied, falls back to namespace search
    # This simulates a regular data scientist without cluster-admin permissions
    # The cluster's own namespace should be searched FIRST, then platform namespaces
    namespaces_searched = []

    def mock_list_cluster_permission_denied(group, version, plural, label_selector):
        # Simulate permission denied for cluster-wide search
        error = client.exceptions.ApiException(status=403)
        error.status = 403
        raise error

    def mock_list_namespaced_track(group, version, namespace, plural, label_selector):
        namespaces_searched.append(namespace)
        # HTTPRoute found in opendatahub namespace
        if plural == "httproutes":
            if namespace == "opendatahub":
                return {"items": [mock_httproute]}
            return {"items": []}
        return {"items": []}

    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_cluster_custom_object",
        side_effect=mock_list_cluster_permission_denied,
    )
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        side_effect=mock_list_namespaced_track,
    )
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.get_namespaced_custom_object",
        side_effect=mock_get_namespaced_custom_object,
    )

    result = _get_dashboard_url_from_httproute("test-cluster", "test-ns")
    expected_url = (
        "https://data-science-gateway.apps.example.com/ray/test-ns/test-cluster"
    )
    assert result == expected_url, f"Expected {expected_url}, got {result}"
    # Verify cluster's own namespace is searched first
    assert (
        namespaces_searched[0] == "test-ns"
    ), f"Cluster's own namespace should be searched first, but got: {namespaces_searched}"
    assert (
        "redhat-ods-applications" in namespaces_searched
    ), "Should search redhat-ods-applications namespace"
    assert "opendatahub" in namespaces_searched, "Should search opendatahub namespace"

    # Test case: HTTPRoute found in cluster's own namespace
    namespaces_searched.clear()

    def mock_list_namespaced_own_ns(group, version, namespace, plural, label_selector):
        namespaces_searched.append(namespace)
        if plural == "httproutes":
            # HTTPRoute found in cluster's own namespace
            if namespace == "test-ns":
                return {"items": [mock_httproute]}
            return {"items": []}
        return {"items": []}

    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        side_effect=mock_list_namespaced_own_ns,
    )

    result = _get_dashboard_url_from_httproute("test-cluster", "test-ns")
    assert result == expected_url, f"Expected {expected_url}, got {result}"
    # Should find HTTPRoute in first namespace searched (cluster's own)
    assert namespaces_searched == [
        "test-ns"
    ], f"Should stop after finding HTTPRoute in cluster's own namespace, but searched: {namespaces_searched}"

    # Test case: Some namespaces fail with ApiException, but search continues
    namespaces_searched.clear()

    def mock_list_namespaced_with_api_exception(
        group, version, namespace, plural, label_selector
    ):
        namespaces_searched.append(namespace)
        if plural == "httproutes":
            # First namespace fails with ApiException
            if namespace == "test-ns":
                error = client.exceptions.ApiException(status=403)
                error.status = 403
                raise error
            # Second namespace also fails
            if namespace == "redhat-ods-applications":
                error = client.exceptions.ApiException(status=404)
                error.status = 404
                raise error
            # HTTPRoute found in opendatahub namespace
            if namespace == "opendatahub":
                return {"items": [mock_httproute]}
            return {"items": []}
        return {"items": []}

    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        side_effect=mock_list_namespaced_with_api_exception,
    )

    result = _get_dashboard_url_from_httproute("test-cluster", "test-ns")
    assert result == expected_url, f"Expected {expected_url}, got {result}"
    # Verify that search continued despite ApiExceptions
    assert "test-ns" in namespaces_searched, "Should try cluster's own namespace first"
    assert (
        "redhat-ods-applications" in namespaces_searched
    ), "Should try redhat-ods-applications despite earlier failure"
    assert "opendatahub" in namespaces_searched, "Should find HTTPRoute in opendatahub"

    # Real-world scenario: Gateway not found (404) - should return None
    # This can happen if Gateway was deleted but HTTPRoute still exists
    def mock_list_cluster_with_httproute(group, version, plural, label_selector):
        if plural == "httproutes":
            return {"items": [mock_httproute]}
        raise Exception("Unexpected plural")

    def mock_get_gateway_404(group, version, namespace, plural, name):
        if plural == "gateways":
            error = client.exceptions.ApiException(status=404)
            error.status = 404
            raise error
        raise Exception("Unexpected plural")

    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_cluster_custom_object",
        side_effect=mock_list_cluster_with_httproute,
    )
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.get_namespaced_custom_object",
        side_effect=mock_get_gateway_404,
    )

    result = _get_dashboard_url_from_httproute("test-cluster", "test-ns")
    assert result is None, "Should return None when Gateway not found (404)"


def test_cluster_dashboard_uri_httproute_first(mocker):
    """
    Test that cluster_dashboard_uri() tries HTTPRoute first, then falls back to OpenShift Routes
    """
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        return_value=get_local_queue("kueue.x-k8s.io", "v1beta1", "ns", "localqueues"),
    )

    # Test 1: HTTPRoute exists - should return HTTPRoute URL
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster._is_openshift_cluster", return_value=True
    )

    httproute_url = (
        "https://data-science-gateway.apps.example.com/ray/ns/unit-test-cluster"
    )
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster._get_dashboard_url_from_httproute",
        return_value=httproute_url,
    )

    cluster = create_cluster(mocker)
    result = cluster.cluster_dashboard_uri()
    assert result == httproute_url, "Should return HTTPRoute URL when available"

    # Test 2: HTTPRoute not found - should fall back to OpenShift Route
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster._get_dashboard_url_from_httproute",
        return_value=None,
    )
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        return_value={
            "items": [
                {
                    "metadata": {"name": "ray-dashboard-unit-test-cluster"},
                    "spec": {
                        "host": "ray-dashboard-unit-test-cluster-ns.apps.cluster.awsroute.org",
                        "tls": {"termination": "passthrough"},
                    },
                }
            ]
        },
    )

    cluster = create_cluster(mocker)
    result = cluster.cluster_dashboard_uri()
    expected = "https://ray-dashboard-unit-test-cluster-ns.apps.cluster.awsroute.org"
    assert (
        result == expected
    ), f"Should fall back to OpenShift Route. Expected {expected}, got {result}"


def test_map_to_ray_cluster_httproute(mocker):
    """
    Test that _map_to_ray_cluster() uses HTTPRoute-first logic
    """
    from codeflare_sdk.ray.cluster.cluster import _map_to_ray_cluster

    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster._is_openshift_cluster", return_value=True
    )

    # Test with HTTPRoute available
    httproute_url = (
        "https://data-science-gateway.apps.example.com/ray/ns/test-cluster-a"
    )
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster._get_dashboard_url_from_httproute",
        return_value=httproute_url,
    )

    rc = get_ray_obj("ray.io", "v1", "ns", "rayclusters")["items"][0]
    result = _map_to_ray_cluster(rc)

    assert (
        result.dashboard == httproute_url
    ), f"Expected HTTPRoute URL, got {result.dashboard}"

    # Test with HTTPRoute not available - should fall back to OpenShift Route
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster._get_dashboard_url_from_httproute",
        return_value=None,
    )
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        return_value={
            "items": [
                {
                    "kind": "Route",
                    "metadata": {
                        "name": "ray-dashboard-test-cluster-a",
                        "namespace": "ns",
                    },
                    "spec": {"host": "ray-dashboard-test-cluster-a.apps.example.com"},
                }
            ]
        },
    )

    rc = get_ray_obj("ray.io", "v1", "ns", "rayclusters")["items"][0]
    result = _map_to_ray_cluster(rc)

    expected_fallback = "http://ray-dashboard-test-cluster-a.apps.example.com"
    assert (
        result.dashboard == expected_fallback
    ), f"Expected OpenShift Route fallback URL, got {result.dashboard}"


def test_check_tls_certs_exist_warning(mocker, capsys, tmp_path):
    """Test that _check_tls_certs_exist prints warning when certificates don't exist"""
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        return_value=get_local_queue("kueue.x-k8s.io", "v1beta1", "ns", "localqueues"),
    )

    # Mock _get_tls_base_dir to return a temp directory where certs don't exist
    mocker.patch(
        "codeflare_sdk.common.utils.generate_cert._get_tls_base_dir",
        return_value=tmp_path,
    )

    cluster = create_cluster(mocker)
    cluster._check_tls_certs_exist()

    captured = capsys.readouterr()
    assert "WARNING: TLS Certificates Not Found!" in captured.out
    assert "TLS certificates are required for mTLS connections" in captured.out
    assert "cluster.wait_ready()" in captured.out


def test_check_tls_certs_exist_no_warning(mocker, capsys, tmp_path):
    """Test that _check_tls_certs_exist does not print warning when certificates exist"""
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        return_value=get_local_queue("kueue.x-k8s.io", "v1beta1", "ns", "localqueues"),
    )

    # Create the certificate directory and files
    cert_dir = tmp_path / "unit-test-cluster-ns"
    cert_dir.mkdir(parents=True)
    (cert_dir / "tls.crt").write_text("fake cert")
    (cert_dir / "tls.key").write_text("fake key")
    (cert_dir / "ca.crt").write_text("fake ca")

    # Mock _get_tls_base_dir to return our temp directory
    mocker.patch(
        "codeflare_sdk.common.utils.generate_cert._get_tls_base_dir",
        return_value=tmp_path,
    )

    cluster = create_cluster(mocker)
    cluster._check_tls_certs_exist()

    captured = capsys.readouterr()
    assert "WARNING: TLS Certificates Not Found!" not in captured.out


def test_refresh_certificates(mocker, capsys):
    """Test the refresh_certificates method"""
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        return_value=get_local_queue("kueue.x-k8s.io", "v1beta1", "ns", "localqueues"),
    )

    # Mock the certificate functions
    mock_refresh = mocker.patch(
        "codeflare_sdk.common.utils.generate_cert.refresh_tls_cert"
    )
    mock_export = mocker.patch("codeflare_sdk.common.utils.generate_cert.export_env")

    cluster = create_cluster(mocker)
    cluster.refresh_certificates()

    # Verify the refresh and export functions were called with correct args
    mock_refresh.assert_called_once_with("unit-test-cluster", "ns")
    mock_export.assert_called_once_with("unit-test-cluster", "ns")

    captured = capsys.readouterr()
    assert "Refreshing TLS certificates for 'unit-test-cluster'" in captured.out
    assert "TLS certificates refreshed for 'unit-test-cluster'" in captured.out


def test_ca_secret_exists_true(mocker):
    """Test _ca_secret_exists returns True when CA secret is found"""
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        return_value=get_local_queue("kueue.x-k8s.io", "v1beta1", "ns", "localqueues"),
    )

    # Mock list_namespaced_secret to return a matching CA secret
    mock_secret = mocker.MagicMock()
    mock_secret.metadata.name = "unit-test-cluster-ca-secret-abc123"
    mock_secrets = mocker.MagicMock()
    mock_secrets.items = [mock_secret]
    mocker.patch(
        "kubernetes.client.CoreV1Api.list_namespaced_secret",
        return_value=mock_secrets,
    )

    cluster = create_cluster(mocker)
    result = cluster._ca_secret_exists()
    assert result is True


def test_ca_secret_exists_false(mocker):
    """Test _ca_secret_exists returns False when no CA secret is found"""
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        return_value=get_local_queue("kueue.x-k8s.io", "v1beta1", "ns", "localqueues"),
    )

    # Mock list_namespaced_secret to return empty list
    mock_secrets = mocker.MagicMock()
    mock_secrets.items = []
    mocker.patch(
        "kubernetes.client.CoreV1Api.list_namespaced_secret",
        return_value=mock_secrets,
    )

    cluster = create_cluster(mocker)
    result = cluster._ca_secret_exists()
    assert result is False


def test_ca_secret_exists_exception(mocker):
    """Test _ca_secret_exists returns False on exception"""
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        return_value=get_local_queue("kueue.x-k8s.io", "v1beta1", "ns", "localqueues"),
    )

    # Mock list_namespaced_secret to raise exception
    mocker.patch(
        "kubernetes.client.CoreV1Api.list_namespaced_secret",
        side_effect=Exception("API error"),
    )

    cluster = create_cluster(mocker)
    result = cluster._ca_secret_exists()
    assert result is False


def test_up_method(mocker, capsys):
    """Test the deprecated up() method"""
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch("codeflare_sdk.ray.cluster.cluster.Cluster._throw_for_no_raycluster")
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        return_value=get_local_queue("kueue.x-k8s.io", "v1beta1", "ns", "localqueues"),
    )
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.create_namespaced_custom_object",
        return_value={},
    )

    cluster = create_cluster(mocker)
    cluster.up()

    captured = capsys.readouterr()
    assert "WARNING: The up() function is planned for deprecation" in captured.out
    assert (
        "Ray Cluster: 'unit-test-cluster' has successfully been created" in captured.out
    )


def test_apply_generates_tls_certs(mocker, capsys):
    """Test that apply() generates TLS certificates after applying cluster resources"""
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch("codeflare_sdk.ray.cluster.cluster.Cluster._throw_for_no_raycluster")
    mocker.patch("codeflare_sdk.ray.cluster.cluster.Cluster.get_dynamic_client")
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        return_value=get_local_queue("kueue.x-k8s.io", "v1beta1", "ns", "localqueues"),
    )
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_cluster_custom_object",
        return_value={"items": []},
    )

    # Mock _ca_secret_exists to return True (secret is ready)
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster.Cluster._ca_secret_exists",
        return_value=True,
    )

    # Mock the certificate generation functions
    mock_generate = mocker.patch(
        "codeflare_sdk.common.utils.generate_cert.generate_tls_cert"
    )
    mock_export = mocker.patch("codeflare_sdk.common.utils.generate_cert.export_env")

    cluster = create_cluster(mocker)
    cluster.apply()  # TLS certs are always generated

    # Verify certificate generation was called
    mock_generate.assert_called_once_with("unit-test-cluster", "ns")
    mock_export.assert_called_once_with("unit-test-cluster", "ns")

    captured = capsys.readouterr()
    assert "Waiting for client TLS configuration to be available" in captured.out
    assert "Client TLS configuration ready" in captured.out
    assert "Cluster 'unit-test-cluster' is ready" in captured.out


def test_apply_timeout(mocker, capsys):
    """Test that apply() handles timeout gracefully when CA secret is not ready"""
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch("codeflare_sdk.ray.cluster.cluster.Cluster._throw_for_no_raycluster")
    mocker.patch("codeflare_sdk.ray.cluster.cluster.Cluster.get_dynamic_client")
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        return_value=get_local_queue("kueue.x-k8s.io", "v1beta1", "ns", "localqueues"),
    )
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_cluster_custom_object",
        return_value={"items": []},
    )

    # Mock _ca_secret_exists to always return False (CA secret never becomes ready)
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster.Cluster._ca_secret_exists",
        return_value=False,
    )

    cluster = create_cluster(mocker)
    # Use a very short timeout to trigger timeout quickly
    cluster.apply(timeout=1)

    captured = capsys.readouterr()
    assert "Waiting for client TLS configuration to be available" in captured.out
    assert "Timed out after 1s waiting for TLS configuration" in captured.out
    assert "TLS setup incomplete" in captured.out


def test_apply_tls_generation_failure(mocker, capsys):
    """Test that apply() handles TLS generation errors gracefully"""
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch("codeflare_sdk.ray.cluster.cluster.Cluster._throw_for_no_raycluster")
    mocker.patch("codeflare_sdk.ray.cluster.cluster.Cluster.get_dynamic_client")
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        return_value=get_local_queue("kueue.x-k8s.io", "v1beta1", "ns", "localqueues"),
    )
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_cluster_custom_object",
        return_value={"items": []},
    )

    # Mock _ca_secret_exists to return True (secret is ready)
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster.Cluster._ca_secret_exists",
        return_value=True,
    )

    # Mock certificate generation to fail
    mocker.patch(
        "codeflare_sdk.common.utils.generate_cert.generate_tls_cert",
        side_effect=Exception("Kubernetes connection failed"),
    )

    cluster = create_cluster(mocker)
    cluster.apply()

    captured = capsys.readouterr()
    assert "Warning: Could not generate TLS certificates" in captured.out
    assert "Kubernetes connection failed" in captured.out
    assert "TLS setup incomplete" in captured.out


def test_wait_ready_tls_cert_generation_failure(mocker, capsys):
    """Test that wait_ready handles TLS certificate generation failures gracefully"""
    from codeflare_sdk.ray.cluster.status import CodeFlareClusterStatus

    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster._ray_cluster_status", return_value=None
    )
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster.Cluster.status",
        return_value=(CodeFlareClusterStatus.READY, True),
    )
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster.Cluster.is_dashboard_ready",
        return_value=True,
    )
    # Mock Kubernetes API for cluster initialization (local queue lookup)
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        return_value=get_local_queue("kueue.x-k8s.io", "v1beta1", "ns", "localqueues"),
    )

    # Mock certificate generation to raise an exception
    mocker.patch(
        "codeflare_sdk.common.utils.generate_cert.generate_tls_cert",
        side_effect=Exception("Failed to connect to Kubernetes"),
    )

    cf = Cluster(
        ClusterConfiguration(
            name="test-tls-failure",
            namespace="ns",
            write_to_file=False,
        )
    )

    # This should not raise - TLS failures are handled gracefully
    cf.wait_ready(dashboard_check=False)

    captured = capsys.readouterr()
    assert "Requested cluster is up and running!" in captured.out
    assert "Warning: Could not generate TLS certificates" in captured.out
    assert "Failed to connect to Kubernetes" in captured.out
    assert "manually generate certificates" in captured.out


def test_local_client_url_calls_tls_check(mocker, capsys, tmp_path):
    """Test that local_client_url calls _check_tls_certs_exist"""
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster._get_ingress_domain",
        return_value="rayclient-test.apps.example.com",
    )
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        return_value=get_local_queue("kueue.x-k8s.io", "v1beta1", "ns", "localqueues"),
    )

    # Mock _get_tls_base_dir to return a temp directory where certs don't exist
    mocker.patch(
        "codeflare_sdk.common.utils.generate_cert._get_tls_base_dir",
        return_value=tmp_path,
    )

    cluster = create_cluster(mocker)
    url = cluster.local_client_url()

    # Verify the URL is correct
    assert url == "ray://rayclient-test.apps.example.com"

    # Verify the TLS warning was printed (since certs don't exist)
    captured = capsys.readouterr()
    assert "WARNING: TLS Certificates Not Found!" in captured.out


def test_cluster_uri_calls_tls_check(mocker, capsys, tmp_path):
    """Test that cluster_uri calls _check_tls_certs_exist"""
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        return_value=get_local_queue("kueue.x-k8s.io", "v1beta1", "ns", "localqueues"),
    )

    # Mock _get_tls_base_dir to return a temp directory where certs don't exist
    mocker.patch(
        "codeflare_sdk.common.utils.generate_cert._get_tls_base_dir",
        return_value=tmp_path,
    )

    cluster = create_cluster(mocker)
    uri = cluster.cluster_uri()

    # Verify the URI is correct
    assert uri == "ray://unit-test-cluster-head-svc.ns.svc:10001"

    # Verify the TLS warning was printed (since certs don't exist)
    captured = capsys.readouterr()
    assert "WARNING: TLS Certificates Not Found!" in captured.out


def test_job_client_calls_tls_check(mocker, capsys, tmp_path):
    """Test that job_client property calls _check_tls_certs_exist"""
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        return_value=get_local_queue("kueue.x-k8s.io", "v1beta1", "ns", "localqueues"),
    )
    mocker.patch(
        "kubernetes.client.NetworkingV1Api.list_namespaced_ingress",
        return_value=ingress_retrieval(),
    )
    mocker.patch(
        "ray.job_submission.JobSubmissionClient._check_connection_and_version_with_url",
        return_value="None",
    )

    # Mock _get_tls_base_dir to return a temp directory where certs don't exist
    mocker.patch(
        "codeflare_sdk.common.utils.generate_cert._get_tls_base_dir",
        return_value=tmp_path,
    )

    cluster = create_cluster(mocker)
    # Access job_client property
    _ = cluster.job_client

    # Verify the TLS warning was printed (since certs don't exist)
    captured = capsys.readouterr()
    assert "WARNING: TLS Certificates Not Found!" in captured.out


def test_list_jobs(mocker):
    """Test list_jobs method"""
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        return_value=get_local_queue("kueue.x-k8s.io", "v1beta1", "ns", "localqueues"),
    )

    mock_job_client = mocker.MagicMock()
    mock_job_client.list_jobs.return_value = ["job1", "job2"]

    cluster = create_cluster(mocker)
    cluster._job_submission_client = mock_job_client

    jobs = cluster.list_jobs()
    assert jobs == ["job1", "job2"]
    mock_job_client.list_jobs.assert_called_once()


def test_job_status(mocker):
    """Test job_status method"""
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        return_value=get_local_queue("kueue.x-k8s.io", "v1beta1", "ns", "localqueues"),
    )

    mock_job_client = mocker.MagicMock()
    mock_job_client.get_job_status.return_value = "RUNNING"

    cluster = create_cluster(mocker)
    cluster._job_submission_client = mock_job_client

    status = cluster.job_status("job-123")
    assert status == "RUNNING"
    mock_job_client.get_job_status.assert_called_once_with("job-123")


def test_job_logs(mocker):
    """Test job_logs method"""
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        return_value=get_local_queue("kueue.x-k8s.io", "v1beta1", "ns", "localqueues"),
    )

    mock_job_client = mocker.MagicMock()
    mock_job_client.get_job_logs.return_value = "Job output logs here"

    cluster = create_cluster(mocker)
    cluster._job_submission_client = mock_job_client

    logs = cluster.job_logs("job-123")
    assert logs == "Job output logs here"
    mock_job_client.get_job_logs.assert_called_once_with("job-123")


# Make sure to always keep this function last
def test_cleanup():
    # Clean up test files if they exist
    # Using try-except to handle cases where files weren't created (e.g., when running full test suite)
    try:
        os.remove(f"{cluster_dir}test-all-params.yaml")
    except FileNotFoundError:
        pass  # File doesn't exist, nothing to clean up

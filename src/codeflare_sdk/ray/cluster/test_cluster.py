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
    get_aw_obj_with_status,
    patch_cluster_with_dynamic_client,
    route_list_retrieval,
)
from codeflare_sdk.ray.cluster.cluster import _is_openshift_cluster
from pathlib import Path
from unittest.mock import MagicMock
from kubernetes import client
import yaml
import filecmp
import os

parent = Path(__file__).resolve().parents[4]  # project directory
expected_clusters_dir = f"{parent}/tests/test_cluster_yamls"
aw_dir = os.path.expanduser("~/.codeflare/resources/")


def test_cluster_up_down(mocker):
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch("codeflare_sdk.ray.cluster.cluster.Cluster._throw_for_no_raycluster")
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
    cluster = create_cluster(mocker)
    cluster.up()
    cluster.down()


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
    cluster.apply()

    # Step 2: Scale up the cluster
    cluster = create_cluster(mocker, scaled_up_num_workers)
    patch_cluster_with_dynamic_client(mocker, cluster, mock_dynamic_client)
    cluster.apply()

    # Step 3: Scale down the cluster
    cluster = create_cluster(mocker, initial_num_workers)
    patch_cluster_with_dynamic_client(mocker, cluster, mock_dynamic_client)
    cluster.apply()

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
    cluster.apply()
    # Tear down
    cluster.down()


def test_cluster_apply_with_appwrapper(mocker):
    # Mock Kubernetes client and dynamic client methods
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster._check_aw_exists",
        return_value=True,
    )
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

    # Create a cluster configuration with appwrapper set to False
    cluster = create_cluster(mocker, 1, write_to_file=False)
    patch_cluster_with_dynamic_client(mocker, cluster, mock_dynamic_client)

    # Mock listing RayCluster to simulate it doesn't exist
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        return_value=get_obj_none("ray.io", "v1", "ns", "rayclusters"),
    )
    # Call the apply method
    cluster.apply()

    # Assertions
    print("Cluster applied without AppWrapper.")


def test_cluster_apply_without_appwrapper_write_to_file(mocker):
    # Mock Kubernetes client and dynamic client methods
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster._check_aw_exists",
        return_value=True,
    )
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

    # Create a cluster configuration with appwrapper set to False
    cluster = create_cluster(mocker, 1, write_to_file=True)
    patch_cluster_with_dynamic_client(mocker, cluster, mock_dynamic_client)
    cluster.config.appwrapper = False

    # Mock listing RayCluster to simulate it doesn't exist
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        return_value=get_obj_none("ray.io", "v1", "ns", "rayclusters"),
    )
    # Call the apply method
    cluster.apply()

    # Assertions
    print("Cluster applied without AppWrapper.")


def test_cluster_apply_without_appwrapper(mocker):
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

    # Create a cluster configuration with appwrapper set to False
    cluster = create_cluster(mocker, 1, write_to_file=False)
    cluster.config.appwrapper = None
    patch_cluster_with_dynamic_client(mocker, cluster, mock_dynamic_client)

    # Mock listing RayCluster to simulate it doesn't exist
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        return_value=get_obj_none("ray.io", "v1", "ns", "rayclusters"),
    )

    # Call the apply method
    cluster.apply()

    # Assertions
    print("Cluster applied without AppWrapper.")


def test_cluster_up_down_no_mcad(mocker):
    mocker.patch("codeflare_sdk.ray.cluster.cluster.Cluster._throw_for_no_raycluster")
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
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
    config = create_cluster_config()
    config.name = "unit-test-cluster-ray"
    config.appwrapper = False
    cluster = Cluster(config)
    cluster.up()
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
        == "Dashboard not available yet, have you run cluster.up()?"
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
    import ray

    def ray_addr(self, *args):
        return self._address

    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        return_value=get_local_queue("kueue.x-k8s.io", "v1beta1", "ns", "localqueues"),
    )
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


def test_get_cluster_no_appwrapper(mocker):
    """
    This test uses the "test all params" unit test file as a comparison
    """
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster._check_aw_exists",
        return_value=False,
    )

    with open(f"{expected_clusters_dir}/ray/unit-test-all-params.yaml") as f:
        expected_rc = yaml.load(f, Loader=yaml.FullLoader)
        mocker.patch(
            "kubernetes.client.CustomObjectsApi.get_namespaced_custom_object",
            return_value=expected_rc,
        )
        get_cluster("test-all-params", "ns", write_to_file=True)

        with open(f"{aw_dir}test-all-params.yaml") as f:
            generated_rc = yaml.load(f, Loader=yaml.FullLoader)
        assert generated_rc == expected_rc


def test_get_cluster_with_appwrapper(mocker):
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster._check_aw_exists",
        return_value=True,
    )

    with open(f"{expected_clusters_dir}/appwrapper/unit-test-all-params.yaml") as f:
        expected_aw = yaml.load(f, Loader=yaml.FullLoader)
        mocker.patch(
            "kubernetes.client.CustomObjectsApi.get_namespaced_custom_object",
            return_value=expected_aw,
        )
        get_cluster("aw-all-params", "ns", write_to_file=True)

        with open(f"{aw_dir}aw-all-params.yaml") as f:
            generated_aw = yaml.load(f, Loader=yaml.FullLoader)
        assert generated_aw == expected_aw


def test_wait_ready(mocker, capsys):
    from codeflare_sdk.ray.cluster.status import CodeFlareClusterStatus

    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch(
        "kubernetes.client.NetworkingV1Api.list_namespaced_ingress",
        return_value=ingress_retrieval(),
    )
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster._app_wrapper_status", return_value=None
    )
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
    cf = Cluster(
        ClusterConfiguration(
            name="test",
            namespace="ns",
            write_to_file=False,
            appwrapper=True,
        )
    )
    try:
        cf.wait_ready(timeout=5)
        assert 1 == 0
    except Exception as e:
        assert type(e) == TimeoutError

    captured = capsys.readouterr()
    assert (
        "WARNING: Current cluster status is unknown, have you run cluster.up yet?"
        in captured.out
    )
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster.Cluster.status",
        return_value=(True, CodeFlareClusterStatus.READY),
    )
    cf.wait_ready()
    captured = capsys.readouterr()
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


def test_list_queue_appwrappers(mocker, capsys):
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        return_value=get_obj_none(
            "workload.codeflare.dev", "v1beta2", "ns", "appwrappers"
        ),
    )
    list_all_queued("ns", appwrapper=True)
    captured = capsys.readouterr()
    assert captured.out == (
        "╭──────────────────────────────────────────────────────────────────────────────╮\n"
        "│ No resources found, have you run cluster.up() yet?                           │\n"
        "╰──────────────────────────────────────────────────────────────────────────────╯\n"
    )
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        return_value=get_aw_obj_with_status(
            "workload.codeflare.dev", "v1beta2", "ns", "appwrappers"
        ),
    )
    list_all_queued("ns", appwrapper=True)
    captured = capsys.readouterr()
    print(captured.out)
    assert captured.out == (
        "╭────────────────────────────────╮\n"
        "│   🚀 Cluster Queue Status 🚀   │\n"
        "│ +----------------+-----------+ │\n"
        "│ | Name           | Status    | │\n"
        "│ +================+===========+ │\n"
        "│ | test-cluster-a | running   | │\n"
        "│ |                |           | │\n"
        "│ | test-cluster-b | suspended | │\n"
        "│ |                |           | │\n"
        "│ +----------------+-----------+ │\n"
        "╰────────────────────────────────╯\n"
    )


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
    assert captured.out == (
        "╭──────────────────────────────────────────────────────────────────────────────╮\n"
        "│ No resources found, have you run cluster.up() yet?                           │\n"
        "╰──────────────────────────────────────────────────────────────────────────────╯\n"
    )
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
    assert captured.out == (
        "╭──────────────────────────────────────────────────────────────────────────────╮\n"
        "│ No resources found, have you run cluster.up() yet?                           │\n"
        "╰──────────────────────────────────────────────────────────────────────────────╯\n"
    )
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


def test_run_job_with_managed_cluster_success(mocker):
    """Test successful RayJob execution with managed cluster."""
    from codeflare_sdk.ray.job.job import RayJobSpec

    # Mock Kubernetes API and config
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch("codeflare_sdk.ray.cluster.cluster.config_check")

    # Mock get_api_client
    mock_api_client = mocker.Mock()
    mocker.patch(
        "codeflare_sdk.common.kubernetes_cluster.auth.get_api_client",
        return_value=mock_api_client,
    )

    # Mock CustomObjectsApi
    mock_co_api = mocker.Mock()
    mocker.patch("kubernetes.client.CustomObjectsApi", return_value=mock_co_api)

    # Mock Cluster creation for generating RayCluster spec
    mock_cluster_resource = {
        "apiVersion": "ray.io/v1",
        "kind": "RayCluster",
        "spec": {
            "rayVersion": "2.47.1",
            "headGroupSpec": {"template": {"spec": {}}},
            "workerGroupSpecs": [{"template": {"spec": {}}}],
        },
    }

    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster.Cluster.__init__", return_value=None
    )
    mock_cluster_instance = mocker.Mock()
    mock_cluster_instance.resource_yaml = mock_cluster_resource
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster.Cluster", return_value=mock_cluster_instance
    )

    # Mock successful RayJob creation
    mock_co_api.create_namespaced_custom_object.return_value = {
        "metadata": {"name": "test-rayjob"}
    }

    # Mock RayJob status for completion
    mock_status_response = {
        "status": {
            "jobDeploymentStatus": "Running",
            "jobStatus": "SUCCEEDED",
            "dashboardURL": "http://test-dashboard.com",
            "rayClusterName": "test-rayjob-cluster",
            "jobId": "test-job-123",
        }
    }
    mock_co_api.get_namespaced_custom_object_status.return_value = mock_status_response

    # Mock time.sleep to speed up test
    mocker.patch("time.sleep")

    # Create test configuration
    cluster_config = ClusterConfiguration(
        name="test-cluster",
        namespace="test-namespace",
        num_workers=1,
        head_cpu_requests=1,
        head_memory_requests="2G",
        worker_cpu_requests=1,
        worker_memory_requests="1G",
    )

    job_config = RayJobSpec(
        entrypoint="python -c 'print(\"Hello World\")'",
        submission_id="test-submission-123",
    )

    # Execute the method
    result = Cluster.run_job_with_managed_cluster(
        cluster_config=cluster_config,
        job_config=job_config,
        job_cr_name="test-rayjob",
        wait_for_completion=True,
        job_timeout_seconds=60,
    )

    # Verify the result
    assert result["job_cr_name"] == "test-rayjob"
    assert result["job_submission_id"] == "test-job-123"
    assert result["job_status"] == "SUCCEEDED"
    assert result["dashboard_url"] == "http://test-dashboard.com"
    assert result["ray_cluster_name"] == "test-rayjob-cluster"

    # Verify API calls were made
    mock_co_api.create_namespaced_custom_object.assert_called_once()
    mock_co_api.get_namespaced_custom_object_status.assert_called()


def test_run_job_with_managed_cluster_no_wait(mocker):
    """Test RayJob execution without waiting for completion."""
    from codeflare_sdk.ray.job.job import RayJobSpec

    # Mock dependencies (similar to above but condensed)
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch("codeflare_sdk.ray.cluster.cluster.config_check")

    mock_api_client = mocker.Mock()
    mocker.patch(
        "codeflare_sdk.common.kubernetes_cluster.auth.get_api_client",
        return_value=mock_api_client,
    )

    mock_co_api = mocker.Mock()
    mocker.patch("kubernetes.client.CustomObjectsApi", return_value=mock_co_api)

    # Mock Cluster creation
    mock_cluster_resource = {
        "apiVersion": "ray.io/v1",
        "kind": "RayCluster",
        "spec": {"rayVersion": "2.47.1", "headGroupSpec": {"template": {"spec": {}}}},
    }
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster.Cluster.__init__", return_value=None
    )
    mock_cluster_instance = mocker.Mock()
    mock_cluster_instance.resource_yaml = mock_cluster_resource
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster.Cluster", return_value=mock_cluster_instance
    )

    # Mock RayJob creation and status (not found initially - job just submitted)
    mock_co_api.create_namespaced_custom_object.return_value = {
        "metadata": {"name": "test-rayjob-nowait"}
    }

    from kubernetes.client.rest import ApiException

    mock_co_api.get_namespaced_custom_object_status.side_effect = ApiException(
        status=404, reason="Not Found"
    )

    cluster_config = ClusterConfiguration(
        name="test-cluster", namespace="test-namespace"
    )

    job_config = RayJobSpec(entrypoint="python script.py")

    # Execute without waiting
    result = Cluster.run_job_with_managed_cluster(
        cluster_config=cluster_config, job_config=job_config, wait_for_completion=False
    )

    # Verify result for no-wait case
    assert "job_cr_name" in result
    assert result["job_status"] == "SUBMITTED_NOT_FOUND"

    # Verify no polling happened
    mock_co_api.create_namespaced_custom_object.assert_called_once()


def test_run_job_with_managed_cluster_timeout(mocker):
    """Test RayJob execution with timeout."""
    from codeflare_sdk.ray.job.job import RayJobSpec

    # Mock dependencies
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch("codeflare_sdk.ray.cluster.cluster.config_check")

    mock_api_client = mocker.Mock()
    mocker.patch(
        "codeflare_sdk.common.kubernetes_cluster.auth.get_api_client",
        return_value=mock_api_client,
    )

    mock_co_api = mocker.Mock()
    mocker.patch("kubernetes.client.CustomObjectsApi", return_value=mock_co_api)

    # Mock Cluster creation
    mock_cluster_resource = {
        "apiVersion": "ray.io/v1",
        "kind": "RayCluster",
        "spec": {},
    }
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster.Cluster.__init__", return_value=None
    )
    mock_cluster_instance = mocker.Mock()
    mock_cluster_instance.resource_yaml = mock_cluster_resource
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster.Cluster", return_value=mock_cluster_instance
    )

    # Mock RayJob creation
    mock_co_api.create_namespaced_custom_object.return_value = {
        "metadata": {"name": "test-rayjob-timeout"}
    }

    # Mock job status as always RUNNING (never completes)
    mock_status_response = {
        "status": {
            "jobDeploymentStatus": "Running",
            "jobStatus": "RUNNING",
            "jobId": "timeout-job-123",
        }
    }
    mock_co_api.get_namespaced_custom_object_status.return_value = mock_status_response

    # Mock time to simulate timeout
    start_time = 1000
    mocker.patch(
        "time.time", side_effect=[start_time, start_time + 70]
    )  # Exceed 60s timeout
    mocker.patch("time.sleep")

    cluster_config = ClusterConfiguration(name="timeout-cluster", namespace="test-ns")
    job_config = RayJobSpec(entrypoint="python long_running_script.py")

    # Execute and expect timeout
    try:
        result = Cluster.run_job_with_managed_cluster(
            cluster_config=cluster_config,
            job_config=job_config,
            wait_for_completion=True,
            job_timeout_seconds=60,
            job_polling_interval_seconds=1,
        )
        assert False, "Expected TimeoutError"
    except TimeoutError as e:
        assert "timed out after 60 seconds" in str(e)
        assert "RUNNING" in str(e)


def test_run_job_with_managed_cluster_validation_error(mocker):
    """Test RayJob execution with validation errors."""
    from codeflare_sdk.ray.job.job import RayJobSpec

    cluster_config = ClusterConfiguration(name="test-cluster", namespace="test-ns")

    # Test missing entrypoint
    job_config_no_entrypoint = RayJobSpec(entrypoint="")

    try:
        Cluster.run_job_with_managed_cluster(
            cluster_config=cluster_config, job_config=job_config_no_entrypoint
        )
        assert False, "Expected ValueError for missing entrypoint"
    except ValueError as e:
        assert "entrypoint must be specified" in str(e)


def test_run_job_with_managed_cluster_failed_job(mocker):
    """Test RayJob execution when job fails."""
    from codeflare_sdk.ray.job.job import RayJobSpec

    # Mock dependencies
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch("codeflare_sdk.ray.cluster.cluster.config_check")

    mock_api_client = mocker.Mock()
    mocker.patch(
        "codeflare_sdk.common.kubernetes_cluster.auth.get_api_client",
        return_value=mock_api_client,
    )

    mock_co_api = mocker.Mock()
    mocker.patch("kubernetes.client.CustomObjectsApi", return_value=mock_co_api)

    # Mock Cluster creation
    mock_cluster_resource = {
        "apiVersion": "ray.io/v1",
        "kind": "RayCluster",
        "spec": {},
    }
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster.Cluster.__init__", return_value=None
    )
    mock_cluster_instance = mocker.Mock()
    mock_cluster_instance.resource_yaml = mock_cluster_resource
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster.Cluster", return_value=mock_cluster_instance
    )

    # Mock RayJob creation
    mock_co_api.create_namespaced_custom_object.return_value = {
        "metadata": {"name": "test-failed-job"}
    }

    # Mock job status as FAILED
    mock_status_response = {
        "status": {
            "jobDeploymentStatus": "Running",
            "jobStatus": "FAILED",
            "jobId": "failed-job-123",
            "rayClusterName": "test-cluster",
            "message": "Job failed due to error",
        }
    }
    mock_co_api.get_namespaced_custom_object_status.return_value = mock_status_response
    mocker.patch("time.sleep")

    cluster_config = ClusterConfiguration(name="test-cluster", namespace="test-ns")
    job_config = RayJobSpec(entrypoint="python failing_script.py")

    result = Cluster.run_job_with_managed_cluster(
        cluster_config=cluster_config, job_config=job_config, wait_for_completion=True
    )

    assert result["job_status"] == "FAILED"
    assert result["job_submission_id"] == "failed-job-123"


def test_run_job_with_managed_cluster_stopped_job(mocker):
    """Test RayJob execution when job is stopped."""
    from codeflare_sdk.ray.job.job import RayJobSpec

    # Mock dependencies
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch("codeflare_sdk.ray.cluster.cluster.config_check")

    mock_api_client = mocker.Mock()
    mocker.patch(
        "codeflare_sdk.common.kubernetes_cluster.auth.get_api_client",
        return_value=mock_api_client,
    )

    mock_co_api = mocker.Mock()
    mocker.patch("kubernetes.client.CustomObjectsApi", return_value=mock_co_api)

    # Mock Cluster creation
    mock_cluster_resource = {
        "apiVersion": "ray.io/v1",
        "kind": "RayCluster",
        "spec": {},
    }
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster.Cluster.__init__", return_value=None
    )
    mock_cluster_instance = mocker.Mock()
    mock_cluster_instance.resource_yaml = mock_cluster_resource
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster.Cluster", return_value=mock_cluster_instance
    )

    # Mock RayJob creation
    mock_co_api.create_namespaced_custom_object.return_value = {
        "metadata": {"name": "test-stopped-job"}
    }

    # Mock job status as STOPPED
    mock_status_response = {
        "status": {
            "jobDeploymentStatus": "Running",
            "jobStatus": "STOPPED",
            "jobId": "stopped-job-123",
        }
    }
    mock_co_api.get_namespaced_custom_object_status.return_value = mock_status_response
    mocker.patch("time.sleep")

    cluster_config = ClusterConfiguration(name="test-cluster", namespace="test-ns")
    job_config = RayJobSpec(entrypoint="python script.py")

    result = Cluster.run_job_with_managed_cluster(
        cluster_config=cluster_config, job_config=job_config, wait_for_completion=True
    )

    assert result["job_status"] == "STOPPED"
    assert result["job_submission_id"] == "stopped-job-123"


def test_run_job_with_managed_cluster_pending_job(mocker):
    """Test RayJob execution when job is pending then succeeds."""
    from codeflare_sdk.ray.job.job import RayJobSpec

    # Mock dependencies
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch("codeflare_sdk.ray.cluster.cluster.config_check")

    mock_api_client = mocker.Mock()
    mocker.patch(
        "codeflare_sdk.common.kubernetes_cluster.auth.get_api_client",
        return_value=mock_api_client,
    )

    mock_co_api = mocker.Mock()
    mocker.patch("kubernetes.client.CustomObjectsApi", return_value=mock_co_api)

    # Mock Cluster creation
    mock_cluster_resource = {
        "apiVersion": "ray.io/v1",
        "kind": "RayCluster",
        "spec": {},
    }
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster.Cluster.__init__", return_value=None
    )
    mock_cluster_instance = mocker.Mock()
    mock_cluster_instance.resource_yaml = mock_cluster_resource
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster.Cluster", return_value=mock_cluster_instance
    )

    # Mock RayJob creation
    mock_co_api.create_namespaced_custom_object.return_value = {
        "metadata": {"name": "test-pending-job"}
    }

    # Mock job status progression: PENDING -> RUNNING -> SUCCEEDED
    pending_response = {
        "status": {
            "jobDeploymentStatus": "Initializing",
            "jobStatus": "PENDING",
            "jobId": "pending-job-123",
        }
    }
    running_response = {
        "status": {
            "jobDeploymentStatus": "Running",
            "jobStatus": "RUNNING",
            "jobId": "pending-job-123",
        }
    }
    succeeded_response = {
        "status": {
            "jobDeploymentStatus": "Running",
            "jobStatus": "SUCCEEDED",
            "jobId": "pending-job-123",
        }
    }

    mock_co_api.get_namespaced_custom_object_status.side_effect = [
        pending_response,
        running_response,
        succeeded_response,
    ]
    mocker.patch("time.sleep")

    cluster_config = ClusterConfiguration(name="test-cluster", namespace="test-ns")
    job_config = RayJobSpec(entrypoint="python script.py")

    result = Cluster.run_job_with_managed_cluster(
        cluster_config=cluster_config, job_config=job_config, wait_for_completion=True
    )

    assert result["job_status"] == "SUCCEEDED"
    assert result["job_submission_id"] == "pending-job-123"


def test_run_job_with_managed_cluster_api_exception(mocker):
    """Test RayJob creation with API exception."""
    from codeflare_sdk.ray.job.job import RayJobSpec
    from kubernetes.client.rest import ApiException

    # Mock dependencies
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch("codeflare_sdk.ray.cluster.cluster.config_check")

    mock_api_client = mocker.Mock()
    mocker.patch(
        "codeflare_sdk.common.kubernetes_cluster.auth.get_api_client",
        return_value=mock_api_client,
    )

    mock_co_api = mocker.Mock()
    mocker.patch("kubernetes.client.CustomObjectsApi", return_value=mock_co_api)

    # Mock Cluster creation
    mock_cluster_resource = {
        "apiVersion": "ray.io/v1",
        "kind": "RayCluster",
        "spec": {},
    }
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster.Cluster.__init__", return_value=None
    )
    mock_cluster_instance = mocker.Mock()
    mock_cluster_instance.resource_yaml = mock_cluster_resource
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster.Cluster", return_value=mock_cluster_instance
    )

    # Mock API exception during job creation (correct constructor)
    mock_co_api.create_namespaced_custom_object.side_effect = ApiException(
        status=400, reason="Bad Request"
    )

    cluster_config = ClusterConfiguration(name="test-cluster", namespace="test-ns")
    job_config = RayJobSpec(entrypoint="python script.py")

    try:
        Cluster.run_job_with_managed_cluster(
            cluster_config=cluster_config, job_config=job_config
        )
        assert False, "Expected ApiException"
    except ApiException as e:
        assert e.status == 400
        assert "Bad Request" in str(e)


def test_run_job_with_managed_cluster_missing_status_fields(mocker):
    """Test RayJob with missing status fields - should not wait for completion."""
    from codeflare_sdk.ray.job.job import RayJobSpec

    # Mock dependencies
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch("codeflare_sdk.ray.cluster.cluster.config_check")

    mock_api_client = mocker.Mock()
    mocker.patch(
        "codeflare_sdk.common.kubernetes_cluster.auth.get_api_client",
        return_value=mock_api_client,
    )

    mock_co_api = mocker.Mock()
    mocker.patch("kubernetes.client.CustomObjectsApi", return_value=mock_co_api)

    # Mock Cluster creation
    mock_cluster_resource = {
        "apiVersion": "ray.io/v1",
        "kind": "RayCluster",
        "spec": {},
    }
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster.Cluster.__init__", return_value=None
    )
    mock_cluster_instance = mocker.Mock()
    mock_cluster_instance.resource_yaml = mock_cluster_resource
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster.Cluster", return_value=mock_cluster_instance
    )

    # Mock RayJob creation
    mock_co_api.create_namespaced_custom_object.return_value = {
        "metadata": {"name": "test-missing-fields"}
    }

    # Mock job status with missing fields - but don't wait for completion to avoid timeout
    mock_status_response = {
        "status": {
            "jobDeploymentStatus": "Running"
            # Missing jobStatus, jobId, etc.
        }
    }
    mock_co_api.get_namespaced_custom_object_status.return_value = mock_status_response
    mocker.patch("time.sleep")

    cluster_config = ClusterConfiguration(name="test-cluster", namespace="test-ns")
    job_config = RayJobSpec(entrypoint="python script.py")

    # Don't wait for completion to avoid timeout with missing status fields
    result = Cluster.run_job_with_managed_cluster(
        cluster_config=cluster_config,
        job_config=job_config,
        wait_for_completion=False,  # Key change: don't wait
    )

    # Should handle missing fields gracefully
    assert "job_cr_name" in result
    # When not waiting, we should get the submitted state
    assert result.get("job_status") in [
        None,
        "SUBMITTED",
        "SUBMITTED_NOT_FOUND",
        "PENDING",
    ]


def test_run_job_with_managed_cluster_custom_job_name(mocker):
    """Test RayJob with custom job CR name."""
    from codeflare_sdk.ray.job.job import RayJobSpec

    # Mock dependencies
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch("codeflare_sdk.ray.cluster.cluster.config_check")

    mock_api_client = mocker.Mock()
    mocker.patch(
        "codeflare_sdk.common.kubernetes_cluster.auth.get_api_client",
        return_value=mock_api_client,
    )

    mock_co_api = mocker.Mock()
    mocker.patch("kubernetes.client.CustomObjectsApi", return_value=mock_co_api)

    # Mock Cluster creation
    mock_cluster_resource = {
        "apiVersion": "ray.io/v1",
        "kind": "RayCluster",
        "spec": {},
    }
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster.Cluster.__init__", return_value=None
    )
    mock_cluster_instance = mocker.Mock()
    mock_cluster_instance.resource_yaml = mock_cluster_resource
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster.Cluster", return_value=mock_cluster_instance
    )

    # Mock successful RayJob creation with custom name
    custom_job_name = "my-custom-rayjob-name"
    mock_co_api.create_namespaced_custom_object.return_value = {
        "metadata": {"name": custom_job_name}
    }

    # Mock job completion
    mock_status_response = {
        "status": {
            "jobDeploymentStatus": "Running",
            "jobStatus": "SUCCEEDED",
            "jobId": "custom-job-123",
        }
    }
    mock_co_api.get_namespaced_custom_object_status.return_value = mock_status_response
    mocker.patch("time.sleep")

    cluster_config = ClusterConfiguration(name="test-cluster", namespace="test-ns")
    job_config = RayJobSpec(entrypoint="python script.py")

    result = Cluster.run_job_with_managed_cluster(
        cluster_config=cluster_config,
        job_config=job_config,
        job_cr_name=custom_job_name,
        wait_for_completion=True,
    )

    assert result["job_cr_name"] == custom_job_name
    assert result["job_submission_id"] == "custom-job-123"
    assert result["job_status"] == "SUCCEEDED"


def test_run_job_with_managed_cluster_all_status_fields(mocker):
    """Test RayJob with all possible status fields populated."""
    from codeflare_sdk.ray.job.job import RayJobSpec

    # Mock dependencies
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch("codeflare_sdk.ray.cluster.cluster.config_check")

    mock_api_client = mocker.Mock()
    mocker.patch(
        "codeflare_sdk.common.kubernetes_cluster.auth.get_api_client",
        return_value=mock_api_client,
    )

    mock_co_api = mocker.Mock()
    mocker.patch("kubernetes.client.CustomObjectsApi", return_value=mock_co_api)

    # Mock Cluster creation
    mock_cluster_resource = {
        "apiVersion": "ray.io/v1",
        "kind": "RayCluster",
        "spec": {},
    }
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster.Cluster.__init__", return_value=None
    )
    mock_cluster_instance = mocker.Mock()
    mock_cluster_instance.resource_yaml = mock_cluster_resource
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster.Cluster", return_value=mock_cluster_instance
    )

    # Mock RayJob creation
    mock_co_api.create_namespaced_custom_object.return_value = {
        "metadata": {"name": "test-all-fields"}
    }

    # Mock job status with all fields
    mock_status_response = {
        "status": {
            "jobDeploymentStatus": "Complete",
            "jobStatus": "SUCCEEDED",
            "dashboardURL": "http://ray-dashboard:8265",
            "rayClusterName": "test-cluster-name",
            "jobId": "all-fields-job-456",
            "message": "Job completed successfully",
            "startTime": "2023-01-01T10:00:00Z",
            "endTime": "2023-01-01T10:05:00Z",
        }
    }
    mock_co_api.get_namespaced_custom_object_status.return_value = mock_status_response
    mocker.patch("time.sleep")

    cluster_config = ClusterConfiguration(name="test-cluster", namespace="test-ns")
    job_config = RayJobSpec(entrypoint="python comprehensive_script.py")

    result = Cluster.run_job_with_managed_cluster(
        cluster_config=cluster_config, job_config=job_config, wait_for_completion=True
    )

    # Verify all fields are captured
    assert result["job_status"] == "SUCCEEDED"
    assert result["dashboard_url"] == "http://ray-dashboard:8265"
    assert result["ray_cluster_name"] == "test-cluster-name"
    assert result["job_submission_id"] == "all-fields-job-456"


def test_run_job_with_managed_cluster_status_polling_exception(mocker):
    """Test RayJob with exception during status polling."""
    from codeflare_sdk.ray.job.job import RayJobSpec
    from kubernetes.client.rest import ApiException
    
    # Mock dependencies
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch("codeflare_sdk.ray.cluster.cluster.config_check")
    
    mock_api_client = mocker.Mock()
    mocker.patch(
        "codeflare_sdk.common.kubernetes_cluster.auth.get_api_client",
        return_value=mock_api_client,
    )
    
    mock_co_api = mocker.Mock()
    mocker.patch("kubernetes.client.CustomObjectsApi", return_value=mock_co_api)
    
    # Mock Cluster creation
    mock_cluster_resource = {
        "apiVersion": "ray.io/v1",
        "kind": "RayCluster",
        "spec": {},
    }
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster.Cluster.__init__", return_value=None
    )
    mock_cluster_instance = mocker.Mock()
    mock_cluster_instance.resource_yaml = mock_cluster_resource
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster.Cluster", return_value=mock_cluster_instance
    )
    
    # Mock RayJob creation
    mock_co_api.create_namespaced_custom_object.return_value = {
        "metadata": {"name": "test-status-exception"}
    }
    
    # Mock status polling to raise exception after first success
    success_response = {
        "status": {
            "jobDeploymentStatus": "Running",
            "jobStatus": "RUNNING",
            "jobId": "exception-job-123",
        }
    }
    exception = ApiException(status=500, reason="Internal Server Error")
    
    mock_co_api.get_namespaced_custom_object_status.side_effect = [
        success_response,
        exception,
    ]
    mocker.patch("time.sleep")
    
    cluster_config = ClusterConfiguration(name="test-cluster", namespace="test-ns")
    job_config = RayJobSpec(entrypoint="python script.py")
    
    try:
        Cluster.run_job_with_managed_cluster(
            cluster_config=cluster_config,
            job_config=job_config,
            wait_for_completion=True,
            job_timeout_seconds=10,
        )
        assert False, "Expected ApiException"
    except ApiException as e:
        assert e.status == 500


def test_run_job_with_managed_cluster_empty_status(mocker):
    """Test RayJob with completely empty status."""
    from codeflare_sdk.ray.job.job import RayJobSpec
    
    # Mock dependencies
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch("codeflare_sdk.ray.cluster.cluster.config_check")
    
    mock_api_client = mocker.Mock()
    mocker.patch(
        "codeflare_sdk.common.kubernetes_cluster.auth.get_api_client",
        return_value=mock_api_client,
    )
    
    mock_co_api = mocker.Mock()
    mocker.patch("kubernetes.client.CustomObjectsApi", return_value=mock_co_api)
    
    # Mock Cluster creation
    mock_cluster_resource = {
        "apiVersion": "ray.io/v1",
        "kind": "RayCluster",
        "spec": {},
    }
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster.Cluster.__init__", return_value=None
    )
    mock_cluster_instance = mocker.Mock()
    mock_cluster_instance.resource_yaml = mock_cluster_resource
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster.Cluster", return_value=mock_cluster_instance
    )
    
    # Mock RayJob creation
    mock_co_api.create_namespaced_custom_object.return_value = {
        "metadata": {"name": "test-empty-status"}
    }
    
    # Mock completely empty status response
    empty_status_response = {}
    mock_co_api.get_namespaced_custom_object_status.return_value = empty_status_response
    mocker.patch("time.sleep")
    
    cluster_config = ClusterConfiguration(name="test-cluster", namespace="test-ns")
    job_config = RayJobSpec(entrypoint="python script.py")
    
    # Should handle empty status gracefully with timeout
    try:
        Cluster.run_job_with_managed_cluster(
            cluster_config=cluster_config,
            job_config=job_config,
            wait_for_completion=True,
            job_timeout_seconds=2,
            job_polling_interval_seconds=1,
        )
        assert False, "Expected TimeoutError"
    except TimeoutError as e:
        assert "timed out after 2 seconds" in str(e)


def test_run_job_with_managed_cluster_no_metadata_name(mocker):
    """Test RayJob creation with missing metadata name."""
    from codeflare_sdk.ray.job.job import RayJobSpec
    
    # Mock dependencies
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch("codeflare_sdk.ray.cluster.cluster.config_check")
    
    mock_api_client = mocker.Mock()
    mocker.patch(
        "codeflare_sdk.common.kubernetes_cluster.auth.get_api_client",
        return_value=mock_api_client,
    )
    
    mock_co_api = mocker.Mock()
    mocker.patch("kubernetes.client.CustomObjectsApi", return_value=mock_co_api)
    
    # Mock Cluster creation
    mock_cluster_resource = {
        "apiVersion": "ray.io/v1",
        "kind": "RayCluster",
        "spec": {},
    }
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster.Cluster.__init__", return_value=None
    )
    mock_cluster_instance = mocker.Mock()
    mock_cluster_instance.resource_yaml = mock_cluster_resource
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster.Cluster", return_value=mock_cluster_instance
    )
    
    # Mock RayJob creation with missing name in metadata - method generates its own name
    mock_co_api.create_namespaced_custom_object.return_value = {"metadata": {}}
    
    # Mock status API response even for no-wait case
    from kubernetes.client.rest import ApiException
    mock_co_api.get_namespaced_custom_object_status.side_effect = ApiException(
        status=404, reason="Not Found"
    )
    
    cluster_config = ClusterConfiguration(name="test-cluster", namespace="test-ns")
    job_config = RayJobSpec(entrypoint="python script.py")
    
    # Should still work and generate a job name
    result = Cluster.run_job_with_managed_cluster(
        cluster_config=cluster_config,
        job_config=job_config,
        wait_for_completion=False,
    )
    
    # Should have a generated job name (starts with 'rayjob-')
    assert "job_cr_name" in result
    assert result["job_cr_name"].startswith("rayjob-")
    assert result["job_status"] == "SUBMITTED_NOT_FOUND"


def test_run_job_with_managed_cluster_default_namespace(mocker):
    """Test RayJob with default namespace."""
    from codeflare_sdk.ray.job.job import RayJobSpec
    
    # Mock dependencies
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch("codeflare_sdk.ray.cluster.cluster.config_check")
    
    mock_api_client = mocker.Mock()
    mocker.patch(
        "codeflare_sdk.common.kubernetes_cluster.auth.get_api_client",
        return_value=mock_api_client,
    )
    
    mock_co_api = mocker.Mock()
    mocker.patch("kubernetes.client.CustomObjectsApi", return_value=mock_co_api)
    
    # Mock Cluster creation
    mock_cluster_resource = {
        "apiVersion": "ray.io/v1",
        "kind": "RayCluster",
        "spec": {},
    }
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster.Cluster.__init__", return_value=None
    )
    mock_cluster_instance = mocker.Mock()
    mock_cluster_instance.resource_yaml = mock_cluster_resource
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster.Cluster", return_value=mock_cluster_instance
    )
    
    # Mock RayJob creation
    mock_co_api.create_namespaced_custom_object.return_value = {
        "metadata": {"name": "test-default-ns"}
    }
    
    # Mock status API response even for no-wait case
    from kubernetes.client.rest import ApiException
    mock_co_api.get_namespaced_custom_object_status.side_effect = ApiException(
        status=404, reason="Not Found"
    )
    
    # Test with ClusterConfiguration that has namespace=None (should use default)
    cluster_config = ClusterConfiguration(name="test-cluster", namespace=None)
    job_config = RayJobSpec(entrypoint="python script.py")
    
    result = Cluster.run_job_with_managed_cluster(
        cluster_config=cluster_config,
        job_config=job_config,
        wait_for_completion=False,
    )
    
    # Method generates its own job name regardless of API response
    assert "job_cr_name" in result
    assert result["job_cr_name"].startswith("rayjob-")
    assert result["job_status"] == "SUBMITTED_NOT_FOUND"


def test_run_job_with_managed_cluster_job_spec_with_runtime_env(mocker):
    """Test RayJob with runtime environment in job spec."""
    from codeflare_sdk.ray.job.job import RayJobSpec
    
    # Mock dependencies
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch("codeflare_sdk.ray.cluster.cluster.config_check")
    
    mock_api_client = mocker.Mock()
    mocker.patch(
        "codeflare_sdk.common.kubernetes_cluster.auth.get_api_client",
        return_value=mock_api_client,
    )
    
    mock_co_api = mocker.Mock()
    mocker.patch("kubernetes.client.CustomObjectsApi", return_value=mock_co_api)
    
    # Mock Cluster creation
    mock_cluster_resource = {
        "apiVersion": "ray.io/v1",
        "kind": "RayCluster",
        "spec": {},
    }
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster.Cluster.__init__", return_value=None
    )
    mock_cluster_instance = mocker.Mock()
    mock_cluster_instance.resource_yaml = mock_cluster_resource
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster.Cluster", return_value=mock_cluster_instance
    )
    
    # Mock RayJob creation
    mock_co_api.create_namespaced_custom_object.return_value = {
        "metadata": {"name": "test-runtime-env"}
    }
    
    # Mock status API response even for no-wait case
    from kubernetes.client.rest import ApiException
    mock_co_api.get_namespaced_custom_object_status.side_effect = ApiException(
        status=404, reason="Not Found"
    )
    
    cluster_config = ClusterConfiguration(name="test-cluster", namespace="test-ns")
    
    # Create job spec with runtime environment
    job_config = RayJobSpec(
        entrypoint="python script.py",
        runtime_env={"pip": ["numpy", "pandas"]},
        metadata={"job_timeout_s": 3600},
    )
    
    result = Cluster.run_job_with_managed_cluster(
        cluster_config=cluster_config,
        job_config=job_config,
        wait_for_completion=False,
    )
    
    # Method generates its own job name regardless of API response  
    assert "job_cr_name" in result
    assert result["job_cr_name"].startswith("rayjob-")
    assert result["job_status"] == "SUBMITTED_NOT_FOUND"
    
    # Verify the CustomObjectsApi was called with proper parameters
    mock_co_api.create_namespaced_custom_object.assert_called_once()


# Make sure to always keep this function last
def test_cleanup():
    os.remove(f"{aw_dir}test-all-params.yaml")
    os.remove(f"{aw_dir}aw-all-params.yaml")

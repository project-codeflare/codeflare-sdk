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
    createClusterWithConfig,
    arg_check_del_effect,
    ingress_retrieval,
    arg_check_apply_effect,
    get_local_queue,
    createClusterConfig,
    get_ray_obj,
    get_obj_none,
    get_ray_obj_with_status,
    get_aw_obj_with_status,
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
    cluster = cluster = createClusterWithConfig(mocker)
    cluster.up()
    cluster.down()


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
    config = createClusterConfig()
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
    cluster = cluster = createClusterWithConfig(mocker)
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


def test_ray_job_wrapping(mocker):
    import ray

    def ray_addr(self, *args):
        return self._address

    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        return_value=get_local_queue("kueue.x-k8s.io", "v1beta1", "ns", "localqueues"),
    )
    cluster = cluster = createClusterWithConfig(mocker)
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
        assert filecmp.cmp(
            f"{aw_dir}test-all-params.yaml",
            f"{expected_clusters_dir}/ray/unit-test-all-params.yaml",
            shallow=True,
        )


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
        assert filecmp.cmp(
            f"{aw_dir}aw-all-params.yaml",
            f"{expected_clusters_dir}/appwrapper/unit-test-all-params.yaml",
            shallow=True,
        )


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


# Make sure to always keep this function last
def test_cleanup():
    os.remove(f"{aw_dir}test-all-params.yaml")
    os.remove(f"{aw_dir}aw-all-params.yaml")

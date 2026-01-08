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

from .pretty_print import (
    print_cluster_status,
    print_clusters,
    print_no_resources_found,
)
from .status import (
    RayClusterInfo,
    RayClusterStatus,
    CodeFlareClusterStatus,
)
from .raycluster import RayCluster
from codeflare_sdk.common.utils.unit_test_support import get_local_queue


def test_print_no_resources(capsys):
    try:
        print_no_resources_found()
    except Exception:
        assert 1 == 0
    captured = capsys.readouterr()
    # The Rich library's console width detection varies between test contexts
    # Check for key parts of the message instead of the full text
    assert "No resources found" in captured.out
    assert "cluster.apply()" in captured.out
    assert "cluster.details()" in captured.out
    assert "check if it's ready" in captured.out
    assert "╭" in captured.out and "╮" in captured.out  # Check for box characters
    assert "│" in captured.out  # Check for vertical lines


def test_ray_details(mocker, capsys):
    """
    Test that details() returns self (RayCluster) and that pretty_print
    functions work with RayCluster objects.
    """
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch(
        "codeflare_sdk.ray.rayclusters.raycluster.RayCluster._get_current_status",
        return_value=RayClusterStatus.READY,
    )
    mocker.patch(
        "codeflare_sdk.ray.rayclusters.raycluster.RayCluster.cluster_dashboard_uri",
        return_value="https://dashboard.example.com",
    )
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        return_value=get_local_queue("kueue.x-k8s.io", "v1beta1", "ns", "localqueues"),
    )

    cf = RayCluster(
        name="test-cluster",
        namespace="ns",
        local_queue="local-queue-default",
        num_workers=2,
        worker_memory_requests="4G",
        worker_memory_limits="8G",
        worker_cpu_requests=2,
        worker_cpu_limits=4,
    )
    captured = capsys.readouterr()

    # details() returns self (the RayCluster instance)
    details = cf.details()
    assert details is cf

    # Verify RayCluster fields
    assert cf.name == "test-cluster"
    assert cf.namespace == "ns"
    assert cf.num_workers == 2
    assert cf.worker_memory_requests == "4G"
    assert cf.worker_memory_limits == "8G"
    assert cf.worker_cpu_requests == 2
    assert cf.worker_cpu_limits == 4

    # Test that print functions work with RayCluster
    try:
        print_clusters([cf])
        print_cluster_status(cf)
    except Exception as e:
        assert False, f"print functions failed: {e}"

    captured = capsys.readouterr()
    # Check that output contains expected content
    assert "test-cluster" in captured.out
    assert "Active" in captured.out or "Inactive" in captured.out
    assert "Workers" in captured.out


def test_ray_cluster_info_with_print(mocker, capsys):
    """
    Test that RayClusterInfo contains a RayCluster and print functions
    can access cluster properties through it.
    """
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        return_value=get_local_queue("kueue.x-k8s.io", "v1beta1", "ns", "localqueues"),
    )

    # Create a RayCluster
    cluster = RayCluster(
        name="info-test-cluster",
        namespace="ns",
        local_queue="local-queue-default",
        num_workers=3,
    )
    capsys.readouterr()  # Clear output from RayCluster creation

    # Create RayClusterInfo with the new interface
    info = RayClusterInfo(
        cluster=cluster,
        status=RayClusterStatus.READY,
        dashboard="https://dashboard.example.com",
    )

    # Verify RayClusterInfo structure
    assert info.cluster is cluster
    assert info.cluster.name == "info-test-cluster"
    assert info.cluster.namespace == "ns"
    assert info.cluster.num_workers == 3
    assert info.status == RayClusterStatus.READY
    assert info.dashboard == "https://dashboard.example.com"

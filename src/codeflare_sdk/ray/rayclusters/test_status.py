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

from .raycluster import (
    RayCluster,
)
from .status import (
    CodeFlareClusterStatus,
    RayClusterStatus,
    RayClusterInfo,
)
import os
from ...common.utils.unit_test_support import get_local_queue

cluster_dir = os.path.expanduser("~/.codeflare/resources/")


def test_cluster_status(mocker):
    """Test that RayCluster.status() correctly maps RayClusterStatus to CodeFlareClusterStatus."""
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")

    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        return_value=get_local_queue("kueue.x-k8s.io", "v1beta1", "ns", "localqueues"),
    )

    cf = RayCluster(
        name="test",
        namespace="ns",
        write_to_file=True,
        local_queue="local-queue-default",
    )

    # Test: No cluster found -> UNKNOWN status
    mocker.patch(
        "codeflare_sdk.ray.rayclusters.raycluster.RayCluster._ray_cluster_status",
        return_value=None,
    )
    status, ready = cf.status()
    assert status == CodeFlareClusterStatus.UNKNOWN
    assert ready == False

    # Test: UNKNOWN status -> STARTING (cluster exists but state unknown)
    mocker.patch(
        "codeflare_sdk.ray.rayclusters.raycluster.RayCluster._ray_cluster_status",
        return_value=RayClusterStatus.UNKNOWN,
    )
    status, ready = cf.status()
    assert status == CodeFlareClusterStatus.STARTING
    assert ready == False

    # Test: FAILED status
    mocker.patch(
        "codeflare_sdk.ray.rayclusters.raycluster.RayCluster._ray_cluster_status",
        return_value=RayClusterStatus.FAILED,
    )
    status, ready = cf.status()
    assert status == CodeFlareClusterStatus.FAILED
    assert ready == False

    # Test: UNHEALTHY status -> FAILED
    mocker.patch(
        "codeflare_sdk.ray.rayclusters.raycluster.RayCluster._ray_cluster_status",
        return_value=RayClusterStatus.UNHEALTHY,
    )
    status, ready = cf.status()
    assert status == CodeFlareClusterStatus.FAILED
    assert ready == False

    # Test: READY status
    mocker.patch(
        "codeflare_sdk.ray.rayclusters.raycluster.RayCluster._ray_cluster_status",
        return_value=RayClusterStatus.READY,
    )
    status, ready = cf.status()
    assert status == CodeFlareClusterStatus.READY
    assert ready == True

    # Test: SUSPENDED status
    mocker.patch(
        "codeflare_sdk.ray.rayclusters.raycluster.RayCluster._ray_cluster_status",
        return_value=RayClusterStatus.SUSPENDED,
    )
    status, ready = cf.status()
    assert status == CodeFlareClusterStatus.SUSPENDED
    assert ready == False


def rc_status_fields(group, version, namespace, plural, *args):
    assert group == "ray.io"
    assert version == "v1"
    assert namespace == "test-ns"
    assert plural == "rayclusters"
    assert args == tuple()
    return {"items": []}


def test_rc_status(mocker):
    """Test that _ray_cluster_status returns None when cluster not found."""
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        side_effect=rc_status_fields,
    )
    # Create a RayCluster to call its _ray_cluster_status method
    cluster = RayCluster(name="test-rc", namespace="test-ns")
    rc = cluster._ray_cluster_status(cluster.name, cluster.namespace)
    assert rc is None


def test_ray_cluster_info():
    """Test the new simplified RayClusterInfo dataclass."""
    # Create a RayCluster
    cluster = RayCluster(
        name="test-cluster",
        namespace="default",
        num_workers=2,
    )

    # Create RayClusterInfo with the new interface
    info = RayClusterInfo(
        cluster=cluster,
        status=RayClusterStatus.READY,
        dashboard="https://dashboard.example.com",
    )

    # Verify fields
    assert info.cluster.name == "test-cluster"
    assert info.cluster.namespace == "default"
    assert info.cluster.num_workers == 2
    assert info.status == RayClusterStatus.READY
    assert info.dashboard == "https://dashboard.example.com"


# Make sure to always keep this function last
def test_cleanup():
    test_file = f"{cluster_dir}test.yaml"
    if os.path.exists(test_file):
        os.remove(test_file)

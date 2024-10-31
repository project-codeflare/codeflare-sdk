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
    _ray_cluster_status,
)
from codeflare_sdk.ray.cluster.status import (
    CodeFlareClusterStatus,
    RayClusterStatus,
    RayCluster,
)
import os
from ...common.utils.unit_test_support import get_local_queue

aw_dir = os.path.expanduser("~/.codeflare/resources/")


def test_cluster_status(mocker):
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")

    fake_ray = RayCluster(
        name="test",
        status=RayClusterStatus.UNKNOWN,
        num_workers=1,
        worker_mem_requests=2,
        worker_mem_limits=2,
        worker_cpu_requests=1,
        worker_cpu_limits=1,
        namespace="ns",
        dashboard="fake-uri",
        head_cpu_requests=2,
        head_cpu_limits=2,
        head_mem_requests=8,
        head_mem_limits=8,
    )

    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        return_value=get_local_queue("kueue.x-k8s.io", "v1beta1", "ns", "localqueues"),
    )

    cf = Cluster(
        ClusterConfiguration(
            name="test",
            namespace="ns",
            write_to_file=True,
            appwrapper=False,
            local_queue="local-queue-default",
        )
    )
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster._ray_cluster_status", return_value=None
    )
    status, ready = cf.status()
    assert status == CodeFlareClusterStatus.UNKNOWN
    assert ready == False

    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster._ray_cluster_status", return_value=fake_ray
    )

    status, ready = cf.status()
    assert status == CodeFlareClusterStatus.STARTING
    assert ready == False

    fake_ray.status = RayClusterStatus.FAILED
    status, ready = cf.status()
    assert status == CodeFlareClusterStatus.FAILED
    assert ready == False

    fake_ray.status = RayClusterStatus.UNHEALTHY
    status, ready = cf.status()
    assert status == CodeFlareClusterStatus.FAILED
    assert ready == False

    fake_ray.status = RayClusterStatus.READY
    status, ready = cf.status()
    assert status == CodeFlareClusterStatus.READY
    assert ready == True


def rc_status_fields(group, version, namespace, plural, *args):
    assert group == "ray.io"
    assert version == "v1"
    assert namespace == "test-ns"
    assert plural == "rayclusters"
    assert args == tuple()
    return {"items": []}


def test_rc_status(mocker):
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        side_effect=rc_status_fields,
    )
    rc = _ray_cluster_status("test-rc", "test-ns")
    assert rc == None


# Make sure to always keep this function last
def test_cleanup():
    os.remove(f"{aw_dir}test.yaml")

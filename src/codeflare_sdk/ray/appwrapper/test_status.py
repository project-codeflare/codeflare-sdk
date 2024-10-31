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
    _app_wrapper_status,
    Cluster,
    ClusterConfiguration,
)
from codeflare_sdk.ray.appwrapper import AppWrapper, AppWrapperStatus
from codeflare_sdk.ray.cluster.status import CodeFlareClusterStatus
from codeflare_sdk.common.utils.unit_test_support import get_local_queue
import os

aw_dir = os.path.expanduser("~/.codeflare/resources/")


def test_cluster_status(mocker):
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        return_value=get_local_queue("kueue.x-k8s.io", "v1beta1", "ns", "localqueues"),
    )
    fake_aw = AppWrapper("test", AppWrapperStatus.FAILED)

    cf = Cluster(
        ClusterConfiguration(
            name="test",
            namespace="ns",
            write_to_file=True,
            appwrapper=True,
            local_queue="local-queue-default",
        )
    )
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster._app_wrapper_status", return_value=None
    )
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster._ray_cluster_status", return_value=None
    )
    status, ready = cf.status()
    assert status == CodeFlareClusterStatus.UNKNOWN
    assert ready == False

    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster._app_wrapper_status", return_value=fake_aw
    )
    status, ready = cf.status()
    assert status == CodeFlareClusterStatus.FAILED
    assert ready == False

    fake_aw.status = AppWrapperStatus.SUSPENDED
    status, ready = cf.status()
    assert status == CodeFlareClusterStatus.QUEUED
    assert ready == False

    fake_aw.status = AppWrapperStatus.RESUMING
    status, ready = cf.status()
    assert status == CodeFlareClusterStatus.STARTING
    assert ready == False

    fake_aw.status = AppWrapperStatus.RESETTING
    status, ready = cf.status()
    assert status == CodeFlareClusterStatus.STARTING
    assert ready == False

    fake_aw.status = AppWrapperStatus.RUNNING
    status, ready = cf.status()
    assert status == CodeFlareClusterStatus.UNKNOWN
    assert ready == False


def aw_status_fields(group, version, namespace, plural, *args):
    assert group == "workload.codeflare.dev"
    assert version == "v1beta2"
    assert namespace == "test-ns"
    assert plural == "appwrappers"
    assert args == tuple()
    return {"items": []}


def test_aw_status(mocker):
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        side_effect=aw_status_fields,
    )
    aw = _app_wrapper_status("test-aw", "test-ns")
    assert aw == None


# Make sure to always keep this function last
def test_cleanup():
    os.remove(f"{aw_dir}test.yaml")

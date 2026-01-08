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

from codeflare_sdk.ray.cluster.pretty_print import (
    print_cluster_status,
    print_clusters,
    print_no_resources_found,
)
from codeflare_sdk.ray.cluster.status import (
    RayClusterInfo,
    RayClusterStatus,
    CodeFlareClusterStatus,
)
from codeflare_sdk.ray.cluster.raycluster import RayCluster
from codeflare_sdk.common.utils.unit_test_support import get_local_queue


def test_print_no_resources(capsys):
    try:
        print_no_resources_found()
    except Exception:
        assert 1 == 0
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


def test_ray_details(mocker, capsys):
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    ray1 = RayClusterInfo(
        name="raytest1",
        status=RayClusterStatus.READY,
        num_workers=1,
        worker_mem_requests="3G",
        worker_mem_limits="6G",
        worker_cpu_requests=1,
        worker_cpu_limits=1,
        namespace="ns",
        dashboard="fake-uri",
        head_cpu_requests=1,
        head_cpu_limits=2,
        head_mem_requests=5,
        head_mem_limits=8,
    )
    mocker.patch(
        "codeflare_sdk.ray.cluster.raycluster.RayCluster.status",
        return_value=(CodeFlareClusterStatus.UNKNOWN, False),
    )
    mocker.patch(
        "codeflare_sdk.ray.cluster.raycluster.RayCluster.cluster_dashboard_uri",
        return_value="",
    )
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        return_value=get_local_queue("kueue.x-k8s.io", "v1beta1", "ns", "localqueues"),
    )
    cf = RayCluster(
        name="raytest2",
        namespace="ns",
        head_cpu_requests=1,
        head_cpu_limits=2,
        head_memory_requests="5G",
        head_memory_limits="8G",
        worker_cpu_requests=1,
        worker_cpu_limits=1,
        worker_memory_requests="3G",
        worker_memory_limits="6G",
        num_workers=1,
        local_queue="local-queue-default",
    )
    captured = capsys.readouterr()
    ray2 = cf.details()
    assert ray2.name == "raytest2"
    assert ray1.namespace == ray2.namespace
    assert ray1.num_workers == ray2.num_workers
    assert ray1.worker_mem_requests == ray2.worker_mem_requests
    assert ray1.worker_mem_limits == ray2.worker_mem_limits
    assert ray1.worker_cpu_requests == ray2.worker_cpu_requests
    assert ray1.worker_cpu_limits == ray2.worker_cpu_limits
    assert ray1.worker_extended_resources == ray2.worker_extended_resources
    try:
        print_clusters([ray1, ray2])
        print_cluster_status(ray1)
        print_cluster_status(ray2)
    except Exception:
        assert 0 == 1
    captured = capsys.readouterr()
    assert captured.out == (
        "                  🚀 CodeFlare Cluster Details 🚀                  \n"
        "                                                                   \n"
        " ╭───────────────────────────────────────────────────────────────╮ \n"
        " │   Name                                                        │ \n"
        " │   raytest2                                   Inactive ❌      │ \n"
        " │                                                               │ \n"
        " │   URI: ray://raytest2-head-svc.ns.svc:10001                   │ \n"
        " │                                                               │ \n"
        " │   Dashboard🔗                                                 │ \n"
        " │                                                               │ \n"
        " │                       Cluster Resources                       │ \n"
        " │   ╭── Workers ──╮  ╭───────── Worker specs(each) ─────────╮   │ \n"
        " │   │  # Workers  │  │  Memory      CPU         GPU         │   │ \n"
        " │   │             │  │                                      │   │ \n"
        " │   │  1          │  │  3G~6G       1~1         0           │   │ \n"
        " │   │             │  │                                      │   │ \n"
        " │   ╰─────────────╯  ╰──────────────────────────────────────╯   │ \n"
        " ╰───────────────────────────────────────────────────────────────╯ \n"
        "                  🚀 CodeFlare Cluster Details 🚀                  \n"
        "                                                                   \n"
        " ╭───────────────────────────────────────────────────────────────╮ \n"
        " │   Name                                                        │ \n"
        " │   raytest1                                   Active ✅        │ \n"
        " │                                                               │ \n"
        " │   URI: ray://raytest1-head-svc.ns.svc:10001                   │ \n"
        " │                                                               │ \n"
        " │   Dashboard🔗                                                 │ \n"
        " │                                                               │ \n"
        " │                       Cluster Resources                       │ \n"
        " │   ╭── Workers ──╮  ╭───────── Worker specs(each) ─────────╮   │ \n"
        " │   │  # Workers  │  │  Memory      CPU         GPU         │   │ \n"
        " │   │             │  │                                      │   │ \n"
        " │   │  1          │  │  3G~6G       1~1         0           │   │ \n"
        " │   │             │  │                                      │   │ \n"
        " │   ╰─────────────╯  ╰──────────────────────────────────────╯   │ \n"
        " ╰───────────────────────────────────────────────────────────────╯ \n"
        "╭───────────────────────────────────────────────────────────────╮\n"
        "│   Name                                                        │\n"
        "│   raytest2                                   Inactive ❌      │\n"
        "│                                                               │\n"
        "│   URI: ray://raytest2-head-svc.ns.svc:10001                   │\n"
        "│                                                               │\n"
        "│   Dashboard🔗                                                 │\n"
        "│                                                               │\n"
        "│                       Cluster Resources                       │\n"
        "│   ╭── Workers ──╮  ╭───────── Worker specs(each) ─────────╮   │\n"
        "│   │  # Workers  │  │  Memory      CPU         GPU         │   │\n"
        "│   │             │  │                                      │   │\n"
        "│   │  1          │  │  3G~6G       1~1         0           │   │\n"
        "│   │             │  │                                      │   │\n"
        "│   ╰─────────────╯  ╰──────────────────────────────────────╯   │\n"
        "╰───────────────────────────────────────────────────────────────╯\n"
        "                🚀 CodeFlare Cluster Status 🚀                \n"
        "                                                              \n"
        " ╭──────────────────────────────────────────────────────────╮ \n"
        " │   Name                                                   │ \n"
        " │   raytest1                                   Active ✅   │ \n"
        " │                                                          │ \n"
        " │   URI: ray://raytest1-head-svc.ns.svc:10001              │ \n"
        " │                                                          │ \n"
        " │   Dashboard🔗                                            │ \n"
        " │                                                          │ \n"
        " ╰──────────────────────────────────────────────────────────╯ \n"
        "                 🚀 CodeFlare Cluster Status 🚀                 \n"
        "                                                                \n"
        " ╭────────────────────────────────────────────────────────────╮ \n"
        " │   Name                                                     │ \n"
        " │   raytest2                                   Inactive ❌   │ \n"
        " │                                                            │ \n"
        " │   URI: ray://raytest2-head-svc.ns.svc:10001                │ \n"
        " │                                                            │ \n"
        " │   Dashboard🔗                                              │ \n"
        " │                                                            │ \n"
        " ╰────────────────────────────────────────────────────────────╯ \n"
    )

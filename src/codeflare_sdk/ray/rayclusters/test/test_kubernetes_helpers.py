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
Tests for Kubernetes helper mixin utilities.

These tests focus on accelerator helpers that do not require a cluster.
"""

from types import SimpleNamespace

import pytest
from kubernetes.client.rest import ApiException

from codeflare_sdk.ray.cluster.status import RayClusterStatus


def test_head_worker_gpu_count(simple_cluster):
    """
    Validate GPU counting logic for head and worker accelerators.

    This checks the helper returns consistent aggregate values.
    """
    simple_cluster.head_accelerators = {"nvidia.com/gpu": 1}
    simple_cluster.worker_accelerators = {"nvidia.com/gpu": 2}

    head_count, worker_count = simple_cluster._head_worker_gpu_count()
    assert head_count == 1
    assert worker_count == 2


def test_head_worker_accelerators_map(simple_cluster):
    """
    Validate accelerator resource map conversion.

    This ensures accelerator configs map to Ray resource names.
    Note: GPU is filtered out (handled via num-gpus parameter), so we test with TPU.
    """
    # Accelerator configs are already merged in __post_init__
    # Use TPU which is not in FORBIDDEN_CUSTOM_RESOURCE_TYPES
    simple_cluster.head_accelerators = {"google.com/tpu": 1}
    simple_cluster.worker_accelerators = {"google.com/tpu": 2}

    head_map, worker_map = simple_cluster._head_worker_accelerators()
    assert head_map["TPU"] == 1
    assert worker_map["TPU"] == 2


def test_head_worker_gpu_count_no_gpus(simple_cluster):
    """
    Ensure GPU count is zero when no GPUs configured.
    """
    simple_cluster.head_accelerators = {}
    simple_cluster.worker_accelerators = {}
    head_count, worker_count = simple_cluster._head_worker_gpu_count()
    assert head_count == 0
    assert worker_count == 0


def test_head_worker_gpu_count_multiple_gpu_types(simple_cluster):
    """
    Ensure GPU counts aggregate across multiple GPU types.
    """
    simple_cluster.head_accelerators = {"nvidia.com/gpu": 1, "intel.com/gpu": 2}
    simple_cluster.worker_accelerators = {"nvidia.com/gpu": 3}
    head_count, worker_count = simple_cluster._head_worker_gpu_count()
    assert head_count == 3
    assert worker_count == 3


def test_head_worker_accelerators_forbidden_types(simple_cluster):
    """
    Ensure forbidden resource types are excluded from accelerator mapping.
    """
    simple_cluster.accelerator_configs = {"custom.com/cpu": "CPU"}
    simple_cluster.head_accelerators = {"custom.com/cpu": 1}
    simple_cluster.worker_accelerators = {"custom.com/cpu": 2}
    head_map, worker_map = simple_cluster._head_worker_accelerators()
    assert "CPU" not in head_map
    assert "CPU" not in worker_map


def test_extract_status_from_rc_ready(simple_cluster):
    """
    Ensure READY status is extracted from resource dict.
    """
    rc = {"status": {"state": "ready"}}
    assert RayClusterStatus.READY == simple_cluster._extract_status_from_rc(
        rc
    )  # type: ignore[name-defined]


def test_extract_status_from_rc_invalid_state(simple_cluster):
    """
    Ensure invalid state yields UNKNOWN status.
    """
    rc = {"status": {"state": "bogus"}}
    assert RayClusterStatus.UNKNOWN == simple_cluster._extract_status_from_rc(
        rc
    )  # type: ignore[name-defined]


def test_head_worker_extended_resources_from_rc_dict(simple_cluster):
    """
    Ensure extended resources are extracted from RC dict.
    """
    rc = {
        "spec": {
            "workerGroupSpecs": [
                {
                    "template": {
                        "spec": {
                            "containers": [
                                {
                                    "resources": {
                                        "limits": {"cpu": "1", "nvidia.com/gpu": 2}
                                    }
                                }
                            ]
                        }
                    }
                }
            ],
            "headGroupSpec": {
                "template": {
                    "spec": {
                        "containers": [
                            {
                                "resources": {
                                    "limits": {"memory": "1Gi", "custom.com/accel": 1}
                                }
                            }
                        ]
                    }
                }
            },
        }
    }
    head, worker = simple_cluster._head_worker_extended_resources_from_rc_dict(rc)
    assert "nvidia.com/gpu" in worker
    assert "custom.com/accel" in head
    assert "cpu" not in worker
    assert "memory" not in head


def test_is_openshift_cluster_true(simple_cluster, monkeypatch):
    """
    Ensure OpenShift detection returns True when route API present.
    """
    import codeflare_sdk.ray.rayclusters.kubernetes_helpers as kh

    monkeypatch.setattr(kh, "_openshift_cluster_cache", None)

    def fake_get_api_versions():
        return SimpleNamespace(
            groups=[
                SimpleNamespace(
                    versions=[SimpleNamespace(group_version="route.openshift.io/v1")]
                )
            ]
        )

    class FakeApis:
        def __init__(self, *_args, **_kwargs):
            pass

        def get_api_versions(self):
            return fake_get_api_versions()

    monkeypatch.setattr(
        "codeflare_sdk.ray.rayclusters.kubernetes_helpers.client.ApisApi",
        FakeApis,
    )
    assert simple_cluster._is_openshift_cluster() is True


def test_is_openshift_cluster_false(simple_cluster, monkeypatch):
    """
    Ensure OpenShift detection returns False when route API missing.
    """
    # Reset the cache before testing.
    import codeflare_sdk.ray.rayclusters.kubernetes_helpers as kh

    monkeypatch.setattr(kh, "_openshift_cluster_cache", None)

    def fake_get_api_versions():
        return SimpleNamespace(
            groups=[SimpleNamespace(versions=[SimpleNamespace(group_version="v1")])]
        )

    class FakeApis:
        def __init__(self, *_args, **_kwargs):
            pass

        def get_api_versions(self):
            return fake_get_api_versions()

    monkeypatch.setattr(
        "codeflare_sdk.ray.rayclusters.kubernetes_helpers.client.ApisApi",
        FakeApis,
    )
    assert simple_cluster._is_openshift_cluster() is False


def test_get_dashboard_url_from_httproute_found(simple_cluster, monkeypatch):
    """
    Ensure HTTPRoute dashboard URL is constructed when found.
    """

    def fake_list_cluster_custom_object(*_args, **_kwargs):
        return {
            "items": [{"spec": {"parentRefs": [{"name": "gw", "namespace": "gw-ns"}]}}]
        }

    def fake_get_namespaced_custom_object(*_args, **_kwargs):
        return {"spec": {"listeners": [{"hostname": "example.com"}]}}

    class FakeCustomObjects:
        def list_cluster_custom_object(self, *args, **kwargs):
            return fake_list_cluster_custom_object(*args, **kwargs)

        def get_namespaced_custom_object(self, *args, **kwargs):
            return fake_get_namespaced_custom_object(*args, **kwargs)

    monkeypatch.setattr(
        "codeflare_sdk.ray.rayclusters.kubernetes_helpers.config_check", lambda: None
    )
    monkeypatch.setattr(
        "codeflare_sdk.ray.rayclusters.kubernetes_helpers.client.CustomObjectsApi",
        lambda *_args, **_kwargs: FakeCustomObjects(),
    )
    url = simple_cluster._get_dashboard_url_from_httproute("demo", "default")
    assert url == "https://example.com/ray/default/demo"


def test_get_dashboard_url_from_httproute_not_found(simple_cluster, monkeypatch):
    """
    Ensure HTTPRoute returns None when not found.
    """

    class FakeCustomObjects:
        def list_cluster_custom_object(self, *args, **kwargs):
            return {"items": []}

    monkeypatch.setattr(
        "codeflare_sdk.ray.rayclusters.kubernetes_helpers.config_check", lambda: None
    )
    monkeypatch.setattr(
        "codeflare_sdk.ray.rayclusters.kubernetes_helpers.client.CustomObjectsApi",
        lambda *_args, **_kwargs: FakeCustomObjects(),
    )
    url = simple_cluster._get_dashboard_url_from_httproute("demo", "default")
    assert url is None


def test_ray_cluster_status_found(simple_cluster, monkeypatch):
    """
    Ensure ray cluster status is returned for matching resource.
    """

    class FakeCustomObjects:
        def list_namespaced_custom_object(self, *args, **kwargs):
            return {
                "items": [{"metadata": {"name": "demo"}, "status": {"state": "ready"}}]
            }

    monkeypatch.setattr(
        "codeflare_sdk.ray.rayclusters.kubernetes_helpers.config_check", lambda: None
    )
    monkeypatch.setattr(
        "codeflare_sdk.ray.rayclusters.kubernetes_helpers.client.CustomObjectsApi",
        lambda *_args, **_kwargs: FakeCustomObjects(),
    )
    status = simple_cluster._ray_cluster_status("demo", "default")
    assert status == RayClusterStatus.READY


def test_ray_cluster_status_not_found(simple_cluster, monkeypatch):
    """
    Ensure None returned when cluster not found.
    """

    class FakeCustomObjects:
        def list_namespaced_custom_object(self, *args, **kwargs):
            return {"items": []}

    monkeypatch.setattr(
        "codeflare_sdk.ray.rayclusters.kubernetes_helpers.config_check", lambda: None
    )
    monkeypatch.setattr(
        "codeflare_sdk.ray.rayclusters.kubernetes_helpers.client.CustomObjectsApi",
        lambda *_args, **_kwargs: FakeCustomObjects(),
    )
    assert simple_cluster._ray_cluster_status("demo", "default") is None


def test_throw_for_no_raycluster_available(simple_cluster, monkeypatch):
    """
    Ensure RuntimeError raised when RayCluster CRD is missing.
    """

    class FakeCustomObjects:
        def list_namespaced_custom_object(self, *args, **kwargs):
            raise ApiException(status=404)

    monkeypatch.setattr(
        "codeflare_sdk.ray.rayclusters.kubernetes_helpers.client.CustomObjectsApi",
        lambda *_args, **_kwargs: FakeCustomObjects(),
    )
    with pytest.raises(
        RuntimeError, match="RayCluster CustomResourceDefinition unavailable"
    ):
        simple_cluster._throw_for_no_raycluster()


def test_local_queue_exists_true(simple_cluster, monkeypatch):
    """
    Ensure local queue exists returns True when present.
    """
    simple_cluster.local_queue = "queue-a"

    class FakeCustomObjects:
        def list_namespaced_custom_object(self, *args, **kwargs):
            return {"items": [{"metadata": {"name": "queue-a"}}]}

    monkeypatch.setattr(
        "codeflare_sdk.ray.rayclusters.kubernetes_helpers.config_check", lambda: None
    )
    monkeypatch.setattr(
        "codeflare_sdk.ray.rayclusters.kubernetes_helpers.client.CustomObjectsApi",
        lambda *_args, **_kwargs: FakeCustomObjects(),
    )
    assert simple_cluster._local_queue_exists() is True


def test_get_default_local_queue_found(simple_cluster, monkeypatch):
    """
    Ensure default local queue name is returned.
    """

    class FakeCustomObjects:
        def list_namespaced_custom_object(self, *args, **kwargs):
            return {
                "items": [
                    {
                        "metadata": {
                            "name": "queue-a",
                            "annotations": {"kueue.x-k8s.io/default-queue": "true"},
                        }
                    }
                ]
            }

    monkeypatch.setattr(
        "codeflare_sdk.ray.rayclusters.kubernetes_helpers.config_check", lambda: None
    )
    monkeypatch.setattr(
        "codeflare_sdk.ray.rayclusters.kubernetes_helpers.client.CustomObjectsApi",
        lambda *_args, **_kwargs: FakeCustomObjects(),
    )
    assert simple_cluster._get_default_local_queue() == "queue-a"


def test_extract_status_from_rc_unknown(simple_cluster):
    """
    Ensure UNKNOWN status when no status field present.
    """
    rc = {}
    assert RayClusterStatus.UNKNOWN == simple_cluster._extract_status_from_rc(rc)


def test_local_queue_exists_false(simple_cluster, monkeypatch):
    """
    Ensure local queue exists returns False when missing.
    """
    simple_cluster.local_queue = "queue-a"

    class FakeCustomObjects:
        def list_namespaced_custom_object(self, *args, **kwargs):
            return {"items": []}

    monkeypatch.setattr(
        "codeflare_sdk.ray.rayclusters.kubernetes_helpers.config_check", lambda: None
    )
    monkeypatch.setattr(
        "codeflare_sdk.ray.rayclusters.kubernetes_helpers.client.CustomObjectsApi",
        lambda *_args, **_kwargs: FakeCustomObjects(),
    )
    assert simple_cluster._local_queue_exists() is False


def test_get_default_local_queue_not_found(simple_cluster, monkeypatch):
    """
    Ensure None returned when no default queue exists.
    """

    class FakeCustomObjects:
        def list_namespaced_custom_object(self, *args, **kwargs):
            return {"items": [{"metadata": {"name": "queue-a", "annotations": {}}}]}

    monkeypatch.setattr(
        "codeflare_sdk.ray.rayclusters.kubernetes_helpers.config_check", lambda: None
    )
    monkeypatch.setattr(
        "codeflare_sdk.ray.rayclusters.kubernetes_helpers.client.CustomObjectsApi",
        lambda *_args, **_kwargs: FakeCustomObjects(),
    )
    assert simple_cluster._get_default_local_queue() is None


def test_throw_for_no_raycluster_other_error(simple_cluster, monkeypatch):
    """
    Ensure RuntimeError raised for unexpected errors.
    """

    class FakeCustomObjects:
        def list_namespaced_custom_object(self, *args, **kwargs):
            raise ApiException(status=500)

    monkeypatch.setattr(
        "codeflare_sdk.ray.rayclusters.kubernetes_helpers.client.CustomObjectsApi",
        lambda *_args, **_kwargs: FakeCustomObjects(),
    )
    with pytest.raises(
        RuntimeError, match="Failed to get RayCluster CustomResourceDefinition"
    ):
        simple_cluster._throw_for_no_raycluster()

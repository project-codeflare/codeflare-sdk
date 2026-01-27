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
Tests for rayclusters module-level utilities.
"""

from types import SimpleNamespace

from codeflare_sdk.ray.rayclusters import RayCluster
from codeflare_sdk.ray.rayclusters import utils as raycluster_utils
from codeflare_sdk.ray.cluster.status import RayClusterStatus


def test_list_all_clusters_success(monkeypatch):
    """Ensure list_all_clusters returns clusters and prints when enabled."""
    cluster = RayCluster(name="demo", namespace="default")
    monkeypatch.setattr(
        raycluster_utils, "_get_ray_clusters", lambda *_args, **_kwargs: [cluster]
    )
    printed = {"count": 0}

    def fake_print_clusters(_clusters):
        printed["count"] += 1

    monkeypatch.setattr(
        "codeflare_sdk.ray.cluster.pretty_print.print_clusters",
        fake_print_clusters,
    )
    result = raycluster_utils.list_all_clusters("default", print_to_console=True)
    assert result == [cluster]
    assert printed["count"] == 1


def test_list_all_clusters_no_print(monkeypatch):
    """Ensure list_all_clusters does not print when disabled."""
    cluster = RayCluster(name="demo", namespace="default")
    monkeypatch.setattr(
        raycluster_utils, "_get_ray_clusters", lambda *_args, **_kwargs: [cluster]
    )
    monkeypatch.setattr(
        "codeflare_sdk.ray.cluster.pretty_print.print_clusters",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("should not print")
        ),
    )
    result = raycluster_utils.list_all_clusters("default", print_to_console=False)
    assert result == [cluster]


def test_list_all_queued_success(monkeypatch):
    """Ensure list_all_queued returns filtered clusters and prints."""
    cluster = RayCluster(name="demo", namespace="default")
    monkeypatch.setattr(
        raycluster_utils, "_get_ray_clusters", lambda *_args, **_kwargs: [cluster]
    )
    monkeypatch.setattr(
        "codeflare_sdk.ray.cluster.pretty_print.print_ray_clusters_status",
        lambda *_args, **_kwargs: None,
    )
    result = raycluster_utils.list_all_queued("default", print_to_console=True)
    assert result == [cluster]


def test_get_cluster_success(monkeypatch):
    """Ensure get_cluster returns RayCluster and updates resource_yaml."""
    resource = {
        "spec": {
            "headGroupSpec": {
                "template": {
                    "spec": {
                        "containers": [
                            {
                                "resources": {
                                    "limits": {"cpu": "1", "memory": "1Gi"},
                                    "requests": {"cpu": "1", "memory": "1Gi"},
                                }
                            }
                        ]
                    }
                }
            },
            "workerGroupSpecs": [
                {
                    "minReplicas": 1,
                    "template": {
                        "spec": {
                            "containers": [
                                {
                                    "resources": {
                                        "limits": {"cpu": "1", "memory": "1Gi"},
                                        "requests": {"cpu": "1", "memory": "1Gi"},
                                    }
                                }
                            ]
                        }
                    },
                }
            ],
        },
    }
    monkeypatch.setattr(raycluster_utils, "config_check", lambda: None)

    class FakeCustomObjects:
        def get_namespaced_custom_object(self, *args, **kwargs):
            return resource

    monkeypatch.setattr(
        "codeflare_sdk.ray.rayclusters.utils.client.CustomObjectsApi",
        lambda *_args, **_kwargs: FakeCustomObjects(),
    )
    monkeypatch.setattr(
        RayCluster,
        "_head_worker_extended_resources_from_rc_dict",
        lambda *_args, **_kwargs: ({}, {}),
    )
    cluster = raycluster_utils.get_cluster("demo", "default")
    assert isinstance(cluster, RayCluster)
    assert cluster._resource_yaml == resource


def test_get_cluster_not_found(monkeypatch):
    """Ensure get_cluster returns error handler result on failure."""
    monkeypatch.setattr(raycluster_utils, "config_check", lambda: None)

    class FakeCustomObjects:
        def get_namespaced_custom_object(self, *args, **kwargs):
            raise Exception("not found")

    monkeypatch.setattr(
        "codeflare_sdk.ray.rayclusters.utils.client.CustomObjectsApi",
        lambda *_args, **_kwargs: FakeCustomObjects(),
    )
    monkeypatch.setattr(
        raycluster_utils, "_kube_api_error_handling", lambda *_args, **_kwargs: "error"
    )
    assert raycluster_utils.get_cluster("demo", "default") == "error"


def test_get_ray_clusters_with_filter(monkeypatch):
    """Ensure _get_ray_clusters applies status filter."""
    monkeypatch.setattr(raycluster_utils, "config_check", lambda: None)

    class FakeCustomObjects:
        def list_namespaced_custom_object(self, *args, **kwargs):
            return {
                "items": [{"metadata": {"name": "demo"}, "status": {"state": "ready"}}]
            }

    monkeypatch.setattr(
        "codeflare_sdk.ray.rayclusters.utils.client.CustomObjectsApi",
        lambda *_args, **_kwargs: FakeCustomObjects(),
    )
    monkeypatch.setattr(
        raycluster_utils,
        "_map_to_ray_cluster",
        lambda *_args, **_kwargs: RayCluster(name="demo", namespace="default"),
    )
    monkeypatch.setattr(
        RayCluster,
        "_extract_status_from_rc",
        lambda *_args, **_kwargs: RayClusterStatus.READY,
    )
    clusters = raycluster_utils._get_ray_clusters(filter=[RayClusterStatus.READY])
    assert len(clusters) == 1


def test_map_to_ray_cluster_success():
    """Ensure _map_to_ray_cluster maps a resource into RayCluster."""
    rc = {
        "metadata": {"name": "demo", "namespace": "default"},
        "spec": {
            "workerGroupSpecs": [
                {
                    "replicas": 1,
                    "template": {
                        "spec": {
                            "containers": [
                                {
                                    "resources": {
                                        "limits": {"cpu": "1", "memory": "1Gi"},
                                        "requests": {"cpu": "1", "memory": "1Gi"},
                                    }
                                }
                            ]
                        }
                    },
                }
            ],
            "headGroupSpec": {
                "template": {
                    "spec": {
                        "containers": [
                            {
                                "resources": {
                                    "limits": {"cpu": "1", "memory": "1Gi"},
                                    "requests": {"cpu": "1", "memory": "1Gi"},
                                }
                            }
                        ]
                    }
                }
            },
        },
    }
    cluster = raycluster_utils._map_to_ray_cluster(rc)
    assert cluster.name == "demo"


def test_remove_autogenerated_fields():
    """Ensure autogenerated fields removed recursively."""
    resource = {
        "metadata": {"creationTimestamp": "now", "labels": {"a": "b"}},
        "status": {"state": "ready"},
        "nested": {"uid": "123", "keep": "ok"},
        "items": [{"managedFields": "x", "keep": "y"}],
    }
    raycluster_utils._remove_autogenerated_fields(resource)
    assert "creationTimestamp" not in resource["metadata"]
    assert "status" not in resource
    assert "uid" not in resource["nested"]
    assert "managedFields" not in resource["items"][0]


def test_map_to_ray_cluster_malformed_spec_missing_metadata():
    """Ensure _map_to_ray_cluster returns None for specs missing metadata."""
    malformed_rc = {"spec": {"headGroupSpec": {}, "workerGroupSpecs": []}}
    result = raycluster_utils._map_to_ray_cluster(malformed_rc)
    assert result is None


def test_map_to_ray_cluster_malformed_spec_missing_spec():
    """Ensure _map_to_ray_cluster returns None for specs missing spec field."""
    malformed_rc = {"metadata": {"name": "broken", "namespace": "default"}}
    result = raycluster_utils._map_to_ray_cluster(malformed_rc)
    assert result is None


def test_map_to_ray_cluster_malformed_spec_empty_workers():
    """Ensure _map_to_ray_cluster handles empty workerGroupSpecs."""
    rc = {
        "metadata": {"name": "no-workers", "namespace": "default"},
        "spec": {"headGroupSpec": {}, "workerGroupSpecs": []},
    }
    result = raycluster_utils._map_to_ray_cluster(rc)
    assert result is None


def test_map_to_ray_cluster_malformed_spec_missing_containers():
    """Ensure _map_to_ray_cluster handles missing containers."""
    rc = {
        "metadata": {"name": "no-containers", "namespace": "default"},
        "spec": {
            "headGroupSpec": {"template": {"spec": {"containers": []}}},
            "workerGroupSpecs": [
                {"replicas": 1, "template": {"spec": {"containers": []}}}
            ],
        },
    }
    result = raycluster_utils._map_to_ray_cluster(rc)
    assert result is None


def test_map_to_ray_cluster_malformed_spec_missing_resources():
    """Ensure _map_to_ray_cluster handles missing resources field."""
    rc = {
        "metadata": {"name": "no-resources", "namespace": "default"},
        "spec": {
            "headGroupSpec": {"template": {"spec": {"containers": [{"name": "ray"}]}}},
            "workerGroupSpecs": [
                {
                    "replicas": 1,
                    "template": {"spec": {"containers": [{"name": "ray"}]}},
                }
            ],
        },
    }
    result = raycluster_utils._map_to_ray_cluster(rc)
    assert result is None

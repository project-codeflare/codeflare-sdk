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
Lightweight lifecycle tests.

These tests only verify that lifecycle methods are present, avoiding
Kubernetes calls that require a live cluster.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from codeflare_sdk.ray.cluster.status import CodeFlareClusterStatus, RayClusterStatus


def test_lifecycle_methods_present(simple_cluster):
    """
    Confirm the RayCluster instance exposes lifecycle operations.

    This guards against refactors that drop methods from the class.
    """
    expected_methods = [
        "apply",
        "down",
        "status",
        "wait_ready",
        "is_dashboard_ready",
        "cluster_uri",
        "cluster_dashboard_uri",
        "details",
    ]
    for method_name in expected_methods:
        assert callable(getattr(simple_cluster, method_name))


def test_get_current_status_without_name(simple_cluster):
    """Ensure unknown status when name is missing."""
    simple_cluster.name = None
    assert simple_cluster._get_current_status() == RayClusterStatus.UNKNOWN


def test_get_current_status_with_name(simple_cluster, monkeypatch):
    """Ensure status returned from _ray_cluster_status."""
    monkeypatch.setattr(
        simple_cluster, "_ray_cluster_status", lambda *_args: RayClusterStatus.READY
    )
    assert simple_cluster._get_current_status() == RayClusterStatus.READY


def test_dashboard_property_without_name(simple_cluster):
    """Ensure dashboard property returns error string without name."""
    simple_cluster.name = None
    assert "Dashboard not available" in simple_cluster.dashboard


def test_cluster_uri_without_name(simple_cluster):
    """Ensure cluster_uri raises when name is missing."""
    simple_cluster.name = None
    with pytest.raises(ValueError, match="name is required"):
        simple_cluster.cluster_uri()


def test_cluster_uri_format(simple_cluster, monkeypatch):
    """Ensure cluster_uri format is correct."""
    monkeypatch.setattr(simple_cluster, "_check_tls_certs_exist", lambda: None)
    assert simple_cluster.cluster_uri().startswith("ray://")


def test_apply_without_name(simple_cluster):
    """Ensure apply raises when name missing."""
    simple_cluster.name = None
    with pytest.raises(ValueError, match="name is required"):
        simple_cluster.apply()


def test_down_without_name(simple_cluster):
    """Ensure down raises when name missing."""
    simple_cluster.name = None
    with pytest.raises(ValueError, match="name is required"):
        simple_cluster.down()


def test_apply_success(simple_cluster, monkeypatch):
    """Ensure apply calls server-side apply helpers."""
    simple_cluster.name = "demo"
    simple_cluster.namespace = "default"
    monkeypatch.setattr(simple_cluster, "_ensure_namespace", lambda: None)
    monkeypatch.setattr(
        simple_cluster, "_build_standalone_ray_cluster", lambda: {"kind": "RayCluster"}
    )
    monkeypatch.setattr(simple_cluster, "_throw_for_no_raycluster", lambda: None)
    monkeypatch.setattr(
        "codeflare_sdk.ray.rayclusters.lifecycle.config_check",
        lambda: None,
    )
    monkeypatch.setattr(
        "codeflare_sdk.ray.rayclusters.lifecycle.get_api_client",
        lambda: object(),
    )

    class FakeResources:
        def get(self, *args, **kwargs):
            return "api"

    class FakeDynamic:
        def __init__(self, *_args, **_kwargs):
            self.resources = FakeResources()

    apply_calls = {"count": 0}

    def fake_apply(*_args, **_kwargs):
        apply_calls["count"] += 1

    monkeypatch.setattr(
        "codeflare_sdk.ray.rayclusters.lifecycle.DynamicClient",
        FakeDynamic,
    )
    monkeypatch.setattr(simple_cluster, "_apply_ray_cluster", fake_apply)
    monkeypatch.setattr(
        simple_cluster, "_generate_tls_certs_with_wait", lambda *_args, **_kwargs: True
    )
    simple_cluster.apply()
    assert apply_calls["count"] == 1


def test_down_success(simple_cluster, monkeypatch):
    """Ensure down calls delete resources."""
    simple_cluster.name = "demo"
    simple_cluster.namespace = "default"
    monkeypatch.setattr(simple_cluster, "_ensure_namespace", lambda: None)
    monkeypatch.setattr(simple_cluster, "_throw_for_no_raycluster", lambda: None)
    monkeypatch.setattr(
        "codeflare_sdk.ray.rayclusters.lifecycle.config_check",
        lambda: None,
    )
    monkeypatch.setattr(
        "codeflare_sdk.ray.rayclusters.lifecycle.get_api_client",
        lambda: object(),
    )

    delete_calls = {"count": 0}

    def fake_delete(*_args, **_kwargs):
        delete_calls["count"] += 1

    monkeypatch.setattr(simple_cluster, "_delete_resources", fake_delete)
    monkeypatch.setattr(
        "codeflare_sdk.common.utils.generate_cert.cleanup_tls_cert",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "codeflare_sdk.ray.rayclusters.lifecycle.client.CustomObjectsApi",
        lambda *_args, **_kwargs: object(),
    )
    simple_cluster.down()
    assert delete_calls["count"] == 1


def test_cluster_dashboard_uri_httproute(simple_cluster, monkeypatch):
    """Ensure HTTPRoute URL is returned when available."""
    monkeypatch.setattr(
        "codeflare_sdk.ray.rayclusters.lifecycle.config_check",
        lambda: None,
    )
    monkeypatch.setattr(
        simple_cluster,
        "_get_dashboard_url_from_httproute",
        lambda *_args: "http://example.com",
    )
    simple_cluster.name = "demo"
    simple_cluster.namespace = "default"
    assert simple_cluster.cluster_dashboard_uri() == "http://example.com"


def test_local_client_url(simple_cluster, monkeypatch):
    """Ensure local_client_url uses ingress domain."""
    monkeypatch.setattr(simple_cluster, "_check_tls_certs_exist", lambda: None)
    monkeypatch.setattr(simple_cluster, "_get_ingress_domain", lambda: "example.com")
    assert simple_cluster.local_client_url() == "ray://example.com"


def test_status_ready(simple_cluster, monkeypatch):
    """Ensure status maps READY correctly."""
    monkeypatch.setattr(
        simple_cluster, "_ray_cluster_status", lambda *_args: RayClusterStatus.READY
    )
    status, ready = simple_cluster.status(print_to_console=False)
    assert status == CodeFlareClusterStatus.READY
    assert ready is True


def test_status_unknown_when_missing(simple_cluster, monkeypatch):
    """Ensure status UNKNOWN when cluster missing."""
    monkeypatch.setattr(simple_cluster, "_ray_cluster_status", lambda *_args: None)
    status, ready = simple_cluster.status(print_to_console=False)
    assert status == CodeFlareClusterStatus.UNKNOWN
    assert ready is False


def test_wait_ready_timeout(simple_cluster, monkeypatch):
    """Ensure wait_ready times out when cluster not ready."""
    monkeypatch.setattr(
        simple_cluster,
        "status",
        lambda *args, **kwargs: (CodeFlareClusterStatus.STARTING, False),
    )
    monkeypatch.setattr(
        "codeflare_sdk.ray.rayclusters.lifecycle.sleep", lambda *_args: None
    )
    with pytest.raises(TimeoutError, match="timed out"):
        simple_cluster.wait_ready(timeout=5, dashboard_check=False)


def test_wait_ready_success(simple_cluster, monkeypatch):
    """Ensure wait_ready exits when cluster is ready."""
    calls = {"count": 0}

    def fake_status(*_args, **_kwargs):
        calls["count"] += 1
        if calls["count"] < 2:
            return CodeFlareClusterStatus.STARTING, False
        return CodeFlareClusterStatus.READY, True

    monkeypatch.setattr(simple_cluster, "status", fake_status)
    monkeypatch.setattr(
        "codeflare_sdk.ray.rayclusters.lifecycle.sleep", lambda *_args: None
    )
    monkeypatch.setattr(
        "codeflare_sdk.common.utils.generate_cert.generate_tls_cert",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "codeflare_sdk.common.utils.generate_cert.export_env",
        lambda *_args, **_kwargs: None,
    )
    simple_cluster.wait_ready(timeout=10, dashboard_check=False)


def test_is_dashboard_ready_success(simple_cluster, monkeypatch):
    """Ensure dashboard is ready on 200 response."""
    monkeypatch.setattr(
        simple_cluster, "cluster_dashboard_uri", lambda: "http://example.com"
    )
    monkeypatch.setattr(
        "codeflare_sdk.ray.rayclusters.lifecycle.requests.get",
        lambda *_args, **_kwargs: SimpleNamespace(status_code=200),
    )
    assert simple_cluster.is_dashboard_ready() is True


def test_is_dashboard_ready_error(simple_cluster, monkeypatch):
    """Ensure dashboard readiness returns False on errors."""
    monkeypatch.setattr(
        simple_cluster, "cluster_dashboard_uri", lambda: "http://example.com"
    )

    def raise_error(*_args, **_kwargs):
        raise Exception("boom")

    monkeypatch.setattr(
        "codeflare_sdk.ray.rayclusters.lifecycle.requests.get", raise_error
    )
    assert simple_cluster.is_dashboard_ready() is False


def test_job_client_cached(simple_cluster, monkeypatch):
    """Ensure job client is cached after first creation."""
    fake_client = object()
    monkeypatch.setattr(simple_cluster, "_check_tls_certs_exist", lambda: None)
    monkeypatch.setattr(simple_cluster, "_is_openshift_cluster", lambda: False)
    monkeypatch.setattr(
        simple_cluster, "cluster_dashboard_uri", lambda: "http://example.com"
    )
    monkeypatch.setattr(
        "codeflare_sdk.ray.rayclusters.lifecycle.JobSubmissionClient",
        lambda *_args, **_kwargs: fake_client,
    )
    assert simple_cluster.job_client is fake_client
    assert simple_cluster.job_client is fake_client


def test_list_jobs(simple_cluster):
    """Ensure list_jobs forwards to job_client."""
    simple_cluster._job_submission_client = MagicMock()
    simple_cluster._job_submission_client.list_jobs.return_value = ["job-1"]
    assert simple_cluster.list_jobs() == ["job-1"]


def test_job_status(simple_cluster):
    """Ensure job_status forwards to job_client."""
    simple_cluster._job_submission_client = MagicMock()
    simple_cluster._job_submission_client.get_job_status.return_value = "SUCCEEDED"
    assert simple_cluster.job_status("id") == "SUCCEEDED"


def test_job_logs(simple_cluster):
    """Ensure job_logs forwards to job_client."""
    simple_cluster._job_submission_client = MagicMock()
    simple_cluster._job_submission_client.get_job_logs.return_value = "logs"
    assert simple_cluster.job_logs("id") == "logs"


def test_client_headers(simple_cluster, monkeypatch):
    """Ensure client headers include authorization."""
    fake_config = SimpleNamespace(get_api_key_with_prefix=lambda *_args: "token")
    monkeypatch.setattr(
        "codeflare_sdk.ray.rayclusters.lifecycle.get_api_client",
        lambda: SimpleNamespace(configuration=fake_config),
    )
    assert simple_cluster._client_headers["Authorization"] == "token"


def test_client_verify_tls(simple_cluster, monkeypatch):
    """Ensure TLS verification follows OpenShift and verify_tls flag."""
    monkeypatch.setattr(simple_cluster, "_is_openshift_cluster", lambda: True)
    simple_cluster.verify_tls = True
    assert simple_cluster._client_verify_tls is True


def test_ca_secret_exists_false(simple_cluster, monkeypatch):
    """Ensure _ca_secret_exists returns False when no matching secret."""

    class FakeCoreV1:
        def list_namespaced_secret(self, *_args, **_kwargs):
            return SimpleNamespace(items=[])

    monkeypatch.setattr(
        "codeflare_sdk.ray.rayclusters.lifecycle.client.CoreV1Api",
        lambda *_args, **_kwargs: FakeCoreV1(),
    )
    assert simple_cluster._ca_secret_exists() is False


def test_ca_secret_exists_true(simple_cluster, monkeypatch):
    """Ensure _ca_secret_exists returns True when matching secret exists."""

    class FakeSecret:
        def __init__(self, name):
            self.metadata = SimpleNamespace(name=name)

    class FakeCoreV1:
        def list_namespaced_secret(self, *_args, **_kwargs):
            return SimpleNamespace(
                items=[FakeSecret(f"{simple_cluster.name}-ca-secret-1")]
            )

    monkeypatch.setattr(
        "codeflare_sdk.ray.rayclusters.lifecycle.client.CoreV1Api",
        lambda *_args, **_kwargs: FakeCoreV1(),
    )
    assert simple_cluster._ca_secret_exists() is True


def test_check_tls_certs_exist_warning(simple_cluster, monkeypatch, tmp_path, capsys):
    """Ensure warning is printed when certs are missing."""
    monkeypatch.setattr(
        "codeflare_sdk.common.utils.generate_cert._get_tls_base_dir",
        lambda: tmp_path,
    )
    simple_cluster._check_tls_certs_exist()
    assert "TLS Certificates Not Found" in capsys.readouterr().out


def test_generate_tls_certs_with_wait_timeout(simple_cluster, monkeypatch):
    """Ensure timeout returns False when CA secret not available."""
    monkeypatch.setattr(simple_cluster, "_ca_secret_exists", lambda: False)
    monkeypatch.setattr(
        "codeflare_sdk.ray.rayclusters.lifecycle.sleep", lambda *_args: None
    )
    assert simple_cluster._generate_tls_certs_with_wait(timeout=1) is False


def test_refresh_certificates(simple_cluster, monkeypatch):
    """Ensure refresh_certificates calls generate_cert helpers."""
    monkeypatch.setattr(
        "codeflare_sdk.common.utils.generate_cert.refresh_tls_cert",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "codeflare_sdk.common.utils.generate_cert.export_env",
        lambda *_args, **_kwargs: None,
    )
    simple_cluster.refresh_certificates()


def test_ensure_namespace_sets_default(simple_cluster, monkeypatch):
    """Ensure namespace is set when missing."""
    simple_cluster.namespace = None
    monkeypatch.setattr(
        "codeflare_sdk.ray.rayclusters.lifecycle.get_current_namespace",
        lambda: "default",
    )
    simple_cluster._ensure_namespace()
    assert simple_cluster.namespace == "default"


def test_ensure_namespace_invalid_type(simple_cluster, monkeypatch):
    """Ensure non-string namespace triggers TypeError."""
    simple_cluster.namespace = None
    monkeypatch.setattr(
        "codeflare_sdk.ray.rayclusters.lifecycle.get_current_namespace",
        lambda: 123,
    )
    with pytest.raises(TypeError, match="Namespace"):
        simple_cluster._ensure_namespace()


# -------------------------------------------------------------------------
# Dashboard URL Helper Tests
# -------------------------------------------------------------------------


def test_get_dashboard_url_success(simple_cluster, monkeypatch):
    """Ensure get_dashboard_url returns URL when available."""
    monkeypatch.setattr(
        simple_cluster, "cluster_dashboard_uri", lambda: "https://example.com/dashboard"
    )
    assert simple_cluster.get_dashboard_url() == "https://example.com/dashboard"


def test_get_dashboard_url_http(simple_cluster, monkeypatch):
    """Ensure get_dashboard_url works with http URLs."""
    monkeypatch.setattr(
        simple_cluster, "cluster_dashboard_uri", lambda: "http://localhost:8265"
    )
    assert simple_cluster.get_dashboard_url() == "http://localhost:8265"


def test_get_dashboard_url_not_available(simple_cluster, monkeypatch):
    """Ensure get_dashboard_url returns None when dashboard not available."""
    monkeypatch.setattr(
        simple_cluster,
        "cluster_dashboard_uri",
        lambda: "Dashboard not available yet, have you run cluster.apply()?",
    )
    assert simple_cluster.get_dashboard_url() is None


def test_get_dashboard_url_error_message(simple_cluster, monkeypatch):
    """Ensure get_dashboard_url returns None for any error message."""
    monkeypatch.setattr(
        simple_cluster,
        "cluster_dashboard_uri",
        lambda: "Some error occurred",
    )
    assert simple_cluster.get_dashboard_url() is None


def test_get_dashboard_url_none(simple_cluster, monkeypatch):
    """Ensure get_dashboard_url handles None from cluster_dashboard_uri."""
    monkeypatch.setattr(
        simple_cluster,
        "cluster_dashboard_uri",
        lambda: None,
    )
    assert simple_cluster.get_dashboard_url() is None


# -------------------------------------------------------------------------
# is_dashboard_ready Tests
# -------------------------------------------------------------------------


def test_is_dashboard_ready_returns_false_when_uri_none(simple_cluster, monkeypatch):
    """Ensure is_dashboard_ready returns False when URI is None."""
    monkeypatch.setattr(simple_cluster, "cluster_dashboard_uri", lambda: None)
    assert simple_cluster.is_dashboard_ready() is False


def test_is_dashboard_ready_returns_false_for_error_message(
    simple_cluster, monkeypatch
):
    """Ensure is_dashboard_ready returns False for error messages."""
    monkeypatch.setattr(
        simple_cluster,
        "cluster_dashboard_uri",
        lambda: "Dashboard not available yet",
    )
    assert simple_cluster.is_dashboard_ready() is False


# -------------------------------------------------------------------------
# create_resource Tests
# -------------------------------------------------------------------------


def test_create_resource_without_name(simple_cluster):
    """Ensure create_resource raises when name is missing."""
    simple_cluster.name = None
    with pytest.raises(ValueError, match="name is required"):
        simple_cluster.create_resource()


def test_create_resource_success(simple_cluster, monkeypatch):
    """Ensure create_resource builds yaml."""
    simple_cluster.name = "test-cluster"
    simple_cluster.namespace = "test-ns"
    monkeypatch.setattr(simple_cluster, "_ensure_namespace", lambda: None)
    monkeypatch.setattr(
        simple_cluster, "_build_standalone_ray_cluster", lambda: {"kind": "RayCluster"}
    )
    result = simple_cluster.create_resource()
    assert result == {"kind": "RayCluster"}

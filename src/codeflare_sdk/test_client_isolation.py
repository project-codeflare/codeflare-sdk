# Copyright 2026 IBM, Red Hat
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

"""Regression tests for RHOAIENG-98754 PR 1.

Covers instance-bound Kubernetes client handling (P1-1), the
``cf.jobs.submit()`` execution-target contract (P1-5), and facade namespace
resolution (P2-8).
"""

import pytest
from unittest.mock import MagicMock

from codeflare_sdk import ClusterConfiguration
from codeflare_sdk.common.kubernetes_cluster import auth


@pytest.fixture
def recorded_clients(monkeypatch):
    """Record the ApiClient each CustomObjectsApi is constructed with."""
    seen = []

    class RecordingCustomObjectsApi:
        def __init__(self, api_client=None):
            self.api_client = api_client
            seen.append(api_client)

        def list_namespaced_custom_object(self, *a, **kw):
            return {"items": []}

        def list_cluster_custom_object(self, *a, **kw):
            return {"items": []}

        def get_namespaced_custom_object(self, group, version, namespace, plural, name):
            return {"metadata": {"name": name, "namespace": namespace}, "spec": {}}

    monkeypatch.setattr("kubernetes.client.CustomObjectsApi", RecordingCustomObjectsApi)
    return seen


@pytest.fixture(autouse=True)
def reset_global_client():
    """Keep the module-level auth state from leaking between tests."""
    original_client, original_path = auth.api_client, auth.config_path
    yield
    auth.api_client, auth.config_path = original_client, original_path
    # _use_api_client's finally should already have reset this; belt and braces
    # so one leaked scope cannot silently green a later test.
    assert auth._active_api_client.get() is None, "scoped client leaked"


def make_codeflare(mocker, client, namespace="test-ns"):
    from codeflare_sdk.codeflare import Codeflare, SDKConfig

    mocker.patch("codeflare_sdk.codeflare.get_k8s_client", return_value=client)
    return Codeflare(SDKConfig(namespace=namespace))


class TestClientIsolation:
    """P1-1: a Codeflare instance must use its own Kubernetes client."""

    def test_cluster_created_by_facade_is_bound_to_that_client(self, mocker):
        client_a = MagicMock(name="client_a")
        cf_a = make_codeflare(mocker, client_a)

        cluster = cf_a.clusters.create(
            ClusterConfiguration(name="training", num_workers=1)
        )

        assert cluster._api_client is client_a

    def test_second_codeflare_does_not_steal_first_clusters_client(
        self, mocker, recorded_clients
    ):
        client_a = MagicMock(name="client_a")
        client_b = MagicMock(name="client_b")
        from codeflare_sdk.codeflare import Codeflare, SDKConfig

        mocker.patch(
            "codeflare_sdk.codeflare.get_k8s_client",
            side_effect=[client_a, client_b],
        )
        cf_a = Codeflare(SDKConfig(namespace="prod"))
        cluster_a = cf_a.clusters.create(
            ClusterConfiguration(name="training", num_workers=1)
        )

        Codeflare(SDKConfig(namespace="dev"))  # cf_b takes over the global

        recorded_clients.clear()
        cluster_a.status(print_to_console=False)

        assert recorded_clients, "expected a Kubernetes API call"
        assert all(c is client_a for c in recorded_clients), (
            f"cluster_a used {recorded_clients!r}, expected only client_a"
        )
        assert client_b not in recorded_clients

    def test_rayjob_created_by_facade_is_bound_to_that_client(self, mocker):
        client_a = MagicMock(name="client_a")
        cf_a = make_codeflare(mocker, client_a)

        job = cf_a.jobs.create(
            name="train", entrypoint="python train.py", cluster_name="existing"
        )

        assert job._api_client is client_a

    def test_cluster_retrieved_by_facade_is_bound_to_that_client(self, mocker):
        """get() must bind the client too, not just create()."""
        import pathlib

        import yaml

        client_a = MagicMock(name="client_a")
        cf_a = make_codeflare(mocker, client_a)

        repo_root = pathlib.Path(__file__).resolve().parents[2]
        fixture = (
            repo_root
            / "tests"
            / "test_cluster_yamls"
            / "ray"
            / "unit-test-all-params.yaml"
        )
        mocker.patch("kubernetes.client.ApisApi.get_api_versions")
        mocker.patch(
            "kubernetes.client.CustomObjectsApi.get_namespaced_custom_object",
            return_value=yaml.safe_load(fixture.read_text()),
        )

        cluster = cf_a.clusters.get(name="test-all-params")

        assert cluster._api_client is client_a

    def test_legacy_cluster_falls_back_to_global_client(self, mocker, recorded_clients):
        """Backward compatibility: Cluster(config) keeps using the global client."""
        from codeflare_sdk import Cluster, ClusterConfiguration

        sentinel = MagicMock(name="global_client")
        auth.api_client = sentinel

        cluster = Cluster(ClusterConfiguration(name="legacy", namespace="ns"))
        assert cluster._api_client is None

        recorded_clients.clear()
        cluster.status(print_to_console=False)
        assert all(c is sentinel for c in recorded_clients)

    def test_scoped_client_is_restored_after_operation(self, mocker):
        """The context-scoped client must not leak past the call."""
        client_a = MagicMock(name="client_a")
        cf_a = make_codeflare(mocker, client_a)
        cluster = cf_a.clusters.create(
            ClusterConfiguration(name="training", num_workers=1)
        )

        cluster.status(print_to_console=False)

        assert auth._active_api_client.get() is None


class TestJobSubmitContract:
    """P1-5: the advertised happy path must either work or fail clearly."""

    def test_submit_without_execution_target_raises_clear_error(self, mocker):
        cf = make_codeflare(mocker, MagicMock())

        with pytest.raises(ValueError) as excinfo:
            cf.jobs.submit(name="train-job", entrypoint="python train.py")

        message = str(excinfo.value)
        assert "cluster_name" in message
        assert "cluster_config" in message
        # The old message said "but not both" on the neither-supplied branch.
        assert "but not both" not in message

    def test_submit_accepts_cluster_name_as_named_parameter(self, mocker):
        import inspect
        from codeflare_sdk.codeflare import JobHandler

        params = inspect.signature(JobHandler.submit).parameters
        assert "cluster_name" in params
        assert "cluster_config" in params

    def test_create_accepts_cluster_name_as_named_parameter(self, mocker):
        import inspect
        from codeflare_sdk.codeflare import JobHandler

        params = inspect.signature(JobHandler.create).parameters
        assert "cluster_name" in params
        assert "cluster_config" in params

    def test_submit_with_both_targets_raises(self, mocker):
        from codeflare_sdk import ClusterConfiguration

        cf = make_codeflare(mocker, MagicMock())

        with pytest.raises(ValueError, match="cannot specify both"):
            cf.jobs.submit(
                name="train",
                entrypoint="python train.py",
                cluster_name="existing",
                cluster_config=ClusterConfiguration(name="c", namespace="ns"),
            )


class TestNamespaceResolution:
    """P2-8: deterministic namespace precedence for the facade."""

    def test_explicit_namespace_wins(self, mocker):
        cf = make_codeflare(mocker, MagicMock(), namespace="from-config")

        cluster = cf.clusters.create(
            ClusterConfiguration(name="c", num_workers=1), namespace="explicit"
        )

        assert cluster.config.namespace == "explicit"

    def test_sdk_config_namespace_used_when_no_explicit(self, mocker):
        cf = make_codeflare(mocker, MagicMock(), namespace="from-config")

        cluster = cf.clusters.create(ClusterConfiguration(name="c", num_workers=1))

        assert cluster.config.namespace == "from-config"

    def test_detected_namespace_used_when_config_empty(self, mocker):
        mocker.patch(
            "codeflare_sdk.codeflare.get_current_namespace",
            return_value="detected-ns",
        )
        cf = make_codeflare(mocker, MagicMock(), namespace=None)

        cluster = cf.clusters.create(ClusterConfiguration(name="c", num_workers=1))

        assert cluster.config.namespace == "detected-ns"

    def test_raises_when_no_namespace_can_be_determined(self, mocker):
        mocker.patch("codeflare_sdk.codeflare.get_current_namespace", return_value=None)
        cf = make_codeflare(mocker, MagicMock(), namespace=None)

        with pytest.raises(ValueError, match="[Nn]amespace"):
            cf.clusters.create(ClusterConfiguration(name="c", num_workers=1))

    def test_does_not_silently_use_default_namespace(self, mocker):
        mocker.patch("codeflare_sdk.codeflare.get_current_namespace", return_value=None)
        cf = make_codeflare(mocker, MagicMock(), namespace=None)

        with pytest.raises(ValueError):
            cf.clusters.list()


class TestReviewFollowups:
    """Follow-ups from review of PR #1176."""

    def test_rayjob_uses_its_client_after_second_codeflare(
        self, mocker, recorded_clients
    ):
        """Same post-cf_b API-call assertion the Cluster path already has.

        Asserting job._api_client is not enough: it proves the attribute was
        stored, not that a later call resolves through it.
        """
        from codeflare_sdk import ClusterConfiguration
        from codeflare_sdk.codeflare import Codeflare, SDKConfig

        client_a = MagicMock(name="client_a")
        client_b = MagicMock(name="client_b")
        mocker.patch(
            "codeflare_sdk.codeflare.get_k8s_client",
            side_effect=[client_a, client_b],
        )

        cf_a = Codeflare(SDKConfig(namespace="prod"))
        job = cf_a.jobs.create(
            name="train",
            entrypoint="python train.py",
            cluster_config=ClusterConfiguration(name="c", namespace="prod"),
        )

        Codeflare(SDKConfig(namespace="dev"))  # cf_b takes over the global

        recorded_clients.clear()
        job._build_rayjob_cr()

        assert recorded_clients, "expected a Kubernetes API call"
        assert all(c is client_a for c in recorded_clients), (
            f"rayjob used {recorded_clients!r}, expected only client_a"
        )
        assert client_b not in recorded_clients

    def test_cluster_config_check_is_scoped(self, mocker):
        """Cluster.config_check() must run under the instance's client."""
        client_a = MagicMock(name="client_a")
        cf_a = make_codeflare(mocker, client_a)
        cluster = cf_a.clusters.create(ClusterConfiguration(name="c", num_workers=1))

        seen = []
        # cluster.py imports these by name, so patch them there, not on auth.
        mocker.patch(
            "codeflare_sdk.ray.cluster.cluster.config_check",
            side_effect=lambda: seen.append(auth._active_api_client.get()),
        )

        cluster.config_check()

        assert seen == [client_a]

    def test_cluster_client_headers_is_scoped(self, mocker):
        """_client_headers resolves a client, so it must be scoped too."""
        client_a = MagicMock(name="client_a")
        cf_a = make_codeflare(mocker, client_a)
        cluster = cf_a.clusters.create(ClusterConfiguration(name="c", num_workers=1))

        seen = []
        mocker.patch(
            "codeflare_sdk.ray.cluster.cluster.get_api_client",
            side_effect=lambda: seen.append(auth._active_api_client.get()) or client_a,
        )

        cluster._client_headers

        assert seen == [client_a]

    def test_config_check_prefers_scoped_client_over_global(self, mocker):
        """auth.config_check() must honour the scoped client, not just the global.

        Otherwise a scoped operation with no module-level client falls through
        to auto-detection and overwrites the global as a side effect.
        """
        scoped = MagicMock(name="scoped")
        # Both must be cleared: a stale config_path short-circuits the function
        # and would make this test pass without exercising the scoped lookup.
        auth.api_client = None
        auth.config_path = None
        detect = mocker.patch.object(auth, "get_k8s_client")

        with auth._use_api_client(scoped):
            auth.config_check()

        detect.assert_not_called()
        assert auth.api_client is None, "scoped call must not write the global"


class TestFacadePositionalCompat:
    """Review item: namespace must stay positionally accepted."""

    def test_submit_accepts_positional_namespace(self, mocker):
        cf = make_codeflare(mocker, MagicMock())
        mock_rayjob = mocker.patch("codeflare_sdk.codeflare.RayJob")

        cf.jobs.submit("train", "python train.py", "other-ns", cluster_name="c")

        assert mock_rayjob.call_args.kwargs["namespace"] == "other-ns"

    def test_create_accepts_positional_namespace(self, mocker):
        cf = make_codeflare(mocker, MagicMock())
        mock_rayjob = mocker.patch("codeflare_sdk.codeflare.RayJob")

        cf.jobs.create("train", "python train.py", "other-ns", cluster_name="c")

        assert mock_rayjob.call_args.kwargs["namespace"] == "other-ns"


@pytest.fixture
def recorded_apis_clients(monkeypatch):
    """Record the ApiClient each ApisApi is constructed with."""
    seen = []

    class RecordingApisApi:
        def __init__(self, api_client=None):
            seen.append(api_client)

        def get_api_versions(self):
            return type("V", (), {"groups": []})()

    monkeypatch.setattr("kubernetes.client.ApisApi", RecordingApisApi)
    return seen


def two_codeflares(mocker, client_a, client_b):
    """Build cf_a, then cf_b so cf_b owns the module-level global."""
    from codeflare_sdk.codeflare import Codeflare, SDKConfig

    mocker.patch(
        "codeflare_sdk.codeflare.get_k8s_client", side_effect=[client_a, client_b]
    )
    cf_a = Codeflare(SDKConfig(namespace="prod"))
    return cf_a, lambda: Codeflare(SDKConfig(namespace="dev"))


class TestReviewNits:
    """Second review pass on b6b184b."""

    def test_client_verify_tls_is_scoped(self, mocker, recorded_apis_clients):
        """Reached directly, not only via decorated callers."""
        client_a = MagicMock(name="client_a")
        client_b = MagicMock(name="client_b")
        cf_a, make_cf_b = two_codeflares(mocker, client_a, client_b)
        cluster = cf_a.clusters.create(ClusterConfiguration(name="c", num_workers=1))
        make_cf_b()

        recorded_apis_clients.clear()
        cluster._client_verify_tls

        assert recorded_apis_clients, "expected an ApisApi call"
        assert all(c is client_a for c in recorded_apis_clients)
        assert client_b not in recorded_apis_clients

    def test_cluster_uri_is_scoped(self, mocker):
        client_a = MagicMock(name="client_a")
        cf_a = make_codeflare(mocker, client_a)
        cluster = cf_a.clusters.create(ClusterConfiguration(name="c", num_workers=1))

        seen = []
        mocker.patch.object(
            type(cluster),
            "_check_tls_certs_exist",
            lambda self: seen.append(auth._active_api_client.get()),
        )

        cluster.cluster_uri()

        assert seen == [client_a]

    def test_clusters_list_uses_its_client_after_second_codeflare(
        self, mocker, recorded_clients
    ):
        """list() goes through module helpers + ContextVar, not Cluster._api_client."""
        client_a = MagicMock(name="client_a")
        client_b = MagicMock(name="client_b")
        cf_a, make_cf_b = two_codeflares(mocker, client_a, client_b)
        make_cf_b()

        recorded_clients.clear()
        cf_a.clusters.list()

        assert recorded_clients, "expected a Kubernetes API call"
        assert all(c is client_a for c in recorded_clients)
        assert client_b not in recorded_clients

    def test_clusters_list_queued_uses_its_client_after_second_codeflare(
        self, mocker, recorded_clients
    ):
        client_a = MagicMock(name="client_a")
        client_b = MagicMock(name="client_b")
        cf_a, make_cf_b = two_codeflares(mocker, client_a, client_b)
        make_cf_b()

        recorded_clients.clear()
        cf_a.clusters.list_queued()

        assert recorded_clients, "expected a Kubernetes API call"
        assert all(c is client_a for c in recorded_clients)
        assert client_b not in recorded_clients

    def test_rayjob_api_is_built_on_its_own_client(self, mocker, recorded_clients):
        """RayJob captures a client at init; that one must be cf_a's."""
        client_a = MagicMock(name="client_a")
        client_b = MagicMock(name="client_b")
        cf_a, make_cf_b = two_codeflares(mocker, client_a, client_b)
        job = cf_a.jobs.create(
            name="train", entrypoint="python train.py", cluster_name="existing"
        )
        make_cf_b()

        assert job._api.api.api_client is client_a

    def test_facade_runtime_env_type_matches_rayjob(self):
        """Union[..., Any] collapses to Any and documents nothing."""
        import typing

        from codeflare_sdk.codeflare import JobHandler
        from codeflare_sdk.ray.rayjobs.rayjob import RayJob

        facade = typing.get_type_hints(JobHandler.create)["runtime_env"]
        real = typing.get_type_hints(RayJob.__init__)["runtime_env"]
        assert facade == real

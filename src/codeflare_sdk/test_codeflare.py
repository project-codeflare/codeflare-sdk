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

"""Tests for the Codeflare single entrypoint."""

import inspect
import logging
import pytest
from typing import get_overloads, get_type_hints
from unittest.mock import MagicMock
from kube_authkit import AuthConfig


class TestSDKConfig:
    def test_default_config(self):
        from codeflare_sdk.codeflare import SDKConfig

        config = SDKConfig()
        assert config.namespace is None
        assert config.log_level == "WARNING"
        assert isinstance(config.auth, AuthConfig)

    def test_custom_config(self):
        from codeflare_sdk.codeflare import SDKConfig

        auth = AuthConfig(method="kubeconfig")
        config = SDKConfig(
            auth=auth,
            namespace="my-ns",
            log_level="DEBUG",
        )
        assert config.namespace == "my-ns"
        assert config.log_level == "DEBUG"
        assert config.auth is auth

    def test_invalid_log_level_raises(self):
        from codeflare_sdk.codeflare import SDKConfig

        with pytest.raises(ValueError, match="log_level"):
            SDKConfig(log_level="INVALID")


class TestCodeflare:
    def test_default_init(self, mocker):
        """Codeflare() with no args uses auto-detection."""
        from codeflare_sdk.codeflare import Codeflare, SDKConfig

        mock_get_k8s_client = mocker.patch("codeflare_sdk.codeflare.get_k8s_client")
        mock_client = MagicMock()
        mock_get_k8s_client.return_value = mock_client

        mock_set_api = mocker.patch("codeflare_sdk.codeflare.set_api_client")

        cf = Codeflare()

        assert isinstance(cf.config, SDKConfig)
        mock_get_k8s_client.assert_called_once_with(config=cf.config.auth)
        mock_set_api.assert_called_once_with(mock_client)
        assert cf._client is mock_client

    def test_custom_config_init(self, mocker):
        """Codeflare with explicit SDKConfig."""
        from codeflare_sdk.codeflare import Codeflare, SDKConfig

        mock_get_k8s_client = mocker.patch("codeflare_sdk.codeflare.get_k8s_client")
        mock_client = MagicMock()
        mock_get_k8s_client.return_value = mock_client
        mocker.patch("codeflare_sdk.codeflare.set_api_client")

        auth = AuthConfig(method="kubeconfig")
        config = SDKConfig(auth=auth, namespace="test-ns", log_level="DEBUG")
        cf = Codeflare(config=config)

        assert cf.config.namespace == "test-ns"
        assert cf.config.log_level == "DEBUG"
        mock_get_k8s_client.assert_called_once_with(config=auth)

    def test_sets_log_level(self, mocker):
        """Codeflare sets the SDK logger level."""
        from codeflare_sdk.codeflare import Codeflare, SDKConfig

        mocker.patch("codeflare_sdk.codeflare.get_k8s_client")
        mocker.patch("codeflare_sdk.codeflare.set_api_client")

        config = SDKConfig(log_level="DEBUG")
        Codeflare(config=config)

        logger = logging.getLogger("codeflare_sdk")
        assert logger.level == logging.DEBUG

    def test_has_cluster_handler(self, mocker):
        """Codeflare exposes a clusters handler."""
        from codeflare_sdk.codeflare import Codeflare, ClusterHandler

        mocker.patch("codeflare_sdk.codeflare.get_k8s_client")
        mocker.patch("codeflare_sdk.codeflare.set_api_client")

        cf = Codeflare()
        assert isinstance(cf.clusters, ClusterHandler)

    def test_has_job_handler(self, mocker):
        """Codeflare exposes a jobs handler."""
        from codeflare_sdk.codeflare import Codeflare, JobHandler

        mocker.patch("codeflare_sdk.codeflare.get_k8s_client")
        mocker.patch("codeflare_sdk.codeflare.set_api_client")

        cf = Codeflare()
        assert isinstance(cf.jobs, JobHandler)

    def test_auth_failure_propagates(self, mocker):
        """Auth failure in kube-authkit propagates to caller."""
        from codeflare_sdk.codeflare import Codeflare
        from kube_authkit.exceptions import AuthenticationError

        mocker.patch(
            "codeflare_sdk.codeflare.get_k8s_client",
            side_effect=AuthenticationError("bad token"),
        )

        with pytest.raises(AuthenticationError, match="bad token"):
            Codeflare()


class TestClusterHandler:
    @pytest.fixture
    def cf(self, mocker):
        """Create a Codeflare instance with mocked auth."""
        from codeflare_sdk.codeflare import Codeflare, SDKConfig

        mocker.patch("codeflare_sdk.codeflare.get_k8s_client")
        mocker.patch("codeflare_sdk.codeflare.set_api_client")
        return Codeflare(config=SDKConfig(namespace="default-ns"))

    def test_create_cluster(self, cf, mocker):
        """create() returns a Cluster with the right config."""
        mock_cluster_cls = mocker.patch("codeflare_sdk.codeflare.Cluster")
        mock_cluster_config_cls = mocker.patch(
            "codeflare_sdk.codeflare.ClusterConfiguration"
        )

        result = cf.clusters.create(name="my-cluster", num_workers=3)

        mock_cluster_config_cls.assert_called_once_with(
            name="my-cluster", namespace="default-ns", num_workers=3
        )
        mock_cluster_cls.assert_called_once_with(
            mock_cluster_config_cls.return_value, api_client=cf.client
        )
        assert result is mock_cluster_cls.return_value

    def test_create_cluster_override_namespace(self, cf, mocker):
        """create() allows namespace override."""
        mocker.patch("codeflare_sdk.codeflare.Cluster")
        mock_cluster_config_cls = mocker.patch(
            "codeflare_sdk.codeflare.ClusterConfiguration"
        )

        cf.clusters.create(name="my-cluster", namespace="other-ns")

        mock_cluster_config_cls.assert_called_once_with(
            name="my-cluster", namespace="other-ns"
        )

    def test_get_cluster(self, cf, mocker):
        """get() delegates to get_cluster function."""
        mock_get = mocker.patch("codeflare_sdk.codeflare.get_cluster")

        result = cf.clusters.get(name="existing-cluster")

        mock_get.assert_called_once_with(
            cluster_name="existing-cluster",
            namespace="default-ns",
            verify_tls=True,
            write_to_file=False,
            api_client=cf.client,
        )
        assert result is mock_get.return_value

    def test_get_cluster_override_namespace(self, cf, mocker):
        """get() allows namespace override."""
        mock_get = mocker.patch("codeflare_sdk.codeflare.get_cluster")

        cf.clusters.get(name="existing-cluster", namespace="other-ns")

        mock_get.assert_called_once_with(
            cluster_name="existing-cluster",
            namespace="other-ns",
            verify_tls=True,
            write_to_file=False,
            api_client=cf.client,
        )

    def test_get_cluster_forwards_explicit_options(self, cf, mocker):
        """get() no longer takes **kwargs; verify_tls/write_to_file are named."""
        mock_get = mocker.patch("codeflare_sdk.codeflare.get_cluster")

        cf.clusters.get(name="existing-cluster", verify_tls=False, write_to_file=True)

        mock_get.assert_called_once_with(
            cluster_name="existing-cluster",
            namespace="default-ns",
            verify_tls=False,
            write_to_file=True,
            api_client=cf.client,
        )

    def test_get_cluster_rejects_unknown_option(self, cf, mocker):
        """RHOAIENG-98954: an unsupported key fails here, not inside get_cluster."""
        mocker.patch("codeflare_sdk.codeflare.get_cluster")

        with pytest.raises(TypeError, match="bogus"):
            cf.clusters.get(name="existing-cluster", bogus=True)

    def test_list_clusters(self, cf, mocker):
        """list() delegates to list_all_clusters."""
        mock_list = mocker.patch("codeflare_sdk.codeflare.list_all_clusters")
        mock_list.return_value = ["cluster1", "cluster2"]

        result = cf.clusters.list()

        mock_list.assert_called_once_with(
            "default-ns", print_to_console=False, api_client=cf.client
        )
        assert result == ["cluster1", "cluster2"]

    def test_list_queued(self, cf, mocker):
        """list_queued() delegates to list_all_queued."""
        mock_list = mocker.patch("codeflare_sdk.codeflare.list_all_queued")
        mock_list.return_value = []

        result = cf.clusters.list_queued()

        mock_list.assert_called_once_with(
            "default-ns", print_to_console=False, api_client=cf.client
        )
        assert result == []

    def test_list_uses_detected_namespace_when_none_configured(self, mocker):
        """RHOAIENG-98754 P2-8: fall back to the current context, not 'default'."""
        from codeflare_sdk.codeflare import Codeflare, SDKConfig

        mocker.patch("codeflare_sdk.codeflare.get_k8s_client")
        mocker.patch("codeflare_sdk.codeflare.set_api_client")
        mocker.patch(
            "codeflare_sdk.codeflare.get_current_namespace", return_value="detected"
        )
        mock_list = mocker.patch("codeflare_sdk.codeflare.list_all_clusters")

        cf = Codeflare(config=SDKConfig(namespace=None))
        cf.clusters.list()

        mock_list.assert_called_once_with(
            "detected", print_to_console=False, api_client=cf.client
        )

    def test_create_uses_detected_namespace_when_none_configured(self, mocker):
        """RHOAIENG-98754 P2-8: fall back to the current context, not 'default'."""
        from codeflare_sdk.codeflare import Codeflare, SDKConfig

        mocker.patch("codeflare_sdk.codeflare.get_k8s_client")
        mocker.patch("codeflare_sdk.codeflare.set_api_client")
        mocker.patch(
            "codeflare_sdk.codeflare.get_current_namespace", return_value="detected"
        )
        mocker.patch("codeflare_sdk.codeflare.Cluster")
        mock_config = mocker.patch("codeflare_sdk.codeflare.ClusterConfiguration")

        cf = Codeflare(config=SDKConfig(namespace=None))
        cf.clusters.create(name="test")

        mock_config.assert_called_once_with(name="test", namespace="detected")


class TestJobHandler:
    @pytest.fixture
    def cf(self, mocker):
        """Create a Codeflare instance with mocked auth."""
        from codeflare_sdk.codeflare import Codeflare, SDKConfig

        mocker.patch("codeflare_sdk.codeflare.get_k8s_client")
        mocker.patch("codeflare_sdk.codeflare.set_api_client")
        return Codeflare(config=SDKConfig(namespace="default-ns"))

    def test_submit_job(self, cf, mocker):
        """submit() creates and submits a RayJob."""
        mock_rayjob_cls = mocker.patch("codeflare_sdk.codeflare.RayJob")
        mock_job = MagicMock()
        mock_rayjob_cls.return_value = mock_job

        result = cf.jobs.submit(
            name="train",
            entrypoint="python train.py",
            cluster_name="my-cluster",
        )

        kwargs = mock_rayjob_cls.call_args.kwargs
        assert kwargs["job_name"] == "train"
        assert kwargs["entrypoint"] == "python train.py"
        assert kwargs["namespace"] == "default-ns"
        assert kwargs["cluster_name"] == "my-cluster"
        assert kwargs["api_client"] is cf.client
        mock_job.submit.assert_called_once()
        assert result is mock_job

    def test_submit_job_override_namespace(self, cf, mocker):
        """submit() allows namespace override."""
        mock_rayjob_cls = mocker.patch("codeflare_sdk.codeflare.RayJob")
        mock_rayjob_cls.return_value = MagicMock()

        cf.jobs.submit(
            name="train",
            entrypoint="python train.py",
            namespace="other-ns",
            cluster_name="my-cluster",
        )

        kwargs = mock_rayjob_cls.call_args.kwargs
        assert kwargs["job_name"] == "train"
        assert kwargs["entrypoint"] == "python train.py"
        assert kwargs["namespace"] == "other-ns"
        assert kwargs["cluster_name"] == "my-cluster"
        assert kwargs["api_client"] is cf.client

    def test_create_job_without_submit(self, cf, mocker):
        """create() returns a RayJob without submitting."""
        mock_rayjob_cls = mocker.patch("codeflare_sdk.codeflare.RayJob")
        mock_job = MagicMock()
        mock_rayjob_cls.return_value = mock_job

        result = cf.jobs.create(
            name="train",
            entrypoint="python train.py",
            cluster_name="my-cluster",
        )

        kwargs = mock_rayjob_cls.call_args.kwargs
        assert kwargs["job_name"] == "train"
        assert kwargs["entrypoint"] == "python train.py"
        assert kwargs["namespace"] == "default-ns"
        assert kwargs["cluster_name"] == "my-cluster"
        assert kwargs["api_client"] is cf.client
        mock_job.submit.assert_not_called()
        assert result is mock_job

    def test_submit_uses_detected_namespace_when_none_configured(self, mocker):
        """RHOAIENG-98754 P2-8: fall back to the current context, not 'default'."""
        from codeflare_sdk.codeflare import Codeflare, SDKConfig

        mocker.patch("codeflare_sdk.codeflare.get_k8s_client")
        mocker.patch("codeflare_sdk.codeflare.set_api_client")
        mocker.patch(
            "codeflare_sdk.codeflare.get_current_namespace", return_value="detected"
        )
        mock_rayjob_cls = mocker.patch("codeflare_sdk.codeflare.RayJob")
        mock_rayjob_cls.return_value = MagicMock()

        cf = Codeflare(config=SDKConfig(namespace=None))
        cf.jobs.submit(
            name="job", entrypoint="python run.py", cluster_name="my-cluster"
        )

        assert mock_rayjob_cls.call_args.kwargs["namespace"] == "detected"


class TestFacadeTypeSignatures:
    """RHOAIENG-98954: the facade's kwargs are typed, and stay in sync.

    The TypedDicts duplicate names and types that live elsewhere, so these
    tests are the thing that keeps them honest — a new ClusterConfiguration
    field or JobHandler parameter fails here instead of silently becoming
    unreachable through the facade.
    """

    def _cluster_config_hints(self):
        from codeflare_sdk.ray.cluster.config import ClusterConfiguration

        hints = get_type_hints(ClusterConfiguration)
        return {k: v for k, v in hints.items() if k not in ("name", "namespace")}

    def test_cluster_kwargs_cover_every_configuration_field(self):
        """ClusterConfigKwargs exposes every field create() can forward."""
        from codeflare_sdk.codeflare import ClusterConfigKwargs

        expected = set(self._cluster_config_hints())
        actual = set(get_type_hints(ClusterConfigKwargs))

        assert actual - expected == set(), "ClusterConfigKwargs has unknown keys"
        assert expected - actual == set(), "ClusterConfiguration field not exposed"

    def test_cluster_kwargs_types_match_configuration(self):
        """A field's type cannot drift from the dataclass it forwards to."""
        from codeflare_sdk.codeflare import ClusterConfigKwargs

        expected = self._cluster_config_hints()
        actual = get_type_hints(ClusterConfigKwargs)

        mismatched = {
            key: (expected[key], actual[key])
            for key in expected
            if key in actual and expected[key] != actual[key]
        }
        assert mismatched == {}

    def test_cluster_kwargs_excludes_handler_owned_fields(self):
        """name and namespace are the handler's to set, not the caller's."""
        from codeflare_sdk.codeflare import ClusterConfigKwargs

        keys = get_type_hints(ClusterConfigKwargs)
        assert "name" not in keys
        assert "namespace" not in keys

    def test_job_options_match_create_signature(self):
        """JobOptions holds exactly create()'s non-target keyword arguments."""
        from codeflare_sdk.codeflare import JobHandler, JobOptions

        params = inspect.signature(JobHandler.create).parameters
        expected = {
            name
            for name, p in params.items()
            if p.kind is inspect.Parameter.KEYWORD_ONLY
            and name not in ("cluster_name", "cluster_config")
        }

        assert set(get_type_hints(JobOptions)) == expected

    def test_job_options_types_match_create_signature(self):
        """An option's type cannot drift from the parameter it stands in for."""
        from codeflare_sdk.codeflare import JobHandler, JobOptions

        params = inspect.signature(JobHandler.create).parameters
        hints = get_type_hints(JobOptions)

        mismatched = {
            key: (params[key].annotation, hints[key])
            for key in hints
            if key in params and params[key].annotation != hints[key]
        }
        assert mismatched == {}

    def test_job_overloads_cover_both_execution_targets(self):
        """create() and submit() each declare the cluster_name/cluster_config pair."""
        from codeflare_sdk.codeflare import JobHandler

        for method in (JobHandler.create, JobHandler.submit):
            overloads = get_overloads(method)
            assert len(overloads) == 2, f"{method.__name__} lost an overload"

            targets = [
                set(inspect.signature(o).parameters)
                & {"cluster_name", "cluster_config"}
                for o in overloads
            ]
            assert targets == [{"cluster_name"}, {"cluster_config"}]

    def test_create_still_accepts_every_cluster_kwarg(self, mocker):
        """The typed keys are real: each one reaches ClusterConfiguration."""
        from codeflare_sdk.codeflare import ClusterConfigKwargs, Codeflare, SDKConfig

        mocker.patch("codeflare_sdk.codeflare.get_k8s_client")
        mocker.patch("codeflare_sdk.codeflare.set_api_client")
        mocker.patch("codeflare_sdk.codeflare.Cluster")
        mock_config = mocker.patch("codeflare_sdk.codeflare.ClusterConfiguration")

        cf = Codeflare(config=SDKConfig(namespace="ns"))
        sentinels = {key: MagicMock() for key in get_type_hints(ClusterConfigKwargs)}
        cf.clusters.create(name="c", **sentinels)

        mock_config.assert_called_once_with(name="c", namespace="ns", **sentinels)


class TestLegacyAuthRemoved:
    def test_token_auth_not_importable(self):
        """TokenAuthentication is no longer exported from codeflare_sdk."""
        with pytest.raises(ImportError):
            from codeflare_sdk import TokenAuthentication  # noqa: F401

    def test_kubeconfig_auth_not_importable(self):
        """KubeConfigFileAuthentication is no longer exported from codeflare_sdk."""
        with pytest.raises(ImportError):
            from codeflare_sdk import KubeConfigFileAuthentication  # noqa: F401

    def test_authentication_not_importable(self):
        """Authentication base class is no longer exported from codeflare_sdk."""
        with pytest.raises(ImportError):
            from codeflare_sdk import Authentication  # noqa: F401

    def test_kube_configuration_not_importable(self):
        """KubeConfiguration base class is no longer exported from codeflare_sdk."""
        with pytest.raises(ImportError):
            from codeflare_sdk import KubeConfiguration  # noqa: F401

    def test_set_api_client_not_importable(self):
        """set_api_client is no longer exported from codeflare_sdk top-level."""
        with pytest.raises(ImportError):
            from codeflare_sdk import set_api_client  # noqa: F401

    def test_codeflare_importable(self):
        """Codeflare is importable from codeflare_sdk."""
        from codeflare_sdk import Codeflare  # noqa: F401

    def test_sdk_config_importable(self):
        """SDKConfig is importable from codeflare_sdk."""
        from codeflare_sdk import SDKConfig  # noqa: F401

    def test_facade_kwarg_types_importable(self):
        """The TypedDicts are exported so callers can annotate their own wrappers."""
        from codeflare_sdk import ClusterConfigKwargs, JobOptions  # noqa: F401

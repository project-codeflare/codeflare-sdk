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

from codeflare_sdk.ray.cluster.config import ClusterConfiguration


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
        """create() binds the given ClusterConfiguration to this client."""
        mock_cluster_cls = mocker.patch("codeflare_sdk.codeflare.Cluster")
        config = ClusterConfiguration(name="my-cluster", num_workers=3)

        result = cf.clusters.create(config)

        passed = mock_cluster_cls.call_args.args[0]
        assert passed.name == "my-cluster"
        assert passed.num_workers == 3
        assert passed.namespace == "default-ns"
        assert mock_cluster_cls.call_args.kwargs == {"api_client": cf.client}
        assert result is mock_cluster_cls.return_value

    def test_create_cluster_keeps_config_namespace(self, cf, mocker):
        """A namespace already on the config wins over SDKConfig."""
        mock_cluster_cls = mocker.patch("codeflare_sdk.codeflare.Cluster")
        config = ClusterConfiguration(name="my-cluster", namespace="config-ns")

        cf.clusters.create(config)

        assert mock_cluster_cls.call_args.args[0].namespace == "config-ns"

    def test_create_cluster_override_namespace(self, cf, mocker):
        """The namespace argument overrides both the config and SDKConfig."""
        mock_cluster_cls = mocker.patch("codeflare_sdk.codeflare.Cluster")
        config = ClusterConfiguration(name="my-cluster", namespace="config-ns")

        cf.clusters.create(config, namespace="other-ns")

        assert mock_cluster_cls.call_args.args[0].namespace == "other-ns"

    def test_create_does_not_mutate_the_callers_config(self, cf, mocker):
        """Injecting the namespace must not reach back into the caller's object."""
        mock_cluster_cls = mocker.patch("codeflare_sdk.codeflare.Cluster")
        config = ClusterConfiguration(name="my-cluster")

        cf.clusters.create(config, namespace="one")
        cf.clusters.create(config, namespace="two")

        assert config.namespace is None
        namespaces = [c.args[0].namespace for c in mock_cluster_cls.call_args_list]
        assert namespaces == ["one", "two"]

    def test_create_accepts_a_fully_configured_config(self, cf, mocker):
        """Namespace injection cannot re-run ClusterConfiguration.__post_init__.

        __post_init__ merges the default accelerator mapping into
        extended_resource_mapping and then rejects the merged result, so
        dataclasses.replace() raises on an already-constructed instance.
        """
        mock_cluster_cls = mocker.patch("codeflare_sdk.codeflare.Cluster")
        config = ClusterConfiguration(
            name="my-cluster",
            extended_resource_mapping={"custom.com/acc": "ACC"},
        )

        cf.clusters.create(config, namespace="ns")

        passed = mock_cluster_cls.call_args.args[0]
        assert passed.namespace == "ns"
        assert passed.extended_resource_mapping["custom.com/acc"] == "ACC"
        assert passed.extended_resource_mapping["nvidia.com/gpu"] == "GPU"

    def test_create_requires_a_cluster_name(self, cf, mocker):
        """A config without a name fails here, with a message naming the field."""
        mocker.patch("codeflare_sdk.codeflare.Cluster")

        with pytest.raises(ValueError, match="ClusterConfiguration.name is required"):
            cf.clusters.create(ClusterConfiguration())

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
        mock_cluster_cls = mocker.patch("codeflare_sdk.codeflare.Cluster")

        cf = Codeflare(config=SDKConfig(namespace=None))
        cf.clusters.create(ClusterConfiguration(name="test"))

        assert mock_cluster_cls.call_args.args[0].namespace == "detected"


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
    """RHOAIENG-98954: the facade's arguments are typed, and stay that way.

    Cluster creation takes a ClusterConfiguration, so there is nothing to keep
    in sync there — these tests just stop **kwargs from creeping back in. The
    job handler does mirror its parameters into the JobOptions TypedDict, and
    those tests fail when the two drift.
    """

    def test_cluster_create_takes_a_configuration_object(self):
        """RHOAIENG-98954: no **kwargs to mirror — the dataclass is the contract."""
        from codeflare_sdk.codeflare import ClusterHandler

        params = inspect.signature(ClusterHandler.create).parameters

        assert list(params) == ["self", "config", "namespace"]
        assert params["config"].annotation is ClusterConfiguration
        assert not any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values())

    def test_cluster_get_takes_no_var_keywords(self):
        """get()'s options are named, so an unknown key fails at the facade."""
        from codeflare_sdk.codeflare import ClusterHandler

        params = inspect.signature(ClusterHandler.get).parameters

        assert list(params) == [
            "self",
            "name",
            "namespace",
            "verify_tls",
            "write_to_file",
        ]
        assert not any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values())

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

    def test_cluster_config_reaches_the_facade_unchanged(self, mocker):
        """Every configured field survives the handler, not just the namespace."""
        from codeflare_sdk.codeflare import Codeflare, SDKConfig

        mocker.patch("codeflare_sdk.codeflare.get_k8s_client")
        mocker.patch("codeflare_sdk.codeflare.set_api_client")
        mock_cluster_cls = mocker.patch("codeflare_sdk.codeflare.Cluster")

        cf = Codeflare(config=SDKConfig(namespace="ns"))
        config = ClusterConfiguration(
            name="c",
            num_workers=4,
            enable_autoscaling=True,
            min_workers=1,
            max_workers=4,
            labels={"team": "ml"},
            image_pull_secrets=["my-secret"],
        )

        cf.clusters.create(config)

        passed = mock_cluster_cls.call_args.args[0]
        for field_name in (
            "num_workers",
            "enable_autoscaling",
            "min_workers",
            "max_workers",
            "labels",
            "image_pull_secrets",
        ):
            assert getattr(passed, field_name) == getattr(config, field_name)


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

    def test_job_options_importable(self):
        """JobOptions is exported so callers can annotate their own wrappers."""
        from codeflare_sdk import JobOptions  # noqa: F401

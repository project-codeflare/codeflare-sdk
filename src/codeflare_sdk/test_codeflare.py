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

import logging
import pytest
from unittest.mock import MagicMock, patch
from kube_authkit import AuthConfig


class TestSDKConfig:
    def test_default_config(self):
        from codeflare_sdk.codeflare import SDKConfig

        config = SDKConfig()
        assert config.retries == 3
        assert config.timeout == 300
        assert config.namespace is None
        assert config.log_level == "WARNING"
        assert isinstance(config.auth, AuthConfig)

    def test_custom_config(self):
        from codeflare_sdk.codeflare import SDKConfig

        auth = AuthConfig(method="kubeconfig")
        config = SDKConfig(
            auth=auth,
            retries=5,
            timeout=600,
            namespace="my-ns",
            log_level="DEBUG",
        )
        assert config.retries == 5
        assert config.timeout == 600
        assert config.namespace == "my-ns"
        assert config.log_level == "DEBUG"
        assert config.auth is auth

    def test_negative_retries_raises(self):
        from codeflare_sdk.codeflare import SDKConfig

        with pytest.raises(ValueError, match="retries"):
            SDKConfig(retries=-1)

    def test_zero_timeout_raises(self):
        from codeflare_sdk.codeflare import SDKConfig

        with pytest.raises(ValueError, match="timeout"):
            SDKConfig(timeout=0)

    def test_negative_timeout_raises(self):
        from codeflare_sdk.codeflare import SDKConfig

        with pytest.raises(ValueError, match="timeout"):
            SDKConfig(timeout=-10)

    def test_invalid_log_level_raises(self):
        from codeflare_sdk.codeflare import SDKConfig

        with pytest.raises(ValueError, match="log_level"):
            SDKConfig(log_level="INVALID")

    def test_zero_retries_allowed(self):
        from codeflare_sdk.codeflare import SDKConfig

        config = SDKConfig(retries=0)
        assert config.retries == 0


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
        mock_cluster_cls.assert_called_once_with(mock_cluster_config_cls.return_value)
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
            cluster_name="existing-cluster", namespace="default-ns"
        )
        assert result is mock_get.return_value

    def test_get_cluster_override_namespace(self, cf, mocker):
        """get() allows namespace override."""
        mock_get = mocker.patch("codeflare_sdk.codeflare.get_cluster")

        cf.clusters.get(name="existing-cluster", namespace="other-ns")

        mock_get.assert_called_once_with(
            cluster_name="existing-cluster", namespace="other-ns"
        )

    def test_list_clusters(self, cf, mocker):
        """list() delegates to list_all_clusters."""
        mock_list = mocker.patch("codeflare_sdk.codeflare.list_all_clusters")
        mock_list.return_value = ["cluster1", "cluster2"]

        result = cf.clusters.list()

        mock_list.assert_called_once_with("default-ns", print_to_console=False)
        assert result == ["cluster1", "cluster2"]

    def test_list_queued(self, cf, mocker):
        """list_queued() delegates to list_all_queued."""
        mock_list = mocker.patch("codeflare_sdk.codeflare.list_all_queued")
        mock_list.return_value = []

        result = cf.clusters.list_queued()

        mock_list.assert_called_once_with("default-ns", print_to_console=False)
        assert result == []

    def test_list_no_default_namespace_uses_default(self, mocker):
        """list() falls back to 'default' when no namespace configured."""
        from codeflare_sdk.codeflare import Codeflare, SDKConfig

        mocker.patch("codeflare_sdk.codeflare.get_k8s_client")
        mocker.patch("codeflare_sdk.codeflare.set_api_client")
        mock_list = mocker.patch("codeflare_sdk.codeflare.list_all_clusters")

        cf = Codeflare(config=SDKConfig(namespace=None))
        cf.clusters.list()

        mock_list.assert_called_once_with("default", print_to_console=False)


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

        mock_rayjob_cls.assert_called_once_with(
            job_name="train",
            entrypoint="python train.py",
            namespace="default-ns",
            cluster_name="my-cluster",
        )
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

        mock_rayjob_cls.assert_called_once_with(
            job_name="train",
            entrypoint="python train.py",
            namespace="other-ns",
            cluster_name="my-cluster",
        )

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

        mock_rayjob_cls.assert_called_once_with(
            job_name="train",
            entrypoint="python train.py",
            namespace="default-ns",
            cluster_name="my-cluster",
        )
        mock_job.submit.assert_not_called()
        assert result is mock_job

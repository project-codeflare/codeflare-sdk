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

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

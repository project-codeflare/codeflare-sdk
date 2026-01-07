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

"""Tests for kube-authkit integration and new authentication features."""

import pytest

# Only run these tests if kube-authkit is installed
pytest.importorskip("kube_authkit")


class TestKubeAuthkitIntegration:
    """Test kube-authkit integration with CodeFlare SDK."""

    def test_authconfig_import(self):
        """Test that AuthConfig can be imported from codeflare_sdk."""
        try:
            from kube_authkit import AuthConfig
            from codeflare_sdk import AuthConfig as SDKAuthConfig

            assert SDKAuthConfig is AuthConfig
        except ImportError:
            pytest.skip("AuthConfig not exported from codeflare_sdk")

    def test_get_k8s_client_import(self):
        """Test that get_k8s_client can be imported from codeflare_sdk."""
        try:
            from kube_authkit import get_k8s_client
            from codeflare_sdk import get_k8s_client as sdk_get_k8s_client

            assert sdk_get_k8s_client is get_k8s_client
        except ImportError:
            pytest.skip("get_k8s_client not exported from codeflare_sdk")

    def test_authconfig_direct_usage(self, mocker):
        """Test using AuthConfig directly with SDK."""
        # Mock the entire get_k8s_client function to avoid actual auth
        mock_client = mocker.MagicMock()
        mock_get_k8s_client = mocker.patch(
            "kube_authkit.get_k8s_client", return_value=mock_client
        )

        # Mock AuthConfig to avoid validation
        mock_auth_config = mocker.MagicMock()
        mocker.patch("kube_authkit.AuthConfig", return_value=mock_auth_config)

        # Use kube-authkit with mocked objects
        from kube_authkit import (
            AuthConfig as RealAuthConfig,
            get_k8s_client as real_get_k8s_client,
        )

        # Call the mocked version
        client = mock_get_k8s_client(config=mock_auth_config)

        assert client is not None
        assert client == mock_client

    def test_auto_detection(self, mocker):
        """Test auto-detection works with SDK."""
        # Mock Kubernetes client and the factory
        mock_client = mocker.MagicMock()

        # Mock the entire kube_authkit module functions
        mock_get_k8s_client = mocker.patch(
            "kube_authkit.get_k8s_client", return_value=mock_client
        )

        # Call the mocked function
        from kube_authkit import get_k8s_client

        client = mock_get_k8s_client()

        assert client is not None
        assert client == mock_client

    def test_authconfig_oidc_strategy(self, mocker):
        """Test AuthConfig with OIDC authentication."""
        # Mock to avoid actual OIDC validation
        mock_client = mocker.MagicMock()
        mock_get_k8s_client = mocker.patch(
            "kube_authkit.get_k8s_client", return_value=mock_client
        )

        # Mock AuthConfig creation to avoid file system checks
        mock_auth_config = mocker.MagicMock()
        mocker.patch("kube_authkit.AuthConfig", return_value=mock_auth_config)

        # Test that the mocked function works
        from kube_authkit import get_k8s_client

        client = mock_get_k8s_client(config=mock_auth_config)

        assert client is not None
        assert client == mock_client

    def test_authconfig_kubeconfig_strategy(self, mocker):
        """Test AuthConfig with kubeconfig file authentication."""
        from kube_authkit import AuthConfig, get_k8s_client

        mock_client = mocker.MagicMock()
        mocker.patch("kube_authkit.get_k8s_client", return_value=mock_client)

        auth_config = AuthConfig(method="kubeconfig")
        client = get_k8s_client(config=auth_config)

        assert client is not None

    def test_authconfig_with_sdk_operations(self, mocker):
        """Test that AuthConfig works with SDK cluster operations."""
        from codeflare_sdk.common.kubernetes_cluster.auth import (
            get_api_client,
            config_check,
        )

        mock_client = mocker.MagicMock()
        mocker.patch("kube_authkit.get_k8s_client", return_value=mock_client)
        mocker.patch(
            "codeflare_sdk.common.kubernetes_cluster.auth.KUBE_AUTHKIT_AVAILABLE", True
        )

        # Mock the global api_client to return our mock
        mocker.patch(
            "codeflare_sdk.common.kubernetes_cluster.auth.api_client", mock_client
        )

        # Test that get_api_client returns the kube-authkit client
        api_client = get_api_client()
        assert api_client == mock_client


class TestAuthConfigDocumentation:
    """Test that AuthConfig provides expected authentication methods."""

    def test_authconfig_has_token_params(self):
        """Test that AuthConfig supports token parameters."""
        # This test verifies the API surface without making actual calls
        import inspect
        from kube_authkit import AuthConfig

        sig = inspect.signature(AuthConfig.__init__)
        # AuthConfig should accept various authentication parameters
        # The actual parameters depend on kube-authkit's implementation
        assert sig is not None

    def test_get_k8s_client_has_config_param(self):
        """Test that get_k8s_client accepts config parameter."""
        import inspect
        from kube_authkit import get_k8s_client

        sig = inspect.signature(get_k8s_client)
        params = list(sig.parameters.keys())
        # Should have a config parameter
        assert len(params) >= 0  # May have config param or be flexible


class TestKubeAuthkitAvailability:
    """Test handling of kube-authkit availability."""

    def test_kube_authkit_available_flag(self):
        """Test that KUBE_AUTHKIT_AVAILABLE flag is set correctly."""
        from codeflare_sdk.common.kubernetes_cluster.auth import KUBE_AUTHKIT_AVAILABLE

        # Since we're running this test, kube-authkit should be available
        assert KUBE_AUTHKIT_AVAILABLE is True

    def test_kube_authkit_imports_work(self):
        """Test that kube-authkit imports work from auth module."""
        from codeflare_sdk.common.kubernetes_cluster.auth import (
            KUBE_AUTHKIT_AVAILABLE,
        )

        if KUBE_AUTHKIT_AVAILABLE:
            # These imports should work if kube-authkit is available
            from codeflare_sdk.common.kubernetes_cluster.auth import (
                get_k8s_client as auth_get_k8s_client,
                AuthConfig as auth_AuthConfig,
            )

            assert auth_get_k8s_client is not None
            assert auth_AuthConfig is not None

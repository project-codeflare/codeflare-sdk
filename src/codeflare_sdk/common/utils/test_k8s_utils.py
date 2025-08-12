# Copyright 2025 IBM, Red Hat
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
Tests for k8s_utils module.
"""

import pytest
from unittest.mock import mock_open, patch, MagicMock
from codeflare_sdk.common.utils.k8s_utils import get_current_namespace


class TestGetCurrentNamespace:
    """Test cases for get_current_namespace function."""

    def test_get_current_namespace_incluster_success(self):
        """Test successful namespace detection from in-cluster service account."""
        mock_file_content = "test-namespace\n"

        with patch("os.path.isfile", return_value=True):
            with patch("builtins.open", mock_open(read_data=mock_file_content)):
                result = get_current_namespace()

        assert result == "test-namespace"

    def test_get_current_namespace_incluster_file_read_error(self):
        """Test handling of file read errors when reading service account namespace."""
        with patch("os.path.isfile", return_value=True):
            with patch("builtins.open", side_effect=IOError("File read error")):
                with patch("builtins.print") as mock_print:
                    # Mock config_check to avoid kubeconfig fallback
                    with patch(
                        "codeflare_sdk.common.utils.k8s_utils.config_check",
                        side_effect=Exception("Config error"),
                    ):
                        with patch(
                            "codeflare_sdk.common.utils.k8s_utils._kube_api_error_handling",
                            return_value=None,
                        ):
                            result = get_current_namespace()

        assert result is None
        # Should see both error messages: in-cluster failure and kubeconfig fallback
        mock_print.assert_any_call("Unable to find current namespace")
        mock_print.assert_any_call("trying to gather from current context")

    def test_get_current_namespace_incluster_file_open_error(self):
        """Test handling of file open errors when reading service account namespace."""
        with patch("os.path.isfile", return_value=True):
            with patch(
                "builtins.open", side_effect=PermissionError("Permission denied")
            ):
                with patch("builtins.print") as mock_print:
                    # Mock config_check to avoid kubeconfig fallback
                    with patch(
                        "codeflare_sdk.common.utils.k8s_utils.config_check",
                        side_effect=Exception("Config error"),
                    ):
                        with patch(
                            "codeflare_sdk.common.utils.k8s_utils._kube_api_error_handling",
                            return_value=None,
                        ):
                            result = get_current_namespace()

        assert result is None
        # Should see both error messages: in-cluster failure and kubeconfig fallback
        mock_print.assert_any_call("Unable to find current namespace")
        mock_print.assert_any_call("trying to gather from current context")

    def test_get_current_namespace_kubeconfig_success(self):
        """Test successful namespace detection from kubeconfig context."""
        mock_contexts = [
            {"name": "context1", "context": {"namespace": "default"}},
            {"name": "context2", "context": {"namespace": "test-namespace"}},
        ]
        mock_active_context = {
            "name": "context2",
            "context": {"namespace": "test-namespace"},
        }

        with patch("os.path.isfile", return_value=False):
            with patch("builtins.print") as mock_print:
                with patch(
                    "codeflare_sdk.common.utils.k8s_utils.config_check",
                    return_value="~/.kube/config",
                ):
                    with patch(
                        "kubernetes.config.list_kube_config_contexts",
                        return_value=(mock_contexts, mock_active_context),
                    ):
                        result = get_current_namespace()

        assert result == "test-namespace"
        mock_print.assert_called_with("trying to gather from current context")

    def test_get_current_namespace_kubeconfig_no_namespace_in_context(self):
        """Test handling when kubeconfig context has no namespace field."""
        mock_contexts = [
            {"name": "context1", "context": {}},
            {"name": "context2", "context": {"cluster": "test-cluster"}},
        ]
        mock_active_context = {
            "name": "context2",
            "context": {"cluster": "test-cluster"},
        }

        with patch("os.path.isfile", return_value=False):
            with patch("builtins.print") as mock_print:
                with patch(
                    "codeflare_sdk.common.utils.k8s_utils.config_check",
                    return_value="~/.kube/config",
                ):
                    with patch(
                        "kubernetes.config.list_kube_config_contexts",
                        return_value=(mock_contexts, mock_active_context),
                    ):
                        result = get_current_namespace()

        assert result is None
        mock_print.assert_called_with("trying to gather from current context")

    def test_get_current_namespace_kubeconfig_config_check_error(self):
        """Test handling when config_check raises an exception."""
        with patch("os.path.isfile", return_value=False):
            with patch("builtins.print") as mock_print:
                with patch(
                    "codeflare_sdk.common.utils.k8s_utils.config_check",
                    side_effect=Exception("Config error"),
                ):
                    with patch(
                        "codeflare_sdk.common.utils.k8s_utils._kube_api_error_handling",
                        return_value=None,
                    ) as mock_error_handler:
                        result = get_current_namespace()

        assert result is None
        mock_print.assert_called_with("trying to gather from current context")
        mock_error_handler.assert_called_once()

    def test_get_current_namespace_kubeconfig_list_contexts_error(self):
        """Test handling when list_kube_config_contexts raises an exception."""
        with patch("os.path.isfile", return_value=False):
            with patch("builtins.print") as mock_print:
                with patch(
                    "codeflare_sdk.common.utils.k8s_utils.config_check",
                    return_value="~/.kube/config",
                ):
                    with patch(
                        "kubernetes.config.list_kube_config_contexts",
                        side_effect=Exception("Context error"),
                    ):
                        with patch(
                            "codeflare_sdk.common.utils.k8s_utils._kube_api_error_handling",
                            return_value=None,
                        ) as mock_error_handler:
                            result = get_current_namespace()

        assert result is None
        mock_print.assert_called_with("trying to gather from current context")
        mock_error_handler.assert_called_once()

    def test_get_current_namespace_kubeconfig_key_error(self):
        """Test handling when accessing context namespace raises KeyError."""
        mock_contexts = [{"name": "context1", "context": {"namespace": "default"}}]
        mock_active_context = {"name": "context1"}  # Missing 'context' key

        with patch("os.path.isfile", return_value=False):
            with patch("builtins.print") as mock_print:
                with patch(
                    "codeflare_sdk.common.utils.k8s_utils.config_check",
                    return_value="~/.kube/config",
                ):
                    with patch(
                        "kubernetes.config.list_kube_config_contexts",
                        return_value=(mock_contexts, mock_active_context),
                    ):
                        result = get_current_namespace()

        assert result is None
        mock_print.assert_called_with("trying to gather from current context")

    def test_get_current_namespace_fallback_flow(self):
        """Test the complete fallback flow from in-cluster to kubeconfig."""
        # First attempt: in-cluster file doesn't exist
        # Second attempt: kubeconfig context has namespace
        mock_contexts = [
            {"name": "context1", "context": {"namespace": "fallback-namespace"}}
        ]
        mock_active_context = {
            "name": "context1",
            "context": {"namespace": "fallback-namespace"},
        }

        with patch("os.path.isfile", return_value=False):
            with patch("builtins.print") as mock_print:
                with patch(
                    "codeflare_sdk.common.utils.k8s_utils.config_check",
                    return_value="~/.kube/config",
                ):
                    with patch(
                        "kubernetes.config.list_kube_config_contexts",
                        return_value=(mock_contexts, mock_active_context),
                    ):
                        result = get_current_namespace()

        assert result == "fallback-namespace"
        mock_print.assert_called_with("trying to gather from current context")

    def test_get_current_namespace_complete_failure(self):
        """Test complete failure scenario where no namespace can be detected."""
        with patch("os.path.isfile", return_value=False):
            with patch("builtins.print") as mock_print:
                with patch(
                    "codeflare_sdk.common.utils.k8s_utils.config_check",
                    side_effect=Exception("Config error"),
                ):
                    with patch(
                        "codeflare_sdk.common.utils.k8s_utils._kube_api_error_handling",
                        return_value=None,
                    ):
                        result = get_current_namespace()

        assert result is None
        mock_print.assert_called_with("trying to gather from current context")

    def test_get_current_namespace_mixed_errors(self):
        """Test scenario with mixed error conditions."""
        # In-cluster file exists but read fails, then kubeconfig also fails
        with patch("os.path.isfile", return_value=True):
            with patch("builtins.open", side_effect=IOError("File read error")):
                with patch("builtins.print") as mock_print:
                    with patch(
                        "codeflare_sdk.common.utils.k8s_utils.config_check",
                        side_effect=Exception("Config error"),
                    ):
                        with patch(
                            "codeflare_sdk.common.utils.k8s_utils._kube_api_error_handling",
                            return_value=None,
                        ):
                            result = get_current_namespace()

        assert result is None
        # Should see both error messages
        assert mock_print.call_count >= 2

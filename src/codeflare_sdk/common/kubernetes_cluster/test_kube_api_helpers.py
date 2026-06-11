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
Tests for kube_api_helpers module.
"""

import pytest
from unittest.mock import patch
from kubernetes import client

from codeflare_sdk.common.kubernetes_cluster.kube_api_helpers import (
    _format_api_error_body,
    _kube_api_error_handling,
)


class TestFormatApiErrorBody:
    """Tests for _format_api_error_body."""

    def test_empty_body_returns_empty_string(self):
        assert _format_api_error_body(None) == ""
        assert _format_api_error_body("") == ""

    def test_valid_json_with_message_returns_details_line(self):
        body = '{"message": "Something went wrong"}'
        assert _format_api_error_body(body) == "Details: Something went wrong"

    def test_bytes_body_decoded_and_parsed(self):
        body = b'{"message": "Bytes message"}'
        assert _format_api_error_body(body) == "Details: Bytes message"

    def test_cluster_name_validation_returns_friendly_message(self):
        body = '{"message": "Invalid value: metadata.name must be lowercase RFC 1123 subdomain"}'
        result = _format_api_error_body(body)
        assert "Cluster name is invalid" in result
        assert "lowercase" in result and "my-cluster" in result

    def test_json_without_message_returns_empty(self):
        assert _format_api_error_body('{"code": 404}') == ""

    def test_invalid_json_returns_response_line(self):
        result = _format_api_error_body("not json")
        assert result.startswith("Response:")
        assert "not json" in result


class TestKubeApiErrorHandling:
    """Tests for _kube_api_error_handling."""

    @patch("builtins.print")
    def test_422_cluster_name_error_prints_friendly_detail_only(self, mock_print):
        api_exc = client.ApiException(status=422, reason="Unprocessable Entity")
        api_exc.body = b'{"message": "Invalid value: metadata.name lowercase RFC 1123"}'
        _kube_api_error_handling(api_exc)
        # Should print the friendly cluster-name message, not the generic Unprocessable Entity line
        call_args = [str(c) for c in mock_print.call_args_list]
        assert any("Cluster name is invalid" in c for c in call_args)
        assert not any(
            "something in your cluster configuration is invalid" in c for c in call_args
        )

    @patch("builtins.print")
    def test_404_with_body_prints_message_and_detail(self, mock_print):
        api_exc = client.ApiException(status=404, reason="Not Found")
        api_exc.body = '{"message": "RayCluster xyz not found"}'
        _kube_api_error_handling(api_exc)
        call_args = [str(c) for c in mock_print.call_args_list]
        assert any("requested resource could not be located" in c for c in call_args)
        assert any("Details: RayCluster xyz not found" in c for c in call_args)

    @patch("builtins.print")
    def test_403_prints_forbidden_message(self, mock_print):
        """403 uses status-code lookup so it gets the right message (not fallback)."""
        api_exc = client.ApiException(status=403, reason="Forbidden")
        api_exc.body = None
        _kube_api_error_handling(api_exc)
        call_args = [str(c) for c in mock_print.call_args_list]
        assert any("Access denied:" in c for c in call_args)

    @patch("builtins.print")
    def test_api_exception_with_no_body_prints_reason_and_status(self, mock_print):
        api_exc = client.ApiException(status=500, reason="Internal Server Error")
        api_exc.body = None
        _kube_api_error_handling(api_exc)
        call_args = [str(c) for c in mock_print.call_args_list]
        assert any("Reason: Internal Server Error" in c for c in call_args)
        assert any("HTTP 500" in c for c in call_args)

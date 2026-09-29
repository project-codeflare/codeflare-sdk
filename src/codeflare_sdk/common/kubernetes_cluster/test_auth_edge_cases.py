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
Tests for edge cases in auth.py cert helpers.
"""

import pytest
from codeflare_sdk.common.kubernetes_cluster.auth import (
    _client_with_cert,
    _gen_ca_cert_path,
)


def test_gen_ca_cert_path_with_env_var(monkeypatch):
    """Test _gen_ca_cert_path with CF_SDK_CA_CERT_PATH environment variable."""
    monkeypatch.setenv("CF_SDK_CA_CERT_PATH", "/custom/ca/cert.crt")

    result = _gen_ca_cert_path(None)
    assert result == "/custom/ca/cert.crt"


def test_gen_ca_cert_path_with_explicit_path():
    """Test _gen_ca_cert_path with explicit path parameter."""
    result = _gen_ca_cert_path("/explicit/path.crt")
    assert result == "/explicit/path.crt"


def test_gen_ca_cert_path_defaults_to_none(monkeypatch):
    """Test _gen_ca_cert_path returns None when no cert path is configured."""
    monkeypatch.delenv("CF_SDK_CA_CERT_PATH", raising=False)

    result = _gen_ca_cert_path(None)
    assert result is None or result == "/etc/pki/tls/custom-certs/ca-bundle.crt"


def test_client_with_cert_none(mocker, monkeypatch):
    """Test _client_with_cert when cert_path is None preserves existing ssl_ca_cert."""
    monkeypatch.delenv("CF_SDK_CA_CERT_PATH", raising=False)

    mock_client = mocker.MagicMock()
    mock_client.configuration = mocker.MagicMock()
    mock_client.configuration.ssl_ca_cert = "/existing/ca.crt"

    _client_with_cert(mock_client, None)

    assert mock_client.configuration.verify_ssl is True
    assert mock_client.configuration.ssl_ca_cert == "/existing/ca.crt"


def test_client_with_cert_file_not_found(mocker):
    """Test _client_with_cert raises FileNotFoundError for missing cert."""
    mock_client = mocker.MagicMock()
    mock_client.configuration = mocker.MagicMock()

    with pytest.raises(FileNotFoundError, match="Certificate file not found"):
        _client_with_cert(mock_client, "/nonexistent/cert.crt")


def test_client_with_cert_valid_file(mocker, tmp_path):
    """Test _client_with_cert sets ssl_ca_cert when valid cert file exists."""
    cert_file = tmp_path / "ca.crt"
    cert_file.write_text("-----BEGIN CERTIFICATE-----\ntest\n-----END CERTIFICATE-----")

    mock_client = mocker.MagicMock()
    mock_client.configuration = mocker.MagicMock()
    mock_client.configuration.ssl_ca_cert = None

    _client_with_cert(mock_client, str(cert_file))

    assert mock_client.configuration.verify_ssl is True
    assert mock_client.configuration.ssl_ca_cert == str(cert_file)

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

import base64

from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PublicFormat,
    load_pem_private_key,
)
from cryptography.x509 import load_pem_x509_certificate
from cryptography.x509.oid import ExtensionOID
import os
from pathlib import Path
from codeflare_sdk.common.utils.generate_cert import (
    export_env,
    generate_ca_cert,
    generate_tls_cert,
    _get_tls_base_dir,
)
from kubernetes import client


def test_generate_ca_cert():
    """
    test the function codeflare_sdk.common.utils.generate_ca_cert generates the correct outputs
    """
    key, certificate = generate_ca_cert()
    cert = load_pem_x509_certificate(base64.b64decode(certificate))
    private_key = load_pem_private_key(base64.b64decode(key), password=None)
    private_pub_key_bytes = private_key.public_key().public_bytes(
        Encoding.PEM, PublicFormat.SubjectPublicKeyInfo
    )
    cert_pub_key_bytes = cert.public_key().public_bytes(
        Encoding.PEM, PublicFormat.SubjectPublicKeyInfo
    )
    assert isinstance(key, str)
    assert isinstance(certificate, str)
    # Veirfy ca.cert is self signed
    assert cert.verify_directly_issued_by(cert) is None
    # Verify cert has the public key bytes from the private key
    assert cert_pub_key_bytes == private_pub_key_bytes

    # Verify RSA key size is 3072 bits for security compliance
    assert (
        private_key.key_size == 3072
    ), f"CA key size should be 3072 bits, got {private_key.key_size}"

    # Verify CA certificate has required extensions
    assert (
        cert.extensions.get_extension_for_oid(ExtensionOID.BASIC_CONSTRAINTS)
        is not None
    )
    assert cert.extensions.get_extension_for_oid(ExtensionOID.KEY_USAGE) is not None


def secret_ca_retreival(secret_name, namespace):
    ca_private_key_bytes, ca_cert = generate_ca_cert()
    data = {"ca.crt": ca_cert, "tls.key": ca_private_key_bytes}
    assert secret_name == "ca-secret-cluster"
    assert namespace == "namespace"
    return client.models.V1Secret(data=data)


def test_generate_tls_cert(mocker):
    """
    test the function codeflare_sdk.common.utils.generate_ca_cert generates the correct outputs
    """
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch(
        "codeflare_sdk.common.utils.generate_cert.get_secret_name",
        return_value="ca-secret-cluster",
    )
    mocker.patch(
        "kubernetes.client.CoreV1Api.read_namespaced_secret",
        side_effect=secret_ca_retreival,
    )
    # Mock _get_tls_base_dir to return CWD for test isolation
    mocker.patch(
        "codeflare_sdk.common.utils.generate_cert._get_tls_base_dir",
        return_value=Path(os.getcwd()),
    )

    generate_tls_cert("cluster", "namespace")
    tls_dir = os.path.join(os.getcwd(), "cluster-namespace")
    assert os.path.exists(tls_dir)
    assert os.path.exists(os.path.join(tls_dir, "ca.crt"))
    assert os.path.exists(os.path.join(tls_dir, "tls.crt"))
    assert os.path.exists(os.path.join(tls_dir, "tls.key"))

    # verify the that the signed tls.crt is issued by the ca_cert (root cert)
    with open(os.path.join(tls_dir, "tls.crt"), "r") as f:
        tls_cert = load_pem_x509_certificate(f.read().encode("utf-8"))
    with open(os.path.join(tls_dir, "ca.crt"), "r") as f:
        root_cert = load_pem_x509_certificate(f.read().encode("utf-8"))
    assert tls_cert.verify_directly_issued_by(root_cert) is None

    # Verify RSA key size is 3072 bits for security compliance
    with open(os.path.join(tls_dir, "tls.key"), "rb") as f:
        tls_key = load_pem_private_key(f.read(), password=None)
    assert (
        tls_key.key_size == 3072
    ), f"TLS key size should be 3072 bits, got {tls_key.key_size}"

    # Verify RFC 5280 certificate extensions are present
    # BasicConstraints (CA:FALSE for client cert)
    basic_constraints = tls_cert.extensions.get_extension_for_oid(
        ExtensionOID.BASIC_CONSTRAINTS
    )
    assert (
        basic_constraints is not None
    ), "Certificate should have BasicConstraints extension"
    assert basic_constraints.value.ca is False, "Client cert should have CA:FALSE"

    # KeyUsage extension
    key_usage = tls_cert.extensions.get_extension_for_oid(ExtensionOID.KEY_USAGE)
    assert key_usage is not None, "Certificate should have KeyUsage extension"
    assert (
        key_usage.value.digital_signature is True
    ), "KeyUsage should include digitalSignature"
    assert (
        key_usage.value.key_encipherment is True
    ), "KeyUsage should include keyEncipherment"

    # ExtendedKeyUsage (serverAuth and clientAuth for mTLS)
    extended_key_usage = tls_cert.extensions.get_extension_for_oid(
        ExtensionOID.EXTENDED_KEY_USAGE
    )
    assert (
        extended_key_usage is not None
    ), "Certificate should have ExtendedKeyUsage extension"

    # SubjectAlternativeName
    san = tls_cert.extensions.get_extension_for_oid(
        ExtensionOID.SUBJECT_ALTERNATIVE_NAME
    )
    assert san is not None, "Certificate should have SubjectAlternativeName extension"

    # SubjectKeyIdentifier
    ski = tls_cert.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_KEY_IDENTIFIER)
    assert ski is not None, "Certificate should have SubjectKeyIdentifier extension"

    # AuthorityKeyIdentifier
    aki = tls_cert.extensions.get_extension_for_oid(
        ExtensionOID.AUTHORITY_KEY_IDENTIFIER
    )
    assert aki is not None, "Certificate should have AuthorityKeyIdentifier extension"

    # Verify file permissions are 0600 (owner read/write only)
    tls_key_path = os.path.join(tls_dir, "tls.key")
    tls_crt_path = os.path.join(tls_dir, "tls.crt")
    ca_crt_path = os.path.join(tls_dir, "ca.crt")

    # Get permission bits (last 9 bits of st_mode)
    key_perms = os.stat(tls_key_path).st_mode & 0o777
    crt_perms = os.stat(tls_crt_path).st_mode & 0o777
    ca_perms = os.stat(ca_crt_path).st_mode & 0o777

    assert (
        key_perms == 0o600
    ), f"tls.key should have 0600 permissions, got {oct(key_perms)}"
    assert (
        crt_perms == 0o600
    ), f"tls.crt should have 0600 permissions, got {oct(crt_perms)}"
    assert (
        ca_perms == 0o600
    ), f"ca.crt should have 0600 permissions, got {oct(ca_perms)}"


def secret_ca_retreival_with_ca_key(secret_name, namespace):
    """Mock secret retrieval with ca.key instead of tls.key (KubeRay format)"""
    ca_private_key_bytes, ca_cert = generate_ca_cert()
    data = {"ca.crt": ca_cert, "ca.key": ca_private_key_bytes}
    assert secret_name == "ca-secret-cluster2"
    assert namespace == "namespace2"
    return client.models.V1Secret(data=data)


def test_generate_tls_cert_with_ca_key_fallback(mocker):
    """
    Test that generate_tls_cert works when secret contains ca.key instead of tls.key
    This tests the fallback logic for KubeRay-created secrets
    """
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch(
        "codeflare_sdk.common.utils.generate_cert.get_secret_name",
        return_value="ca-secret-cluster2",
    )
    mocker.patch(
        "kubernetes.client.CoreV1Api.read_namespaced_secret",
        side_effect=secret_ca_retreival_with_ca_key,
    )
    # Mock _get_tls_base_dir to return CWD for test isolation
    mocker.patch(
        "codeflare_sdk.common.utils.generate_cert._get_tls_base_dir",
        return_value=Path(os.getcwd()),
    )

    generate_tls_cert("cluster2", "namespace2")
    tls_dir = os.path.join(os.getcwd(), "cluster2-namespace2")
    assert os.path.exists(tls_dir)
    assert os.path.exists(os.path.join(tls_dir, "ca.crt"))
    assert os.path.exists(os.path.join(tls_dir, "tls.crt"))
    assert os.path.exists(os.path.join(tls_dir, "tls.key"))

    # verify the that the signed tls.crt is issued by the ca_cert (root cert)
    with open(os.path.join(tls_dir, "tls.crt"), "r") as f:
        tls_cert = load_pem_x509_certificate(f.read().encode("utf-8"))
    with open(os.path.join(tls_dir, "ca.crt"), "r") as f:
        root_cert = load_pem_x509_certificate(f.read().encode("utf-8"))
    assert tls_cert.verify_directly_issued_by(root_cert) is None

    # Cleanup for this test
    os.remove(os.path.join(tls_dir, "ca.crt"))
    os.remove(os.path.join(tls_dir, "tls.crt"))
    os.remove(os.path.join(tls_dir, "tls.key"))
    os.rmdir(tls_dir)


def test_export_env(mocker):
    """
    test the function codeflare_sdk.common.utils.generate_ca_cert.export_ev generates the correct outputs
    """
    # Mock _get_tls_base_dir to return CWD for test isolation
    mocker.patch(
        "codeflare_sdk.common.utils.generate_cert._get_tls_base_dir",
        return_value=Path(os.getcwd()),
    )

    cluster_name = "cluster"
    ns = "namespace"
    export_env(cluster_name, ns)

    tls_dir = os.path.join(os.getcwd(), f"{cluster_name}-{ns}")

    assert os.environ["RAY_USE_TLS"] == "1"
    assert os.environ["RAY_TLS_SERVER_CERT"] == os.path.join(tls_dir, "tls.crt")
    assert os.environ["RAY_TLS_SERVER_KEY"] == os.path.join(tls_dir, "tls.key")
    assert os.environ["RAY_TLS_CA_CERT"] == os.path.join(tls_dir, "ca.crt")


def secret_ca_retreival_generic(secret_name, namespace):
    """Generic mock that works with any cluster/namespace"""
    ca_private_key_bytes, ca_cert = generate_ca_cert()
    data = {"ca.crt": ca_cert, "tls.key": ca_private_key_bytes}
    return client.models.V1Secret(data=data)


def test_force_regenerate(mocker):
    """
    Test that force_regenerate parameter works correctly
    """
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch(
        "codeflare_sdk.common.utils.generate_cert.get_secret_name",
        return_value="ca-secret-test-regen",
    )
    mocker.patch(
        "kubernetes.client.CoreV1Api.read_namespaced_secret",
        side_effect=secret_ca_retreival_generic,
    )
    mocker.patch(
        "codeflare_sdk.common.utils.generate_cert._get_tls_base_dir",
        return_value=Path(os.getcwd()),
    )

    # Generate certificates first time
    generate_tls_cert("test-regen", "default")
    tls_dir = Path(os.getcwd()) / "test-regen-default"
    assert tls_dir.exists()

    # Get modification time of tls.crt
    import time

    tls_crt = tls_dir / "tls.crt"
    first_mtime = tls_crt.stat().st_mtime

    # Wait a moment
    time.sleep(0.1)

    # Try to generate again without force_regenerate (should skip)
    generate_tls_cert("test-regen", "default", force_regenerate=False)
    second_mtime = tls_crt.stat().st_mtime
    assert first_mtime == second_mtime, "Should not regenerate without force_regenerate"

    # Wait a moment
    time.sleep(0.1)

    # Generate with force_regenerate (should regenerate)
    generate_tls_cert("test-regen", "default", force_regenerate=True)
    third_mtime = tls_crt.stat().st_mtime
    assert third_mtime > second_mtime, "Should regenerate with force_regenerate=True"

    # Cleanup
    import shutil

    shutil.rmtree(tls_dir)


def test_refresh_tls_cert(mocker):
    """
    Test the refresh_tls_cert function
    """
    from codeflare_sdk.common.utils.generate_cert import refresh_tls_cert

    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch(
        "codeflare_sdk.common.utils.generate_cert.get_secret_name",
        return_value="ca-secret-refresh-test",
    )
    mocker.patch(
        "kubernetes.client.CoreV1Api.read_namespaced_secret",
        side_effect=secret_ca_retreival_generic,
    )
    mocker.patch(
        "codeflare_sdk.common.utils.generate_cert._get_tls_base_dir",
        return_value=Path(os.getcwd()),
    )

    # Generate initial certificates
    generate_tls_cert("refresh-test", "default")
    tls_dir = Path(os.getcwd()) / "refresh-test-default"
    assert tls_dir.exists()

    # Refresh should remove and regenerate
    result = refresh_tls_cert("refresh-test", "default")
    assert result is True
    assert tls_dir.exists()  # Should exist again

    # Cleanup
    import shutil

    shutil.rmtree(tls_dir)


def test_cleanup_tls_cert(mocker, tmp_path):
    """Test cleanup_tls_cert removes certificate directory"""
    from codeflare_sdk.common.utils.generate_cert import cleanup_tls_cert

    # Mock _get_tls_base_dir to return tmp_path
    mocker.patch(
        "codeflare_sdk.common.utils.generate_cert._get_tls_base_dir",
        return_value=tmp_path,
    )

    # Create a fake cert directory
    cert_dir = tmp_path / "test-cluster-test-ns"
    cert_dir.mkdir(parents=True)
    (cert_dir / "tls.crt").write_text("fake cert")
    (cert_dir / "tls.key").write_text("fake key")
    (cert_dir / "ca.crt").write_text("fake ca")

    assert cert_dir.exists()

    # Cleanup should return True and remove directory
    result = cleanup_tls_cert("test-cluster", "test-ns")
    assert result is True
    assert not cert_dir.exists()


def test_cleanup_tls_cert_not_exists(mocker, tmp_path):
    """Test cleanup_tls_cert returns False when directory doesn't exist"""
    from codeflare_sdk.common.utils.generate_cert import cleanup_tls_cert

    mocker.patch(
        "codeflare_sdk.common.utils.generate_cert._get_tls_base_dir",
        return_value=tmp_path,
    )

    # No directory exists
    result = cleanup_tls_cert("nonexistent-cluster", "test-ns")
    assert result is False


def test_list_tls_certificates(mocker, tmp_path):
    """Test list_tls_certificates returns certificate info"""
    from codeflare_sdk.common.utils.generate_cert import list_tls_certificates

    mocker.patch(
        "codeflare_sdk.common.utils.generate_cert._get_tls_base_dir",
        return_value=tmp_path,
    )

    # Create fake cert directories (format: cluster_name-namespace)
    cert_dir1 = tmp_path / "cluster1-ns1"
    cert_dir1.mkdir(parents=True)
    (cert_dir1 / "tls.crt").write_text("fake cert")

    cert_dir2 = tmp_path / "cluster2-ns2"
    cert_dir2.mkdir(parents=True)
    (cert_dir2 / "tls.crt").write_text("fake cert")

    certs = list_tls_certificates()
    assert len(certs) == 2

    # Check structure - function returns cluster_name and namespace
    cluster_names = [c["cluster_name"] for c in certs]
    namespaces = [c["namespace"] for c in certs]
    assert "cluster1" in cluster_names
    assert "cluster2" in cluster_names
    assert "ns1" in namespaces
    assert "ns2" in namespaces

    # Check other fields exist
    for cert in certs:
        assert "path" in cert
        assert "created" in cert
        assert "size" in cert
        assert "cert_expiry" in cert


def test_list_tls_certificates_empty(mocker, tmp_path):
    """Test list_tls_certificates returns empty list when no certs exist"""
    from codeflare_sdk.common.utils.generate_cert import list_tls_certificates

    mocker.patch(
        "codeflare_sdk.common.utils.generate_cert._get_tls_base_dir",
        return_value=tmp_path,
    )

    certs = list_tls_certificates()
    assert certs == []


def test_list_tls_certificates_no_namespace_in_name(mocker, tmp_path):
    """Test list_tls_certificates handles directory names without namespace separator"""
    from codeflare_sdk.common.utils.generate_cert import list_tls_certificates

    mocker.patch(
        "codeflare_sdk.common.utils.generate_cert._get_tls_base_dir",
        return_value=tmp_path,
    )

    # Create a directory without the hyphen separator
    cert_dir = tmp_path / "clusterwithoutnamespace"
    cert_dir.mkdir(parents=True)
    (cert_dir / "tls.crt").write_text("fake cert")

    certs = list_tls_certificates()
    assert len(certs) == 1
    assert certs[0]["cluster_name"] == "clusterwithoutnamespace"
    assert certs[0]["namespace"] == "unknown"


def test_cleanup_expired_certificates_dry_run(mocker, tmp_path):
    """Test cleanup_expired_certificates in dry_run mode"""
    from codeflare_sdk.common.utils.generate_cert import cleanup_expired_certificates
    import datetime
    from datetime import timezone

    mocker.patch(
        "codeflare_sdk.common.utils.generate_cert._get_tls_base_dir",
        return_value=tmp_path,
    )

    # Create a cert directory
    cert_dir = tmp_path / "expired-cluster-ns"
    cert_dir.mkdir(parents=True)
    (cert_dir / "tls.crt").write_text("fake cert")

    # Mock list_tls_certificates to return an expired cert
    expired_time = datetime.datetime.now(timezone.utc) - datetime.timedelta(days=1)
    mocker.patch(
        "codeflare_sdk.common.utils.generate_cert.list_tls_certificates",
        return_value=[
            {
                "cluster_name": "expired-cluster",
                "namespace": "ns",
                "path": str(cert_dir),
                "created": datetime.datetime.now(),
                "size": 100,
                "cert_expiry": expired_time,
            }
        ],
    )

    # Dry run should return list but not delete
    result = cleanup_expired_certificates(dry_run=True)
    assert len(result) == 1
    assert cert_dir.exists()  # Directory still exists


def test_cleanup_expired_certificates_delete(mocker, tmp_path):
    """Test cleanup_expired_certificates actually deletes when dry_run=False"""
    from codeflare_sdk.common.utils.generate_cert import cleanup_expired_certificates
    import datetime
    from datetime import timezone

    mocker.patch(
        "codeflare_sdk.common.utils.generate_cert._get_tls_base_dir",
        return_value=tmp_path,
    )

    # Create a cert directory
    cert_dir = tmp_path / "expired-cluster-ns"
    cert_dir.mkdir(parents=True)
    (cert_dir / "tls.crt").write_text("fake cert")

    # Mock list_tls_certificates to return an expired cert
    expired_time = datetime.datetime.now(timezone.utc) - datetime.timedelta(days=1)
    mocker.patch(
        "codeflare_sdk.common.utils.generate_cert.list_tls_certificates",
        return_value=[
            {
                "cluster_name": "expired-cluster",
                "namespace": "ns",
                "path": str(cert_dir),
                "created": datetime.datetime.now(),
                "size": 100,
                "cert_expiry": expired_time,
            }
        ],
    )

    # Should delete
    result = cleanup_expired_certificates(dry_run=False)
    assert len(result) == 1
    assert not cert_dir.exists()  # Directory was deleted


def test_cleanup_old_certificates_dry_run(mocker, tmp_path):
    """Test cleanup_old_certificates in dry_run mode"""
    from codeflare_sdk.common.utils.generate_cert import cleanup_old_certificates
    import datetime

    mocker.patch(
        "codeflare_sdk.common.utils.generate_cert._get_tls_base_dir",
        return_value=tmp_path,
    )

    # Create a cert directory
    cert_dir = tmp_path / "old-cluster-ns"
    cert_dir.mkdir(parents=True)
    (cert_dir / "tls.crt").write_text("fake cert")

    # Mock list_tls_certificates to return an old cert
    old_time = datetime.datetime.now() - datetime.timedelta(days=60)
    mocker.patch(
        "codeflare_sdk.common.utils.generate_cert.list_tls_certificates",
        return_value=[
            {
                "cluster_name": "old-cluster",
                "namespace": "ns",
                "path": str(cert_dir),
                "created": old_time,
                "size": 100,
                "cert_expiry": None,
            }
        ],
    )

    # Dry run should return list but not delete
    result = cleanup_old_certificates(days=30, dry_run=True)
    assert len(result) == 1
    assert cert_dir.exists()


def test_cleanup_old_certificates_delete(mocker, tmp_path):
    """Test cleanup_old_certificates actually deletes when dry_run=False"""
    from codeflare_sdk.common.utils.generate_cert import cleanup_old_certificates
    import datetime

    mocker.patch(
        "codeflare_sdk.common.utils.generate_cert._get_tls_base_dir",
        return_value=tmp_path,
    )

    # Create a cert directory
    cert_dir = tmp_path / "old-cluster-ns"
    cert_dir.mkdir(parents=True)
    (cert_dir / "tls.crt").write_text("fake cert")

    # Mock list_tls_certificates to return an old cert
    old_time = datetime.datetime.now() - datetime.timedelta(days=60)
    mocker.patch(
        "codeflare_sdk.common.utils.generate_cert.list_tls_certificates",
        return_value=[
            {
                "cluster_name": "old-cluster",
                "namespace": "ns",
                "path": str(cert_dir),
                "created": old_time,
                "size": 100,
                "cert_expiry": None,
            }
        ],
    )

    # Should delete
    result = cleanup_old_certificates(days=30, dry_run=False)
    assert len(result) == 1
    assert not cert_dir.exists()


def test_get_tls_base_dir_env_override(monkeypatch, tmp_path):
    """Test that CODEFLARE_TLS_DIR environment variable overrides default"""
    custom_dir = tmp_path / "custom_tls"
    monkeypatch.setenv("CODEFLARE_TLS_DIR", str(custom_dir))

    result = _get_tls_base_dir()
    assert result == custom_dir


def test_get_tls_base_dir_xdg_fallback(monkeypatch, tmp_path):
    """Test that XDG_DATA_HOME is used when CODEFLARE_TLS_DIR not set"""
    monkeypatch.delenv("CODEFLARE_TLS_DIR", raising=False)
    xdg_dir = tmp_path / "xdg_data"
    monkeypatch.setenv("XDG_DATA_HOME", str(xdg_dir))

    result = _get_tls_base_dir()
    assert result == xdg_dir / "codeflare" / "tls"


def test_get_tls_base_dir_default(monkeypatch):
    """Test default fallback to ~/.local/share/codeflare/tls"""
    monkeypatch.delenv("CODEFLARE_TLS_DIR", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)

    result = _get_tls_base_dir()
    expected = Path.home() / ".local" / "share" / "codeflare" / "tls"
    assert result == expected


# Make sure to always keep this function last
def test_cleanup():
    """Clean up test certificate directories."""
    import shutil

    # Clean up any remaining test directories
    test_dirs = [
        "cluster-namespace",
        "cluster2-namespace2",
        "test-regen-default",
        "refresh-test-default",
    ]

    for dir_name in test_dirs:
        tls_dir = os.path.join(os.getcwd(), dir_name)
        if os.path.exists(tls_dir):
            shutil.rmtree(tls_dir)

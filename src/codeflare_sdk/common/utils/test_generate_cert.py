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
    private_pub_key_bytes = (
        load_pem_private_key(base64.b64decode(key), password=None)
        .public_key()
        .public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo)
    )
    cert_pub_key_bytes = cert.public_key().public_bytes(
        Encoding.PEM, PublicFormat.SubjectPublicKeyInfo
    )
    assert type(key) == str
    assert type(certificate) == str
    # Veirfy ca.cert is self signed
    assert cert.verify_directly_issued_by(cert) == None
    # Verify cert has the public key bytes from the private key
    assert cert_pub_key_bytes == private_pub_key_bytes


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
    assert tls_cert.verify_directly_issued_by(root_cert) == None


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
    assert tls_cert.verify_directly_issued_by(root_cert) == None

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
    assert result == True
    assert tls_dir.exists()  # Should exist again

    # Cleanup
    import shutil

    shutil.rmtree(tls_dir)


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

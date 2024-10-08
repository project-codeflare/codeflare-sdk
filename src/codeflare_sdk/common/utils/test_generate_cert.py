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
from codeflare_sdk.common.utils.generate_cert import (
    export_env,
    generate_ca_cert,
    generate_tls_cert,
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
    data = {"ca.crt": ca_cert, "ca.key": ca_private_key_bytes}
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

    generate_tls_cert("cluster", "namespace")
    assert os.path.exists("tls-cluster-namespace")
    assert os.path.exists(os.path.join("tls-cluster-namespace", "ca.crt"))
    assert os.path.exists(os.path.join("tls-cluster-namespace", "tls.crt"))
    assert os.path.exists(os.path.join("tls-cluster-namespace", "tls.key"))

    # verify the that the signed tls.crt is issued by the ca_cert (root cert)
    with open(os.path.join("tls-cluster-namespace", "tls.crt"), "r") as f:
        tls_cert = load_pem_x509_certificate(f.read().encode("utf-8"))
    with open(os.path.join("tls-cluster-namespace", "ca.crt"), "r") as f:
        root_cert = load_pem_x509_certificate(f.read().encode("utf-8"))
    assert tls_cert.verify_directly_issued_by(root_cert) == None


def test_export_env():
    """
    test the function codeflare_sdk.common.utils.generate_ca_cert.export_ev generates the correct outputs
    """
    tls_dir = "cluster"
    ns = "namespace"
    export_env(tls_dir, ns)
    assert os.environ["RAY_USE_TLS"] == "1"
    assert os.environ["RAY_TLS_SERVER_CERT"] == os.path.join(
        os.getcwd(), f"tls-{tls_dir}-{ns}", "tls.crt"
    )
    assert os.environ["RAY_TLS_SERVER_KEY"] == os.path.join(
        os.getcwd(), f"tls-{tls_dir}-{ns}", "tls.key"
    )
    assert os.environ["RAY_TLS_CA_CERT"] == os.path.join(
        os.getcwd(), f"tls-{tls_dir}-{ns}", "ca.crt"
    )


# Make sure to always keep this function last
def test_cleanup():
    os.remove("tls-cluster-namespace/ca.crt")
    os.remove("tls-cluster-namespace/tls.crt")
    os.remove("tls-cluster-namespace/tls.key")
    os.rmdir("tls-cluster-namespace")

# Copyright 2022 IBM, Red Hat
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
import os
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography import x509
from cryptography.x509.oid import NameOID
import datetime
from ..cluster.auth import config_check, api_config_handler
from kubernetes import client, config


def generate_ca_cert(days: int = 30):
    # Generate base64 encoded ca.key and ca.cert
    # Similar to:
    # openssl req -x509 -nodes -newkey rsa:2048 -keyout ca.key -days 1826 -out ca.crt -subj '/CN=root-ca'
    # base64 -i ca.crt -i ca.key

    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    key = base64.b64encode(
        private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    ).decode("utf-8")

    # Generate Certificate
    one_day = datetime.timedelta(1, 0, 0)
    public_key = private_key.public_key()
    builder = (
        x509.CertificateBuilder()
        .subject_name(
            x509.Name(
                [
                    x509.NameAttribute(NameOID.COMMON_NAME, "root-ca"),
                ]
            )
        )
        .issuer_name(
            x509.Name(
                [
                    x509.NameAttribute(NameOID.COMMON_NAME, "root-ca"),
                ]
            )
        )
        .not_valid_before(datetime.datetime.today() - one_day)
        .not_valid_after(datetime.datetime.today() + (one_day * days))
        .serial_number(x509.random_serial_number())
        .public_key(public_key)
    )
    certificate = base64.b64encode(
        builder.sign(private_key=private_key, algorithm=hashes.SHA256()).public_bytes(
            serialization.Encoding.PEM
        )
    ).decode("utf-8")
    return key, certificate


def generate_tls_cert(cluster_name, namespace, days=30):
    # Create a folder tls-<cluster>-<namespace> and store three files: ca.crt, tls.crt, and tls.key
    tls_dir = os.path.join(os.getcwd(), f"tls-{cluster_name}-{namespace}")
    if not os.path.exists(tls_dir):
        os.makedirs(tls_dir)

    # Similar to:
    # oc get secret ca-secret-<cluster-name> -o template='{{index .data "ca.key"}}'
    # oc get secret ca-secret-<cluster-name> -o template='{{index .data "ca.crt"}}'|base64 -d > ${TLSDIR}/ca.crt
    config_check()
    v1 = client.CoreV1Api(api_config_handler())
    secret = v1.read_namespaced_secret(f"ca-secret-{cluster_name}", namespace).data
    ca_cert = secret.get("ca.crt")
    ca_key = secret.get("ca.key")

    with open(os.path.join(tls_dir, "ca.crt"), "w") as f:
        f.write(base64.b64decode(ca_cert).decode("utf-8"))

    # Generate tls.key and signed tls.cert locally for ray client
    # Similar to running these commands:
    # openssl req -nodes -newkey rsa:2048 -keyout ${TLSDIR}/tls.key -out ${TLSDIR}/tls.csr -subj '/CN=local'
    # cat <<EOF >${TLSDIR}/domain.ext
    # authorityKeyIdentifier=keyid,issuer
    # basicConstraints=CA:FALSE
    # subjectAltName = @alt_names
    # [alt_names]
    # DNS.1 = 127.0.0.1
    # DNS.2 = localhost
    # EOF
    # openssl x509 -req -CA ${TLSDIR}/ca.crt -CAkey ${TLSDIR}/ca.key -in ${TLSDIR}/tls.csr -out ${TLSDIR}/tls.crt -days 365 -CAcreateserial -extfile ${TLSDIR}/domain.ext
    key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    tls_key = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    with open(os.path.join(tls_dir, "tls.key"), "w") as f:
        f.write(tls_key.decode("utf-8"))

    one_day = datetime.timedelta(1, 0, 0)
    tls_cert = (
        x509.CertificateBuilder()
        .issuer_name(
            x509.Name(
                [
                    x509.NameAttribute(NameOID.COMMON_NAME, "root-ca"),
                ]
            )
        )
        .subject_name(
            x509.Name(
                [
                    x509.NameAttribute(NameOID.COMMON_NAME, "local"),
                ]
            )
        )
        .public_key(key.public_key())
        .not_valid_before(datetime.datetime.today() - one_day)
        .not_valid_after(datetime.datetime.today() + (one_day * days))
        .serial_number(x509.random_serial_number())
        .add_extension(
            x509.SubjectAlternativeName(
                [x509.DNSName("localhost"), x509.DNSName("127.0.0.1")]
            ),
            False,
        )
        .sign(
            serialization.load_pem_private_key(base64.b64decode(ca_key), None),
            hashes.SHA256(),
        )
    )

    with open(os.path.join(tls_dir, "tls.crt"), "w") as f:
        f.write(tls_cert.public_bytes(serialization.Encoding.PEM).decode("utf-8"))


def export_env(cluster_name, namespace):
    tls_dir = os.path.join(os.getcwd(), f"tls-{cluster_name}-{namespace}")
    os.environ["RAY_USE_TLS"] = "1"
    os.environ["RAY_TLS_SERVER_CERT"] = os.path.join(tls_dir, "tls.crt")
    os.environ["RAY_TLS_SERVER_KEY"] = os.path.join(tls_dir, "tls.key")
    os.environ["RAY_TLS_CA_CERT"] = os.path.join(tls_dir, "ca.crt")

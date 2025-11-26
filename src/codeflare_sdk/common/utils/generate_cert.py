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
import stat
import ipaddress
from pathlib import Path
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography import x509
from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID
import datetime
from datetime import timezone
from ..kubernetes_cluster.auth import (
    config_check,
    get_api_client,
)
from kubernetes import client
from .. import _kube_api_error_handling


def generate_ca_cert(days: int = 30):
    """
    Generates a self-signed CA certificate and private key, encoded in base64 format.

    The certificate includes RFC 5280 compliant extensions:
    - BasicConstraints (CA:TRUE)
    - KeyUsage (keyCertSign, cRLSign)
    - SubjectKeyIdentifier

    Similar to:
        openssl req -x509 -nodes -newkey rsa:3072 -keyout ca.key -days 1826 -out ca.crt -subj '/CN=root-ca'

    Args:
        days (int):
            The number of days for which the CA certificate will be valid. Default is 30.

    Returns:
        Tuple[str, str]:
            A tuple containing the base64-encoded private key and CA certificate.
    """

    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=3072,  # Increased from 2048 for better security
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
        .not_valid_before(datetime.datetime.now(timezone.utc) - one_day)
        .not_valid_after(datetime.datetime.now(timezone.utc) + (one_day * days))
        .serial_number(x509.random_serial_number())
        .public_key(public_key)
        # Add CA certificate extensions for RFC 5280 compliance
        .add_extension(
            x509.BasicConstraints(ca=True, path_length=0),
            critical=True,
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=False,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(public_key),
            critical=False,
        )
    )
    certificate = base64.b64encode(
        builder.sign(private_key=private_key, algorithm=hashes.SHA256()).public_bytes(
            serialization.Encoding.PEM
        )
    ).decode("utf-8")
    return key, certificate


def get_secret_name(cluster_name, namespace, api_instance):
    """
    Retrieves the name of the Kubernetes secret containing the CA certificate for the given Ray cluster.

    Args:
        cluster_name (str):
            The name of the Ray cluster.
        namespace (str):
            The Kubernetes namespace where the Ray cluster is located.
        api_instance (client.CoreV1Api):
            An instance of the Kubernetes CoreV1Api.

    Returns:
        str:
            The name of the Kubernetes secret containing the CA certificate.

    Raises:
        KeyError:
            If no secret matching the cluster name is found.
    """
    label_selector = f"ray.openshift.ai/cluster-name={cluster_name}"
    try:
        secrets = api_instance.list_namespaced_secret(
            namespace, label_selector=label_selector
        )
        for secret in secrets.items:
            if (
                f"{cluster_name}-ca-secret-" in secret.metadata.name
            ):  # Oauth secret share the same label this conditional is to make things more specific
                return secret.metadata.name
            else:
                continue
        raise KeyError(f"Unable to gather secret name for {cluster_name}")
    except Exception as e:  # pragma: no cover
        return _kube_api_error_handling(e)


def generate_tls_cert(cluster_name, namespace, days=30, force_regenerate=False):
    """
    Generates a TLS certificate and key for a Ray cluster, saving them locally along with the CA certificate.

    The certificate includes RFC 5280 compliant extensions:
    - BasicConstraints (CA:FALSE)
    - KeyUsage (digitalSignature, keyEncipherment)
    - ExtendedKeyUsage (serverAuth, clientAuth for mTLS)
    - SubjectAlternativeName (localhost, 127.0.0.1, ::1)
    - SubjectKeyIdentifier
    - AuthorityKeyIdentifier

    Files are created with restricted permissions (0600) for security.

    Certificates are stored in a user-private directory:
    - Default: ~/.local/share/codeflare/tls/{cluster_name}-{namespace}/
    - Override via CODEFLARE_TLS_DIR environment variable

    Args:
        cluster_name (str):
            The name of the Ray cluster.
        namespace (str):
            The Kubernetes namespace where the Ray cluster is located.
        days (int):
            The number of days for which the TLS certificate will be valid. Default is 30.
        force_regenerate (bool):
            If True, regenerates certificates even if they already exist. Useful when the server
            CA secret has been rotated and existing certificates are no longer valid. Default is False.

    Files Created:
        - ca.crt: The CA certificate (permissions: 0600).
        - tls.crt: The TLS certificate signed by the CA (permissions: 0600).
        - tls.key: The private key for the TLS certificate (permissions: 0600).

    Raises:
        Exception:
            If an error occurs while retrieving the CA secret.

    Example:
        # Normal generation
        generate_tls_cert("my-cluster", "default")

        # Force regeneration if CA was rotated
        generate_tls_cert("my-cluster", "default", force_regenerate=True)
    """
    tls_base_dir = _get_tls_base_dir()
    tls_dir = tls_base_dir / f"{cluster_name}-{namespace}"

    # Check if certificates already exist and skip if not forcing regeneration
    if not force_regenerate and tls_dir.exists():
        ca_crt = tls_dir / "ca.crt"
        tls_crt = tls_dir / "tls.crt"
        tls_key = tls_dir / "tls.key"

        if ca_crt.exists() and tls_crt.exists() and tls_key.exists():
            # Certificates already exist, no need to regenerate
            return

    # Create directory with secure permissions (including parent directories)
    tls_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    tls_dir = str(tls_dir)

    # Similar to:
    # oc get secret ca-secret-<cluster-name> -o template='{{index .data "tls.key"}}'
    # oc get secret ca-secret-<cluster-name> -o template='{{index .data "ca.crt"}}'|base64 -d > ${TLSDIR}/ca.crt
    config_check()
    v1 = client.CoreV1Api(get_api_client())

    # Secrets have a suffix appended to the end so we must list them and gather the secret that includes cluster_name-ca-secret-
    secret_name = get_secret_name(cluster_name, namespace, v1)
    secret = v1.read_namespaced_secret(secret_name, namespace).data

    ca_cert = secret.get("ca.crt") or secret.get("tls.crt")
    ca_key = secret.get("tls.key") or secret.get("ca.key")

    if not ca_cert:
        raise ValueError(
            f"CA certificate (ca.crt or tls.crt) not found in secret {secret_name}. "
            f"Available keys: {list(secret.keys())}"
        )
    if not ca_key:
        raise ValueError(
            f"CA private key (tls.key or ca.key) not found in secret {secret_name}. "
            f"Available keys: {list(secret.keys())}"
        )

    # Load the CA certificate for issuer information and AuthorityKeyIdentifier
    ca_cert_obj = x509.load_pem_x509_certificate(base64.b64decode(ca_cert))

    ca_private_key = serialization.load_pem_private_key(base64.b64decode(ca_key), None)

    # Write CA certificate with secure permissions
    ca_crt_path = os.path.join(tls_dir, "ca.crt")
    with open(ca_crt_path, "w") as f:
        f.write(base64.b64decode(ca_cert).decode("utf-8"))
    os.chmod(ca_crt_path, stat.S_IRUSR | stat.S_IWUSR)  # Set permissions to 0600

    # Generate tls.key and signed tls.cert locally for ray client
    # Similar to running these commands:
    # openssl req -nodes -newkey rsa:3072 -keyout ${TLSDIR}/tls.key -out ${TLSDIR}/tls.csr -subj '/CN=local'
    # cat <<EOF >${TLSDIR}/domain.ext
    # authorityKeyIdentifier=keyid,issuer
    # basicConstraints=CA:FALSE
    # keyUsage = digitalSignature, keyEncipherment
    # extendedKeyUsage = serverAuth, clientAuth
    # subjectAltName = @alt_names
    # [alt_names]
    # DNS.1 = localhost
    # IP.1 = 127.0.0.1
    # IP.2 = ::1
    # EOF
    # openssl x509 -req -CA ${TLSDIR}/ca.crt -CAkey ${TLSDIR}/ca.key -in ${TLSDIR}/tls.csr -out ${TLSDIR}/tls.crt -days 365 -CAcreateserial -extfile ${TLSDIR}/domain.ext
    key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=3072,  # Increased from 2048 for better security
    )

    tls_key = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    tls_key_path = os.path.join(tls_dir, "tls.key")
    with open(tls_key_path, "w") as f:
        f.write(tls_key.decode("utf-8"))
    os.chmod(tls_key_path, stat.S_IRUSR | stat.S_IWUSR)  # Set permissions to 0600

    # Build SAN list with service DNS names for cluster communication
    head_svc_name = f"{cluster_name}-head-svc"
    service_dns = f"{head_svc_name}.{namespace}.svc"
    service_dns_cluster_local = f"{head_svc_name}.{namespace}.svc.cluster.local"

    one_day = datetime.timedelta(1, 0, 0)
    tls_cert = (
        x509.CertificateBuilder()
        .issuer_name(ca_cert_obj.subject)
        .subject_name(
            x509.Name(
                [
                    x509.NameAttribute(NameOID.COMMON_NAME, "local"),
                ]
            )
        )
        .public_key(key.public_key())
        .not_valid_before(datetime.datetime.now(timezone.utc) - one_day)
        .not_valid_after(datetime.datetime.now(timezone.utc) + (one_day * days))
        .serial_number(x509.random_serial_number())
        # Add TLS certificate extensions for RFC 5280 compliance
        .add_extension(
            x509.BasicConstraints(ca=False, path_length=None),
            critical=True,
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=True,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.ExtendedKeyUsage(
                [
                    ExtendedKeyUsageOID.SERVER_AUTH,
                    ExtendedKeyUsageOID.CLIENT_AUTH,  # For mTLS support
                ]
            ),
            critical=True,
        )
        .add_extension(
            x509.SubjectAlternativeName(
                [
                    x509.DNSName("localhost"),
                    x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
                    x509.IPAddress(ipaddress.IPv6Address("::1")),
                    x509.DNSName(head_svc_name),
                    x509.DNSName(service_dns),
                    x509.DNSName(service_dns_cluster_local),
                ]
            ),
            critical=False,
        )
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(key.public_key()),
            critical=False,
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(
                ca_cert_obj.public_key()
            ),
            critical=False,
        )
        .sign(
            ca_private_key,
            hashes.SHA256(),
        )
    )

    tls_crt_path = os.path.join(tls_dir, "tls.crt")
    with open(tls_crt_path, "w") as f:
        f.write(tls_cert.public_bytes(serialization.Encoding.PEM).decode("utf-8"))
    os.chmod(tls_crt_path, stat.S_IRUSR | stat.S_IWUSR)  # Set permissions to 0600

    del ca_key, ca_private_key
    try:
        del secret
    except:
        pass  # May already be out of scope


def export_env(cluster_name, namespace):
    """
    Sets environment variables to configure TLS for a Ray cluster.

    Args:
        cluster_name (str):
            The name of the Ray cluster.
        namespace (str):
            The Kubernetes namespace where the Ray cluster is located.

    Environment Variables Set:
        - RAY_USE_TLS: Enables TLS for Ray.
        - RAY_TLS_SERVER_CERT: Path to the TLS server certificate.
        - RAY_TLS_SERVER_KEY: Path to the TLS server private key.
        - RAY_TLS_CA_CERT: Path to the CA certificate.
    """
    tls_base_dir = _get_tls_base_dir()
    tls_dir = tls_base_dir / f"{cluster_name}-{namespace}"
    tls_dir = str(tls_dir)
    os.environ["RAY_USE_TLS"] = "1"
    os.environ["RAY_TLS_SERVER_CERT"] = os.path.join(tls_dir, "tls.crt")
    os.environ["RAY_TLS_SERVER_KEY"] = os.path.join(tls_dir, "tls.key")
    os.environ["RAY_TLS_CA_CERT"] = os.path.join(tls_dir, "ca.crt")


def cleanup_tls_cert(cluster_name, namespace):
    """
    Removes TLS certificates and keys for a specific Ray cluster.

    This should be called when a cluster is deleted to clean up sensitive key material.

    Args:
        cluster_name (str):
            The name of the Ray cluster.
        namespace (str):
            The Kubernetes namespace where the Ray cluster is located.

    Returns:
        bool: True if certificates were removed, False if they didn't exist.

    Example:
        >>> cleanup_tls_cert("my-cluster", "default")
        True
    """
    import shutil

    tls_base_dir = _get_tls_base_dir()
    tls_dir = tls_base_dir / f"{cluster_name}-{namespace}"

    if tls_dir.exists():
        shutil.rmtree(tls_dir)
        return True
    return False


def list_tls_certificates():
    """
    Lists all TLS certificate directories and their details.

    Returns:
        list: List of dictionaries containing certificate information:
            - cluster_name: Name of the cluster
            - namespace: Kubernetes namespace
            - path: Full path to certificate directory
            - created: Creation time of the directory
            - size: Total size of certificates in bytes
            - cert_expiry: Expiration date of tls.crt (if readable)

    Example:
        >>> certs = list_tls_certificates()
        >>> for cert in certs:
        ...     print(f"{cert['cluster_name']}/{cert['namespace']}: expires {cert['cert_expiry']}")
    """
    tls_base_dir = _get_tls_base_dir()

    if not tls_base_dir.exists():
        return []

    certificates = []

    for cert_dir in tls_base_dir.iterdir():
        if cert_dir.is_dir():
            # Parse cluster name and namespace from directory name
            dir_name = cert_dir.name
            parts = dir_name.rsplit("-", 1)

            if len(parts) == 2:
                cluster_name, namespace = parts
            else:
                cluster_name = dir_name
                namespace = "unknown"

            # Get directory stats
            stat_info = cert_dir.stat()
            created = datetime.datetime.fromtimestamp(stat_info.st_ctime)

            # Calculate total size
            total_size = sum(
                f.stat().st_size for f in cert_dir.rglob("*") if f.is_file()
            )

            # Try to read certificate expiry
            cert_expiry = None
            tls_cert_path = cert_dir / "tls.crt"
            if tls_cert_path.exists():
                try:
                    with open(tls_cert_path, "rb") as f:
                        cert = x509.load_pem_x509_certificate(f.read())
                        cert_expiry = cert.not_valid_after_utc
                except Exception:
                    cert_expiry = None

            certificates.append(
                {
                    "cluster_name": cluster_name,
                    "namespace": namespace,
                    "path": str(cert_dir),
                    "created": created,
                    "size": total_size,
                    "cert_expiry": cert_expiry,
                }
            )

    return certificates


def cleanup_expired_certificates(dry_run=True):
    """
    Removes TLS certificates that have expired.

    Args:
        dry_run (bool):
            If True (default), only lists expired certificates without deleting them.
            Set to False to actually delete expired certificates.

    Returns:
        list: List of certificate paths that were (or would be) removed.

    Example:
        >>> # Check what would be deleted
        >>> expired = cleanup_expired_certificates(dry_run=True)
        >>> print(f"Found {len(expired)} expired certificates")
        >>>
        >>> # Actually delete them
        >>> cleanup_expired_certificates(dry_run=False)
    """
    import shutil

    now = datetime.datetime.now(timezone.utc)
    expired_certs = []

    certificates = list_tls_certificates()

    for cert_info in certificates:
        if cert_info["cert_expiry"] and cert_info["cert_expiry"] < now:
            expired_certs.append(cert_info["path"])

            if not dry_run:
                cert_dir = Path(cert_info["path"])
                if cert_dir.exists():
                    shutil.rmtree(cert_dir)

    return expired_certs


def cleanup_old_certificates(days=30, dry_run=True):
    """
    Removes TLS certificates older than a specified number of days.

    Args:
        days (int):
            Remove certificates created more than this many days ago. Default is 30.
        dry_run (bool):
            If True (default), only lists old certificates without deleting them.
            Set to False to actually delete old certificates.

    Returns:
        list: List of certificate paths that were (or would be) removed.

    Example:
        >>> # Check certificates older than 90 days
        >>> old = cleanup_old_certificates(days=90, dry_run=True)
        >>> print(f"Found {len(old)} certificates older than 90 days")
        >>>
        >>> # Delete certificates older than 30 days
        >>> cleanup_old_certificates(days=30, dry_run=False)
    """
    import shutil

    cutoff_date = datetime.datetime.now() - datetime.timedelta(days=days)
    old_certs = []

    certificates = list_tls_certificates()

    for cert_info in certificates:
        if cert_info["created"] < cutoff_date:
            old_certs.append(cert_info["path"])

            if not dry_run:
                cert_dir = Path(cert_info["path"])
                if cert_dir.exists():
                    shutil.rmtree(cert_dir)

    return old_certs


def refresh_tls_cert(cluster_name, namespace, days=30):
    """
    Refreshes TLS certificates by removing old ones and generating new ones.

    This is useful when the server CA secret has been rotated and existing
    client certificates are no longer valid.

    Args:
        cluster_name (str):
            The name of the Ray cluster.
        namespace (str):
            The Kubernetes namespace where the Ray cluster is located.
        days (int):
            The number of days for which the new TLS certificate will be valid. Default is 30.

    Returns:
        bool: True if certificates were successfully refreshed.

    Example:
        >>> # Server CA was rotated, refresh client certificates
        >>> refresh_tls_cert("my-cluster", "default")
        >>> export_env("my-cluster", "default")
        >>> # Now you can reconnect with fresh certificates
    """
    # Remove old certificates
    cleanup_tls_cert(cluster_name, namespace)

    # Generate new ones
    generate_tls_cert(cluster_name, namespace, days=days, force_regenerate=True)

    return True


def _get_tls_base_dir():
    """
    Get the base directory for TLS certificate storage.

    Priority order:
    1. CODEFLARE_TLS_DIR environment variable
    2. XDG_DATA_HOME/codeflare/tls (Linux standard)
    3. ~/.local/share/codeflare/tls (fallback)

    Returns:
        Path: Base directory for TLS certificates
    """
    # Check for explicit override
    tls_dir_env = os.environ.get("CODEFLARE_TLS_DIR")
    if tls_dir_env:
        return Path(tls_dir_env)

    # Use XDG Base Directory specification
    xdg_data_home = os.environ.get("XDG_DATA_HOME")
    if xdg_data_home:
        return Path(xdg_data_home) / "codeflare" / "tls"

    # Fallback to standard location
    return Path.home() / ".local" / "share" / "codeflare" / "tls"

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
Global pytest configuration for CodeFlare SDK tests.
This ensures proper mocking and isolation across all test modules.

IMPORTANT: This fixture does NOT globally patch kubernetes.config.load_kube_config
or load_incluster_config. Tests that need to assert config loader behavior will
patch them locally.
"""

import pytest
import os


@pytest.fixture(autouse=True)
def mock_kubernetes(monkeypatch, tmp_path):
    """
    Mock Kubernetes API clients with fake implementations that support
    the methods used by tests. This prevents actual API calls while
    allowing tests to exercise their code paths.

    CRITICAL: Does NOT patch kubernetes.config.load_kube_config or
    load_incluster_config globally. Tests will patch these locally as needed.
    """

    # Fake AuthenticationApi used by config_check() and auth flows
    class FakeAuthenticationApi:
        def __init__(self, api_client=None):
            self._api_client = api_client

        def get_api_group(self):
            """Return minimal expected shape for API group."""
            return {"kind": "APIGroupList", "groups": []}

    monkeypatch.setattr("kubernetes.client.AuthenticationApi", FakeAuthenticationApi)

    # Fake CoreV1Api with methods used by tests
    class FakeCoreV1Api:
        def __init__(self, api_client=None):
            pass

        def read_namespaced_secret(self, name, namespace):
            """Return a fake secret object with data attribute."""

            class Secret:
                data = {
                    "tls.crt": "ZmFrZWNlcnQ=",  # base64 "fakecert"
                    "tls.key": "ZmFrZWtleQ==",  # base64 "fakekey"
                }

            return Secret()

        def create_namespaced_secret(self, namespace, body):
            """Return created secret object."""

            class Secret:
                metadata = type(
                    "obj",
                    (object,),
                    {"name": body.get("metadata", {}).get("name", "created-secret")},
                )

            return Secret()

        def delete_namespaced_secret(self, name, namespace):
            """Return empty dict for delete operations."""
            return {}

        def list_namespace(self, *args, **kwargs):
            """Return empty namespace list."""

            class NamespaceList:
                items = []

            return NamespaceList()

    monkeypatch.setattr("kubernetes.client.CoreV1Api", FakeCoreV1Api)

    # Fake CustomObjectsApi with all methods used across tests
    class FakeCustomObjectsApi:
        def __init__(self, api_client=None):
            pass

        def list_namespaced_custom_object(
            self, group, version, namespace, plural, **kwargs
        ):
            """Return empty list of custom objects in namespace."""
            return {"items": []}

        def list_cluster_custom_object(self, group, version, plural, **kwargs):
            """Return empty list for cluster-scoped custom objects."""
            return {"items": []}

        def get_namespaced_custom_object(self, group, version, namespace, plural, name):
            """Return a minimal custom object."""
            return {"metadata": {"name": name, "namespace": namespace}, "spec": {}}

        def get_cluster_custom_object(self, group, version, plural, name):
            """Return a minimal cluster-scoped custom object."""
            return {
                "metadata": {"name": name},
                "spec": {"domain": "apps.cluster.example.com"},
            }

        def create_namespaced_custom_object(
            self, group, version, namespace, plural, body
        ):
            """Return created object metadata."""
            return {
                "metadata": {
                    "name": body.get("metadata", {}).get("name", "created"),
                    "namespace": namespace,
                }
            }

        def delete_namespaced_custom_object(self, *args, **kwargs):
            """Return empty dict for delete operations."""
            return {}

        def patch_namespaced_custom_object(self, *args, **kwargs):
            """Return empty dict for patch operations."""
            return {}

    monkeypatch.setattr("kubernetes.client.CustomObjectsApi", FakeCustomObjectsApi)

    # Mock load_kube_config to prevent actual kubeconfig parsing
    # Tests that need specific behavior will override this
    def mock_load_kube_config(*args, **kwargs):
        """Mock load_kube_config - does nothing but doesn't raise."""
        pass

    monkeypatch.setattr("kubernetes.config.load_kube_config", mock_load_kube_config)

    # Use real HOME directory for test resources
    # DO NOT change HOME - module-level code has already captured it
    import pathlib

    real_home = pathlib.Path.home()
    resources_dir = real_home / ".codeflare" / "resources"
    resources_dir.mkdir(parents=True, exist_ok=True)

    # Create a minimal kubeconfig file in ~/.kube/config if it doesn't exist
    # This prevents PermissionError in config_check()
    kube_dir = real_home / ".kube"
    kube_dir.mkdir(exist_ok=True)
    kubeconfig_path = kube_dir / "config"

    # Only create if it doesn't exist to avoid overwriting user's real kubeconfig
    kubeconfig_existed = kubeconfig_path.exists()
    if not kubeconfig_existed:
        kubeconfig_path.write_text(
            """
apiVersion: v1
kind: Config
clusters:
- cluster:
    server: https://127.0.0.1:6443
    insecure-skip-tls-verify: true
  name: test-cluster
contexts:
- context:
    cluster: test-cluster
    user: test-user
  name: test-context
current-context: test-context
users:
- name: test-user
  user:
    token: test-token
"""
        )

    # Create TLS certificate files under expected resource locations
    tls_dir = resources_dir / "tls-cluster-namespace"
    tls_dir.mkdir(exist_ok=True)
    (tls_dir / "ca.crt").write_text(
        "-----BEGIN CERTIFICATE-----\n"
        "MIIDMjCCAhqgAwIBAgIRAKz6UjGPWFAKGAKEAAAAIAQwDQYJKoZIhvcNAQELBQAw\n"
        "-----END CERTIFICATE-----\n"
    )
    (tls_dir / "ca.key").write_text(
        "-----BEGIN PRIVATE KEY-----\nFAKEKEY\n-----END PRIVATE KEY-----\n"
    )

    # Also create TLS files in CWD for tests that look relative to working directory
    cwd_tls_dir = tmp_path / "tls-cluster-namespace"
    cwd_tls_dir.mkdir(exist_ok=True)
    (cwd_tls_dir / "ca.crt").write_text(
        "-----BEGIN CERTIFICATE-----\n"
        "MIIDMjCCAhqgAwIBAgIRAKz6UjGPWFAKGAKEAAAAIAQwDQYJKoZIhvcNAQELBQAw\n"
        "-----END CERTIFICATE-----\n"
    )
    (cwd_tls_dir / "ca.key").write_text(
        "-----BEGIN PRIVATE KEY-----\nFAKEKEY\n-----END PRIVATE KEY-----\n"
    )

    yield

    # Cleanup: Remove TLS files created for tests
    if tls_dir.exists():
        try:
            for f in tls_dir.glob("*"):
                f.unlink()
            tls_dir.rmdir()
        except:
            pass

    # Remove fake kubeconfig if we created it
    if not kubeconfig_existed and kubeconfig_path.exists():
        try:
            kubeconfig_path.unlink()
        except:
            pass

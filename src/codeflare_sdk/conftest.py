# Copyright 2026 IBM, Red Hat
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
"""

import pytest
import os
from pathlib import Path


@pytest.fixture(scope="session", autouse=True)
def mock_kubernetes_config_for_ci(request):
    """
    Mock Kubernetes configuration for CI environments.
    This prevents tests from trying to access actual Kubernetes clusters.
    Only applies if running in CI (detected by CI environment variable).
    """
    # Check if running in CI
    is_ci = os.environ.get("CI") == "true" or os.environ.get("GITHUB_ACTIONS") == "true"

    if is_ci:
        # Create a minimal kubeconfig file for CI
        import tempfile

        kubeconfig_content = """
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
        # Create temporary kubeconfig
        with tempfile.NamedTemporaryFile(
            mode="w", delete=False, suffix=".kubeconfig"
        ) as f:
            f.write(kubeconfig_content)
            temp_kubeconfig = f.name

        # Set KUBECONFIG environment variable
        os.environ["KUBECONFIG"] = temp_kubeconfig

        yield

        # Cleanup
        os.unlink(temp_kubeconfig)
        if "KUBECONFIG" in os.environ:
            del os.environ["KUBECONFIG"]
    else:
        yield


@pytest.fixture(autouse=True)
def ensure_test_directories():
    """
    Ensure test directories exist before running tests.
    This prevents FileNotFoundError in tests that write files.
    """
    test_dirs = [
        os.path.expanduser("~/.codeflare/resources"),
    ]

    for directory in test_dirs:
        os.makedirs(directory, exist_ok=True)

    yield


@pytest.fixture(autouse=True)
def mock_kubernetes(monkeypatch, tmp_path):
    # Prevent kube config loaders from attempting actual cluster auth
    monkeypatch.setattr("kubernetes.config.load_kube_config", lambda *a, **k: None)
    monkeypatch.setattr("kubernetes.config.load_incluster_config", lambda *a, **k: None)

    # Mock AuthenticationApi (for api.get_api_group(), etc.)
    class FakeAuthenticationApi:
        def __init__(self, api_client=None):
            pass

        def get_api_group(self):
            return {}

    monkeypatch.setattr("kubernetes.client.AuthenticationApi", FakeAuthenticationApi)

    # Optionally mock other k8s clients used in tests if needed
    class FakeCoreV1Api:
        def __init__(self, api_client=None):
            pass

        def list_namespace(self, *args, **kwargs):
            return []

    monkeypatch.setattr("kubernetes.client.CoreV1Api", FakeCoreV1Api)

    class FakeCustomObjectsApi:
        def __init__(self, api_client=None):
            pass

        def get_cluster_custom_object(self, *args, **kwargs):
            return {}

    monkeypatch.setattr("kubernetes.client.CustomObjectsApi", FakeCustomObjectsApi)

    # Create all required test resource files in a fake HOME for the test session
    fake_home = tmp_path / "home"
    resources_dir = fake_home / ".codeflare" / "resources"
    resources_dir.mkdir(parents=True, exist_ok=True)

    # Resource files seen missing in your logs
    resources = [
        "test.yaml",
        "unit-test-cluster-kueue.yaml",
        "test-all-params.yaml",
    ]
    for fname in resources:
        (resources_dir / fname).write_text("kind: Test\n")

    # Create tls files under expected resource location
    tls_dir = resources_dir / "tls-cluster-namespace"
    tls_dir.mkdir(exist_ok=True)
    (tls_dir / "ca.crt").write_text(
        "-----BEGIN CERTIFICATE-----\nFAKE\n-----END CERTIFICATE-----\n"
    )
    (tls_dir / "ca.key").write_text("FAKEKEY\n")

    # Some tests may look in CWD for tls files, so create those too
    cwd_tls_dir = tmp_path / "tls-cluster-namespace"
    cwd_tls_dir.mkdir(exist_ok=True)
    (cwd_tls_dir / "ca.crt").write_text(
        "-----BEGIN CERTIFICATE-----\nFAKE\n-----END CERTIFICATE-----\n"
    )
    (cwd_tls_dir / "ca.key").write_text("FAKEKEY\n")

    # Point $HOME to ensure the tests use the mock resource directory
    monkeypatch.setenv("HOME", str(fake_home))

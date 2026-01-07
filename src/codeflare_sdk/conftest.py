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
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.kubeconfig') as f:
            f.write(kubeconfig_content)
            temp_kubeconfig = f.name

        # Set KUBECONFIG environment variable
        os.environ['KUBECONFIG'] = temp_kubeconfig

        yield

        # Cleanup
        os.unlink(temp_kubeconfig)
        if 'KUBECONFIG' in os.environ:
            del os.environ['KUBECONFIG']
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

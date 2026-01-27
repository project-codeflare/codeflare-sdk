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
Shared fixtures for rayclusters tests.

These fixtures keep test setup simple and avoid repeating boilerplate in every file.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from kubernetes.client import V1SecretVolumeSource, V1Volume, V1VolumeMount

from codeflare_sdk.ray.rayclusters import RayCluster


@pytest.fixture()
def simple_cluster():
    """
    Provide a minimal RayCluster instance for unit tests.

    This avoids Kubernetes calls and focuses tests on pure Python behavior.
    """
    return RayCluster(name="test-cluster", namespace="default")


@pytest.fixture()
def cluster_with_gpu():
    """Provide a RayCluster configured with GPU accelerators."""
    return RayCluster(
        name="gpu-cluster",
        namespace="default",
        head_accelerators={"nvidia.com/gpu": 1},
        worker_accelerators={"nvidia.com/gpu": 2},
    )


@pytest.fixture()
def cluster_with_gcs_ft():
    """Provide a RayCluster configured with GCS fault tolerance."""
    return RayCluster(
        name="gcs-ft-cluster",
        namespace="default",
        enable_gcs_ft=True,
        redis_address="redis:6379",
        redis_password_secret={"name": "redis-secret", "key": "password"},
    )


@pytest.fixture()
def cluster_with_envs():
    """Provide a RayCluster configured with environment variables."""
    return RayCluster(
        name="env-cluster",
        namespace="default",
        envs={"FOO": "bar"},
    )


@pytest.fixture()
def cluster_with_volumes():
    """Provide a RayCluster configured with volumes and mounts."""
    volume = V1Volume(name="data", secret=V1SecretVolumeSource(secret_name="demo"))
    mount = V1VolumeMount(name="data", mount_path="/data")
    return RayCluster(
        name="volume-cluster",
        namespace="default",
        volumes=[volume],
        volume_mounts=[mount],
    )


@pytest.fixture()
def mock_k8s_api():
    """Provide a simple mock Kubernetes API object."""
    return SimpleNamespace(
        list_namespaced_custom_object=MagicMock(),
        get_namespaced_custom_object=MagicMock(),
    )


@pytest.fixture()
def mock_requests():
    """Provide a mock requests.get callable."""
    return MagicMock()

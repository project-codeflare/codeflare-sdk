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
Tests for rayclusters constants.
"""

from codeflare_sdk.ray.rayclusters.constants import (
    CF_SDK_FIELD_MANAGER,
    DEFAULT_ACCELERATORS,
    FORBIDDEN_CUSTOM_RESOURCE_TYPES,
    _ODH_VOLUME_MOUNTS,
    _ODH_VOLUMES,
)


def test_default_accelerators_structure():
    """Ensure default accelerators include GPU mapping."""
    assert "nvidia.com/gpu" in DEFAULT_ACCELERATORS
    assert DEFAULT_ACCELERATORS["nvidia.com/gpu"] == "GPU"


def test_forbidden_resource_types():
    """Ensure forbidden resource types include CPU/memory/GPU."""
    assert "CPU" in FORBIDDEN_CUSTOM_RESOURCE_TYPES
    assert "memory" in FORBIDDEN_CUSTOM_RESOURCE_TYPES
    assert "GPU" in FORBIDDEN_CUSTOM_RESOURCE_TYPES


def test_odh_volume_mounts_structure():
    """Ensure ODH volume mounts are defined."""
    assert _ODH_VOLUME_MOUNTS
    assert all(getattr(mount, "mount_path", None) for mount in _ODH_VOLUME_MOUNTS)


def test_odh_volumes_structure():
    """Ensure ODH volumes are defined."""
    assert _ODH_VOLUMES
    assert all(getattr(volume, "name", None) for volume in _ODH_VOLUMES)


def test_field_manager_constant():
    """Ensure field manager constant is set."""
    assert CF_SDK_FIELD_MANAGER == "codeflare-sdk"

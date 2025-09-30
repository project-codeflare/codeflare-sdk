# Copyright 2025 IBM, Red Hat
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
Tests for common/utils/utils.py
"""

import pytest
from collections import namedtuple
from codeflare_sdk.common.utils.utils import (
    update_image,
    get_ray_image_for_python_version,
)
from codeflare_sdk.common.utils.constants import (
    SUPPORTED_PYTHON_VERSIONS,
    CUDA_PY311_RUNTIME_IMAGE,
    CUDA_PY312_RUNTIME_IMAGE,
)


def test_update_image_with_empty_string_python_311(mocker):
    """Test that update_image() with empty string returns default image for Python 3.11."""
    # Mock sys.version_info to simulate Python 3.11
    VersionInfo = namedtuple(
        "version_info", ["major", "minor", "micro", "releaselevel", "serial"]
    )
    mocker.patch("sys.version_info", VersionInfo(3, 11, 0, "final", 0))

    # Test with empty image (should use default for Python 3.11)
    image = update_image("")
    assert image == CUDA_PY311_RUNTIME_IMAGE
    assert image == SUPPORTED_PYTHON_VERSIONS["3.11"]


def test_update_image_with_empty_string_python_312(mocker):
    """Test that update_image() with empty string returns default image for Python 3.12."""
    # Mock sys.version_info to simulate Python 3.12
    VersionInfo = namedtuple(
        "version_info", ["major", "minor", "micro", "releaselevel", "serial"]
    )
    mocker.patch("sys.version_info", VersionInfo(3, 12, 0, "final", 0))

    # Test with empty image (should use default for Python 3.12)
    image = update_image("")
    assert image == CUDA_PY312_RUNTIME_IMAGE
    assert image == SUPPORTED_PYTHON_VERSIONS["3.12"]


def test_update_image_with_none_python_311(mocker):
    """Test that update_image() with None returns default image for Python 3.11."""
    # Mock sys.version_info to simulate Python 3.11
    VersionInfo = namedtuple(
        "version_info", ["major", "minor", "micro", "releaselevel", "serial"]
    )
    mocker.patch("sys.version_info", VersionInfo(3, 11, 0, "final", 0))

    # Test with None image (should use default for Python 3.11)
    image = update_image(None)
    assert image == CUDA_PY311_RUNTIME_IMAGE


def test_update_image_with_none_python_312(mocker):
    """Test that update_image() with None returns default image for Python 3.12."""
    # Mock sys.version_info to simulate Python 3.12
    VersionInfo = namedtuple(
        "version_info", ["major", "minor", "micro", "releaselevel", "serial"]
    )
    mocker.patch("sys.version_info", VersionInfo(3, 12, 0, "final", 0))

    # Test with None image (should use default for Python 3.12)
    image = update_image(None)
    assert image == CUDA_PY312_RUNTIME_IMAGE


def test_update_image_with_unsupported_python_version(mocker):
    """Test update_image() warning for unsupported Python versions."""
    # Mock sys.version_info to simulate Python 3.8 (unsupported)
    VersionInfo = namedtuple(
        "version_info", ["major", "minor", "micro", "releaselevel", "serial"]
    )
    mocker.patch("sys.version_info", VersionInfo(3, 8, 0, "final", 0))

    # Mock warnings.warn to check if it gets called
    warn_mock = mocker.patch("warnings.warn")

    # Call update_image with empty image
    image = update_image("")

    # Assert that the warning was called with the expected message
    warn_mock.assert_called_once()
    assert "No default Ray image defined for 3.8" in warn_mock.call_args[0][0]
    assert "3.11, 3.12" in warn_mock.call_args[0][0]

    # Assert that no image was set since the Python version is not supported
    assert image is None


def test_update_image_with_provided_custom_image():
    """Test that providing a custom image bypasses auto-detection."""
    custom_image = "my-custom-ray:latest"
    image = update_image(custom_image)

    # Should return the provided image unchanged
    assert image == custom_image


def test_update_image_with_provided_image_empty_string():
    """Test update_image() with provided custom image as a non-empty string."""
    custom_image = "docker.io/rayproject/ray:2.40.0"
    image = update_image(custom_image)

    # Should return the provided image unchanged
    assert image == custom_image


def test_get_ray_image_for_python_version_explicit_311():
    """Test get_ray_image_for_python_version() with explicit Python 3.11."""
    image = get_ray_image_for_python_version("3.11")
    assert image == CUDA_PY311_RUNTIME_IMAGE


def test_get_ray_image_for_python_version_explicit_312():
    """Test get_ray_image_for_python_version() with explicit Python 3.12."""
    image = get_ray_image_for_python_version("3.12")
    assert image == CUDA_PY312_RUNTIME_IMAGE


def test_get_ray_image_for_python_version_auto_detect_311(mocker):
    """Test get_ray_image_for_python_version() auto-detects Python 3.11."""
    # Mock sys.version_info to simulate Python 3.11
    VersionInfo = namedtuple(
        "version_info", ["major", "minor", "micro", "releaselevel", "serial"]
    )
    mocker.patch("sys.version_info", VersionInfo(3, 11, 0, "final", 0))

    # Test with None (should auto-detect)
    image = get_ray_image_for_python_version()
    assert image == CUDA_PY311_RUNTIME_IMAGE


def test_get_ray_image_for_python_version_auto_detect_312(mocker):
    """Test get_ray_image_for_python_version() auto-detects Python 3.12."""
    # Mock sys.version_info to simulate Python 3.12
    VersionInfo = namedtuple(
        "version_info", ["major", "minor", "micro", "releaselevel", "serial"]
    )
    mocker.patch("sys.version_info", VersionInfo(3, 12, 0, "final", 0))

    # Test with None (should auto-detect)
    image = get_ray_image_for_python_version()
    assert image == CUDA_PY312_RUNTIME_IMAGE


def test_get_ray_image_for_python_version_unsupported_with_warning(mocker):
    """Test get_ray_image_for_python_version() warns for unsupported versions."""
    warn_mock = mocker.patch("warnings.warn")

    # Test with unsupported version and warn_on_unsupported=True (default)
    image = get_ray_image_for_python_version("3.9", warn_on_unsupported=True)

    # Should have warned
    warn_mock.assert_called_once()
    assert "No default Ray image defined for 3.9" in warn_mock.call_args[0][0]

    # Should return None
    assert image is None


def test_get_ray_image_for_python_version_unsupported_without_warning():
    """Test get_ray_image_for_python_version() falls back to 3.12 without warning."""
    # Test with unsupported version and warn_on_unsupported=False
    image = get_ray_image_for_python_version("3.10", warn_on_unsupported=False)

    # Should fall back to Python 3.12 image
    assert image == CUDA_PY312_RUNTIME_IMAGE


def test_get_ray_image_for_python_version_unsupported_silent_fallback():
    """Test get_ray_image_for_python_version() silently falls back for old versions."""
    # Test with Python 3.8 and warn_on_unsupported=False
    image = get_ray_image_for_python_version("3.8", warn_on_unsupported=False)

    # Should fall back to Python 3.12 image without warning
    assert image == CUDA_PY312_RUNTIME_IMAGE


def test_get_ray_image_for_python_version_none_defaults_to_current(mocker):
    """Test that passing None to get_ray_image_for_python_version() uses current Python."""
    # Mock sys.version_info to simulate Python 3.11
    VersionInfo = namedtuple(
        "version_info", ["major", "minor", "micro", "releaselevel", "serial"]
    )
    mocker.patch("sys.version_info", VersionInfo(3, 11, 5, "final", 0))

    # Passing None should detect the mocked version
    image = get_ray_image_for_python_version(None, warn_on_unsupported=True)

    assert image == CUDA_PY311_RUNTIME_IMAGE

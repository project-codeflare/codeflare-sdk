# Copyright 2022-2025 IBM, Red Hat
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

from codeflare_sdk.common.utils.validation import (
    extract_ray_version_from_image,
    validate_ray_version_compatibility,
)
from codeflare_sdk.common.utils.constants import RAY_VERSION


class TestRayVersionDetection:
    """Test Ray version detection from container image names."""

    def test_extract_ray_version_standard_format(self):
        """Test extraction from standard Ray image formats."""
        # Standard format
        assert extract_ray_version_from_image("ray:2.47.1") == "2.47.1"
        assert extract_ray_version_from_image("ray:2.46.0") == "2.46.0"
        assert extract_ray_version_from_image("ray:1.13.0") == "1.13.0"

    def test_extract_ray_version_with_registry(self):
        """Test extraction from images with registry prefixes."""
        assert extract_ray_version_from_image("quay.io/ray:2.47.1") == "2.47.1"
        assert (
            extract_ray_version_from_image("docker.io/rayproject/ray:2.47.1")
            == "2.47.1"
        )
        assert (
            extract_ray_version_from_image("gcr.io/my-project/ray:2.47.1") == "2.47.1"
        )

    def test_extract_ray_version_with_suffixes(self):
        """Test extraction from images with version suffixes."""
        assert (
            extract_ray_version_from_image("quay.io/modh/ray:2.47.1-py311-cu121")
            == "2.47.1"
        )
        assert extract_ray_version_from_image("ray:2.47.1-py311") == "2.47.1"
        assert extract_ray_version_from_image("ray:2.47.1-gpu") == "2.47.1"
        assert extract_ray_version_from_image("ray:2.47.1-rocm62") == "2.47.1"

    def test_extract_ray_version_complex_registry_paths(self):
        """Test extraction from complex registry paths."""
        assert (
            extract_ray_version_from_image("quay.io/modh/ray:2.47.1-py311-cu121")
            == "2.47.1"
        )
        assert (
            extract_ray_version_from_image("registry.company.com/team/ray:2.47.1")
            == "2.47.1"
        )

    def test_extract_ray_version_no_version_found(self):
        """Test cases where no version can be extracted."""
        # SHA-based tags
        assert (
            extract_ray_version_from_image(
                "quay.io/modh/ray@sha256:6d076aeb38ab3c34a6a2ef0f58dc667089aa15826fa08a73273c629333e12f1e"
            )
            is None
        )

        # Non-semantic versions
        assert extract_ray_version_from_image("ray:latest") is None
        assert extract_ray_version_from_image("ray:nightly") is None
        assert (
            extract_ray_version_from_image("ray:v2.47") is None
        )  # Missing patch version

        # Non-Ray images
        assert extract_ray_version_from_image("python:3.11") is None
        assert extract_ray_version_from_image("ubuntu:20.04") is None

        # Empty or None
        assert extract_ray_version_from_image("") is None
        assert extract_ray_version_from_image(None) is None

    def test_extract_ray_version_edge_cases(self):
        """Test edge cases for version extraction."""
        # Version with 'v' prefix should not match our pattern
        assert extract_ray_version_from_image("ray:v2.47.1") is None

        # Multiple version-like patterns - should match the first valid one
        assert (
            extract_ray_version_from_image("registry/ray:2.47.1-based-on-1.0.0")
            == "2.47.1"
        )


class TestRayVersionValidation:
    """Test Ray version compatibility validation."""

    def test_validate_compatible_versions(self):
        """Test validation with compatible Ray versions."""
        # Exact match
        is_compatible, is_warning, message = validate_ray_version_compatibility(
            f"ray:{RAY_VERSION}"
        )
        assert is_compatible is True
        assert is_warning is False
        assert "Ray versions match" in message

        # With registry and suffixes
        is_compatible, is_warning, message = validate_ray_version_compatibility(
            f"quay.io/modh/ray:{RAY_VERSION}-py311-cu121"
        )
        assert is_compatible is True
        assert is_warning is False
        assert "Ray versions match" in message

    def test_validate_incompatible_versions(self):
        """Test validation with incompatible Ray versions."""
        # Different version
        is_compatible, is_warning, message = validate_ray_version_compatibility(
            "ray:2.46.0"
        )
        assert is_compatible is False
        assert is_warning is False
        assert "Ray version mismatch detected" in message
        assert "CodeFlare SDK uses Ray" in message
        assert "runtime image uses Ray" in message

        # Older version
        is_compatible, is_warning, message = validate_ray_version_compatibility(
            "ray:1.13.0"
        )
        assert is_compatible is False
        assert is_warning is False
        assert "Ray version mismatch detected" in message

    def test_validate_empty_image(self):
        """Test validation with no custom image (should use default)."""
        # Empty string
        is_compatible, is_warning, message = validate_ray_version_compatibility("")
        assert is_compatible is True
        assert is_warning is False
        assert "Using default Ray image compatible with SDK" in message

        # None
        is_compatible, is_warning, message = validate_ray_version_compatibility(None)
        assert is_compatible is True
        assert is_warning is False
        assert "Using default Ray image compatible with SDK" in message

    def test_validate_unknown_version(self):
        """Test validation when version cannot be determined."""
        # SHA-based image
        is_compatible, is_warning, message = validate_ray_version_compatibility(
            "quay.io/modh/ray@sha256:6d076aeb38ab3c34a6a2ef0f58dc667089aa15826fa08a73273c629333e12f1e"
        )
        assert is_compatible is True
        assert is_warning is True
        assert "Cannot determine Ray version" in message

        # Custom image without version
        is_compatible, is_warning, message = validate_ray_version_compatibility(
            "my-custom-ray:latest"
        )
        assert is_compatible is True
        assert is_warning is True
        assert "Cannot determine Ray version" in message

    def test_validate_custom_sdk_version(self):
        """Test validation with custom SDK version."""
        # Compatible with custom SDK version
        is_compatible, is_warning, message = validate_ray_version_compatibility(
            "ray:2.46.0", "2.46.0"
        )
        assert is_compatible is True
        assert is_warning is False
        assert "Ray versions match" in message

        # Incompatible with custom SDK version
        is_compatible, is_warning, message = validate_ray_version_compatibility(
            "ray:2.47.1", "2.46.0"
        )
        assert is_compatible is False
        assert is_warning is False
        assert "CodeFlare SDK uses Ray 2.46.0" in message
        assert "runtime image uses Ray 2.47.1" in message

    def test_validate_message_content(self):
        """Test that validation messages contain expected guidance."""
        # Mismatch message should contain helpful guidance
        is_compatible, is_warning, message = validate_ray_version_compatibility(
            "ray:2.46.0"
        )
        assert is_compatible is False
        assert is_warning is False
        assert "compatibility issues" in message.lower()
        assert "unexpected behavior" in message.lower()
        assert "please use a runtime image" in message.lower()
        assert "update your sdk version" in message.lower()

    def test_semantic_version_comparison(self):
        """Test that semantic version comparison works correctly."""
        # Test that 2.10.0 > 2.9.1 (would fail with string comparison)
        is_compatible, is_warning, message = validate_ray_version_compatibility(
            "ray:2.10.0", "2.9.1"
        )
        assert is_compatible is False
        assert is_warning is False
        assert "CodeFlare SDK uses Ray 2.9.1" in message
        assert "runtime image uses Ray 2.10.0" in message

        # Test that 2.9.1 < 2.10.0 (would fail with string comparison)
        is_compatible, is_warning, message = validate_ray_version_compatibility(
            "ray:2.9.1", "2.10.0"
        )
        assert is_compatible is False
        assert is_warning is False
        assert "CodeFlare SDK uses Ray 2.10.0" in message
        assert "runtime image uses Ray 2.9.1" in message

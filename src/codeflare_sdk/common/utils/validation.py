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

"""
Validation utilities for the CodeFlare SDK.

This module contains validation functions used across the SDK for ensuring
configuration compatibility and correctness.
"""

import logging
import re
from typing import Optional, Tuple
from packaging.version import Version, InvalidVersion
from .constants import RAY_VERSION

logger = logging.getLogger(__name__)


def extract_ray_version_from_image(image_name: str) -> Optional[str]:
    """
    Extract Ray version from a container image name.

    Supports various image naming patterns:
    - quay.io/modh/ray:2.47.1-py311-cu121
    - ray:2.47.1
    - some-registry/ray:2.47.1-py311
    - quay.io/modh/ray@sha256:... (falls back to None)

    Args:
        image_name: The container image name/tag

    Returns:
        The extracted Ray version, or None if not found
    """
    if not image_name:
        return None

    # Pattern to match semantic version after ray: or ray/
    # Looks for patterns like ray:2.47.1, ray:2.47.1-py311, etc.
    patterns = [
        r"ray:(\d+\.\d+\.\d+)",  # ray:2.47.1
        r"ray/[^:]*:(\d+\.\d+\.\d+)",  # registry/ray:2.47.1
        r"/ray:(\d+\.\d+\.\d+)",  # any-registry/ray:2.47.1
    ]

    for pattern in patterns:
        match = re.search(pattern, image_name)
        if match:
            return match.group(1)

    # If we can't extract version, return None to indicate unknown
    return None


def validate_ray_version_compatibility(
    image_name: str, sdk_ray_version: str = RAY_VERSION
) -> Tuple[bool, bool, str]:
    """
    Validate that the Ray version in the runtime image matches the SDK's Ray version.

    Args:
        image_name: The container image name/tag
        sdk_ray_version: The Ray version used by the CodeFlare SDK

    Returns:
        tuple: (is_compatible, is_warning, message)
            - is_compatible: True if versions match or cannot be determined, False if mismatch
            - is_warning: True if this is a warning (non-fatal), False otherwise
            - message: Descriptive message about the validation result
    """
    if not image_name:
        # No custom image specified, will use default - this is compatible
        logger.debug("Using default Ray image compatible with SDK")
        return True, False, "Using default Ray image compatible with SDK"

    image_ray_version = extract_ray_version_from_image(image_name)

    if image_ray_version is None:
        # Cannot determine version from image name, issue a warning but allow
        return (
            True,
            True,
            f"Cannot determine Ray version from image '{image_name}'. Please ensure it's compatible with Ray {sdk_ray_version}",
        )

    # Use semantic version comparison for robust version checking
    try:
        sdk_version = Version(sdk_ray_version)
        image_version = Version(image_ray_version)

        if image_version != sdk_version:
            # Version mismatch detected
            message = (
                f"Ray version mismatch detected!\n"
                f"CodeFlare SDK uses Ray {sdk_ray_version}, but runtime image uses Ray {image_ray_version}.\n"
                f"This mismatch can cause compatibility issues and unexpected behavior.\n"
                f"Please use a runtime image with Ray {sdk_ray_version} or update your SDK version."
            )
            return False, False, message
    except InvalidVersion as e:
        # If version parsing fails, fall back to string comparison with a warning
        logger.warning(
            f"Failed to parse version for comparison ({e}), falling back to string comparison"
        )
        if image_ray_version != sdk_ray_version:
            message = (
                f"Ray version mismatch detected!\n"
                f"CodeFlare SDK uses Ray {sdk_ray_version}, but runtime image uses Ray {image_ray_version}.\n"
                f"This mismatch can cause compatibility issues and unexpected behavior.\n"
                f"Please use a runtime image with Ray {sdk_ray_version} or update your SDK version."
            )
            return False, False, message

    # Versions match
    logger.debug(
        f"Ray version validation successful: SDK and runtime image both use Ray {sdk_ray_version}"
    )
    return (
        True,
        False,
        f"Ray versions match: SDK and runtime image both use Ray {sdk_ray_version}",
    )

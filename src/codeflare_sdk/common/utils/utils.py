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
import sys

from codeflare_sdk.common.utils.constants import (
    SUPPORTED_PYTHON_VERSIONS,
    CUDA_PY312_RUNTIME_IMAGE,
)


def update_image(image) -> str:
    """
    The update_image() function automatically sets the image config parameter to a preset image based on Python version if not specified.
    This now points to the centralized function in utils.py.
    """
    if not image:
        # Pull the image based on the matching Python version (or output a warning if not supported)
        image = get_ray_image_for_python_version(warn_on_unsupported=True)
    return image


def get_ray_image_for_python_version(python_version=None, warn_on_unsupported=True):
    """
    Get the appropriate Ray image for a given Python version.
    If no version is provided, uses the current runtime Python version.
    This prevents us needing to hard code image versions for tests.

    Args:
        python_version: Python version string (e.g. "3.11"). If None, detects current version.
        warn_on_unsupported: If True, warns and returns None for unsupported versions.
                           If False, silently falls back to Python 3.12 image.
    """
    if python_version is None:
        python_version = f"{sys.version_info.major}.{sys.version_info.minor}"

    if python_version in SUPPORTED_PYTHON_VERSIONS:
        return SUPPORTED_PYTHON_VERSIONS[python_version]
    elif warn_on_unsupported:
        import warnings

        warnings.warn(
            f"No default Ray image defined for {python_version}. Please provide your own image or use one of the following python versions: {', '.join(SUPPORTED_PYTHON_VERSIONS.keys())}."
        )
        return None
    else:
        return CUDA_PY312_RUNTIME_IMAGE

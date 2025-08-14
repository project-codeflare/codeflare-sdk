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

import pytest
from codeflare_sdk.common.utils.constants import RAY_VERSION, CUDA_RUNTIME_IMAGE


class TestConstants:
    """Test constants module for expected values."""

    def test_ray_version_is_defined(self):
        """Test that RAY_VERSION constant is properly defined."""
        assert RAY_VERSION is not None
        assert isinstance(RAY_VERSION, str)
        assert RAY_VERSION == "2.47.1"

    def test_cuda_runtime_image_is_defined(self):
        """Test that CUDA_RUNTIME_IMAGE constant is properly defined."""
        assert CUDA_RUNTIME_IMAGE is not None
        assert isinstance(CUDA_RUNTIME_IMAGE, str)
        assert "quay.io/modh/ray" in CUDA_RUNTIME_IMAGE

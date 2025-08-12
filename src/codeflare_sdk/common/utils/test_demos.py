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
Tests for demos module.
"""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
from codeflare_sdk.common.utils.demos import copy_demo_nbs


class TestCopyDemoNbs:
    """Test cases for copy_demo_nbs function."""

    def test_copy_demo_nbs_directory_exists_error(self):
        """Test that FileExistsError is raised when directory exists and overwrite=False."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a subdirectory that will conflict
            conflict_dir = Path(temp_dir) / "demo-notebooks"
            conflict_dir.mkdir()

            with pytest.raises(FileExistsError, match="Directory.*already exists"):
                copy_demo_nbs(dir=str(conflict_dir), overwrite=False)

    def test_copy_demo_nbs_overwrite_true(self):
        """Test that overwrite=True allows copying to existing directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a subdirectory that will conflict
            conflict_dir = Path(temp_dir) / "demo-notebooks"
            conflict_dir.mkdir()

            # Mock the demo_dir to point to a real directory
            with patch("codeflare_sdk.common.utils.demos.demo_dir", temp_dir):
                # Should not raise an error with overwrite=True
                copy_demo_nbs(dir=str(conflict_dir), overwrite=True)

    def test_copy_demo_nbs_default_parameters(self):
        """Test copy_demo_nbs with default parameters."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Mock the demo_dir to point to a real directory
            with patch("codeflare_sdk.common.utils.demos.demo_dir", temp_dir):
                # Should work with default parameters
                copy_demo_nbs(dir=temp_dir, overwrite=True)

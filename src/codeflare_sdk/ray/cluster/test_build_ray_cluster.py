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
from collections import namedtuple
import sys
from .build_ray_cluster import gen_names, update_image
import uuid


def test_gen_names_with_name(mocker):
    mocker.patch.object(
        uuid, "uuid4", return_value=uuid.UUID("00000000-0000-0000-0000-000000000001")
    )
    name = "myname"
    appwrapper_name, cluster_name = gen_names(name)
    assert appwrapper_name == name
    assert cluster_name == name


def test_gen_names_without_name(mocker):
    mocker.patch.object(
        uuid, "uuid4", return_value=uuid.UUID("00000000-0000-0000-0000-000000000001")
    )
    appwrapper_name, cluster_name = gen_names(None)
    assert appwrapper_name.startswith("appwrapper-")
    assert cluster_name.startswith("cluster-")


def test_update_image_without_supported_python_version(mocker):
    # Mock SUPPORTED_PYTHON_VERSIONS
    mocker.patch.dict(
        "codeflare_sdk.ray.cluster.build_ray_cluster.SUPPORTED_PYTHON_VERSIONS",
        {
            "3.9": "ray-py3.9",
            "3.11": "ray-py3.11",
        },
    )

    # Create a namedtuple to mock sys.version_info
    VersionInfo = namedtuple(
        "version_info", ["major", "minor", "micro", "releaselevel", "serial"]
    )
    mocker.patch.object(sys, "version_info", VersionInfo(3, 8, 0, "final", 0))

    # Mock warnings.warn to check if it gets called
    warn_mock = mocker.patch("warnings.warn")

    # Call the update_image function with no image provided
    image = update_image(None)

    # Assert that the warning was called with the expected message
    warn_mock.assert_called_once_with(
        "No default Ray image defined for 3.8. Please provide your own image or use one of the following python versions: 3.9, 3.11."
    )

    # Assert that no image was set since the Python version is not supported
    assert image is None

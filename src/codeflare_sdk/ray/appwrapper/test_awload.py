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
from codeflare_sdk.common.utils.unit_test_support import (
    arg_check_aw_apply_effect,
    arg_check_aw_del_effect,
)
from codeflare_sdk.ray.appwrapper import AWManager
from codeflare_sdk.ray.cluster import Cluster, ClusterConfiguration
import os
from pathlib import Path

parent = Path(__file__).resolve().parents[4]  # project directory
aw_dir = os.path.expanduser("~/.codeflare/resources/")


def test_AWManager_creation(mocker):
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch("kubernetes.client.CustomObjectsApi.list_namespaced_custom_object")
    # Create test.yaml
    Cluster(
        ClusterConfiguration(
            name="test",
            namespace="ns",
            write_to_file=True,
            appwrapper=True,
        )
    )

    testaw = AWManager(f"{aw_dir}test.yaml")
    assert testaw.name == "test"
    assert testaw.namespace == "ns"
    assert testaw.submitted == False
    try:
        testaw = AWManager("fake")
    except Exception as e:
        assert type(e) == FileNotFoundError
        assert str(e) == "[Errno 2] No such file or directory: 'fake'"
    try:
        testaw = AWManager(
            f"{parent}/tests/test_cluster_yamls/appwrapper/test-case-bad.yaml"
        )
    except Exception as e:
        assert type(e) == ValueError
        assert (
            str(e)
            == f"{parent}/tests/test_cluster_yamls/appwrapper/test-case-bad.yaml is not a correctly formatted AppWrapper yaml"
        )


def test_AWManager_submit_remove(mocker, capsys):
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    testaw = AWManager(f"{aw_dir}test.yaml")
    testaw.remove()
    captured = capsys.readouterr()
    assert (
        captured.out
        == "AppWrapper not submitted by this manager yet, nothing to remove\n"
    )
    assert testaw.submitted == False
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.create_namespaced_custom_object",
        side_effect=arg_check_aw_apply_effect,
    )
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.delete_namespaced_custom_object",
        side_effect=arg_check_aw_del_effect,
    )
    testaw.submit()
    assert testaw.submitted == True
    testaw.remove()
    assert testaw.submitted == False


# Make sure to always keep this function last
def test_cleanup():
    os.remove(f"{aw_dir}test.yaml")

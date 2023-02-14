# Copyright 2022 IBM, Red Hat
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

from pathlib import Path
import sys
import filecmp
import os

parent = Path(__file__).resolve().parents[1]
sys.path.append(str(parent) + "/src")

from codeflare_sdk.cluster.cluster import (
    Cluster,
    ClusterConfiguration,
    get_current_namespace,
    list_all_clusters,
    list_all_queued,
)
from codeflare_sdk.cluster.auth import (
    TokenAuthentication,
    PasswordUserAuthentication,
    Authentication,
)
from codeflare_sdk.utils.generate_yaml import main
import openshift
from openshift import OpenShiftPythonException
import ray
import pytest


# For mocking openshift client results
fake_res = openshift.Result("fake")


def arg_side_effect(*args):
    fake_res.high_level_operation = args
    return fake_res


def att_side_effect(self):
    return self.high_level_operation


def att_side_effect_tls(self):
    if "--insecure-skip-tls-verify" in self.high_level_operation[1]:
        return self.high_level_operation
    else:
        raise OpenShiftPythonException(
            "The server uses a certificate signed by unknown authority"
        )


def test_token_auth_creation():
    try:
        token_auth = TokenAuthentication()
        assert token_auth.token == None
        assert token_auth.server == None
        assert token_auth.skip_tls == False

        token_auth = TokenAuthentication("token")
        assert token_auth.token == "token"
        assert token_auth.server == None
        assert token_auth.skip_tls == False

        token_auth = TokenAuthentication("token", "server")
        assert token_auth.token == "token"
        assert token_auth.server == "server"
        assert token_auth.skip_tls == False

        token_auth = TokenAuthentication("token", server="server")
        assert token_auth.token == "token"
        assert token_auth.server == "server"
        assert token_auth.skip_tls == False

        token_auth = TokenAuthentication(token="token", server="server")
        assert token_auth.token == "token"
        assert token_auth.server == "server"
        assert token_auth.skip_tls == False

        token_auth = TokenAuthentication(token="token", server="server", skip_tls=True)
        assert token_auth.token == "token"
        assert token_auth.server == "server"
        assert token_auth.skip_tls == True

    except Exception:
        assert 0 == 1


def test_token_auth_login_logout(mocker):
    mocker.patch("openshift.invoke", side_effect=arg_side_effect)
    mock_res = mocker.patch.object(openshift.Result, "out")
    mock_res.side_effect = lambda: att_side_effect(fake_res)

    token_auth = TokenAuthentication(token="testtoken", server="testserver")
    assert token_auth.login() == (
        "login",
        ["--token=testtoken", "--server=testserver:6443"],
    )
    assert token_auth.logout() == ("logout",)


def test_token_auth_login_tls(mocker):
    mocker.patch("openshift.invoke", side_effect=arg_side_effect)
    mock_res = mocker.patch.object(openshift.Result, "out")
    mock_res.side_effect = lambda: att_side_effect_tls(fake_res)

    # FIXME - Pytest mocker not allowing caught exception
    # token_auth = TokenAuthentication(token="testtoken", server="testserver")
    # assert token_auth.login() == "Error: certificate auth failure, please set `skip_tls=True` in TokenAuthentication"

    token_auth = TokenAuthentication(
        token="testtoken", server="testserver", skip_tls=True
    )
    assert token_auth.login() == (
        "login",
        ["--token=testtoken", "--server=testserver:6443", "--insecure-skip-tls-verify"],
    )


def test_passwd_auth_creation():
    try:
        passwd_auth = PasswordUserAuthentication()
        assert passwd_auth.username == None
        assert passwd_auth.password == None

        passwd_auth = PasswordUserAuthentication("user")
        assert passwd_auth.username == "user"
        assert passwd_auth.password == None

        passwd_auth = PasswordUserAuthentication("user", "passwd")
        assert passwd_auth.username == "user"
        assert passwd_auth.password == "passwd"

        passwd_auth = PasswordUserAuthentication("user", password="passwd")
        assert passwd_auth.username == "user"
        assert passwd_auth.password == "passwd"

        passwd_auth = PasswordUserAuthentication(username="user", password="passwd")
        assert passwd_auth.username == "user"
        assert passwd_auth.password == "passwd"

    except Exception:
        assert 0 == 1


def test_passwd_auth_login_logout(mocker):
    mocker.patch("openshift.invoke", side_effect=arg_side_effect)
    mocker.patch("openshift.login", side_effect=arg_side_effect)
    mock_res = mocker.patch.object(openshift.Result, "out")
    mock_res.side_effect = lambda: att_side_effect(fake_res)

    token_auth = PasswordUserAuthentication(username="user", password="passwd")
    assert token_auth.login() == ("user", "passwd")
    assert token_auth.logout() == ("logout",)


def test_auth_coverage():
    abstract = Authentication()
    abstract.login()
    abstract.logout()


def test_config_creation():
    config = ClusterConfiguration(
        name="unit-test-cluster",
        namespace="ns",
        min_worker=1,
        max_worker=2,
        min_cpus=3,
        max_cpus=4,
        min_memory=5,
        max_memory=6,
        gpu=7,
        instascale=True,
        machine_types=["cpu.small", "gpu.large"],
        auth=TokenAuthentication(token="testtoken", server="testserver"),
    )

    assert config.name == "unit-test-cluster" and config.namespace == "ns"
    assert config.min_worker == 1 and config.max_worker == 2
    assert config.min_cpus == 3 and config.max_cpus == 4
    assert config.min_memory == 5 and config.max_memory == 6
    assert config.gpu == 7
    assert (
        config.image
        == "ghcr.io/foundation-model-stack/base:ray2.1.0-py38-gpu-pytorch1.12.0cu116-20221213-193103"
    )
    assert config.template == f"{parent}/src/codeflare_sdk/templates/new-template.yaml"
    assert config.instascale
    assert config.machine_types == ["cpu.small", "gpu.large"]
    assert config.auth.__class__ == TokenAuthentication
    return config


def test_cluster_creation():
    cluster = Cluster(test_config_creation())
    assert cluster.app_wrapper_yaml == "unit-test-cluster.yaml"
    assert cluster.app_wrapper_name == "unit-test-cluster"
    assert filecmp.cmp(
        "unit-test-cluster.yaml", f"{parent}/tests/test-case.yaml", shallow=True
    )
    return cluster


def arg_check_apply_effect(*args):
    assert args[0] == "apply"
    assert args[1] == ["-f", "unit-test-cluster.yaml"]


def arg_check_del_effect(*args):
    assert args[0] == "delete"
    assert args[1] == ["AppWrapper", "unit-test-cluster"]


def test_cluster_up_down(mocker):
    mocker.patch(
        "codeflare_sdk.cluster.auth.TokenAuthentication.login", return_value="ignore"
    )
    mocker.patch(
        "codeflare_sdk.cluster.auth.TokenAuthentication.logout", return_value="ignore"
    )
    mocker.patch("openshift.invoke", side_effect=arg_check_apply_effect)
    cluster = test_cluster_creation()
    cluster.up()
    mocker.patch("openshift.invoke", side_effect=arg_check_del_effect)
    cluster.down()


def out_route(self):
    return "ray-dashboard-raycluster-autoscaler-ns.apps.cluster.awsroute.org ray-dashboard-unit-test-cluster-ns.apps.cluster.awsroute.org"


def test_cluster_uris(mocker):
    mocker.patch("openshift.invoke", return_value=fake_res)
    mock_res = mocker.patch.object(openshift.Result, "out")
    mock_res.side_effect = lambda: out_route(fake_res)

    cluster = test_cluster_creation()
    assert cluster.cluster_uri() == "ray://unit-test-cluster-head-svc.ns.svc:10001"
    assert (
        cluster.cluster_dashboard_uri()
        == "http://ray-dashboard-unit-test-cluster-ns.apps.cluster.awsroute.org"
    )
    cluster.config.name = "fake"
    assert (
        cluster.cluster_dashboard_uri()
        == "Dashboard route not available yet, have you run cluster.up()?"
    )


def ray_addr(self):
    return self._address


def test_ray_job_wrapping(mocker):
    mocker.patch("openshift.invoke", return_value=fake_res)
    mock_res = mocker.patch.object(openshift.Result, "out")
    mock_res.side_effect = lambda: out_route(fake_res)
    cluster = test_cluster_creation()

    mocker.patch(
        "ray.job_submission.JobSubmissionClient._check_connection_and_version_with_url",
        return_value="None",
    )
    # mocker.patch("ray.job_submission.JobSubmissionClient.list_jobs", side_effect=ray_addr)
    mock_res = mocker.patch.object(
        ray.job_submission.JobSubmissionClient, "list_jobs", autospec=True
    )
    mock_res.side_effect = ray_addr
    assert cluster.list_jobs() == cluster.cluster_dashboard_uri()
    # cluster.job_status()
    # cluster.job_logs()


def test_get_namespace(mocker):
    pass


def test_list_clusters(mocker):
    pass


def test_list_queue(mocker):
    pass


def test_cmd_line_generation():
    os.system(
        f"python3 {parent}/src/codeflare_sdk/utils/generate_yaml.py --name=unit-cmd-cluster --min-cpu=1 --max-cpu=1 --min-memory=2 --max-memory=2 --gpu=1 --workers=2 --template=src/codeflare_sdk/templates/new-template.yaml"
    )
    assert filecmp.cmp(
        "unit-cmd-cluster.yaml", f"{parent}/tests/test-case-cmd.yaml", shallow=True
    )
    os.remove("unit-test-cluster.yaml")
    os.remove("unit-cmd-cluster.yaml")

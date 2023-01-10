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

from codeflare_sdk.cluster.cluster import Cluster, ClusterConfiguration
from codeflare_sdk.cluster.auth import TokenAuthentication, PasswordUserAuthentication
import openshift
import pytest


# For mocking openshift client results
fake_res = openshift.Result("fake")


def arg_side_effect(*args):
    fake_res.high_level_operation = args
    return fake_res


def att_side_effect(self):
    return self.high_level_operation


def test_token_auth_creation():
    try:
        token_auth = TokenAuthentication()
        assert token_auth.token == None
        assert token_auth.server == None

        token_auth = TokenAuthentication("token")
        assert token_auth.token == "token"
        assert token_auth.server == None

        token_auth = TokenAuthentication("token", "server")
        assert token_auth.token == "token"
        assert token_auth.server == "server"

        token_auth = TokenAuthentication("token", server="server")
        assert token_auth.token == "token"
        assert token_auth.server == "server"

        token_auth = TokenAuthentication(token="token", server="server")
        assert token_auth.token == "token"
        assert token_auth.server == "server"

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

# Copyright 2026 IBM, Red Hat
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

"""What of the v0.39.x public surface still works, and what does not.

RHOAIENG-98947. ``set_api_client``, the legacy auth classes and the
``2_basic_interactive`` notebook all work again. ``ManagedClusterConfig`` does
not and is not coming back, so v0.39.1 copies of ``5_submit_rayjob_cr`` and
``7_rayjob_checkpointing`` still fail at import; what is tested there is that
the error explains itself.
"""

import re
import warnings

import pytest
from kubernetes import client

from codeflare_sdk import (
    Authentication,
    KubeConfigFileAuthentication,
    TokenAuthentication,
)
from codeflare_sdk._compat import REMOVED
from codeflare_sdk.common.kubernetes_cluster import auth


class TestNotebookFromV0391StillRuns:
    """demo-notebooks/guided-demos/2_basic_interactive.ipynb as it shipped.

    That notebook is the concrete promise: a user who wrote against v0.39.1
    must not have to edit it. Its first cell is reproduced verbatim.
    """

    def test_opening_import_line(self):
        from codeflare_sdk import (  # noqa: F401
            Cluster,
            ClusterConfiguration,
            set_api_client,
        )
        from kube_authkit import AuthConfig, get_k8s_client  # noqa: F401

    def test_auth_cell_binds_the_client(self):
        """The notebook's cell 2 run for real, not a paraphrase.

        It builds an AuthConfig, passes it to get_k8s_client, and hands the
        result to set_api_client. Calling set_api_client(ApiClient()) directly
        would skip the two steps that actually have to keep working.

        Nothing is mocked because nothing needs to be: with an explicit token
        the OpenShift strategy skips OAuth discovery entirely, which
        test_token_auth_makes_no_network_call pins separately.
        """
        from codeflare_sdk import AuthConfig, get_k8s_client, set_api_client

        try:
            auth_config = AuthConfig(
                method="openshift",
                k8s_api_host="https://api.example.com:6443",
                token="sha256~XXXXX",
            )
            api_client = get_k8s_client(config=auth_config)

            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                set_api_client(api_client)

            assert auth.get_api_client() is api_client
            assert api_client.configuration.host == "https://api.example.com:6443"
        finally:
            auth.api_client = None
            auth.config_path = None

    def test_cluster_cell_builds_against_that_client(self):
        """The config kwargs the notebook passes are all still accepted."""
        from codeflare_sdk import Cluster, ClusterConfiguration

        cluster = Cluster(
            ClusterConfiguration(
                name="interactivetest",
                head_cpu_requests=1,
                head_cpu_limits=1,
                head_memory_requests=6,
                head_memory_limits=8,
                head_extended_resource_requests={"nvidia.com/gpu": 1},
                worker_extended_resource_requests={"nvidia.com/gpu": 1},
                num_workers=2,
                worker_cpu_requests="250m",
                worker_cpu_limits=1,
                worker_memory_requests=4,
                worker_memory_limits=6,
                write_to_file=False,
            )
        )

        assert cluster.config.name == "interactivetest"


class TestSetApiClientIsDeprecatedNotRemoved:
    def test_it_warns(self):
        from codeflare_sdk import set_api_client

        try:
            with pytest.warns(DeprecationWarning, match="Codeflare"):
                set_api_client(client.ApiClient())
        finally:
            auth.api_client = None
            auth.config_path = None

    def test_the_internal_one_does_not_warn(self):
        """Codeflare() calls set_api_client; it must not warn at users.

        The deprecation lives on the ``codeflare_sdk`` re-export only. If an
        internal caller is ever repointed at that wrapper, every Codeflare()
        starts emitting a DeprecationWarning about itself.
        """
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", DeprecationWarning)
                auth.set_api_client(client.ApiClient())
        finally:
            auth.api_client = None
            auth.config_path = None

    def test_codeflare_does_not_warn(self, mocker):
        """Codeflare() must not emit the set_api_client deprecation.

        Deliberately does *not* patch codeflare_sdk.codeflare.set_api_client.
        Codeflare.__init__ binds that name at import, so patching it replaces
        the call outright and the test passes even if __init__ were switched
        to the deprecated _compat wrapper — which is the regression it exists
        to catch. The real auth.set_api_client runs instead.
        """
        from codeflare_sdk import Codeflare, SDKConfig

        mocker.patch(
            "codeflare_sdk.codeflare.get_k8s_client", return_value=client.ApiClient()
        )

        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", DeprecationWarning)
                Codeflare(config=SDKConfig(namespace="ns"))
        finally:
            auth.api_client = None
            auth.config_path = None

    def test_codeflare_uses_the_unwrapped_set_api_client(self, mocker):
        """Pins the import that makes the test above meaningful."""
        import codeflare_sdk.codeflare as facade
        from codeflare_sdk._compat import set_api_client as wrapper

        assert facade.set_api_client is auth.set_api_client
        assert facade.set_api_client is not wrapper


class TestDeprecatedAuthClassesStillWork:
    """Restored by team decision (RHOAIENG-98947), not merely importable.

    v0.39.x promised these would survive, and the migration guide told token
    users to stay on TokenAuthentication. Importing them is not enough — the
    constructor surface, the return strings and the global they set all have
    to behave as they did, or a pinned script fails later instead of sooner.
    """

    def test_the_v0391_import_line_works(self):
        from codeflare_sdk import (  # noqa: F401
            Authentication,
            KubeConfigFileAuthentication,
            KubeConfiguration,
            TokenAuthentication,
        )

    @pytest.mark.parametrize(
        "name",
        [
            "Authentication",
            "KubeConfiguration",
            "TokenAuthentication",
            "KubeConfigFileAuthentication",
        ],
    )
    def test_also_importable_from_the_v0391_subpackages(self, name):
        import codeflare_sdk.common as common
        import codeflare_sdk.common.kubernetes_cluster as kc

        assert hasattr(common, name)
        assert hasattr(kc, name)

    def test_token_auth_keeps_its_constructor_surface(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            auth_obj = TokenAuthentication(
                token="sha256~tok",
                server="https://api.example.com:6443",
                skip_tls=True,
                ca_cert_path="/tmp/ca.crt",
            )

        assert isinstance(auth_obj, Authentication)
        assert (auth_obj.token, auth_obj.server) == (
            "sha256~tok",
            "https://api.example.com:6443",
        )
        assert auth_obj.skip_tls is True
        assert auth_obj.ca_cert_path == "/tmp/ca.crt"

    @pytest.mark.parametrize(
        "cls,kwargs",
        [
            (TokenAuthentication, {"token": "t", "server": "https://x:6443"}),
            (KubeConfigFileAuthentication, {"kube_config_path": "/tmp/kc"}),
        ],
    )
    def test_each_warns_exactly_once(self, cls, kwargs):
        """v0.39.x stacked @deprecated on a warnings.warn() and warned twice."""
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            cls(**kwargs)

        deprecations = [w for w in caught if w.category is DeprecationWarning]
        assert len(deprecations) == 1
        assert cls.__name__ in str(deprecations[0].message)

    @pytest.mark.parametrize(
        "cls,kwargs",
        [
            (TokenAuthentication, {"token": "t", "server": "https://x:6443"}),
            (KubeConfigFileAuthentication, {"kube_config_path": "/tmp/kc"}),
        ],
    )
    def test_no_removal_version_is_promised(self, cls, kwargs):
        """The team dropped the v1.0.0 date; removal may come sooner.

        Naming any version here re-makes the promise that was already broken
        once, so the warning says 'a future release' and nothing more.
        """
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            cls(**kwargs)

        message = str(caught[0].message)
        assert "future release" in message
        assert not re.search(r"v?\d+\.\d+\.\d+", message), (
            "the deprecation notice names a version again"
        )

    def test_token_login_delegates_to_kube_authkit(self, mocker):
        """The AC says no duplicate auth implementation.

        v0.39.x hand-rolled a Configuration here because kube-authkit could
        not do tokens. It can, so login() must go through it.
        """
        fake = client.ApiClient()
        get_client = mocker.patch(
            "codeflare_sdk.common.kubernetes_cluster.deprecated_auth.get_k8s_client",
            return_value=fake,
        )
        mocker.patch(
            "codeflare_sdk.common.kubernetes_cluster.deprecated_auth.client.AuthenticationApi"
        )

        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                result = TokenAuthentication(
                    token="sha256~tok", server="https://api.example.com:6443"
                ).login()

            assert result == "Logged into https://api.example.com:6443"
            cfg = get_client.call_args.kwargs["config"]
            assert cfg.method == "openshift"
            assert cfg.k8s_api_host == "https://api.example.com:6443"
            assert cfg.token == "sha256~tok"
            assert cfg.verify_ssl is True
            assert auth.get_api_client() is fake
        finally:
            auth.api_client = None
            auth.config_path = None

    def test_token_login_makes_no_network_call(self, monkeypatch):
        """v0.39.1 built a raw Configuration(host=server) + bearer token.

        Routing through AuthConfig(method="openshift") must stay equivalent:
        the OpenShift strategy can do interactive OAuth discovery, and if it
        did so here, vanilla Kubernetes token logins — which have no OpenShift
        OAuth server to discover — would break. Raised by @pawelpaszki.

        Blocks sockets and requests rather than asserting on a mock, so this
        fails if any layer underneath starts reaching out.
        """
        import socket

        import requests

        class Blocked(Exception):
            pass

        def deny(*args, **kwargs):
            raise Blocked("network call attempted during token login")

        monkeypatch.setattr(socket.socket, "connect", deny)
        monkeypatch.setattr(socket, "create_connection", deny)
        monkeypatch.setattr(requests, "get", deny)
        monkeypatch.setattr(requests, "post", deny)
        monkeypatch.setattr(requests.Session, "request", deny)

        from kube_authkit import AuthConfig, get_k8s_client

        api_client = get_k8s_client(
            config=AuthConfig(
                method="openshift",
                k8s_api_host="https://api.example.com:6443",
                token="sha256~tok",
            )
        )

        assert api_client.configuration.host == "https://api.example.com:6443"
        assert api_client.configuration.api_key["authorization"] == "Bearer sha256~tok"

    def test_token_login_sets_both_bearer_key_spellings(self, mocker):
        """Preserves 2eedf55.

        The kubernetes client looks the token up by header name in <=35 and by
        scheme name in >=36, and pyproject pins only `kubernetes >= 27.2.0`.
        kube-authkit's OpenShift strategy writes just `authorization`, so
        delegating without re-applying this would reintroduce the bug.
        """
        fake = client.ApiClient()
        mocker.patch(
            "codeflare_sdk.common.kubernetes_cluster.deprecated_auth.get_k8s_client",
            return_value=fake,
        )
        mocker.patch(
            "codeflare_sdk.common.kubernetes_cluster.deprecated_auth.client.AuthenticationApi"
        )

        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                TokenAuthentication(token="sha256~tok", server="https://x:6443").login()

            for key in ("authorization", "BearerToken"):
                assert fake.configuration.api_key[key] == "sha256~tok"
                assert fake.configuration.api_key_prefix[key] == "Bearer"
        finally:
            auth.api_client = None
            auth.config_path = None

    def test_token_login_leaves_config_path_none(self, mocker):
        """Not "custom", which set_api_client() would have written.

        config_check() returns config_path and common/utils/k8s_utils.py hands
        it to list_kube_config_contexts() as a kubeconfig path, so "custom"
        would break namespace detection after a token login.
        """
        mocker.patch(
            "codeflare_sdk.common.kubernetes_cluster.deprecated_auth.get_k8s_client",
            return_value=client.ApiClient(),
        )
        mocker.patch(
            "codeflare_sdk.common.kubernetes_cluster.deprecated_auth.client.AuthenticationApi"
        )

        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                TokenAuthentication(token="t", server="https://x:6443").login()

            assert auth.config_path is None
        finally:
            auth.api_client = None
            auth.config_path = None

    def test_token_skip_tls_turns_verification_off(self, mocker):
        get_client = mocker.patch(
            "codeflare_sdk.common.kubernetes_cluster.deprecated_auth.get_k8s_client",
            return_value=client.ApiClient(),
        )
        mocker.patch(
            "codeflare_sdk.common.kubernetes_cluster.deprecated_auth.client.AuthenticationApi"
        )

        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                TokenAuthentication(
                    token="t", server="https://x:6443", skip_tls=True
                ).login()

            cfg = get_client.call_args.kwargs["config"]
            assert cfg.verify_ssl is False
            assert cfg.ca_cert is None
        finally:
            auth.api_client = None
            auth.config_path = None

    def test_token_logout_clears_the_global(self, mocker):
        mocker.patch(
            "codeflare_sdk.common.kubernetes_cluster.deprecated_auth.get_k8s_client",
            return_value=client.ApiClient(),
        )
        mocker.patch(
            "codeflare_sdk.common.kubernetes_cluster.deprecated_auth.client.AuthenticationApi"
        )

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            auth_obj = TokenAuthentication(token="t", server="https://x:6443")
            auth_obj.login()
            message = auth_obj.logout()

        assert message == "Successfully logged out of https://x:6443"
        assert auth.api_client is None
        assert auth.config_path is None

    def test_token_login_failure_clears_the_global_and_raises(self, mocker):
        """A failed login must not leave a half-bound client behind.

        2eedf55 added the `api_client = None` and the bare `raise` here: before
        it, a rejected token left the module-level client set to a client that
        did not work, and swallowed the exception.
        """
        mocker.patch(
            "codeflare_sdk.common.kubernetes_cluster.deprecated_auth.get_k8s_client",
            return_value=client.ApiClient(),
        )
        mocker.patch(
            "codeflare_sdk.common.kubernetes_cluster.deprecated_auth.client.AuthenticationApi",
            side_effect=client.ApiException(status=401, reason="Unauthorized"),
        )
        mocker.patch(
            "codeflare_sdk.common.kubernetes_cluster.deprecated_auth._kube_api_error_handling"
        )
        auth.api_client = None
        auth.config_path = None

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            auth_obj = TokenAuthentication(token="bad", server="https://x:6443")
            with pytest.raises(client.ApiException):
                auth_obj.login()

        assert auth.api_client is None
        assert auth.config_path is None

    def test_kubeconfig_logout_clears_the_global(self, mocker, tmp_path):
        kubeconfig = tmp_path / "kubeconfig"
        kubeconfig.write_text("apiVersion: v1\nkind: Config\n")
        mocker.patch(
            "codeflare_sdk.common.kubernetes_cluster.deprecated_auth.get_k8s_client",
            return_value=client.ApiClient(),
        )

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            loader = KubeConfigFileAuthentication(kube_config_path=str(kubeconfig))
            loader.load_kube_config()
            message = loader.logout()

        assert message == f"Successfully logged out of {kubeconfig}"
        assert auth.api_client is None
        assert auth.config_path is None

    def test_kubeconfig_failure_propagates_rather_than_falling_back(self, mocker):
        """Deliberate divergence from v0.39.x. Raised by @pawelpaszki.

        v0.39.x caught any kube-authkit failure and silently retried with
        kubernetes.config.load_kube_config(). That is not restored, for two
        reasons: kube-authkit's kubeconfig strategy *is* load_kube_config, so
        the fallback could only ever paper over a real error, and the ticket
        asks for no duplicate auth implementation. A failure is now reported.
        """
        from kube_authkit.exceptions import AuthenticationError

        mocker.patch(
            "codeflare_sdk.common.kubernetes_cluster.deprecated_auth.get_k8s_client",
            side_effect=AuthenticationError("boom"),
        )
        load = mocker.patch("kubernetes.config.load_kube_config")

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            loader = KubeConfigFileAuthentication(kube_config_path="/tmp/kc")

        with pytest.raises(AuthenticationError):
            loader.load_kube_config()

        load.assert_not_called()
        assert auth.api_client is None

    def test_the_abstract_bases_are_still_subclassable(self):
        """They are exported, so someone may have subclassed them.

        v0.39.x gave both no-op method bodies rather than @abstractmethod, so
        a subclass that overrides nothing is legal and must stay legal.
        """
        from codeflare_sdk import Authentication, KubeConfiguration

        class MyAuth(Authentication):
            pass

        class MyConfig(KubeConfiguration):
            pass

        assert MyAuth().login() is None
        assert MyAuth().logout() is None
        assert MyConfig().load_kube_config() is None
        assert MyConfig().logout() is None

    def test_kubeconfig_without_a_path_says_so(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            loader = KubeConfigFileAuthentication()

        assert loader.load_kube_config() == "Please specify a config file path"

    def test_kubeconfig_passes_the_path_through(self, mocker, tmp_path):
        """v0.39.x dropped it.

        It built AuthConfig(method="kubeconfig") with no path, so whenever
        kube-authkit succeeded the kube_config_path argument was ignored and
        auto-detection won — then reported the path it had not loaded.
        AuthConfig takes kubeconfig_path now.
        """
        kubeconfig = tmp_path / "kubeconfig"
        kubeconfig.write_text("apiVersion: v1\nkind: Config\n")
        fake = client.ApiClient()
        get_client = mocker.patch(
            "codeflare_sdk.common.kubernetes_cluster.deprecated_auth.get_k8s_client",
            return_value=fake,
        )

        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                result = KubeConfigFileAuthentication(
                    kube_config_path=str(kubeconfig)
                ).load_kube_config()

            assert result == f"Loaded user config file at path {kubeconfig}"
            cfg = get_client.call_args.kwargs["config"]
            assert cfg.method == "kubeconfig"
            assert cfg.kubeconfig_path == str(kubeconfig)
            assert auth.config_path == str(kubeconfig)
            assert auth.get_api_client() is fake
        finally:
            auth.api_client = None
            auth.config_path = None

    def test_kubeconfig_rejects_a_path_that_does_not_exist(self, tmp_path):
        """A behaviour change from v0.39.x, and the better one.

        There, the kube-authkit branch ran AuthConfig(method="kubeconfig")
        with no path at all, so a bad path fell through to auto-detection and
        the method returned "Loaded user config file at path <bad path>" —
        reporting a file it had never opened. AuthConfig validates the path,
        so the caller now hears about it.
        """
        missing = tmp_path / "nope"

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            loader = KubeConfigFileAuthentication(kube_config_path=str(missing))

        with pytest.raises(Exception, match="not found"):
            loader.load_kube_config()

        assert auth.api_client is None


class TestRemovedNamesExplainThemselves:
    """Only ManagedClusterConfig now. The four auth names came back."""

    @pytest.mark.parametrize("name", sorted(REMOVED))
    def test_import_error_carries_the_migration_text(self, name):
        """Via a real ``from codeflare_sdk import X``, not getattr.

        getattr would not prove the point: the whole reason __getattr__ raises
        ImportError rather than AttributeError is that the from-import
        machinery discards an AttributeError's message and substitutes its own
        "cannot import name X". Only the statement form exercises that.
        """
        with pytest.raises(ImportError) as excinfo:
            exec(f"from codeflare_sdk import {name}", {})

        message = str(excinfo.value)
        assert name in message
        assert "cannot import name" not in message
        assert "ClusterConfiguration" in message

    @pytest.mark.parametrize("name", sorted(REMOVED))
    def test_hasattr_raises_which_is_the_documented_cost(self, name):
        """The stated trade-off, asserted rather than only written down.

        Raising ImportError from __getattr__ buys a readable message on
        from-import and costs feature detection: hasattr() propagates instead
        of returning False. If that ever becomes intolerable, this test is
        what has to change, so it should be visible.
        """
        import codeflare_sdk

        with pytest.raises(ImportError):
            hasattr(codeflare_sdk, name)

    def test_only_managed_cluster_config_stays_removed(self):
        """The restored auth names must not linger in REMOVED.

        An entry here shadows a working export: __getattr__ is only consulted
        for names the package does not define, so a stale entry would be dead
        code that silently disagrees with the module.
        """
        assert set(REMOVED) == {"ManagedClusterConfig"}

    def test_managed_cluster_config_lists_the_renamed_fields(self):
        """Three fields were renamed, not just the class. Verified against
        the v0.39.1 dataclass in the commit that added this test."""
        message = REMOVED["ManagedClusterConfig"]
        for old, new in (
            ("head_accelerators", "head_extended_resource_requests"),
            ("worker_accelerators", "worker_extended_resource_requests"),
            ("accelerator_configs", "extended_resource_mapping"),
        ):
            assert old in message and new in message

    def test_managed_cluster_config_warns_that_defaults_moved(self):
        """A rename-only migration silently resizes the cluster.

        Four scalar defaults differ between v0.39.1's ManagedClusterConfig and
        today's ClusterConfiguration. (The migration guide's table lists six
        rows, but head_cpu_limits and head_memory_limits are unchanged.)
        """
        message = REMOVED["ManagedClusterConfig"]
        for field_name in (
            "head_cpu_requests",
            "head_memory_requests",
            "worker_memory_requests",
            "worker_memory_limits",
        ):
            assert field_name in message
        assert "rayjob_config_migration_guide" in message

    def test_managed_cluster_config_does_not_claim_tech_preview(self):
        """It was a documented public export used by two guided notebooks.

        v0.39.1 never labelled anything tech preview, and ManagedClusterConfig
        shipped no DeprecationWarning, so that rationale does not hold.
        """
        assert "tech preview" not in REMOVED["ManagedClusterConfig"].lower()

    def test_an_unknown_name_is_still_an_attribute_error(self):
        import codeflare_sdk

        with pytest.raises(AttributeError):
            codeflare_sdk.NoSuchThing

    def test_removed_names_are_not_in_dir(self):
        """So tab-completion and autodoc do not offer a name that raises."""
        import codeflare_sdk

        assert set(REMOVED).isdisjoint(dir(codeflare_sdk))

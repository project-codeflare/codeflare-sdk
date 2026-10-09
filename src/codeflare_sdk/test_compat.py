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

"""The v0.39.x public surface still behaves as promised (RHOAIENG-98947)."""

import warnings

import pytest
from kubernetes import client

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
        api_client = client.ApiClient()
        from codeflare_sdk import set_api_client

        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                set_api_client(api_client)

            assert auth.get_api_client() is api_client
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
        from codeflare_sdk import Codeflare, SDKConfig

        mocker.patch(
            "codeflare_sdk.codeflare.get_k8s_client", return_value=client.ApiClient()
        )
        mocker.patch("codeflare_sdk.codeflare.set_api_client")

        with warnings.catch_warnings():
            warnings.simplefilter("error", DeprecationWarning)
            Codeflare(config=SDKConfig(namespace="ns"))


class TestRemovedNamesExplainThemselves:
    @pytest.mark.parametrize("name", sorted(REMOVED))
    def test_import_error_carries_the_migration_text(self, name):
        """The message must survive ``from codeflare_sdk import X``.

        An AttributeError would be swallowed and replaced with "cannot import
        name", which is the behaviour this exists to avoid.
        """
        import codeflare_sdk

        with pytest.raises(ImportError) as excinfo:
            getattr(codeflare_sdk, name)

        message = str(excinfo.value)
        assert name in message
        assert "cannot import name" not in message

    @pytest.mark.parametrize(
        "name,expected",
        [
            ("TokenAuthentication", 'method="openshift"'),
            ("KubeConfigFileAuthentication", 'method="kubeconfig"'),
            ("Authentication", "kube_authkit.AuthConfig"),
            ("KubeConfiguration", "kube_authkit.AuthConfig"),
            ("ManagedClusterConfig", "ClusterConfiguration"),
        ],
    )
    def test_each_names_its_replacement(self, name, expected):
        assert expected in REMOVED[name]

    @pytest.mark.parametrize(
        "name,forbidden",
        [
            ("TokenAuthentication", ["verify_ssl", "ca_cert="]),
            ("KubeConfigFileAuthentication", ["kubeconfig_path"]),
        ],
    )
    def test_snippets_keep_to_the_documented_style(self, name, forbidden):
        """Match docs/sphinx/user-docs/authentication.rst, not just AuthConfig.

        AuthConfig does accept kubeconfig_path, verify_ssl and ca_cert, so a
        snippet naming them is valid but teaches a second style. That page is
        where a user sent here by the error reads next; it routes a custom CA
        through CF_SDK_CA_CERT_PATH and a kubeconfig path through KUBECONFIG.
        """
        message = REMOVED[name]
        for token in forbidden:
            assert token not in message

    def test_token_auth_points_at_the_env_var_for_a_custom_ca(self):
        assert "CF_SDK_CA_CERT_PATH" in REMOVED["TokenAuthentication"]

    def test_kubeconfig_auth_points_at_the_env_var_for_a_path(self):
        assert "KUBECONFIG" in REMOVED["KubeConfigFileAuthentication"]

    def test_removed_auth_classes_admit_the_v1_0_0_promise(self):
        """v0.39.x README and auth_migration_guide.md said v1.0.0.

        Dropping them in v0.40.0 is earlier than published, so the error
        should say so rather than imply a routine deprecation ran its course.
        """
        for name in ("TokenAuthentication", "KubeConfigFileAuthentication"):
            assert "v1.0.0" in REMOVED[name]

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

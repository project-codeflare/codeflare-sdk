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
import re
import uuid

from codeflare_sdk.ray.cluster import cluster

parent = Path(__file__).resolve().parents[1]
aw_dir = os.path.expanduser("~/.codeflare/resources/")
sys.path.append(str(parent) + "/src")

from kubernetes import client, config, dynamic
from codeflare_sdk.ray.appwrapper.awload import AWManager
from codeflare_sdk.ray.cluster.cluster import (
    Cluster,
    ClusterConfiguration,
    _map_to_ray_cluster,
    list_all_clusters,
    list_all_queued,
    _copy_to_ray,
    get_cluster,
    _app_wrapper_status,
    _ray_cluster_status,
)
from codeflare_sdk.common.kubernetes_cluster import (
    TokenAuthentication,
    Authentication,
    KubeConfigFileAuthentication,
    config_check,
)
from codeflare_sdk.ray.cluster.pretty_print import (
    print_no_resources_found,
    print_app_wrappers_status,
    print_cluster_status,
    print_clusters,
)
from codeflare_sdk.ray.appwrapper.status import (
    AppWrapper,
    AppWrapperStatus,
)
from codeflare_sdk.ray.cluster.status import (
    RayCluster,
    RayClusterStatus,
    CodeFlareClusterStatus,
)
from codeflare_sdk.common.utils.generate_cert import (
    generate_ca_cert,
    generate_tls_cert,
    export_env,
)

from tests.unit_test_support import (
    createClusterWithConfig,
    createClusterConfig,
    createClusterWrongType,
    get_package_and_version,
)

import codeflare_sdk.common.kubernetes_cluster.kube_api_helpers
from codeflare_sdk.ray.cluster.generate_yaml import (
    gen_names,
    is_openshift_cluster,
)

import codeflare_sdk.cluster.widgets as cf_widgets
import pandas as pd

import openshift
from openshift.selector import Selector
import ray
import pytest
import yaml
from unittest.mock import MagicMock, patch
from pytest_mock import MockerFixture
from ray.job_submission import JobSubmissionClient
from codeflare_sdk.ray.client.ray_jobs import RayJobClient

# For mocking openshift client results
fake_res = openshift.Result("fake")


def mock_routes_api(mocker):
    mocker.patch.object(
        "_route_api_getter",
        return_value=MagicMock(
            resources=MagicMock(
                get=MagicMock(
                    return_value=MagicMock(
                        create=MagicMock(),
                        replace=MagicMock(),
                        delete=MagicMock(),
                    )
                )
            )
        ),
    )


def arg_side_effect(*args):
    fake_res.high_level_operation = args
    return fake_res


def att_side_effect(self):
    return self.high_level_operation


def test_token_auth_creation():
    try:
        token_auth = TokenAuthentication(token="token", server="server")
        assert token_auth.token == "token"
        assert token_auth.server == "server"
        assert token_auth.skip_tls == False
        assert token_auth.ca_cert_path == None

        token_auth = TokenAuthentication(token="token", server="server", skip_tls=True)
        assert token_auth.token == "token"
        assert token_auth.server == "server"
        assert token_auth.skip_tls == True
        assert token_auth.ca_cert_path == None

        os.environ["CF_SDK_CA_CERT_PATH"] = "/etc/pki/tls/custom-certs/ca-bundle.crt"
        token_auth = TokenAuthentication(token="token", server="server", skip_tls=False)
        assert token_auth.token == "token"
        assert token_auth.server == "server"
        assert token_auth.skip_tls == False
        assert token_auth.ca_cert_path == "/etc/pki/tls/custom-certs/ca-bundle.crt"
        os.environ.pop("CF_SDK_CA_CERT_PATH")

        token_auth = TokenAuthentication(
            token="token",
            server="server",
            skip_tls=False,
            ca_cert_path=f"{parent}/tests/auth-test.crt",
        )
        assert token_auth.token == "token"
        assert token_auth.server == "server"
        assert token_auth.skip_tls == False
        assert token_auth.ca_cert_path == f"{parent}/tests/auth-test.crt"

    except Exception as e:
        assert 0 == 1


def test_token_auth_login_logout(mocker):
    mocker.patch.object(client, "ApiClient")

    token_auth = TokenAuthentication(
        token="testtoken", server="testserver:6443", skip_tls=False, ca_cert_path=None
    )
    assert token_auth.login() == ("Logged into testserver:6443")
    assert token_auth.logout() == ("Successfully logged out of testserver:6443")


def test_token_auth_login_tls(mocker):
    mocker.patch.object(client, "ApiClient")

    token_auth = TokenAuthentication(
        token="testtoken", server="testserver:6443", skip_tls=True, ca_cert_path=None
    )
    assert token_auth.login() == ("Logged into testserver:6443")
    token_auth = TokenAuthentication(
        token="testtoken", server="testserver:6443", skip_tls=False, ca_cert_path=None
    )
    assert token_auth.login() == ("Logged into testserver:6443")
    token_auth = TokenAuthentication(
        token="testtoken",
        server="testserver:6443",
        skip_tls=False,
        ca_cert_path=f"{parent}/tests/auth-test.crt",
    )
    assert token_auth.login() == ("Logged into testserver:6443")

    os.environ["CF_SDK_CA_CERT_PATH"] = f"{parent}/tests/auth-test.crt"
    token_auth = TokenAuthentication(
        token="testtoken",
        server="testserver:6443",
        skip_tls=False,
    )
    assert token_auth.login() == ("Logged into testserver:6443")


def test_config_check_no_config_file(mocker):
    mocker.patch("os.path.expanduser", return_value="/mock/home/directory")
    mocker.patch("os.path.isfile", return_value=False)
    mocker.patch("codeflare_sdk.common.kubernetes_cluster.auth.config_path", None)
    mocker.patch("codeflare_sdk.common.kubernetes_cluster.auth.api_client", None)

    with pytest.raises(PermissionError) as e:
        config_check()


def test_config_check_with_incluster_config(mocker):
    mocker.patch("os.path.expanduser", return_value="/mock/home/directory")
    mocker.patch("os.path.isfile", return_value=False)
    mocker.patch.dict(os.environ, {"KUBERNETES_PORT": "number"})
    mocker.patch("kubernetes.config.load_incluster_config", side_effect=None)
    mocker.patch("codeflare_sdk.common.kubernetes_cluster.auth.config_path", None)
    mocker.patch("codeflare_sdk.common.kubernetes_cluster.auth.api_client", None)

    result = config_check()
    assert result == None


def test_config_check_with_existing_config_file(mocker):
    mocker.patch("os.path.expanduser", return_value="/mock/home/directory")
    mocker.patch("os.path.isfile", return_value=True)
    mocker.patch("kubernetes.config.load_kube_config", side_effect=None)
    mocker.patch("codeflare_sdk.common.kubernetes_cluster.auth.config_path", None)
    mocker.patch("codeflare_sdk.common.kubernetes_cluster.auth.api_client", None)

    result = config_check()
    assert result == None


def test_config_check_with_config_path_and_no_api_client(mocker):
    mocker.patch(
        "codeflare_sdk.common.kubernetes_cluster.auth.config_path", "/mock/config/path"
    )
    mocker.patch("codeflare_sdk.common.kubernetes_cluster.auth.api_client", None)
    result = config_check()
    assert result == "/mock/config/path"


def test_load_kube_config(mocker):
    mocker.patch.object(config, "load_kube_config")
    kube_config_auth = KubeConfigFileAuthentication(
        kube_config_path="/path/to/your/config"
    )
    response = kube_config_auth.load_kube_config()

    assert (
        response
        == "Loaded user config file at path %s" % kube_config_auth.kube_config_path
    )

    kube_config_auth = KubeConfigFileAuthentication(kube_config_path=None)
    response = kube_config_auth.load_kube_config()
    assert response == "Please specify a config file path"


def test_auth_coverage():
    abstract = Authentication()
    abstract.login()
    abstract.logout()


def test_config_creation():
    config = createClusterConfig()

    assert config.name == "unit-test-cluster" and config.namespace == "ns"
    assert config.num_workers == 2
    assert config.worker_cpu_requests == 3 and config.worker_cpu_limits == 4
    assert config.worker_memory_requests == "5G" and config.worker_memory_limits == "6G"
    assert config.worker_extended_resource_requests == {"nvidia.com/gpu": 7}
    assert (
        config.template
        == f"{parent}/src/codeflare_sdk/ray/templates/base-template.yaml"
    )
    assert config.machine_types == ["cpu.small", "gpu.large"]
    assert config.image_pull_secrets == ["unit-test-pull-secret"]
    assert config.appwrapper == True


def test_config_creation_wrong_type():
    with pytest.raises(TypeError):
        config = createClusterWrongType()


def test_cluster_creation(mocker):
    # Create AppWrapper containing a Ray Cluster with no local queue specified
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        return_value=get_local_queue("kueue.x-k8s.io", "v1beta1", "ns", "localqueues"),
    )
    cluster = createClusterWithConfig(mocker)
    assert cluster.app_wrapper_yaml == f"{aw_dir}unit-test-cluster.yaml"
    assert cluster.app_wrapper_name == "unit-test-cluster"
    assert filecmp.cmp(
        f"{aw_dir}unit-test-cluster.yaml",
        f"{parent}/tests/test-case.yaml",
        shallow=True,
    )


@patch.dict("os.environ", {"NB_PREFIX": "test-prefix"})
def test_cluster_no_kueue_no_aw(mocker):
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.get_cluster_custom_object",
        return_value={"spec": {"domain": "apps.cluster.awsroute.org"}},
    )
    mocker.patch("kubernetes.client.CustomObjectsApi.list_namespaced_custom_object")
    config = createClusterConfig()
    config.appwrapper = False
    config.name = "unit-test-no-kueue"
    config.write_to_file = True
    cluster = Cluster(config)
    assert cluster.app_wrapper_yaml == f"{aw_dir}unit-test-no-kueue.yaml"
    assert cluster.config.local_queue == None
    assert filecmp.cmp(
        f"{aw_dir}unit-test-no-kueue.yaml",
        f"{parent}/tests/test-case-no-kueue-no-aw.yaml",
        shallow=True,
    )


def get_local_queue(group, version, namespace, plural):
    assert group == "kueue.x-k8s.io"
    assert version == "v1beta1"
    assert namespace == "ns"
    assert plural == "localqueues"
    local_queues = {
        "apiVersion": "kueue.x-k8s.io/v1beta1",
        "items": [
            {
                "apiVersion": "kueue.x-k8s.io/v1beta1",
                "kind": "LocalQueue",
                "metadata": {
                    "annotations": {"kueue.x-k8s.io/default-queue": "true"},
                    "name": "local-queue-default",
                    "namespace": "ns",
                },
                "spec": {"clusterQueue": "cluster-queue"},
            },
            {
                "apiVersion": "kueue.x-k8s.io/v1beta1",
                "kind": "LocalQueue",
                "metadata": {
                    "name": "team-a-queue",
                    "namespace": "ns",
                },
                "spec": {"clusterQueue": "team-a-queue"},
            },
        ],
        "kind": "LocalQueueList",
        "metadata": {"continue": "", "resourceVersion": "2266811"},
    }
    return local_queues


@patch.dict("os.environ", {"NB_PREFIX": "test-prefix"})
def test_cluster_creation_no_mcad(mocker):
    # Create Ray Cluster with no local queue specified
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.get_cluster_custom_object",
        return_value={"spec": {"domain": "apps.cluster.awsroute.org"}},
    )
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        return_value=get_local_queue("kueue.x-k8s.io", "v1beta1", "ns", "localqueues"),
    )

    config = createClusterConfig()
    config.name = "unit-test-cluster-ray"
    config.write_to_file = True
    config.labels = {"testlabel": "test", "testlabel2": "test"}
    config.appwrapper = False
    cluster = Cluster(config)

    assert cluster.app_wrapper_yaml == f"{aw_dir}unit-test-cluster-ray.yaml"
    assert cluster.app_wrapper_name == "unit-test-cluster-ray"
    assert filecmp.cmp(
        f"{aw_dir}unit-test-cluster-ray.yaml",
        f"{parent}/tests/test-case-no-mcad.yamls",
        shallow=True,
    )


@patch.dict("os.environ", {"NB_PREFIX": "test-prefix"})
def test_cluster_creation_no_mcad_local_queue(mocker):
    # With written resources
    # Create Ray Cluster with local queue specified
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.get_cluster_custom_object",
        return_value={"spec": {"domain": "apps.cluster.awsroute.org"}},
    )
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        return_value=get_local_queue("kueue.x-k8s.io", "v1beta1", "ns", "localqueues"),
    )
    config = createClusterConfig()
    config.name = "unit-test-cluster-ray"
    config.appwrapper = False
    config.write_to_file = True
    config.local_queue = "local-queue-default"
    config.labels = {"testlabel": "test", "testlabel2": "test"}
    cluster = Cluster(config)
    assert cluster.app_wrapper_yaml == f"{aw_dir}unit-test-cluster-ray.yaml"
    assert cluster.app_wrapper_name == "unit-test-cluster-ray"
    assert filecmp.cmp(
        f"{aw_dir}unit-test-cluster-ray.yaml",
        f"{parent}/tests/test-case-no-mcad.yamls",
        shallow=True,
    )
    # With resources loaded in memory
    config = ClusterConfiguration(
        name="unit-test-cluster-ray",
        namespace="ns",
        num_workers=2,
        worker_cpu_requests=3,
        worker_cpu_limits=4,
        worker_memory_requests=5,
        worker_memory_limits=6,
        worker_extended_resource_requests={"nvidia.com/gpu": 7},
        machine_types=["cpu.small", "gpu.large"],
        image_pull_secrets=["unit-test-pull-secret"],
        write_to_file=True,
        appwrapper=False,
        local_queue="local-queue-default",
        labels={"testlabel": "test", "testlabel2": "test"},
    )
    cluster = Cluster(config)
    assert cluster.app_wrapper_yaml == f"{aw_dir}unit-test-cluster-ray.yaml"
    assert cluster.app_wrapper_name == "unit-test-cluster-ray"
    assert filecmp.cmp(
        f"{aw_dir}unit-test-cluster-ray.yaml",
        f"{parent}/tests/test-case-no-mcad.yamls",
        shallow=True,
    )


def test_default_cluster_creation(mocker):
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster.get_current_namespace",
        return_value="opendatahub",
    )
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        return_value=get_local_queue("kueue.x-k8s.io", "v1beta1", "ns", "localqueues"),
    )
    default_config = ClusterConfiguration(
        name="unit-test-default-cluster",
        appwrapper=True,
    )
    cluster = Cluster(default_config)
    test_aw = yaml.load(cluster.app_wrapper_yaml, Loader=yaml.FullLoader)

    with open(
        f"{parent}/tests/test-default-appwrapper.yaml",
    ) as f:
        default_aw = yaml.load(f, Loader=yaml.FullLoader)
        assert test_aw == default_aw

    assert cluster.app_wrapper_name == "unit-test-default-cluster"
    assert cluster.config.namespace == "opendatahub"


@patch.dict("os.environ", {"NB_PREFIX": "test-prefix"})
def test_cluster_creation_with_custom_image(mocker):
    # With written resources
    # Create Ray Cluster with local queue specified
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.get_cluster_custom_object",
        return_value={"spec": {"domain": "apps.cluster.awsroute.org"}},
    )
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        return_value=get_local_queue("kueue.x-k8s.io", "v1beta1", "ns", "localqueues"),
    )
    config = createClusterConfig()
    config.name = "unit-test-cluster-custom-image"
    config.appwrapper = False
    config.image = "quay.io/project-codeflare/ray:2.20.0-py39-cu118"
    config.local_queue = "local-queue-default"
    config.labels = {"testlabel": "test", "testlabel2": "test"}
    cluster = Cluster(config)
    assert cluster.app_wrapper_yaml == f"{aw_dir}unit-test-cluster-custom-image.yaml"
    assert cluster.app_wrapper_name == "unit-test-cluster-custom-image"
    assert filecmp.cmp(
        f"{aw_dir}unit-test-cluster-custom-image.yaml",
        f"{parent}/tests/test-case-custom-image.yaml",
        shallow=True,
    )
    # With resources loaded in memory
    config = ClusterConfiguration(
        name="unit-test-cluster-custom-image",
        namespace="ns",
        num_workers=2,
        worker_cpu_requests=3,
        worker_cpu_limits=4,
        worker_memory_requests=5,
        worker_memory_limits=6,
        worker_extended_resource_requests={"nvidia.com/gpu": 7},
        machine_types=["cpu.small", "gpu.large"],
        image_pull_secrets=["unit-test-pull-secret"],
        image="quay.io/project-codeflare/ray:2.20.0-py39-cu118",
        write_to_file=True,
        appwrapper=False,
        local_queue="local-queue-default",
        labels={"testlabel": "test", "testlabel2": "test"},
    )
    cluster = Cluster(config)
    assert cluster.app_wrapper_yaml == f"{aw_dir}unit-test-cluster-custom-image.yaml"
    assert cluster.app_wrapper_name == "unit-test-cluster-custom-image"
    assert filecmp.cmp(
        f"{aw_dir}unit-test-cluster-custom-image.yaml",
        f"{parent}/tests/test-case-custom-image.yaml",
        shallow=True,
    )


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


def arg_check_apply_effect(group, version, namespace, plural, body, *args):
    assert namespace == "ns"
    assert args == tuple()
    if plural == "appwrappers":
        assert group == "workload.codeflare.dev"
        assert version == "v1beta2"
        with open(f"{aw_dir}unit-test-cluster.yaml") as f:
            aw = yaml.load(f, Loader=yaml.FullLoader)
        assert body == aw
    elif plural == "rayclusters":
        assert group == "ray.io"
        assert version == "v1"
        with open(f"{aw_dir}unit-test-cluster-ray.yaml") as f:
            yamls = yaml.load_all(f, Loader=yaml.FullLoader)
            for resource in yamls:
                if resource["kind"] == "RayCluster":
                    assert body == resource
    elif plural == "ingresses":
        assert group == "networking.k8s.io"
        assert version == "v1"
        with open(f"{aw_dir}unit-test-cluster-ray.yaml") as f:
            yamls = yaml.load_all(f, Loader=yaml.FullLoader)
            for resource in yamls:
                if resource["kind"] == "Ingress":
                    assert body == resource
    elif plural == "routes":
        assert group == "route.openshift.io"
        assert version == "v1"
        with open(f"{aw_dir}unit-test-cluster-ray.yaml") as f:
            yamls = yaml.load_all(f, Loader=yaml.FullLoader)
            for resource in yamls:
                if resource["kind"] == "Ingress":
                    assert body == resource
    else:
        assert 1 == 0


def arg_check_del_effect(group, version, namespace, plural, name, *args):
    assert namespace == "ns"
    assert args == tuple()
    if plural == "appwrappers":
        assert group == "workload.codeflare.dev"
        assert version == "v1beta2"
        assert name == "unit-test-cluster"
    elif plural == "rayclusters":
        assert group == "ray.io"
        assert version == "v1"
        assert name == "unit-test-cluster-ray"
    elif plural == "ingresses":
        assert group == "networking.k8s.io"
        assert version == "v1"
        assert name == "ray-dashboard-unit-test-cluster-ray"


def test_cluster_up_down(mocker):
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch("codeflare_sdk.ray.cluster.cluster.Cluster._throw_for_no_raycluster")
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.get_cluster_custom_object",
        return_value={"spec": {"domain": ""}},
    )
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.create_namespaced_custom_object",
        side_effect=arg_check_apply_effect,
    )
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.delete_namespaced_custom_object",
        side_effect=arg_check_del_effect,
    )
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_cluster_custom_object",
        return_value={"items": []},
    )
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        return_value=get_local_queue("kueue.x-k8s.io", "v1beta1", "ns", "localqueues"),
    )
    cluster = cluster = createClusterWithConfig(mocker)
    cluster.up()
    cluster.down()


def test_cluster_up_down_no_mcad(mocker):
    mocker.patch("codeflare_sdk.ray.cluster.cluster.Cluster._throw_for_no_raycluster")
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        return_value=get_local_queue("kueue.x-k8s.io", "v1beta1", "ns", "localqueues"),
    )
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.create_namespaced_custom_object",
        side_effect=arg_check_apply_effect,
    )
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.delete_namespaced_custom_object",
        side_effect=arg_check_del_effect,
    )
    mocker.patch(
        "kubernetes.client.CoreV1Api.create_namespaced_secret",
    )
    mocker.patch(
        "kubernetes.client.CoreV1Api.delete_namespaced_secret",
    )
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_cluster_custom_object",
        return_value={"items": []},
    )
    config = createClusterConfig()
    config.name = "unit-test-cluster-ray"
    config.appwrapper = False
    cluster = Cluster(config)
    cluster.up()
    cluster.down()


def arg_check_list_effect(group, version, plural, name, *args):
    assert group == "config.openshift.io"
    assert version == "v1"
    assert plural == "ingresses"
    assert name == "cluster"
    assert args == tuple()
    return {"spec": {"domain": "test"}}


""" We need to fix get_current_namespace in order to reuse this test.
def test_get_ingress_domain(mocker):
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.get_cluster_custom_object",
        side_effect=arg_check_list_effect,
    )
    domain = _get_ingress_domain()
    assert domain == "test"
"""


def aw_status_fields(group, version, namespace, plural, *args):
    assert group == "workload.codeflare.dev"
    assert version == "v1beta2"
    assert namespace == "test-ns"
    assert plural == "appwrappers"
    assert args == tuple()
    return {"items": []}


def test_aw_status(mocker):
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        side_effect=aw_status_fields,
    )
    aw = _app_wrapper_status("test-aw", "test-ns")
    assert aw == None


def rc_status_fields(group, version, namespace, plural, *args):
    assert group == "ray.io"
    assert version == "v1"
    assert namespace == "test-ns"
    assert plural == "rayclusters"
    assert args == tuple()
    return {"items": []}


def test_rc_status(mocker):
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        side_effect=rc_status_fields,
    )
    rc = _ray_cluster_status("test-rc", "test-ns")
    assert rc == None


def test_cluster_uris(mocker):
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster._get_ingress_domain",
        return_value="apps.cluster.awsroute.org",
    )
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        return_value=get_local_queue("kueue.x-k8s.io", "v1beta1", "ns", "localqueues"),
    )
    cluster = cluster = createClusterWithConfig(mocker)
    mocker.patch(
        "kubernetes.client.NetworkingV1Api.list_namespaced_ingress",
        return_value=ingress_retrieval(
            cluster_name="unit-test-cluster",
            annotations={"route.openshift.io/termination": "passthrough"},
        ),
    )
    assert (
        cluster.cluster_dashboard_uri()
        == "https://ray-dashboard-unit-test-cluster-ns.apps.cluster.awsroute.org"
    )
    mocker.patch(
        "kubernetes.client.NetworkingV1Api.list_namespaced_ingress",
        return_value=ingress_retrieval(),
    )
    assert cluster.cluster_uri() == "ray://unit-test-cluster-head-svc.ns.svc:10001"
    assert (
        cluster.cluster_dashboard_uri()
        == "http://ray-dashboard-unit-test-cluster-ns.apps.cluster.awsroute.org"
    )
    cluster.config.name = "fake"
    mocker.patch(
        "kubernetes.client.NetworkingV1Api.list_namespaced_ingress",
    )
    assert (
        cluster.cluster_dashboard_uri()
        == "Dashboard not available yet, have you run cluster.up()?"
    )


def test_local_client_url(mocker):
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.get_cluster_custom_object",
        return_value={"spec": {"domain": ""}},
    )
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster._get_ingress_domain",
        return_value="rayclient-unit-test-cluster-localinter-ns.apps.cluster.awsroute.org",
    )
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster.Cluster.create_app_wrapper",
        return_value="unit-test-cluster-localinter.yaml",
    )

    cluster_config = ClusterConfiguration(
        name="unit-test-cluster-localinter",
        namespace="ns",
        write_to_file=True,
    )
    cluster = Cluster(cluster_config)
    assert (
        cluster.local_client_url()
        == "ray://rayclient-unit-test-cluster-localinter-ns.apps.cluster.awsroute.org"
    )


def ray_addr(self, *args):
    return self._address


def mocked_ingress(port, cluster_name="unit-test-cluster", annotations: dict = None):
    labels = {"ingress-owner": cluster_name}
    if port == 10001:
        name = f"rayclient-{cluster_name}"
    else:
        name = f"ray-dashboard-{cluster_name}"
    mock_ingress = client.V1Ingress(
        metadata=client.V1ObjectMeta(
            name=name,
            annotations=annotations,
            labels=labels,
            owner_references=[
                client.V1OwnerReference(
                    api_version="v1", kind="Ingress", name=cluster_name, uid="unique-id"
                )
            ],
        ),
        spec=client.V1IngressSpec(
            rules=[
                client.V1IngressRule(
                    host=f"{name}-ns.apps.cluster.awsroute.org",
                    http=client.V1HTTPIngressRuleValue(
                        paths=[
                            client.V1HTTPIngressPath(
                                path_type="Prefix",
                                path="/",
                                backend=client.V1IngressBackend(
                                    service=client.V1IngressServiceBackend(
                                        name="head-svc-test",
                                        port=client.V1ServiceBackendPort(number=port),
                                    )
                                ),
                            )
                        ]
                    ),
                )
            ],
        ),
    )
    return mock_ingress


def ingress_retrieval(
    cluster_name="unit-test-cluster", client_ing: bool = False, annotations: dict = None
):
    dashboard_ingress = mocked_ingress(8265, cluster_name, annotations)
    if client_ing:
        client_ingress = mocked_ingress(
            10001, cluster_name=cluster_name, annotations=annotations
        )
        mock_ingress_list = client.V1IngressList(
            items=[client_ingress, dashboard_ingress]
        )
    else:
        mock_ingress_list = client.V1IngressList(items=[dashboard_ingress])

    return mock_ingress_list


def test_ray_job_wrapping(mocker):
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        return_value=get_local_queue("kueue.x-k8s.io", "v1beta1", "ns", "localqueues"),
    )
    cluster = cluster = createClusterWithConfig(mocker)
    mocker.patch(
        "ray.job_submission.JobSubmissionClient._check_connection_and_version_with_url",
        return_value="None",
    )
    mock_res = mocker.patch.object(
        ray.job_submission.JobSubmissionClient, "list_jobs", autospec=True
    )
    mock_res.side_effect = ray_addr
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.get_cluster_custom_object",
        return_value={"spec": {"domain": ""}},
    )
    mocker.patch(
        "kubernetes.client.NetworkingV1Api.list_namespaced_ingress",
        return_value=ingress_retrieval(),
    )
    assert cluster.list_jobs() == cluster.cluster_dashboard_uri()

    mock_res = mocker.patch.object(
        ray.job_submission.JobSubmissionClient, "get_job_status", autospec=True
    )
    mock_res.side_effect = ray_addr
    assert cluster.job_status("fake_id") == cluster.cluster_dashboard_uri()

    mock_res = mocker.patch.object(
        ray.job_submission.JobSubmissionClient, "get_job_logs", autospec=True
    )
    mock_res.side_effect = ray_addr
    assert cluster.job_logs("fake_id") == cluster.cluster_dashboard_uri()


def test_print_no_resources(capsys):
    try:
        print_no_resources_found()
    except:
        assert 1 == 0
    captured = capsys.readouterr()
    assert captured.out == (
        "╭──────────────────────────────────────────────────────────────────────────────╮\n"
        "│ No resources found, have you run cluster.up() yet?                           │\n"
        "╰──────────────────────────────────────────────────────────────────────────────╯\n"
    )


def test_print_no_cluster(capsys):
    try:
        print_cluster_status(None)
    except:
        assert 1 == 0
    captured = capsys.readouterr()
    assert captured.out == (
        "╭──────────────────────────────────────────────────────────────────────────────╮\n"
        "│ No resources found, have you run cluster.up() yet?                           │\n"
        "╰──────────────────────────────────────────────────────────────────────────────╯\n"
    )


def test_print_appwrappers(capsys):
    aw1 = AppWrapper(
        name="awtest1",
        status=AppWrapperStatus.SUSPENDED,
    )
    aw2 = AppWrapper(
        name="awtest2",
        status=AppWrapperStatus.RUNNING,
    )
    try:
        print_app_wrappers_status([aw1, aw2])
    except:
        assert 1 == 0
    captured = capsys.readouterr()
    assert captured.out == (
        "╭─────────────────────────╮\n"
        "│     🚀 Cluster Queue    │\n"
        "│        Status 🚀        │\n"
        "│ +---------+-----------+ │\n"
        "│ | Name    | Status    | │\n"
        "│ +=========+===========+ │\n"
        "│ | awtest1 | suspended | │\n"
        "│ |         |           | │\n"
        "│ | awtest2 | running   | │\n"
        "│ |         |           | │\n"
        "│ +---------+-----------+ │\n"
        "╰─────────────────────────╯\n"
    )


def test_ray_details(mocker, capsys):
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    ray1 = RayCluster(
        name="raytest1",
        status=RayClusterStatus.READY,
        num_workers=1,
        worker_mem_requests="2G",
        worker_mem_limits="2G",
        worker_cpu_requests=1,
        worker_cpu_limits=1,
        namespace="ns",
        dashboard="fake-uri",
        head_cpu_requests=2,
        head_cpu_limits=2,
        head_mem_requests=8,
        head_mem_limits=8,
    )
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster.Cluster.status",
        return_value=(False, CodeFlareClusterStatus.UNKNOWN),
    )
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster.Cluster.cluster_dashboard_uri",
        return_value="",
    )
    mocker.patch(
        "codeflare_sdk.common.kueue.kueue.local_queue_exists",
        return_value="true",
    )
    cf = Cluster(
        ClusterConfiguration(
            name="raytest2",
            namespace="ns",
            write_to_file=True,
            appwrapper=True,
            local_queue="local_default_queue",
        )
    )
    captured = capsys.readouterr()
    ray2 = _copy_to_ray(cf)
    details = cf.details()
    assert details == ray2
    assert ray2.name == "raytest2"
    assert ray1.namespace == ray2.namespace
    assert ray1.num_workers == ray2.num_workers
    assert ray1.worker_mem_requests == ray2.worker_mem_requests
    assert ray1.worker_mem_limits == ray2.worker_mem_limits
    assert ray1.worker_cpu_requests == ray2.worker_cpu_requests
    assert ray1.worker_cpu_limits == ray2.worker_cpu_limits
    assert ray1.worker_extended_resources == ray2.worker_extended_resources
    try:
        print_clusters([ray1, ray2])
        print_cluster_status(ray1)
        print_cluster_status(ray2)
    except:
        assert 0 == 1
    captured = capsys.readouterr()
    assert captured.out == (
        "                  🚀 CodeFlare Cluster Details 🚀                  \n"
        "                                                                   \n"
        " ╭───────────────────────────────────────────────────────────────╮ \n"
        " │   Name                                                        │ \n"
        " │   raytest2                                   Inactive ❌      │ \n"
        " │                                                               │ \n"
        " │   URI: ray://raytest2-head-svc.ns.svc:10001                   │ \n"
        " │                                                               │ \n"
        " │   Dashboard🔗                                                 │ \n"
        " │                                                               │ \n"
        " │                       Cluster Resources                       │ \n"
        " │   ╭── Workers ──╮  ╭───────── Worker specs(each) ─────────╮   │ \n"
        " │   │  # Workers  │  │  Memory      CPU         GPU         │   │ \n"
        " │   │             │  │                                      │   │ \n"
        " │   │  1          │  │  2G~2G       1~1         0           │   │ \n"
        " │   │             │  │                                      │   │ \n"
        " │   ╰─────────────╯  ╰──────────────────────────────────────╯   │ \n"
        " ╰───────────────────────────────────────────────────────────────╯ \n"
        "                  🚀 CodeFlare Cluster Details 🚀                  \n"
        "                                                                   \n"
        " ╭───────────────────────────────────────────────────────────────╮ \n"
        " │   Name                                                        │ \n"
        " │   raytest1                                   Active ✅        │ \n"
        " │                                                               │ \n"
        " │   URI: ray://raytest1-head-svc.ns.svc:10001                   │ \n"
        " │                                                               │ \n"
        " │   Dashboard🔗                                                 │ \n"
        " │                                                               │ \n"
        " │                       Cluster Resources                       │ \n"
        " │   ╭── Workers ──╮  ╭───────── Worker specs(each) ─────────╮   │ \n"
        " │   │  # Workers  │  │  Memory      CPU         GPU         │   │ \n"
        " │   │             │  │                                      │   │ \n"
        " │   │  1          │  │  2G~2G       1~1         0           │   │ \n"
        " │   │             │  │                                      │   │ \n"
        " │   ╰─────────────╯  ╰──────────────────────────────────────╯   │ \n"
        " ╰───────────────────────────────────────────────────────────────╯ \n"
        "╭───────────────────────────────────────────────────────────────╮\n"
        "│   Name                                                        │\n"
        "│   raytest2                                   Inactive ❌      │\n"
        "│                                                               │\n"
        "│   URI: ray://raytest2-head-svc.ns.svc:10001                   │\n"
        "│                                                               │\n"
        "│   Dashboard🔗                                                 │\n"
        "│                                                               │\n"
        "│                       Cluster Resources                       │\n"
        "│   ╭── Workers ──╮  ╭───────── Worker specs(each) ─────────╮   │\n"
        "│   │  # Workers  │  │  Memory      CPU         GPU         │   │\n"
        "│   │             │  │                                      │   │\n"
        "│   │  1          │  │  2G~2G       1~1         0           │   │\n"
        "│   │             │  │                                      │   │\n"
        "│   ╰─────────────╯  ╰──────────────────────────────────────╯   │\n"
        "╰───────────────────────────────────────────────────────────────╯\n"
        "                🚀 CodeFlare Cluster Status 🚀                \n"
        "                                                              \n"
        " ╭──────────────────────────────────────────────────────────╮ \n"
        " │   Name                                                   │ \n"
        " │   raytest1                                   Active ✅   │ \n"
        " │                                                          │ \n"
        " │   URI: ray://raytest1-head-svc.ns.svc:10001              │ \n"
        " │                                                          │ \n"
        " │   Dashboard🔗                                            │ \n"
        " │                                                          │ \n"
        " ╰──────────────────────────────────────────────────────────╯ \n"
        "                 🚀 CodeFlare Cluster Status 🚀                 \n"
        "                                                                \n"
        " ╭────────────────────────────────────────────────────────────╮ \n"
        " │   Name                                                     │ \n"
        " │   raytest2                                   Inactive ❌   │ \n"
        " │                                                            │ \n"
        " │   URI: ray://raytest2-head-svc.ns.svc:10001                │ \n"
        " │                                                            │ \n"
        " │   Dashboard🔗                                              │ \n"
        " │                                                            │ \n"
        " ╰────────────────────────────────────────────────────────────╯ \n"
    )


def act_side_effect_list(self):
    print([self])
    self.out = str(self.high_level_operation)
    return [self]


def get_obj_none(group, version, namespace, plural):
    return {"items": []}


def get_ray_obj(group, version, namespace, plural, cls=None):
    api_obj = {
        "items": [
            {
                "apiVersion": "ray.io/v1",
                "kind": "RayCluster",
                "metadata": {
                    "creationTimestamp": "2024-03-05T09:55:37Z",
                    "generation": 1,
                    "labels": {
                        "controller-tools.k8s.io": "1.0",
                        "resourceName": "quicktest",
                        "orderedinstance": "m4.xlarge_g4dn.xlarge",
                        "kueue.x-k8s.io/queue-name": "team-a-queue",
                    },
                    "name": "quicktest",
                    "namespace": "ns",
                    "ownerReferences": [
                        {
                            "apiVersion": "workload.codeflare.dev/v1beta2",
                            "blockOwnerDeletion": True,
                            "controller": True,
                            "kind": "AppWrapper",
                            "name": "quicktest",
                            "uid": "a29b1a7a-0992-4860-a8d5-a689a751a3e8",
                        }
                    ],
                    "resourceVersion": "5305674",
                    "uid": "820d065d-bf0c-4675-b951-d32ea496020e",
                },
                "spec": {
                    "autoscalerOptions": {
                        "idleTimeoutSeconds": 60,
                        "imagePullPolicy": "Always",
                        "resources": {
                            "limits": {"cpu": "500m", "memory": "512Mi"},
                            "requests": {"cpu": "500m", "memory": "512Mi"},
                        },
                        "upscalingMode": "Default",
                    },
                    "enableInTreeAutoscaling": False,
                    "headGroupSpec": {
                        "rayStartParams": {
                            "block": "true",
                            "dashboard-host": "0.0.0.0",
                            "num-gpus": "0",
                        },
                        "serviceType": "ClusterIP",
                        "template": {
                            "metadata": {},
                            "spec": {
                                "containers": [
                                    {
                                        "env": [
                                            {
                                                "name": "MY_POD_IP",
                                                "valueFrom": {
                                                    "fieldRef": {
                                                        "fieldPath": "status.podIP"
                                                    }
                                                },
                                            },
                                            {"name": "RAY_USE_TLS", "value": "0"},
                                            {
                                                "name": "RAY_TLS_SERVER_CERT",
                                                "value": "/home/ray/workspace/tls/server.crt",
                                            },
                                            {
                                                "name": "RAY_TLS_SERVER_KEY",
                                                "value": "/home/ray/workspace/tls/server.key",
                                            },
                                            {
                                                "name": "RAY_TLS_CA_CERT",
                                                "value": "/home/ray/workspace/tls/ca.crt",
                                            },
                                        ],
                                        "image": "ghcr.io/foundation-model-stack/base:ray2.1.0-py38-gpu-pytorch1.12.0cu116-20221213-193103",
                                        "imagePullPolicy": "Always",
                                        "lifecycle": {
                                            "preStop": {
                                                "exec": {
                                                    "command": [
                                                        "/bin/sh",
                                                        "-c",
                                                        "ray stop",
                                                    ]
                                                }
                                            }
                                        },
                                        "name": "ray-head",
                                        "ports": [
                                            {
                                                "containerPort": 6379,
                                                "name": "gcs",
                                                "protocol": "TCP",
                                            },
                                            {
                                                "containerPort": 8265,
                                                "name": "dashboard",
                                                "protocol": "TCP",
                                            },
                                            {
                                                "containerPort": 10001,
                                                "name": "client",
                                                "protocol": "TCP",
                                            },
                                        ],
                                        "resources": {
                                            "limits": {
                                                "cpu": 2,
                                                "memory": "8G",
                                            },
                                            "requests": {
                                                "cpu": 2,
                                                "memory": "8G",
                                            },
                                        },
                                        "volumeMounts": [
                                            {
                                                "mountPath": "/etc/pki/tls/certs/odh-trusted-ca-bundle.crt",
                                                "name": "odh-trusted-ca-cert",
                                                "subPath": "odh-trusted-ca-bundle.crt",
                                            },
                                            {
                                                "mountPath": "/etc/ssl/certs/odh-trusted-ca-bundle.crt",
                                                "name": "odh-trusted-ca-cert",
                                                "subPath": "odh-trusted-ca-bundle.crt",
                                            },
                                            {
                                                "mountPath": "/etc/pki/tls/certs/odh-ca-bundle.crt",
                                                "name": "odh-ca-cert",
                                                "subPath": "odh-ca-bundle.crt",
                                            },
                                            {
                                                "mountPath": "/etc/ssl/certs/odh-ca-bundle.crt",
                                                "name": "odh-ca-cert",
                                                "subPath": "odh-ca-bundle.crt",
                                            },
                                        ],
                                    }
                                ],
                                "volumes": [
                                    {
                                        "configMap": {
                                            "items": [
                                                {
                                                    "key": "ca-bundle.crt",
                                                    "path": "odh-trusted-ca-bundle.crt",
                                                }
                                            ],
                                            "name": "odh-trusted-ca-bundle",
                                            "optional": True,
                                        },
                                        "name": "odh-trusted-ca-cert",
                                    },
                                    {
                                        "configMap": {
                                            "items": [
                                                {
                                                    "key": "odh-ca-bundle.crt",
                                                    "path": "odh-ca-bundle.crt",
                                                }
                                            ],
                                            "name": "odh-trusted-ca-bundle",
                                            "optional": True,
                                        },
                                        "name": "odh-ca-cert",
                                    },
                                ],
                            },
                        },
                    },
                    "rayVersion": "2.35.0",
                    "workerGroupSpecs": [
                        {
                            "groupName": "small-group-quicktest",
                            "maxReplicas": 1,
                            "minReplicas": 1,
                            "rayStartParams": {
                                "block": "true",
                                "num-gpus": "0",
                            },
                            "replicas": 1,
                            "scaleStrategy": {},
                            "template": {
                                "metadata": {
                                    "annotations": {"key": "value"},
                                    "labels": {"key": "value"},
                                },
                                "spec": {
                                    "containers": [
                                        {
                                            "env": [
                                                {
                                                    "name": "MY_POD_IP",
                                                    "valueFrom": {
                                                        "fieldRef": {
                                                            "fieldPath": "status.podIP"
                                                        }
                                                    },
                                                },
                                                {"name": "RAY_USE_TLS", "value": "0"},
                                                {
                                                    "name": "RAY_TLS_SERVER_CERT",
                                                    "value": "/home/ray/workspace/tls/server.crt",
                                                },
                                                {
                                                    "name": "RAY_TLS_SERVER_KEY",
                                                    "value": "/home/ray/workspace/tls/server.key",
                                                },
                                                {
                                                    "name": "RAY_TLS_CA_CERT",
                                                    "value": "/home/ray/workspace/tls/ca.crt",
                                                },
                                            ],
                                            "image": "ghcr.io/foundation-model-stack/base:ray2.1.0-py38-gpu-pytorch1.12.0cu116-20221213-193103",
                                            "lifecycle": {
                                                "preStop": {
                                                    "exec": {
                                                        "command": [
                                                            "/bin/sh",
                                                            "-c",
                                                            "ray stop",
                                                        ]
                                                    }
                                                }
                                            },
                                            "name": "machine-learning",
                                            "resources": {
                                                "limits": {
                                                    "cpu": 1,
                                                    "memory": "2G",
                                                },
                                                "requests": {
                                                    "cpu": 1,
                                                    "memory": "2G",
                                                },
                                            },
                                            "volumeMounts": [
                                                {
                                                    "mountPath": "/etc/pki/tls/certs/odh-trusted-ca-bundle.crt",
                                                    "name": "odh-trusted-ca-cert",
                                                    "subPath": "odh-trusted-ca-bundle.crt",
                                                },
                                                {
                                                    "mountPath": "/etc/ssl/certs/odh-trusted-ca-bundle.crt",
                                                    "name": "odh-trusted-ca-cert",
                                                    "subPath": "odh-trusted-ca-bundle.crt",
                                                },
                                                {
                                                    "mountPath": "/etc/pki/tls/certs/odh-ca-bundle.crt",
                                                    "name": "odh-ca-cert",
                                                    "subPath": "odh-ca-bundle.crt",
                                                },
                                                {
                                                    "mountPath": "/etc/ssl/certs/odh-ca-bundle.crt",
                                                    "name": "odh-ca-cert",
                                                    "subPath": "odh-ca-bundle.crt",
                                                },
                                            ],
                                        }
                                    ],
                                    "volumes": [
                                        {
                                            "configMap": {
                                                "items": [
                                                    {
                                                        "key": "ca-bundle.crt",
                                                        "path": "odh-trusted-ca-bundle.crt",
                                                    }
                                                ],
                                                "name": "odh-trusted-ca-bundle",
                                                "optional": True,
                                            },
                                            "name": "odh-trusted-ca-cert",
                                        },
                                        {
                                            "configMap": {
                                                "items": [
                                                    {
                                                        "key": "odh-ca-bundle.crt",
                                                        "path": "odh-ca-bundle.crt",
                                                    }
                                                ],
                                                "name": "odh-trusted-ca-bundle",
                                                "optional": True,
                                            },
                                            "name": "odh-ca-cert",
                                        },
                                    ],
                                },
                            },
                        }
                    ],
                },
                "status": {
                    "desiredWorkerReplicas": 1,
                    "endpoints": {
                        "client": "10001",
                        "dashboard": "8265",
                        "gcs": "6379",
                        "metrics": "8080",
                    },
                    "head": {"serviceIP": "172.30.179.88"},
                    "lastUpdateTime": "2024-03-05T09:55:37Z",
                    "maxWorkerReplicas": 1,
                    "minWorkerReplicas": 1,
                    "observedGeneration": 1,
                    "state": "ready",
                },
            },
            {
                "apiVersion": "ray.io/v1",
                "kind": "RayCluster",
                "metadata": {
                    "creationTimestamp": "2023-02-22T16:26:07Z",
                    "generation": 1,
                    "labels": {
                        "controller-tools.k8s.io": "1.0",
                        "resourceName": "quicktest2",
                        "orderedinstance": "m4.xlarge_g4dn.xlarge",
                    },
                    "name": "quicktest2",
                    "namespace": "ns",
                    "ownerReferences": [
                        {
                            "apiVersion": "workload.codeflare.dev/v1beta2",
                            "blockOwnerDeletion": True,
                            "controller": True,
                            "kind": "AppWrapper",
                            "name": "quicktest2",
                            "uid": "6334fc1b-471e-4876-8e7b-0b2277679235",
                        }
                    ],
                    "resourceVersion": "9482407",
                    "uid": "44d45d1f-26c8-43e7-841f-831dbd8c1285",
                },
                "spec": {
                    "autoscalerOptions": {
                        "idleTimeoutSeconds": 60,
                        "imagePullPolicy": "Always",
                        "resources": {
                            "limits": {"cpu": "500m", "memory": "512Mi"},
                            "requests": {"cpu": "500m", "memory": "512Mi"},
                        },
                        "upscalingMode": "Default",
                    },
                    "enableInTreeAutoscaling": False,
                    "headGroupSpec": {
                        "rayStartParams": {
                            "block": "true",
                            "dashboard-host": "0.0.0.0",
                            "num-gpus": "0",
                        },
                        "serviceType": "ClusterIP",
                        "template": {
                            "spec": {
                                "containers": [
                                    {
                                        "image": "ghcr.io/foundation-model-stack/base:ray2.1.0-py38-gpu-pytorch1.12.0cu116-20221213-193103",
                                        "imagePullPolicy": "Always",
                                        "lifecycle": {
                                            "preStop": {
                                                "exec": {
                                                    "command": [
                                                        "/bin/sh",
                                                        "-c",
                                                        "ray stop",
                                                    ]
                                                }
                                            }
                                        },
                                        "name": "ray-head",
                                        "ports": [
                                            {
                                                "containerPort": 6379,
                                                "name": "gcs",
                                                "protocol": "TCP",
                                            },
                                            {
                                                "containerPort": 8265,
                                                "name": "dashboard",
                                                "protocol": "TCP",
                                            },
                                            {
                                                "containerPort": 10001,
                                                "name": "client",
                                                "protocol": "TCP",
                                            },
                                        ],
                                        "resources": {
                                            "limits": {
                                                "cpu": 2,
                                                "memory": "8G",
                                            },
                                            "requests": {
                                                "cpu": 2,
                                                "memory": "8G",
                                            },
                                        },
                                    }
                                ]
                            }
                        },
                    },
                    "rayVersion": "2.35.0",
                    "workerGroupSpecs": [
                        {
                            "groupName": "small-group-quicktest2",
                            "maxReplicas": 1,
                            "minReplicas": 1,
                            "rayStartParams": {
                                "block": "true",
                                "num-gpus": "0",
                            },
                            "replicas": 1,
                            "template": {
                                "metadata": {
                                    "annotations": {"key": "value"},
                                    "labels": {"key": "value"},
                                },
                                "spec": {
                                    "containers": [
                                        {
                                            "env": [
                                                {
                                                    "name": "MY_POD_IP",
                                                    "valueFrom": {
                                                        "fieldRef": {
                                                            "fieldPath": "status.podIP"
                                                        }
                                                    },
                                                }
                                            ],
                                            "image": "ghcr.io/foundation-model-stack/base:ray2.1.0-py38-gpu-pytorch1.12.0cu116-20221213-193103",
                                            "lifecycle": {
                                                "preStop": {
                                                    "exec": {
                                                        "command": [
                                                            "/bin/sh",
                                                            "-c",
                                                            "ray stop",
                                                        ]
                                                    }
                                                }
                                            },
                                            "name": "machine-learning",
                                            "resources": {
                                                "limits": {
                                                    "cpu": 1,
                                                    "memory": "2G",
                                                },
                                                "requests": {
                                                    "cpu": 1,
                                                    "memory": "2G",
                                                },
                                            },
                                        }
                                    ],
                                },
                            },
                        }
                    ],
                },
                "status": {
                    "availableWorkerReplicas": 2,
                    "desiredWorkerReplicas": 1,
                    "endpoints": {
                        "client": "10001",
                        "dashboard": "8265",
                        "gcs": "6379",
                    },
                    "lastUpdateTime": "2023-02-22T16:26:16Z",
                    "maxWorkerReplicas": 1,
                    "minWorkerReplicas": 1,
                    "state": "suspended",
                },
            },
        ]
    }
    return api_obj


def get_named_aw(group, version, namespace, plural, name):
    aws = get_aw_obj("workload.codeflare.dev", "v1beta2", "ns", "appwrappers")
    return aws["items"][0]


def get_aw_obj(group, version, namespace, plural):
    api_obj1 = {
        "items": [
            {
                "apiVersion": "workload.codeflare.dev/v1beta2",
                "kind": "AppWrapper",
                "metadata": {
                    "name": "quicktest1",
                    "namespace": "ns",
                },
                "spec": {
                    "components": [
                        {
                            "template": {
                                "apiVersion": "ray.io/v1",
                                "kind": "RayCluster",
                                "metadata": {
                                    "labels": {
                                        "controller-tools.k8s.io": "1.0",
                                    },
                                    "name": "quicktest1",
                                    "namespace": "ns",
                                },
                                "spec": {
                                    "autoscalerOptions": {
                                        "idleTimeoutSeconds": 60,
                                        "imagePullPolicy": "Always",
                                        "resources": {
                                            "limits": {
                                                "cpu": "500m",
                                                "memory": "512Mi",
                                            },
                                            "requests": {
                                                "cpu": "500m",
                                                "memory": "512Mi",
                                            },
                                        },
                                        "upscalingMode": "Default",
                                    },
                                    "enableInTreeAutoscaling": False,
                                    "headGroupSpec": {
                                        "rayStartParams": {
                                            "block": "true",
                                            "dashboard-host": "0.0.0.0",
                                            "num-gpus": "0",
                                        },
                                        "serviceType": "ClusterIP",
                                        "template": {
                                            "spec": {
                                                "containers": [
                                                    {
                                                        "image": "ghcr.io/foundation-model-stack/base:ray2.1.0-py38-gpu-pytorch1.12.0cu116-20221213-193103",
                                                        "imagePullPolicy": "Always",
                                                        "lifecycle": {
                                                            "preStop": {
                                                                "exec": {
                                                                    "command": [
                                                                        "/bin/sh",
                                                                        "-c",
                                                                        "ray stop",
                                                                    ]
                                                                }
                                                            }
                                                        },
                                                        "name": "ray-head",
                                                        "ports": [
                                                            {
                                                                "containerPort": 6379,
                                                                "name": "gcs",
                                                            },
                                                            {
                                                                "containerPort": 8265,
                                                                "name": "dashboard",
                                                            },
                                                            {
                                                                "containerPort": 10001,
                                                                "name": "client",
                                                            },
                                                        ],
                                                        "resources": {
                                                            "limits": {
                                                                "cpu": 2,
                                                                "memory": "8G",
                                                            },
                                                            "requests": {
                                                                "cpu": 2,
                                                                "memory": "8G",
                                                            },
                                                        },
                                                    }
                                                ]
                                            }
                                        },
                                    },
                                    "rayVersion": "1.12.0",
                                    "workerGroupSpecs": [
                                        {
                                            "groupName": "small-group-quicktest",
                                            "maxReplicas": 1,
                                            "minReplicas": 1,
                                            "rayStartParams": {
                                                "block": "true",
                                                "num-gpus": "0",
                                            },
                                            "replicas": 1,
                                            "template": {
                                                "metadata": {
                                                    "annotations": {"key": "value"},
                                                    "labels": {"key": "value"},
                                                },
                                                "spec": {
                                                    "containers": [
                                                        {
                                                            "env": [
                                                                {
                                                                    "name": "MY_POD_IP",
                                                                    "valueFrom": {
                                                                        "fieldRef": {
                                                                            "fieldPath": "status.podIP"
                                                                        }
                                                                    },
                                                                }
                                                            ],
                                                            "image": "ghcr.io/foundation-model-stack/base:ray2.1.0-py38-gpu-pytorch1.12.0cu116-20221213-193103",
                                                            "lifecycle": {
                                                                "preStop": {
                                                                    "exec": {
                                                                        "command": [
                                                                            "/bin/sh",
                                                                            "-c",
                                                                            "ray stop",
                                                                        ]
                                                                    }
                                                                }
                                                            },
                                                            "name": "machine-learning",
                                                            "resources": {
                                                                "limits": {
                                                                    "cpu": 1,
                                                                    "memory": "2G",
                                                                },
                                                                "requests": {
                                                                    "cpu": 1,
                                                                    "memory": "2G",
                                                                },
                                                            },
                                                        }
                                                    ],
                                                },
                                            },
                                        }
                                    ],
                                },
                            },
                        },
                        {
                            "template": {
                                "apiVersion": "networking.k8s.io/v1",
                                "kind": "Ingress",
                                "metadata": {
                                    "labels": {
                                        "ingress-owner": "appwrapper-name",
                                    },
                                    "name": "ray-dashboard-quicktest",
                                    "namespace": "default",
                                },
                                "spec": {
                                    "ingressClassName": "nginx",
                                    "rules": [
                                        {
                                            "http": {
                                                "paths": {
                                                    "backend": {
                                                        "service": {
                                                            "name": "quicktest-head-svc",
                                                            "port": {"number": 8265},
                                                        },
                                                    },
                                                    "pathType": "Prefix",
                                                    "path": "/",
                                                },
                                            },
                                            "host": "quicktest.awsroute.com",
                                        }
                                    ],
                                },
                            },
                        },
                    ],
                },
                "status": {
                    "phase": "Running",
                },
            },
            {
                "apiVersion": "workload.codeflare.dev/v1beta2",
                "kind": "AppWrapper",
                "metadata": {
                    "name": "quicktest2",
                    "namespace": "ns",
                },
                "spec": {
                    "components": [
                        {
                            "template": {
                                "apiVersion": "ray.io/v1",
                                "kind": "RayCluster",
                                "metadata": {
                                    "labels": {
                                        "controller-tools.k8s.io": "1.0",
                                    },
                                    "name": "quicktest2",
                                    "namespace": "ns",
                                },
                                "spec": {
                                    "autoscalerOptions": {
                                        "idleTimeoutSeconds": 60,
                                        "imagePullPolicy": "Always",
                                        "resources": {
                                            "limits": {
                                                "cpu": "500m",
                                                "memory": "512Mi",
                                            },
                                            "requests": {
                                                "cpu": "500m",
                                                "memory": "512Mi",
                                            },
                                        },
                                        "upscalingMode": "Default",
                                    },
                                    "enableInTreeAutoscaling": False,
                                    "headGroupSpec": {
                                        "rayStartParams": {
                                            "block": "true",
                                            "dashboard-host": "0.0.0.0",
                                            "num-gpus": "0",
                                        },
                                        "serviceType": "ClusterIP",
                                        "template": {
                                            "spec": {
                                                "containers": [
                                                    {
                                                        "image": "ghcr.io/foundation-model-stack/base:ray2.1.0-py38-gpu-pytorch1.12.0cu116-20221213-193103",
                                                        "imagePullPolicy": "Always",
                                                        "lifecycle": {
                                                            "preStop": {
                                                                "exec": {
                                                                    "command": [
                                                                        "/bin/sh",
                                                                        "-c",
                                                                        "ray stop",
                                                                    ]
                                                                }
                                                            }
                                                        },
                                                        "name": "ray-head",
                                                        "ports": [
                                                            {
                                                                "containerPort": 6379,
                                                                "name": "gcs",
                                                            },
                                                            {
                                                                "containerPort": 8265,
                                                                "name": "dashboard",
                                                            },
                                                            {
                                                                "containerPort": 10001,
                                                                "name": "client",
                                                            },
                                                        ],
                                                        "resources": {
                                                            "limits": {
                                                                "cpu": 2,
                                                                "memory": "8G",
                                                            },
                                                            "requests": {
                                                                "cpu": 2,
                                                                "memory": "8G",
                                                            },
                                                        },
                                                    }
                                                ]
                                            }
                                        },
                                    },
                                    "rayVersion": "2.35.0",
                                    "workerGroupSpecs": [
                                        {
                                            "groupName": "small-group-quicktest",
                                            "maxReplicas": 1,
                                            "minReplicas": 1,
                                            "rayStartParams": {
                                                "block": "true",
                                                "num-gpus": "0",
                                            },
                                            "replicas": 1,
                                            "template": {
                                                "metadata": {
                                                    "annotations": {"key": "value"},
                                                    "labels": {"key": "value"},
                                                },
                                                "spec": {
                                                    "containers": [
                                                        {
                                                            "env": [
                                                                {
                                                                    "name": "MY_POD_IP",
                                                                    "valueFrom": {
                                                                        "fieldRef": {
                                                                            "fieldPath": "status.podIP"
                                                                        }
                                                                    },
                                                                }
                                                            ],
                                                            "image": "ghcr.io/foundation-model-stack/base:ray2.1.0-py38-gpu-pytorch1.12.0cu116-20221213-193103",
                                                            "lifecycle": {
                                                                "preStop": {
                                                                    "exec": {
                                                                        "command": [
                                                                            "/bin/sh",
                                                                            "-c",
                                                                            "ray stop",
                                                                        ]
                                                                    }
                                                                }
                                                            },
                                                            "name": "machine-learning",
                                                            "resources": {
                                                                "limits": {
                                                                    "cpu": 1,
                                                                    "memory": "2G",
                                                                },
                                                                "requests": {
                                                                    "cpu": 1,
                                                                    "memory": "2G",
                                                                },
                                                            },
                                                        }
                                                    ],
                                                },
                                            },
                                        }
                                    ],
                                },
                            },
                        },
                        {
                            "template": {
                                "apiVersion": "route.openshift.io/v1",
                                "kind": "Route",
                                "metadata": {
                                    "labels": {
                                        "odh-ray-cluster-service": "quicktest-head-svc"
                                    },
                                    "name": "ray-dashboard-quicktest",
                                    "namespace": "default",
                                },
                                "spec": {
                                    "port": {"targetPort": "dashboard"},
                                    "to": {
                                        "kind": "Service",
                                        "name": "quicktest-head-svc",
                                    },
                                },
                            },
                        },
                    ],
                },
                "status": {
                    "phase": "Suspended",
                },
            },
        ]
    }
    return api_obj1


def route_list_retrieval(group, version, namespace, plural):
    assert group == "route.openshift.io"
    assert version == "v1"
    assert namespace == "ns"
    assert plural == "routes"
    return {
        "kind": "RouteList",
        "apiVersion": "route.openshift.io/v1",
        "metadata": {"resourceVersion": "6072398"},
        "items": [
            {
                "metadata": {
                    "name": "ray-dashboard-quicktest",
                    "namespace": "ns",
                },
                "spec": {
                    "host": "ray-dashboard-quicktest-opendatahub.apps.cluster.awsroute.org",
                    "to": {
                        "kind": "Service",
                        "name": "quicktest-head-svc",
                        "weight": 100,
                    },
                    "port": {"targetPort": "dashboard"},
                    "tls": {"termination": "edge"},
                },
            },
            {
                "metadata": {
                    "name": "rayclient-quicktest",
                    "namespace": "ns",
                },
                "spec": {
                    "host": "rayclient-quicktest-opendatahub.apps.cluster.awsroute.org",
                    "to": {
                        "kind": "Service",
                        "name": "quicktest-head-svc",
                        "weight": 100,
                    },
                    "port": {"targetPort": "client"},
                    "tls": {"termination": "passthrough"},
                },
            },
        ],
    }


def test_get_cluster_openshift(mocker):
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    # Mock the client.ApisApi function to return a mock object
    mock_api = MagicMock()
    mock_api.get_api_versions.return_value.groups = [
        MagicMock(versions=[MagicMock(group_version="route.openshift.io/v1")])
    ]
    mocker.patch("kubernetes.client.ApisApi", return_value=mock_api)
    mocker.patch(
        "codeflare_sdk.common.kueue.kueue.local_queue_exists",
        return_value="true",
    )

    assert is_openshift_cluster()

    def custom_side_effect(group, version, namespace, plural, **kwargs):
        if plural == "routes":
            return route_list_retrieval("route.openshift.io", "v1", "ns", "routes")
        elif plural == "rayclusters":
            return get_ray_obj("ray.io", "v1", "ns", "rayclusters")
        elif plural == "appwrappers":
            return get_aw_obj("workload.codeflare.dev", "v1beta2", "ns", "appwrappers")
        elif plural == "localqueues":
            return get_local_queue("kueue.x-k8s.io", "v1beta1", "ns", "localqueues")

    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object", get_aw_obj
    )

    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        side_effect=custom_side_effect,
    )
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.get_namespaced_custom_object",
        return_value=get_named_aw,
    )
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.get_namespaced_custom_object",
        side_effect=route_list_retrieval("route.openshift.io", "v1", "ns", "routes")[
            "items"
        ],
    )
    mocker.patch(
        "codeflare_sdk.common.kueue.kueue.local_queue_exists",
        return_value="true",
    )

    cluster = get_cluster("quicktest")
    cluster_config = cluster.config
    assert cluster_config.name == "quicktest" and cluster_config.namespace == "ns"
    assert (
        "m4.xlarge" in cluster_config.machine_types
        and "g4dn.xlarge" in cluster_config.machine_types
    )
    assert (
        cluster_config.worker_cpu_requests == 1
        and cluster_config.worker_cpu_limits == 1
    )
    assert (
        cluster_config.worker_memory_requests == "2G"
        and cluster_config.worker_memory_limits == "2G"
    )
    assert cluster_config.worker_extended_resource_requests == {}
    assert (
        cluster_config.image
        == "ghcr.io/foundation-model-stack/base:ray2.1.0-py38-gpu-pytorch1.12.0cu116-20221213-193103"
    )
    assert cluster_config.num_workers == 1


def test_get_cluster(mocker):
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        side_effect=get_ray_obj,
    )
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.get_namespaced_custom_object",
        side_effect=get_named_aw,
    )
    mocker.patch(
        "kubernetes.client.NetworkingV1Api.list_namespaced_ingress",
        return_value=ingress_retrieval(cluster_name="quicktest", client_ing=True),
    )
    mocker.patch(
        "codeflare_sdk.common.kueue.kueue.local_queue_exists",
        return_value="true",
    )
    cluster = get_cluster("quicktest")
    cluster_config = cluster.config
    assert cluster_config.name == "quicktest" and cluster_config.namespace == "ns"
    assert (
        "m4.xlarge" in cluster_config.machine_types
        and "g4dn.xlarge" in cluster_config.machine_types
    )
    assert (
        cluster_config.worker_cpu_requests == 1
        and cluster_config.worker_cpu_limits == 1
    )
    assert (
        cluster_config.worker_memory_requests == "2G"
        and cluster_config.worker_memory_limits == "2G"
    )
    assert cluster_config.worker_extended_resource_requests == {}
    assert (
        cluster_config.image
        == "ghcr.io/foundation-model-stack/base:ray2.1.0-py38-gpu-pytorch1.12.0cu116-20221213-193103"
    )
    assert cluster_config.num_workers == 1


def test_get_cluster_no_mcad(mocker):
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        side_effect=get_ray_obj,
    )
    mocker.patch(
        "kubernetes.client.NetworkingV1Api.list_namespaced_ingress",
        return_value=ingress_retrieval(cluster_name="quicktest", client_ing=True),
    )
    mocker.patch(
        "codeflare_sdk.common.kueue.kueue.local_queue_exists",
        return_value="true",
    )
    cluster = get_cluster("quicktest")
    cluster_config = cluster.config
    assert cluster_config.name == "quicktest" and cluster_config.namespace == "ns"
    assert (
        "m4.xlarge" in cluster_config.machine_types
        and "g4dn.xlarge" in cluster_config.machine_types
    )
    assert (
        cluster_config.worker_cpu_requests == 1
        and cluster_config.worker_cpu_limits == 1
    )
    assert (
        cluster_config.worker_memory_requests == "2G"
        and cluster_config.worker_memory_limits == "2G"
    )
    assert cluster_config.worker_extended_resource_requests == {}
    assert (
        cluster_config.image
        == "ghcr.io/foundation-model-stack/base:ray2.1.0-py38-gpu-pytorch1.12.0cu116-20221213-193103"
    )
    assert cluster_config.num_workers == 1
    assert cluster_config.local_queue == "team-a-queue"


def route_retrieval(group, version, namespace, plural, name):
    assert group == "route.openshift.io"
    assert version == "v1"
    assert namespace == "ns"
    assert plural == "routes"
    assert name == "ray-dashboard-unit-test-cluster"
    return {
        "items": [
            {
                "metadata": {"name": "ray-dashboard-unit-test-cluster"},
                "spec": {
                    "host": "ray-dashboard-unit-test-cluster-ns.apps.cluster.awsroute.org"
                },
            }
        ]
    }


def test_map_to_ray_cluster(mocker):
    mocker.patch("kubernetes.config.load_kube_config")

    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster.is_openshift_cluster", return_value=True
    )

    mock_api_client = mocker.MagicMock(spec=client.ApiClient)
    mocker.patch(
        "codeflare_sdk.common.kubernetes_cluster.auth.get_api_client",
        return_value=mock_api_client,
    )

    mock_routes = {
        "items": [
            {
                "apiVersion": "route.openshift.io/v1",
                "kind": "Route",
                "metadata": {
                    "name": "ray-dashboard-quicktest",
                    "namespace": "ns",
                },
                "spec": {"host": "ray-dashboard-quicktest"},
            },
        ]
    }

    def custom_side_effect(group, version, namespace, plural, **kwargs):
        if plural == "routes":
            return mock_routes
        elif plural == "rayclusters":
            return get_ray_obj("ray.io", "v1", "ns", "rayclusters")

    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        side_effect=custom_side_effect,
    )

    rc = get_ray_obj("ray.io", "v1", "ns", "rayclusters")["items"][0]
    rc_name = rc["metadata"]["name"]
    rc_dashboard = f"http://ray-dashboard-{rc_name}"

    result = _map_to_ray_cluster(rc)

    assert result is not None
    assert result.dashboard == rc_dashboard


def test_list_clusters(mocker, capsys):
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        side_effect=get_obj_none,
    )
    mocker.patch(
        "kubernetes.client.NetworkingV1Api.list_namespaced_ingress",
    )
    list_all_clusters("ns")
    captured = capsys.readouterr()
    assert captured.out == (
        "╭──────────────────────────────────────────────────────────────────────────────╮\n"
        "│ No resources found, have you run cluster.up() yet?                           │\n"
        "╰──────────────────────────────────────────────────────────────────────────────╯\n"
    )
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        side_effect=get_ray_obj,
    )
    list_all_clusters("ns")
    captured = capsys.readouterr()
    assert captured.out == (
        "                  🚀 CodeFlare Cluster Details 🚀                  \n"
        "                                                                   \n"
        " ╭───────────────────────────────────────────────────────────────╮ \n"
        " │   Name                                                        │ \n"
        " │   quicktest                                   Active ✅       │ \n"
        " │                                                               │ \n"
        " │   URI: ray://quicktest-head-svc.ns.svc:10001                  │ \n"
        " │                                                               │ \n"
        " │   Dashboard🔗                                                 │ \n"
        " │                                                               │ \n"
        " │                       Cluster Resources                       │ \n"
        " │   ╭── Workers ──╮  ╭───────── Worker specs(each) ─────────╮   │ \n"
        " │   │  # Workers  │  │  Memory      CPU         GPU         │   │ \n"
        " │   │             │  │                                      │   │ \n"
        " │   │  1          │  │  2G~2G       1~1         0           │   │ \n"
        " │   │             │  │                                      │   │ \n"
        " │   ╰─────────────╯  ╰──────────────────────────────────────╯   │ \n"
        " ╰───────────────────────────────────────────────────────────────╯ \n"
        "╭───────────────────────────────────────────────────────────────╮\n"
        "│   Name                                                        │\n"
        "│   quicktest2                                   Inactive ❌    │\n"
        "│                                                               │\n"
        "│   URI: ray://quicktest2-head-svc.ns.svc:10001                 │\n"
        "│                                                               │\n"
        "│   Dashboard🔗                                                 │\n"
        "│                                                               │\n"
        "│                       Cluster Resources                       │\n"
        "│   ╭── Workers ──╮  ╭───────── Worker specs(each) ─────────╮   │\n"
        "│   │  # Workers  │  │  Memory      CPU         GPU         │   │\n"
        "│   │             │  │                                      │   │\n"
        "│   │  1          │  │  2G~2G       1~1         0           │   │\n"
        "│   │             │  │                                      │   │\n"
        "│   ╰─────────────╯  ╰──────────────────────────────────────╯   │\n"
        "╰───────────────────────────────────────────────────────────────╯\n"
    )


def test_list_queue(mocker, capsys):
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        side_effect=get_obj_none,
    )
    list_all_queued("ns", appwrapper=True)
    captured = capsys.readouterr()
    assert captured.out == (
        "╭──────────────────────────────────────────────────────────────────────────────╮\n"
        "│ No resources found, have you run cluster.up() yet?                           │\n"
        "╰──────────────────────────────────────────────────────────────────────────────╯\n"
    )
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        side_effect=get_aw_obj,
    )
    list_all_queued("ns", appwrapper=True)
    captured = capsys.readouterr()
    assert captured.out == (
        "╭────────────────────────────╮\n"
        "│   🚀 Cluster Queue Status  │\n"
        "│             🚀             │\n"
        "│ +------------+-----------+ │\n"
        "│ | Name       | Status    | │\n"
        "│ +============+===========+ │\n"
        "│ | quicktest1 | running   | │\n"
        "│ |            |           | │\n"
        "│ | quicktest2 | suspended | │\n"
        "│ |            |           | │\n"
        "│ +------------+-----------+ │\n"
        "╰────────────────────────────╯\n"
    )


def test_list_queue_rayclusters(mocker, capsys):
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mock_api = MagicMock()
    mock_api.get_api_versions.return_value.groups = [
        MagicMock(versions=[MagicMock(group_version="route.openshift.io/v1")])
    ]
    mocker.patch("kubernetes.client.ApisApi", return_value=mock_api)

    assert is_openshift_cluster() == True
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        side_effect=get_obj_none,
    )
    list_all_queued("ns")
    captured = capsys.readouterr()
    assert captured.out == (
        "╭──────────────────────────────────────────────────────────────────────────────╮\n"
        "│ No resources found, have you run cluster.up() yet?                           │\n"
        "╰──────────────────────────────────────────────────────────────────────────────╯\n"
    )
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        side_effect=get_ray_obj,
    )
    list_all_queued("ns")
    captured = capsys.readouterr()
    print(captured.out)
    assert captured.out == (
        "╭────────────────────────────╮\n"
        "│   🚀 Cluster Queue Status  │\n"
        "│             🚀             │\n"
        "│ +------------+-----------+ │\n"
        "│ | Name       | Status    | │\n"
        "│ +============+===========+ │\n"
        "│ | quicktest  | ready     | │\n"
        "│ |            |           | │\n"
        "│ | quicktest2 | suspended | │\n"
        "│ |            |           | │\n"
        "│ +------------+-----------+ │\n"
        "╰────────────────────────────╯\n"
    )


def test_cluster_status(mocker):
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch(
        "codeflare_sdk.common.kueue.kueue.local_queue_exists",
        return_value="true",
    )
    fake_aw = AppWrapper("test", AppWrapperStatus.FAILED)
    fake_ray = RayCluster(
        name="test",
        status=RayClusterStatus.UNKNOWN,
        num_workers=1,
        worker_mem_requests=2,
        worker_mem_limits=2,
        worker_cpu_requests=1,
        worker_cpu_limits=1,
        namespace="ns",
        dashboard="fake-uri",
        head_cpu_requests=2,
        head_cpu_limits=2,
        head_mem_requests=8,
        head_mem_limits=8,
    )
    cf = Cluster(
        ClusterConfiguration(
            name="test",
            namespace="ns",
            write_to_file=True,
            appwrapper=True,
            local_queue="local_default_queue",
        )
    )
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster._app_wrapper_status", return_value=None
    )
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster._ray_cluster_status", return_value=None
    )
    status, ready = cf.status()
    assert status == CodeFlareClusterStatus.UNKNOWN
    assert ready == False

    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster._app_wrapper_status", return_value=fake_aw
    )
    status, ready = cf.status()
    assert status == CodeFlareClusterStatus.FAILED
    assert ready == False

    fake_aw.status = AppWrapperStatus.SUSPENDED
    status, ready = cf.status()
    assert status == CodeFlareClusterStatus.QUEUED
    assert ready == False

    fake_aw.status = AppWrapperStatus.RESUMING
    status, ready = cf.status()
    assert status == CodeFlareClusterStatus.STARTING
    assert ready == False

    fake_aw.status = AppWrapperStatus.RESETTING
    status, ready = cf.status()
    assert status == CodeFlareClusterStatus.STARTING
    assert ready == False

    fake_aw.status = AppWrapperStatus.RUNNING
    status, ready = cf.status()
    assert status == CodeFlareClusterStatus.UNKNOWN
    assert ready == False

    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster._ray_cluster_status", return_value=fake_ray
    )

    status, ready = cf.status()
    assert status == CodeFlareClusterStatus.STARTING
    assert ready == False

    fake_ray.status = RayClusterStatus.FAILED
    status, ready = cf.status()
    assert status == CodeFlareClusterStatus.FAILED
    assert ready == False

    fake_ray.status = RayClusterStatus.UNHEALTHY
    status, ready = cf.status()
    assert status == CodeFlareClusterStatus.FAILED
    assert ready == False

    fake_ray.status = RayClusterStatus.READY
    status, ready = cf.status()
    assert status == CodeFlareClusterStatus.READY
    assert ready == True


def test_wait_ready(mocker, capsys):
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch(
        "kubernetes.client.NetworkingV1Api.list_namespaced_ingress",
        return_value=ingress_retrieval(),
    )
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster._app_wrapper_status", return_value=None
    )
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster._ray_cluster_status", return_value=None
    )
    mocker.patch(
        "codeflare_sdk.common.kueue.kueue.local_queue_exists",
        return_value="true",
    )
    mocker.patch.object(
        client.CustomObjectsApi,
        "list_namespaced_custom_object",
        return_value={
            "items": [
                {
                    "metadata": {"name": "ray-dashboard-test"},
                    "spec": {"host": "mocked-host"},
                }
            ]
        },
    )
    mock_response = mocker.Mock()
    mock_response.status_code = 200
    mocker.patch("requests.get", return_value=mock_response)
    cf = Cluster(
        ClusterConfiguration(
            name="test",
            namespace="ns",
            write_to_file=True,
            appwrapper=True,
            local_queue="local-queue-default",
        )
    )
    try:
        cf.wait_ready(timeout=5)
        assert 1 == 0
    except Exception as e:
        assert type(e) == TimeoutError

    captured = capsys.readouterr()
    assert (
        "WARNING: Current cluster status is unknown, have you run cluster.up yet?"
        in captured.out
    )
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster.Cluster.status",
        return_value=(True, CodeFlareClusterStatus.READY),
    )
    cf.wait_ready()
    captured = capsys.readouterr()
    assert (
        captured.out
        == "Waiting for requested resources to be set up...\nRequested cluster is up and running!\nDashboard is ready!\n"
    )
    cf.wait_ready(dashboard_check=False)
    captured = capsys.readouterr()
    assert (
        captured.out
        == "Waiting for requested resources to be set up...\nRequested cluster is up and running!\n"
    )


def arg_check_side_effect(*args):
    assert args[0] == "fake-app-handle"


def parse_j(cmd):
    pattern = r"--nnodes\s+\d+\s+--nproc_per_node\s+\d+"
    match = re.search(pattern, cmd)
    if match:
        substring = match.group(0)
    else:
        return None
    args = substring.split()
    worker = args[1]
    gpu = args[3]
    return f"{worker}x{gpu}"


def test_AWManager_creation(mocker):
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
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
        testaw = AWManager("tests/test-case-bad.yaml")
    except Exception as e:
        assert type(e) == ValueError
        assert (
            str(e)
            == "tests/test-case-bad.yaml is not a correctly formatted AppWrapper yaml"
        )


def arg_check_aw_apply_effect(group, version, namespace, plural, body, *args):
    assert group == "workload.codeflare.dev"
    assert version == "v1beta2"
    assert namespace == "ns"
    assert plural == "appwrappers"
    with open(f"{aw_dir}test.yaml") as f:
        aw = yaml.load(f, Loader=yaml.FullLoader)
    assert body == aw
    assert args == tuple()


def arg_check_aw_del_effect(group, version, namespace, plural, name, *args):
    assert group == "workload.codeflare.dev"
    assert version == "v1beta2"
    assert namespace == "ns"
    assert plural == "appwrappers"
    assert name == "test"
    assert args == tuple()


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


from cryptography.x509 import load_pem_x509_certificate
import base64
from cryptography.hazmat.primitives.serialization import (
    load_pem_private_key,
    Encoding,
    PublicFormat,
)


def test_generate_ca_cert():
    """
    test the function codeflare_sdk.common.utils.generate_ca_cert generates the correct outputs
    """
    key, certificate = generate_ca_cert()
    cert = load_pem_x509_certificate(base64.b64decode(certificate))
    private_pub_key_bytes = (
        load_pem_private_key(base64.b64decode(key), password=None)
        .public_key()
        .public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo)
    )
    cert_pub_key_bytes = cert.public_key().public_bytes(
        Encoding.PEM, PublicFormat.SubjectPublicKeyInfo
    )
    assert type(key) == str
    assert type(certificate) == str
    # Veirfy ca.cert is self signed
    assert cert.verify_directly_issued_by(cert) == None
    # Verify cert has the public key bytes from the private key
    assert cert_pub_key_bytes == private_pub_key_bytes


def secret_ca_retreival(secret_name, namespace):
    ca_private_key_bytes, ca_cert = generate_ca_cert()
    data = {"ca.crt": ca_cert, "ca.key": ca_private_key_bytes}
    assert secret_name == "ca-secret-cluster"
    assert namespace == "namespace"
    return client.models.V1Secret(data=data)


def test_generate_tls_cert(mocker):
    """
    test the function codeflare_sdk.common.utils.generate_ca_cert generates the correct outputs
    """
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch(
        "codeflare_sdk.common.utils.generate_cert.get_secret_name",
        return_value="ca-secret-cluster",
    )
    mocker.patch(
        "kubernetes.client.CoreV1Api.read_namespaced_secret",
        side_effect=secret_ca_retreival,
    )

    generate_tls_cert("cluster", "namespace")
    assert os.path.exists("tls-cluster-namespace")
    assert os.path.exists(os.path.join("tls-cluster-namespace", "ca.crt"))
    assert os.path.exists(os.path.join("tls-cluster-namespace", "tls.crt"))
    assert os.path.exists(os.path.join("tls-cluster-namespace", "tls.key"))

    # verify the that the signed tls.crt is issued by the ca_cert (root cert)
    with open(os.path.join("tls-cluster-namespace", "tls.crt"), "r") as f:
        tls_cert = load_pem_x509_certificate(f.read().encode("utf-8"))
    with open(os.path.join("tls-cluster-namespace", "ca.crt"), "r") as f:
        root_cert = load_pem_x509_certificate(f.read().encode("utf-8"))
    assert tls_cert.verify_directly_issued_by(root_cert) == None


def test_export_env():
    """
    test the function codeflare_sdk.common.utils.generate_ca_cert.export_ev generates the correct outputs
    """
    tls_dir = "cluster"
    ns = "namespace"
    export_env(tls_dir, ns)
    assert os.environ["RAY_USE_TLS"] == "1"
    assert os.environ["RAY_TLS_SERVER_CERT"] == os.path.join(
        os.getcwd(), f"tls-{tls_dir}-{ns}", "tls.crt"
    )
    assert os.environ["RAY_TLS_SERVER_KEY"] == os.path.join(
        os.getcwd(), f"tls-{tls_dir}-{ns}", "tls.key"
    )
    assert os.environ["RAY_TLS_CA_CERT"] == os.path.join(
        os.getcwd(), f"tls-{tls_dir}-{ns}", "ca.crt"
    )


def test_cluster_throw_for_no_raycluster(mocker: MockerFixture):
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster.get_current_namespace",
        return_value="opendatahub",
    )
    mocker.patch(
        "codeflare_sdk.common.kueue.kueue.get_default_kueue_name",
        return_value="default",
    )
    mocker.patch(
        "codeflare_sdk.common.kueue.kueue.local_queue_exists",
        return_value="true",
    )

    def throw_if_getting_raycluster(group, version, namespace, plural):
        if plural == "rayclusters":
            raise client.ApiException(status=404)
        return

    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        side_effect=throw_if_getting_raycluster,
    )
    cluster = Cluster(
        ClusterConfiguration(
            "test_cluster",
            write_to_file=False,
        )
    )
    with pytest.raises(RuntimeError):
        cluster.up()


"""
Ray Jobs tests
"""


# rjc == RayJobClient
@pytest.fixture
def ray_job_client(mocker):
    # Creating a fixture to instantiate RayJobClient with a mocked JobSubmissionClient
    mocker.patch.object(JobSubmissionClient, "__init__", return_value=None)
    return RayJobClient(
        "https://ray-dashboard-unit-test-cluster-ns.apps.cluster.awsroute.org"
    )


def test_rjc_submit_job(ray_job_client, mocker):
    mocked_submit_job = mocker.patch.object(
        JobSubmissionClient, "submit_job", return_value="mocked_submission_id"
    )
    submission_id = ray_job_client.submit_job(entrypoint={"pip": ["numpy"]})

    mocked_submit_job.assert_called_once_with(
        entrypoint={"pip": ["numpy"]},
        job_id=None,
        runtime_env=None,
        metadata=None,
        submission_id=None,
        entrypoint_num_cpus=None,
        entrypoint_num_gpus=None,
        entrypoint_memory=None,
        entrypoint_resources=None,
    )

    assert submission_id == "mocked_submission_id"


def test_rjc_delete_job(ray_job_client, mocker):
    # Case return True
    mocked_delete_job_True = mocker.patch.object(
        JobSubmissionClient, "delete_job", return_value=True
    )
    result = ray_job_client.delete_job(job_id="mocked_job_id")

    mocked_delete_job_True.assert_called_once_with(job_id="mocked_job_id")
    assert result == (True, "Successfully deleted Job mocked_job_id")

    # Case return False
    mocked_delete_job_False = mocker.patch.object(
        JobSubmissionClient, "delete_job", return_value=(False)
    )
    result = ray_job_client.delete_job(job_id="mocked_job_id")

    mocked_delete_job_False.assert_called_once_with(job_id="mocked_job_id")
    assert result == (False, "Failed to delete Job mocked_job_id")


def test_rjc_stop_job(ray_job_client, mocker):
    # Case return True
    mocked_stop_job_True = mocker.patch.object(
        JobSubmissionClient, "stop_job", return_value=(True)
    )
    result = ray_job_client.stop_job(job_id="mocked_job_id")

    mocked_stop_job_True.assert_called_once_with(job_id="mocked_job_id")
    assert result == (True, "Successfully stopped Job mocked_job_id")

    # Case return False
    mocked_stop_job_False = mocker.patch.object(
        JobSubmissionClient, "stop_job", return_value=(False)
    )
    result = ray_job_client.stop_job(job_id="mocked_job_id")

    mocked_stop_job_False.assert_called_once_with(job_id="mocked_job_id")
    assert result == (
        False,
        "Failed to stop Job, mocked_job_id could have already completed.",
    )


def test_rjc_address(ray_job_client, mocker):
    mocked_rjc_address = mocker.patch.object(
        JobSubmissionClient,
        "get_address",
        return_value="https://ray-dashboard-unit-test-cluster-ns.apps.cluster.awsroute.org",
    )
    address = ray_job_client.get_address()

    mocked_rjc_address.assert_called_once()
    assert (
        address
        == "https://ray-dashboard-unit-test-cluster-ns.apps.cluster.awsroute.org"
    )


def test_rjc_get_job_logs(ray_job_client, mocker):
    mocked_rjc_get_job_logs = mocker.patch.object(
        JobSubmissionClient, "get_job_logs", return_value="Logs"
    )
    logs = ray_job_client.get_job_logs(job_id="mocked_job_id")

    mocked_rjc_get_job_logs.assert_called_once_with(job_id="mocked_job_id")
    assert logs == "Logs"


def test_rjc_get_job_info(ray_job_client, mocker):
    job_details_example = "JobDetails(type=<JobType.SUBMISSION: 'SUBMISSION'>, job_id=None, submission_id='mocked_submission_id', driver_info=None, status=<JobStatus.PENDING: 'PENDING'>, entrypoint='python test.py', message='Job has not started yet. It may be waiting for the runtime environment to be set up.', error_type=None, start_time=1701271760641, end_time=None, metadata={}, runtime_env={'working_dir': 'gcs://_ray_pkg_67de6f0e60d43b19.zip', 'pip': {'packages': ['numpy'], 'pip_check': False}, '_ray_commit': 'b4bba4717f5ba04ee25580fe8f88eed63ef0c5dc'}, driver_agent_http_address=None, driver_node_id=None)"
    mocked_rjc_get_job_info = mocker.patch.object(
        JobSubmissionClient, "get_job_info", return_value=job_details_example
    )
    job_details = ray_job_client.get_job_info(job_id="mocked_job_id")

    mocked_rjc_get_job_info.assert_called_once_with(job_id="mocked_job_id")
    assert job_details == job_details_example


def test_rjc_get_job_status(ray_job_client, mocker):
    job_status_example = "<JobStatus.PENDING: 'PENDING'>"
    mocked_rjc_get_job_status = mocker.patch.object(
        JobSubmissionClient, "get_job_status", return_value=job_status_example
    )
    job_status = ray_job_client.get_job_status(job_id="mocked_job_id")

    mocked_rjc_get_job_status.assert_called_once_with(job_id="mocked_job_id")
    assert job_status == job_status_example


def test_rjc_tail_job_logs(ray_job_client, mocker):
    logs_example = [
        "Job started...",
        "Processing input data...",
        "Finalizing results...",
        "Job completed successfully.",
    ]
    mocked_rjc_tail_job_logs = mocker.patch.object(
        JobSubmissionClient, "tail_job_logs", return_value=logs_example
    )
    job_tail_job_logs = ray_job_client.tail_job_logs(job_id="mocked_job_id")

    mocked_rjc_tail_job_logs.assert_called_once_with(job_id="mocked_job_id")
    assert job_tail_job_logs == logs_example


def test_rjc_list_jobs(ray_job_client, mocker):
    requirements_path = "tests/e2e/mnist_pip_requirements.txt"
    pytorch_lightning = get_package_and_version("pytorch_lightning", requirements_path)
    torchmetrics = get_package_and_version("torchmetrics", requirements_path)
    torchvision = get_package_and_version("torchvision", requirements_path)
    jobs_list = [
        f"JobDetails(type=<JobType.SUBMISSION: 'SUBMISSION'>, job_id=None, submission_id='raysubmit_4k2NYS1YbRXYPZCM', driver_info=None, status=<JobStatus.SUCCEEDED: 'SUCCEEDED'>, entrypoint='python mnist.py', message='Job finished successfully.', error_type=None, start_time=1701352132585, end_time=1701352192002, metadata={{}}, runtime_env={{'working_dir': 'gcs://_ray_pkg_6200b93a110e8033.zip', 'pip': {{'packages': ['{pytorch_lightning}', 'ray_lightning', '{torchmetrics}', '{torchvision}'], 'pip_check': False}}, '_ray_commit': 'b4bba4717f5ba04ee25580fe8f88eed63ef0c5dc'}}, driver_agent_http_address='http://10.131.0.18:52365', driver_node_id='9fb515995f5fb13ad4db239ceea378333bebf0a2d45b6aa09d02e691')",
        f"JobDetails(type=<JobType.SUBMISSION: 'SUBMISSION'>, job_id=None, submission_id='raysubmit_iRuwU8vdkbUZZGvT', driver_info=None, status=<JobStatus.STOPPED: 'STOPPED'>, entrypoint='python mnist.py', message='Job was intentionally stopped.', error_type=None, start_time=1701353096163, end_time=1701353097733, metadata={{}}, runtime_env={{'working_dir': 'gcs://_ray_pkg_6200b93a110e8033.zip', 'pip': {{'packages': ['{pytorch_lightning}', 'ray_lightning', '{torchmetrics}', '{torchvision}'], 'pip_check': False}}, '_ray_commit': 'b4bba4717f5ba04ee25580fe8f88eed63ef0c5dc'}}, driver_agent_http_address='http://10.131.0.18:52365', driver_node_id='9fb515995f5fb13ad4db239ceea378333bebf0a2d45b6aa09d02e691')",
    ]
    mocked_rjc_list_jobs = mocker.patch.object(
        JobSubmissionClient, "list_jobs", return_value=jobs_list
    )
    job_list_jobs = ray_job_client.list_jobs()

    mocked_rjc_list_jobs.assert_called_once()
    assert job_list_jobs == jobs_list


def test_cluster_config_deprecation_conversion(mocker):
    config = ClusterConfiguration(
        name="test",
        num_gpus=2,
        head_gpus=1,
        min_memory=3,
        max_memory=4,
        min_cpus=1,
        max_cpus=2,
    )
    assert config.worker_extended_resource_requests == {"nvidia.com/gpu": 2}
    assert config.head_extended_resource_requests == {"nvidia.com/gpu": 1}
    assert config.worker_memory_requests == "3G"
    assert config.worker_memory_limits == "4G"
    assert config.worker_cpu_requests == 1
    assert config.worker_cpu_limits == 2


"""
    Ipywidgets tests
"""


@patch.dict(
    "os.environ", {"JPY_SESSION_NAME": "example-test"}
)  # Mock Jupyter environment variable
def test_cluster_up_down_buttons(mocker):
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.get_cluster_custom_object",
        return_value={"spec": {"domain": "apps.cluster.awsroute.org"}},
    )
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        return_value=get_local_queue("kueue.x-k8s.io", "v1beta1", "ns", "localqueues"),
    )
    cluster = Cluster(createClusterConfig())

    with patch("ipywidgets.Button") as MockButton, patch(
        "ipywidgets.Checkbox"
    ) as MockCheckbox, patch("ipywidgets.Output"), patch("ipywidgets.HBox"), patch(
        "ipywidgets.VBox"
    ), patch.object(
        cluster, "up"
    ) as mock_up, patch.object(
        cluster, "down"
    ) as mock_down, patch.object(
        cluster, "wait_ready"
    ) as mock_wait_ready:
        # Create mock button & CheckBox instances
        mock_up_button = MagicMock()
        mock_down_button = MagicMock()
        mock_wait_ready_check_box = MagicMock()

        # Ensure the mock Button class returns the mock button instances in sequence
        MockCheckbox.side_effect = [mock_wait_ready_check_box]
        MockButton.side_effect = [mock_up_button, mock_down_button]

        # Call the method under test
        cf_widgets.cluster_up_down_buttons(cluster)

        # Simulate checkbox being checked or unchecked
        mock_wait_ready_check_box.value = True  # Simulate checkbox being checked

        # Simulate the button clicks by calling the mock on_click handlers
        mock_up_button.on_click.call_args[0][0](None)  # Simulate clicking "Cluster Up"
        mock_down_button.on_click.call_args[0][0](
            None
        )  # Simulate clicking "Cluster Down"

        # Check if the `up` and `down` methods were called
        mock_wait_ready.assert_called_once()
        mock_up.assert_called_once()
        mock_down.assert_called_once()


@patch.dict("os.environ", {}, clear=True)  # Mock environment with no variables
def test_is_notebook_false():
    from codeflare_sdk.cluster.widgets import is_notebook

    assert is_notebook() is False


@patch.dict(
    "os.environ", {"JPY_SESSION_NAME": "example-test"}
)  # Mock Jupyter environment variable
def test_is_notebook_true():
    from codeflare_sdk.cluster.widgets import is_notebook

    assert is_notebook() is True


def test_view_clusters(mocker, capsys):
    from kubernetes.client.rest import ApiException

    mocker.patch("codeflare_sdk.cluster.widgets.is_notebook", return_value=False)
    with pytest.warns(
        UserWarning,
        match="view_clusters can only be used in a Jupyter Notebook environment.",
    ):
        result = cf_widgets.view_clusters(namespace="default")
        # Assert the function returns None when not in a notebook environment
        assert result is None

    mocker.patch("codeflare_sdk.cluster.widgets.is_notebook", return_value=True)

    # Mock Kubernetes API responses
    mocker.patch("kubernetes.client.ApisApi.get_api_versions")
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        return_value={"items": []},
    )
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster._check_aw_exists", return_value=False
    )

    # Return empty dataframe when no clusters are found
    mocker.patch("codeflare_sdk.ray.cluster.cluster.list_all_clusters", return_value=[])
    mocker.patch(
        "codeflare_sdk.ray.cluster.cluster.get_current_namespace",
        return_value="default",
    )
    df = cf_widgets._fetch_cluster_data(namespace="default")
    assert df.empty

    cf_widgets.view_clusters()
    captured = capsys.readouterr()
    assert f"No clusters found in the default namespace." in captured.out

    # Assert the function returns None
    assert result is None

    test_df = pd.DataFrame(
        {
            "Name": ["test-cluster"],
            "Namespace": ["default"],
            "Num Workers": ["1"],
            "Head GPUs": ["0"],
            "Worker GPUs": ["0"],
            "Head CPU Req~Lim": ["1~1"],
            "Head Memory Req~Lim": ["1Gi~1Gi"],
            "Worker CPU Req~Lim": ["1~1"],
            "Worker Memory Req~Lim": ["1Gi~1Gi"],
            "status": ['<span style="color: green;">Ready ✓</span>'],
        }
    )

    # Mock the _fetch_cluster_data function to return a test DataFrame
    mocker.patch(
        "codeflare_sdk.cluster.widgets._fetch_cluster_data", return_value=test_df
    )

    # Mock the Cluster class and related methods
    mocker.patch("codeflare_sdk.ray.cluster.Cluster")
    mocker.patch("codeflare_sdk.ray.cluster.ClusterConfiguration")

    with patch("ipywidgets.ToggleButtons") as MockToggleButtons, patch(
        "ipywidgets.Button"
    ) as MockButton, patch("ipywidgets.Output") as MockOutput, patch(
        "ipywidgets.HBox"
    ), patch(
        "ipywidgets.VBox"
    ), patch(
        "IPython.display.display"
    ) as mock_display, patch(
        "IPython.display.HTML"
    ), patch(
        "codeflare_sdk.cluster.widgets.Javascript"
    ) as mock_javascript:
        # Create mock widget instances
        mock_toggle = MagicMock()
        mock_delete_button = MagicMock()
        mock_list_jobs_button = MagicMock()
        mock_ray_dashboard_button = MagicMock()
        mock_output = MagicMock()

        # Set the return values for the mocked widgets
        MockToggleButtons.return_value = mock_toggle
        MockButton.side_effect = [
            mock_delete_button,
            mock_list_jobs_button,
            mock_ray_dashboard_button,
        ]
        MockOutput.return_value = mock_output

        # Call the function under test
        cf_widgets.view_clusters()

        # Simulate selecting a cluster
        mock_toggle.value = "test-cluster"
        selection_change = {"new": "test-cluster"}
        cf_widgets._on_cluster_click(
            selection_change, mock_output, "default", mock_toggle
        )

        # Assert that the toggle options are set correctly
        mock_toggle.observe.assert_called()

        # Simulate clicking the list jobs button
        cf_widgets._on_list_jobs_button_click(
            None, mock_toggle, test_df, mock_output, mock_output
        )
        mock_javascript.assert_called_once()

        # Simulate clicking the Ray dashboard button
        cf_widgets._on_ray_dashboard_button_click(
            None, mock_toggle, test_df, mock_output, mock_output
        )
        mock_javascript.call_count = 2

        mocker.patch(
            "kubernetes.client.CustomObjectsApi.delete_namespaced_custom_object",
        )
        mock_response = mocker.MagicMock()
        mock_response.status = 404
        mock_exception = ApiException(http_resp=mock_response)
        mocker.patch(
            "kubernetes.client.CustomObjectsApi.get_namespaced_custom_object",
            side_effect=mock_exception,
        )

        # Simulate clicking the delete button
        cf_widgets._on_delete_button_click(
            None,
            mock_toggle,
            test_df,
            mock_output,
            mock_output,
            mock_delete_button,
            mock_list_jobs_button,
            mock_ray_dashboard_button,
        )
        MockButton.call_count = 3


def test_fetch_cluster_data(mocker):
    # Return empty dataframe when no clusters are found
    mocker.patch("codeflare_sdk.ray.cluster.cluster.list_all_clusters", return_value=[])
    df = cf_widgets._fetch_cluster_data(namespace="default")
    assert df.empty

    # Create mock RayCluster objects
    mock_raycluster1 = MagicMock(spec=RayCluster)
    mock_raycluster1.name = "test-cluster-1"
    mock_raycluster1.namespace = "default"
    mock_raycluster1.num_workers = 1
    mock_raycluster1.head_extended_resources = {"nvidia.com/gpu": "1"}
    mock_raycluster1.worker_extended_resources = {"nvidia.com/gpu": "2"}
    mock_raycluster1.head_cpu_requests = "500m"
    mock_raycluster1.head_cpu_limits = "1000m"
    mock_raycluster1.head_mem_requests = "1Gi"
    mock_raycluster1.head_mem_limits = "2Gi"
    mock_raycluster1.worker_cpu_requests = "1000m"
    mock_raycluster1.worker_cpu_limits = "2000m"
    mock_raycluster1.worker_mem_requests = "2Gi"
    mock_raycluster1.worker_mem_limits = "4Gi"
    mock_raycluster1.status = MagicMock()
    mock_raycluster1.status.name = "READY"
    mock_raycluster1.status = RayClusterStatus.READY

    mock_raycluster2 = MagicMock(spec=RayCluster)
    mock_raycluster2.name = "test-cluster-2"
    mock_raycluster2.namespace = "default"
    mock_raycluster2.num_workers = 2
    mock_raycluster2.head_extended_resources = {}
    mock_raycluster2.worker_extended_resources = {}
    mock_raycluster2.head_cpu_requests = None
    mock_raycluster2.head_cpu_limits = None
    mock_raycluster2.head_mem_requests = None
    mock_raycluster2.head_mem_limits = None
    mock_raycluster2.worker_cpu_requests = None
    mock_raycluster2.worker_cpu_limits = None
    mock_raycluster2.worker_mem_requests = None
    mock_raycluster2.worker_mem_limits = None
    mock_raycluster2.status = MagicMock()
    mock_raycluster2.status.name = "SUSPENDED"
    mock_raycluster2.status = RayClusterStatus.SUSPENDED

    with patch(
        "codeflare_sdk.ray.cluster.cluster.list_all_clusters",
        return_value=[mock_raycluster1, mock_raycluster2],
    ):
        # Call the function under test
        df = cf_widgets._fetch_cluster_data(namespace="default")

    # Expected DataFrame
    expected_data = {
        "Name": ["test-cluster-1", "test-cluster-2"],
        "Namespace": ["default", "default"],
        "Num Workers": [1, 2],
        "Head GPUs": ["nvidia.com/gpu: 1", "0"],
        "Worker GPUs": ["nvidia.com/gpu: 2", "0"],
        "Head CPU Req~Lim": ["500m~1000m", "0~0"],
        "Head Memory Req~Lim": ["1Gi~2Gi", "0~0"],
        "Worker CPU Req~Lim": ["1000m~2000m", "0~0"],
        "Worker Memory Req~Lim": ["2Gi~4Gi", "0~0"],
        "status": [
            '<span style="color: green;">Ready ✓</span>',
            '<span style="color: #007BFF;">Suspended ❄️</span>',
        ],
    }

    expected_df = pd.DataFrame(expected_data)

    # Assert that the DataFrame matches expected
    pd.testing.assert_frame_equal(
        df.reset_index(drop=True), expected_df.reset_index(drop=True)
    )


def test_format_status():
    # Test each possible status
    test_cases = [
        (RayClusterStatus.READY, '<span style="color: green;">Ready ✓</span>'),
        (
            RayClusterStatus.SUSPENDED,
            '<span style="color: #007BFF;">Suspended ❄️</span>',
        ),
        (RayClusterStatus.FAILED, '<span style="color: red;">Failed ✗</span>'),
        (RayClusterStatus.UNHEALTHY, '<span style="color: purple;">Unhealthy</span>'),
        (RayClusterStatus.UNKNOWN, '<span style="color: purple;">Unknown</span>'),
    ]

    for status, expected_output in test_cases:
        assert (
            cf_widgets._format_status(status) == expected_output
        ), f"Failed for status: {status}"

    # Test an unrecognized status
    unrecognized_status = "NotAStatus"
    assert (
        cf_widgets._format_status(unrecognized_status) == "NotAStatus"
    ), "Failed for unrecognized status"


# Make sure to always keep this function last
def test_cleanup():
    os.remove(f"{aw_dir}unit-test-no-kueue.yaml")
    os.remove(f"{aw_dir}unit-test-cluster.yaml")
    os.remove(f"{aw_dir}test.yaml")
    os.remove(f"{aw_dir}raytest2.yaml")
    os.remove(f"{aw_dir}unit-test-cluster-ray.yaml")
    os.remove("tls-cluster-namespace/ca.crt")
    os.remove("tls-cluster-namespace/tls.crt")
    os.remove("tls-cluster-namespace/tls.key")
    os.rmdir("tls-cluster-namespace")

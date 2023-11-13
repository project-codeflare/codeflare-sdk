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

# TODO: replace all instances of torchx_runner

from pathlib import Path
import sys
import filecmp
import os
import re
import uuid

from codeflare_sdk.cluster import cluster

parent = Path(__file__).resolve().parents[1]
aw_dir = os.path.expanduser("~/.codeflare/appwrapper/")
sys.path.append(str(parent) + "/src")

from kubernetes import client, config
from codeflare_sdk.cluster.awload import AWManager
from codeflare_sdk.cluster.cluster import (
    Cluster,
    ClusterConfiguration,
    list_all_clusters,
    list_all_queued,
    _copy_to_ray,
    get_cluster,
    _app_wrapper_status,
    _ray_cluster_status,
    _get_ingress_domain,
)
from codeflare_sdk.cluster.auth import (
    TokenAuthentication,
    Authentication,
    KubeConfigFileAuthentication,
    config_check,
)
from codeflare_sdk.utils.openshift_oauth import (
    create_openshift_oauth_objects,
    delete_openshift_oauth_objects,
)
from codeflare_sdk.utils.pretty_print import (
    print_no_resources_found,
    print_app_wrappers_status,
    print_cluster_status,
    print_clusters,
)
from codeflare_sdk.cluster.model import (
    AppWrapper,
    RayCluster,
    AppWrapperStatus,
    RayClusterStatus,
    CodeFlareClusterStatus,
)
from codeflare_sdk.job.jobs import (
    JobDefinition,
    Job,
    DDPJobDefinition,
    DDPJob,
)
from codeflare_sdk.utils.generate_cert import (
    generate_ca_cert,
    generate_tls_cert,
    export_env,
)

from unit_test_support import (
    createClusterWithConfig,
    createTestDDP,
    createDDPJob_no_cluster,
    createClusterConfig,
    createDDPJob_with_cluster,
)

import codeflare_sdk.utils.kube_api_helpers
from codeflare_sdk.utils.generate_yaml import (
    gen_names,
    is_openshift_cluster,
    read_template,
    enable_local_interactive,
)

import openshift
from openshift.selector import Selector
import ray
from torchx.specs import AppDryRunInfo, AppDef
from torchx.runner import get_runner, Runner
from torchx.schedulers.ray_scheduler import RayJob
from torchx.schedulers.kubernetes_mcad_scheduler import KubernetesMCADJob
import pytest
import yaml
from unittest.mock import MagicMock
from pytest_mock import MockerFixture
from ray.job_submission import JobSubmissionClient

# For mocking openshift client results
fake_res = openshift.Result("fake")


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

        token_auth = TokenAuthentication(token="token", server="server", skip_tls=False)
        assert token_auth.token == "token"
        assert token_auth.server == "server"
        assert token_auth.skip_tls == False
        assert token_auth.ca_cert_path == None

        token_auth = TokenAuthentication(
            token="token", server="server", skip_tls=False, ca_cert_path="path/to/cert"
        )
        assert token_auth.token == "token"
        assert token_auth.server == "server"
        assert token_auth.skip_tls == False
        assert token_auth.ca_cert_path == "path/to/cert"

    except Exception:
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
        ca_cert_path="path/to/cert",
    )
    assert token_auth.login() == ("Logged into testserver:6443")


def test_config_check_no_config_file(mocker):
    mocker.patch("os.path.expanduser", return_value="/mock/home/directory")
    mocker.patch("os.path.isfile", return_value=False)
    mocker.patch("codeflare_sdk.cluster.auth.config_path", None)
    mocker.patch("codeflare_sdk.cluster.auth.api_client", None)

    with pytest.raises(PermissionError) as e:
        config_check()


def test_config_check_with_incluster_config(mocker):
    mocker.patch("os.path.expanduser", return_value="/mock/home/directory")
    mocker.patch("os.path.isfile", return_value=False)
    mocker.patch.dict(os.environ, {"KUBERNETES_PORT": "number"})
    mocker.patch("kubernetes.config.load_incluster_config", side_effect=None)
    mocker.patch("codeflare_sdk.cluster.auth.config_path", None)
    mocker.patch("codeflare_sdk.cluster.auth.api_client", None)

    result = config_check()
    assert result == None


def test_config_check_with_existing_config_file(mocker):
    mocker.patch("os.path.expanduser", return_value="/mock/home/directory")
    mocker.patch("os.path.isfile", return_value=True)
    mocker.patch("kubernetes.config.load_kube_config", side_effect=None)
    mocker.patch("codeflare_sdk.cluster.auth.config_path", None)
    mocker.patch("codeflare_sdk.cluster.auth.api_client", None)

    result = config_check()
    assert result == None


def test_config_check_with_config_path_and_no_api_client(mocker):
    mocker.patch("codeflare_sdk.cluster.auth.config_path", "/mock/config/path")
    mocker.patch("codeflare_sdk.cluster.auth.api_client", None)
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
    assert config.min_cpus == 3 and config.max_cpus == 4
    assert config.min_memory == 5 and config.max_memory == 6
    assert config.num_gpus == 7
    assert config.image == "quay.io/project-codeflare/ray:latest-py39-cu118"
    assert config.template == f"{parent}/src/codeflare_sdk/templates/base-template.yaml"
    assert config.instascale
    assert config.machine_types == ["cpu.small", "gpu.large"]
    assert config.image_pull_secrets == ["unit-test-pull-secret"]
    assert config.dispatch_priority == None
    assert config.mcad == True
    assert config.local_interactive == False


def test_cluster_creation(mocker):
    cluster = createClusterWithConfig(mocker)
    assert cluster.app_wrapper_yaml == f"{aw_dir}unit-test-cluster.yaml"
    assert cluster.app_wrapper_name == "unit-test-cluster"
    assert filecmp.cmp(
        f"{aw_dir}unit-test-cluster.yaml",
        f"{parent}/tests/test-case.yaml",
        shallow=True,
    )


def test_create_app_wrapper_raises_error_with_no_image():
    config = createClusterConfig()
    config.image = ""  # Clear the image to test error handling
    try:
        cluster = Cluster(config)
        cluster.create_app_wrapper()
        assert False, "Expected ValueError when 'image' is not specified."
    except ValueError as error:
        assert (
            str(error) == "Image must be specified in the ClusterConfiguration"
        ), "Error message did not match expected output."


def test_cluster_creation_no_mcad(mocker):
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.get_cluster_custom_object",
        return_value={"spec": {"domain": "apps.cluster.awsroute.org"}},
    )
    config = createClusterConfig()
    config.name = "unit-test-cluster-ray"
    config.mcad = False
    cluster = Cluster(config)
    assert cluster.app_wrapper_yaml == f"{aw_dir}unit-test-cluster-ray.yaml"
    assert cluster.app_wrapper_name == "unit-test-cluster-ray"
    assert filecmp.cmp(
        f"{aw_dir}unit-test-cluster-ray.yaml",
        f"{parent}/tests/test-case-no-mcad.yamls",
        shallow=True,
    )


def test_cluster_creation_priority(mocker):
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_cluster_custom_object",
        return_value={"items": [{"metadata": {"name": "default"}, "value": 10}]},
    )
    config = createClusterConfig()
    config.name = "prio-test-cluster"
    config.dispatch_priority = "default"
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.get_cluster_custom_object",
        return_value={"spec": {"domain": "apps.cluster.awsroute.org"}},
    )
    cluster = Cluster(config)
    assert cluster.app_wrapper_yaml == f"{aw_dir}prio-test-cluster.yaml"
    assert cluster.app_wrapper_name == "prio-test-cluster"
    assert filecmp.cmp(
        f"{aw_dir}prio-test-cluster.yaml",
        f"{parent}/tests/test-case-prio.yaml",
        shallow=True,
    )


def test_default_cluster_creation(mocker):
    mocker.patch(
        "codeflare_sdk.cluster.cluster.get_current_namespace",
        return_value="opendatahub",
    )
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.get_cluster_custom_object",
        return_value={"spec": {"domain": ""}},
    )
    default_config = ClusterConfiguration(
        name="unit-test-default-cluster",
        image="quay.io/project-codeflare/ray:latest-py39-cu118",
    )
    cluster = Cluster(default_config)

    assert cluster.app_wrapper_yaml == f"{aw_dir}unit-test-default-cluster.yaml"
    assert cluster.app_wrapper_name == "unit-test-default-cluster"
    assert cluster.config.namespace == "opendatahub"


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
        assert version == "v1beta1"
        with open(f"{aw_dir}unit-test-cluster.yaml") as f:
            aw = yaml.load(f, Loader=yaml.FullLoader)
        assert body == aw
    elif plural == "rayclusters":
        assert group == "ray.io"
        assert version == "v1alpha1"
        with open(f"{aw_dir}unit-test-cluster-ray.yaml") as f:
            yamls = yaml.load_all(f, Loader=yaml.FullLoader)
            for resource in yamls:
                if resource["kind"] == "RayCluster":
                    assert body == resource
    elif plural == "routes":
        assert group == "route.openshift.io"
        assert version == "v1"
        with open(f"{aw_dir}unit-test-cluster-ray.yaml") as f:
            yamls = yaml.load_all(f, Loader=yaml.FullLoader)
            for resource in yamls:
                if resource["kind"] == "Route":
                    assert body == resource
    else:
        assert 1 == 0


def arg_check_del_effect(group, version, namespace, plural, name, *args):
    assert namespace == "ns"
    assert args == tuple()
    if plural == "appwrappers":
        assert group == "workload.codeflare.dev"
        assert version == "v1beta1"
        assert name == "unit-test-cluster"
    elif plural == "rayclusters":
        assert group == "ray.io"
        assert version == "v1alpha1"
        assert name == "unit-test-cluster-ray"
    elif plural == "routes":
        assert group == "route.openshift.io"
        assert version == "v1"
        assert name == "ray-dashboard-unit-test-cluster-ray"


def test_cluster_up_down(mocker):
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
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
    cluster = cluster = createClusterWithConfig(mocker)
    cluster.up()
    cluster.down()


def test_cluster_up_down_no_mcad(mocker):
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.get_cluster_custom_object",
        return_value={"spec": {"domain": "apps.cluster.awsroute.org"}},
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
    config = createClusterConfig()
    config.name = "unit-test-cluster-ray"
    config.mcad = False
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


"""
def test_get_ingress_domain(self, mocker):
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.get_cluster_custom_object",
        side_effect=arg_check_list_effect,
    )
    domain = _get_ingress_domain(self)
    assert domain == "test"
"""


def aw_status_fields(group, version, namespace, plural, *args):
    assert group == "workload.codeflare.dev"
    assert version == "v1beta1"
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
    assert version == "v1alpha1"
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


def test_delete_openshift_oauth_objects(mocker):
    mocker.patch.object(client.CoreV1Api, "delete_namespaced_service_account")
    mocker.patch.object(client.CoreV1Api, "delete_namespaced_service")
    mocker.patch.object(client.NetworkingV1Api, "delete_namespaced_ingress")
    mocker.patch.object(client.RbacAuthorizationV1Api, "delete_cluster_role_binding")
    delete_openshift_oauth_objects("test-cluster", "test-namespace")

    client.CoreV1Api.delete_namespaced_service_account.assert_called_with(
        name="test-cluster-oauth-proxy", namespace="test-namespace"
    )
    client.CoreV1Api.delete_namespaced_service.assert_called_with(
        name="test-cluster-oauth", namespace="test-namespace"
    )
    client.NetworkingV1Api.delete_namespaced_ingress.assert_called_with(
        name="test-cluster-ingress", namespace="test-namespace"
    )
    client.RbacAuthorizationV1Api.delete_cluster_role_binding.assert_called_with(
        name="test-cluster-rb"
    )


def test_cluster_uris(mocker):
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch(
        "codeflare_sdk.cluster.cluster._get_ingress_domain",
        return_value="apps.cluster.awsroute.org",
    )
    cluster = cluster = createClusterWithConfig(mocker)
    mocker.patch(
        "kubernetes.client.NetworkingV1Api.list_namespaced_ingress",
        return_value=ingress_retrieval(
            port=8265, annotations={"route.openshift.io/termination": "passthrough"}
        ),
    )
    assert (
        cluster.cluster_dashboard_uri()
        == "https://ray-dashboard-unit-test-cluster-ns.apps.cluster.awsroute.org"
    )
    mocker.patch(
        "kubernetes.client.NetworkingV1Api.list_namespaced_ingress",
        return_value=ingress_retrieval(port=8265),
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
        == "Dashboard ingress not available yet, have you run cluster.up()?"
    )


def test_local_client_url(mocker):
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.get_cluster_custom_object",
        return_value={"spec": {"domain": ""}},
    )
    mocker.patch(
        "codeflare_sdk.cluster.cluster._get_ingress_domain",
        return_value="rayclient-unit-test-cluster-localinter-ns.apps.cluster.awsroute.org",
    )
    mocker.patch(
        "codeflare_sdk.cluster.cluster.Cluster.create_app_wrapper",
        return_value="unit-test-cluster-localinter.yaml",
    )

    cluster_config = ClusterConfiguration(
        name="unit-test-cluster-localinter", namespace="ns", local_interactive=True
    )
    cluster = Cluster(cluster_config)
    assert (
        cluster.local_client_url()
        == "ray://rayclient-unit-test-cluster-localinter-ns.apps.cluster.awsroute.org"
    )


def ray_addr(self, *args):
    return self._address


def ingress_retrieval(port, annotations=None):
    if port == 10001:
        serviceName = "client"
    else:
        serviceName = "dashboard"
    mock_ingress = client.V1Ingress(
        metadata=client.V1ObjectMeta(
            name=f"ray-{serviceName}-unit-test-cluster", annotations=annotations
        ),
        spec=client.V1IngressSpec(
            rules=[
                client.V1IngressRule(
                    host=f"ray-{serviceName}-unit-test-cluster-ns.apps.cluster.awsroute.org",
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
    mock_ingress_list = client.V1IngressList(items=[mock_ingress])
    return mock_ingress_list


def test_ray_job_wrapping(mocker):
    cluster = cluster = createClusterWithConfig(mocker)
    cluster.config.image = "quay.io/project-codeflare/ray:latest-py39-cu118"
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
        return_value=ingress_retrieval(8265),
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
        status=AppWrapperStatus.PENDING,
        can_run=False,
        job_state="queue-state",
    )
    aw2 = AppWrapper(
        name="awtest2",
        status=AppWrapperStatus.RUNNING,
        can_run=False,
        job_state="queue-state",
    )
    try:
        print_app_wrappers_status([aw1, aw2])
    except:
        assert 1 == 0
    captured = capsys.readouterr()
    assert captured.out == (
        "╭───────────────────────╮\n"
        "│    🚀 Cluster Queue   │\n"
        "│       Status 🚀       │\n"
        "│ +---------+---------+ │\n"
        "│ | Name    | Status  | │\n"
        "│ +=========+=========+ │\n"
        "│ | awtest1 | pending | │\n"
        "│ |         |         | │\n"
        "│ | awtest2 | running | │\n"
        "│ |         |         | │\n"
        "│ +---------+---------+ │\n"
        "╰───────────────────────╯\n"
    )


def test_ray_details(mocker, capsys):
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.get_cluster_custom_object",
        return_value={"spec": {"domain": ""}},
    )
    ray1 = RayCluster(
        name="raytest1",
        status=RayClusterStatus.READY,
        workers=1,
        worker_mem_min=2,
        worker_mem_max=2,
        worker_cpu=1,
        worker_gpu=0,
        namespace="ns",
        dashboard="fake-uri",
        head_cpus=2,
        head_mem=8,
        head_gpu=0,
    )
    mocker.patch(
        "codeflare_sdk.cluster.cluster.Cluster.status",
        return_value=(False, CodeFlareClusterStatus.UNKNOWN),
    )
    mocker.patch(
        "codeflare_sdk.cluster.cluster.Cluster.cluster_dashboard_uri",
        return_value="",
    )
    cf = Cluster(
        ClusterConfiguration(
            name="raytest2",
            namespace="ns",
            image="quay.io/project-codeflare/ray:latest-py39-cu118",
        )
    )
    captured = capsys.readouterr()
    ray2 = _copy_to_ray(cf)
    details = cf.details()
    assert details == ray2
    assert ray2.name == "raytest2"
    assert ray1.namespace == ray2.namespace
    assert ray1.workers == ray2.workers
    assert ray1.worker_mem_min == ray2.worker_mem_min
    assert ray1.worker_mem_max == ray2.worker_mem_max
    assert ray1.worker_cpu == ray2.worker_cpu
    assert ray1.worker_gpu == ray2.worker_gpu
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
        " │   │  1          │  │  2~2         1           0           │   │ \n"
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
        " │   │  1          │  │  2~2         1           0           │   │ \n"
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
        "│   │  1          │  │  2~2         1           0           │   │\n"
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
                "apiVersion": "ray.io/v1alpha1",
                "kind": "RayCluster",
                "metadata": {
                    "creationTimestamp": "2023-02-22T16:26:07Z",
                    "generation": 1,
                    "labels": {
                        "workload.codeflare.dev/appwrapper": "quicktest",
                        "controller-tools.k8s.io": "1.0",
                        "resourceName": "quicktest",
                        "orderedinstance": "m4.xlarge_g4dn.xlarge",
                    },
                    "managedFields": [
                        {
                            "apiVersion": "ray.io/v1alpha1",
                            "fieldsType": "FieldsV1",
                            "fieldsV1": {
                                "f:metadata": {
                                    "f:labels": {
                                        ".": {},
                                        "f:workload.codeflare.dev/appwrapper": {},
                                        "f:controller-tools.k8s.io": {},
                                        "f:resourceName": {},
                                    },
                                    "f:ownerReferences": {
                                        ".": {},
                                        'k:{"uid":"6334fc1b-471e-4876-8e7b-0b2277679235"}': {},
                                    },
                                },
                                "f:spec": {
                                    ".": {},
                                    "f:autoscalerOptions": {
                                        ".": {},
                                        "f:idleTimeoutSeconds": {},
                                        "f:imagePullPolicy": {},
                                        "f:resources": {
                                            ".": {},
                                            "f:limits": {
                                                ".": {},
                                                "f:cpu": {},
                                                "f:memory": {},
                                            },
                                            "f:requests": {
                                                ".": {},
                                                "f:cpu": {},
                                                "f:memory": {},
                                            },
                                        },
                                        "f:upscalingMode": {},
                                    },
                                    "f:enableInTreeAutoscaling": {},
                                    "f:headGroupSpec": {
                                        ".": {},
                                        "f:rayStartParams": {
                                            ".": {},
                                            "f:block": {},
                                            "f:dashboard-host": {},
                                            "f:num-gpus": {},
                                        },
                                        "f:serviceType": {},
                                        "f:template": {
                                            ".": {},
                                            "f:spec": {".": {}, "f:containers": {}},
                                        },
                                    },
                                    "f:rayVersion": {},
                                    "f:workerGroupSpecs": {},
                                },
                            },
                            "manager": "mcad-controller",
                            "operation": "Update",
                            "time": "2023-02-22T16:26:07Z",
                        },
                        {
                            "apiVersion": "ray.io/v1alpha1",
                            "fieldsType": "FieldsV1",
                            "fieldsV1": {
                                "f:status": {
                                    ".": {},
                                    "f:availableWorkerReplicas": {},
                                    "f:desiredWorkerReplicas": {},
                                    "f:endpoints": {
                                        ".": {},
                                        "f:client": {},
                                        "f:dashboard": {},
                                        "f:gcs": {},
                                    },
                                    "f:lastUpdateTime": {},
                                    "f:maxWorkerReplicas": {},
                                    "f:minWorkerReplicas": {},
                                    "f:state": {},
                                }
                            },
                            "manager": "manager",
                            "operation": "Update",
                            "subresource": "status",
                            "time": "2023-02-22T16:26:16Z",
                        },
                    ],
                    "name": "quicktest",
                    "namespace": "ns",
                    "ownerReferences": [
                        {
                            "apiVersion": "workload.codeflare.dev/v1beta1",
                            "blockOwnerDeletion": True,
                            "controller": True,
                            "kind": "AppWrapper",
                            "name": "quicktest",
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
                                                "nvidia.com/gpu": 0,
                                            },
                                            "requests": {
                                                "cpu": 2,
                                                "memory": "8G",
                                                "nvidia.com/gpu": 0,
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
                            "rayStartParams": {"block": "true", "num-gpus": "0"},
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
                                                    "nvidia.com/gpu": 0,
                                                },
                                                "requests": {
                                                    "cpu": 1,
                                                    "memory": "2G",
                                                    "nvidia.com/gpu": 0,
                                                },
                                            },
                                        }
                                    ],
                                    "initContainers": [
                                        {
                                            "command": [
                                                "sh",
                                                "-c",
                                                "until nslookup $RAY_IP.$(cat /var/run/secrets/kubernetes.io/serviceaccount/namespace).svc.cluster.local; do echo waiting for myservice; sleep 2; done",
                                            ],
                                            "image": "quay.io/project-codeflare/busybox:latest",
                                            "name": "init-myservice",
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
                    "state": "ready",
                },
            }
        ]
    }
    return api_obj


def get_aw_obj(group, version, namespace, plural):
    api_obj1 = {
        "items": [
            {
                "apiVersion": "workload.codeflare.dev/v1beta1",
                "kind": "AppWrapper",
                "metadata": {
                    "annotations": {
                        "kubectl.kubernetes.io/last-applied-configuration": '{"apiVersion":"codeflare.dev/v1beta1","kind":"AppWrapper","metadata":{"annotations":{},"name":"quicktest1","namespace":"ns"},"spec":{"priority":9,"resources":{"GenericItems":[{"custompodresources":[{"limits":{"cpu":2,"memory":"8G","nvidia.com/gpu":0},"replicas":1,"requests":{"cpu":2,"memory":"8G","nvidia.com/gpu":0}},{"limits":{"cpu":1,"memory":"2G","nvidia.com/gpu":0},"replicas":1,"requests":{"cpu":1,"memory":"2G","nvidia.com/gpu":0}}],"generictemplate":{"apiVersion":"ray.io/v1alpha1","kind":"RayCluster","metadata":{"labels":{"appwrapper.codeflare.dev":"quicktest1","controller-tools.k8s.io":"1.0"},"name":"quicktest1","namespace":"ns"},"spec":{"autoscalerOptions":{"idleTimeoutSeconds":60,"imagePullPolicy":"Always","resources":{"limits":{"cpu":"500m","memory":"512Mi"},"requests":{"cpu":"500m","memory":"512Mi"}},"upscalingMode":"Default"},"enableInTreeAutoscaling":false,"headGroupSpec":{"rayStartParams":{"block":"true","dashboard-host":"0.0.0.0","num-gpus":"0"},"serviceType":"ClusterIP","template":{"spec":{"containers":[{"image":"ghcr.io/foundation-model-stack/base:ray2.1.0-py38-gpu-pytorch1.12.0cu116-20221213-193103","imagePullPolicy":"Always","lifecycle":{"preStop":{"exec":{"command":["/bin/sh","-c","ray stop"]}}},"name":"ray-head","ports":[{"containerPort":6379,"name":"gcs"},{"containerPort":8265,"name":"dashboard"},{"containerPort":10001,"name":"client"}],"resources":{"limits":{"cpu":2,"memory":"8G","nvidia.com/gpu":0},"requests":{"cpu":2,"memory":"8G","nvidia.com/gpu":0}}}]}}},"rayVersion":"1.12.0","workerGroupSpecs":[{"groupName":"small-group-quicktest","maxReplicas":1,"minReplicas":1,"rayStartParams":{"block":"true","num-gpus":"0"},"replicas":1,"template":{"metadata":{"annotations":{"key":"value"},"labels":{"key":"value"}},"spec":{"containers":[{"env":[{"name":"MY_POD_IP","valueFrom":{"fieldRef":{"fieldPath":"status.podIP"}}}],"image":"ghcr.io/foundation-model-stack/base:ray2.1.0-py38-gpu-pytorch1.12.0cu116-20221213-193103","lifecycle":{"preStop":{"exec":{"command":["/bin/sh","-c","ray stop"]}}},"name":"machine-learning","resources":{"limits":{"cpu":1,"memory":"2G","nvidia.com/gpu":0},"requests":{"cpu":1,"memory":"2G","nvidia.com/gpu":0}}}],"initContainers":[{"command":["sh","-c","until nslookup $RAY_IP.$(cat /var/run/secrets/kubernetes.io/serviceaccount/namespace).svc.cluster.local; do echo waiting for myservice; sleep 2; done"],"image":"quay.io/project-codeflare/busybox:latest","name":"init-myservice"}]}}}]}},"replicas":1},{"generictemplate":{"apiVersion":"route.openshift.io/v1","kind":"Route","metadata":{"labels":{"odh-ray-cluster-service":"quicktest-head-svc"},"name":"ray-dashboard-quicktest","namespace":"default"},"spec":{"port":{"targetPort":"dashboard"},"to":{"kind":"Service","name":"quicktest-head-svc"}}},"replica":1}],"Items":[]}}}\n'
                    },
                    "creationTimestamp": "2023-02-22T16:26:07Z",
                    "generation": 4,
                    "managedFields": [
                        {
                            "apiVersion": "workload.codeflare.dev/v1beta1",
                            "fieldsType": "FieldsV1",
                            "fieldsV1": {
                                "f:spec": {
                                    "f:resources": {
                                        "f:GenericItems": {},
                                        "f:metadata": {},
                                    },
                                    "f:schedulingSpec": {},
                                    "f:service": {".": {}, "f:spec": {}},
                                },
                                "f:status": {
                                    ".": {},
                                    "f:canrun": {},
                                    "f:conditions": {},
                                    "f:controllerfirsttimestamp": {},
                                    "f:filterignore": {},
                                    "f:queuejobstate": {},
                                    "f:sender": {},
                                    "f:state": {},
                                    "f:systempriority": {},
                                },
                            },
                            "manager": "Go-http-client",
                            "operation": "Update",
                            "time": "2023-02-22T16:26:07Z",
                        },
                        {
                            "apiVersion": "workload.codeflare.dev/v1beta1",
                            "fieldsType": "FieldsV1",
                            "fieldsV1": {
                                "f:metadata": {
                                    "f:annotations": {
                                        ".": {},
                                        "f:kubectl.kubernetes.io/last-applied-configuration": {},
                                    }
                                },
                                "f:spec": {
                                    ".": {},
                                    "f:priority": {},
                                    "f:resources": {".": {}, "f:Items": {}},
                                },
                            },
                            "manager": "kubectl-client-side-apply",
                            "operation": "Update",
                            "time": "2023-02-22T16:26:07Z",
                        },
                    ],
                    "name": "quicktest1",
                    "namespace": "ns",
                    "resourceVersion": "9482384",
                    "uid": "6334fc1b-471e-4876-8e7b-0b2277679235",
                },
                "spec": {
                    "priority": 9,
                    "resources": {
                        "GenericItems": [
                            {
                                "allocated": 0,
                                "custompodresources": [
                                    {
                                        "limits": {
                                            "cpu": "2",
                                            "memory": "8G",
                                            "nvidia.com/gpu": "0",
                                        },
                                        "replicas": 1,
                                        "requests": {
                                            "cpu": "2",
                                            "memory": "8G",
                                            "nvidia.com/gpu": "0",
                                        },
                                    },
                                    {
                                        "limits": {
                                            "cpu": "1",
                                            "memory": "2G",
                                            "nvidia.com/gpu": "0",
                                        },
                                        "replicas": 1,
                                        "requests": {
                                            "cpu": "1",
                                            "memory": "2G",
                                            "nvidia.com/gpu": "0",
                                        },
                                    },
                                ],
                                "generictemplate": {
                                    "apiVersion": "ray.io/v1alpha1",
                                    "kind": "RayCluster",
                                    "metadata": {
                                        "labels": {
                                            "workload.codeflare.dev/appwrapper": "quicktest1",
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
                                                                    "nvidia.com/gpu": 0,
                                                                },
                                                                "requests": {
                                                                    "cpu": 2,
                                                                    "memory": "8G",
                                                                    "nvidia.com/gpu": 0,
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
                                                                        "nvidia.com/gpu": 0,
                                                                    },
                                                                    "requests": {
                                                                        "cpu": 1,
                                                                        "memory": "2G",
                                                                        "nvidia.com/gpu": 0,
                                                                    },
                                                                },
                                                            }
                                                        ],
                                                        "initContainers": [
                                                            {
                                                                "command": [
                                                                    "sh",
                                                                    "-c",
                                                                    "until nslookup $RAY_IP.$(cat /var/run/secrets/kubernetes.io/serviceaccount/namespace).svc.cluster.local; do echo waiting for myservice; sleep 2; done",
                                                                ],
                                                                "image": "quay.io/project-codeflare/busybox:latest",
                                                                "name": "init-myservice",
                                                            }
                                                        ],
                                                    },
                                                },
                                            }
                                        ],
                                    },
                                },
                                "metadata": {},
                                "priority": 0,
                                "priorityslope": 0,
                                "replicas": 1,
                            },
                            {
                                "allocated": 0,
                                "generictemplate": {
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
                                "metadata": {},
                                "priority": 0,
                                "priorityslope": 0,
                            },
                        ],
                        "Items": [],
                        "metadata": {},
                    },
                    "schedulingSpec": {},
                    "service": {"spec": {}},
                },
                "status": {
                    "canrun": True,
                    "conditions": [
                        {
                            "lastTransitionMicroTime": "2023-02-22T16:26:07.559447Z",
                            "lastUpdateMicroTime": "2023-02-22T16:26:07.559447Z",
                            "status": "True",
                            "type": "Init",
                        },
                        {
                            "lastTransitionMicroTime": "2023-02-22T16:26:07.559551Z",
                            "lastUpdateMicroTime": "2023-02-22T16:26:07.559551Z",
                            "reason": "AwaitingHeadOfLine",
                            "status": "True",
                            "type": "Queueing",
                        },
                        {
                            "lastTransitionMicroTime": "2023-02-22T16:26:13.220564Z",
                            "lastUpdateMicroTime": "2023-02-22T16:26:13.220564Z",
                            "reason": "AppWrapperRunnable",
                            "status": "True",
                            "type": "Dispatched",
                        },
                    ],
                    "controllerfirsttimestamp": "2023-02-22T16:26:07.559447Z",
                    "filterignore": True,
                    "queuejobstate": "Dispatched",
                    "sender": "before manageQueueJob - afterEtcdDispatching",
                    "state": "Running",
                    "systempriority": 9,
                },
            },
            {
                "apiVersion": "workload.codeflare.dev/v1beta1",
                "kind": "AppWrapper",
                "metadata": {
                    "annotations": {
                        "kubectl.kubernetes.io/last-applied-configuration": '{"apiVersion":"codeflare.dev/v1beta1","kind":"AppWrapper","metadata":{"annotations":{},"name":"quicktest2","namespace":"ns"},"spec":{"priority":9,"resources":{"GenericItems":[{"custompodresources":[{"limits":{"cpu":2,"memory":"8G","nvidia.com/gpu":0},"replicas":1,"requests":{"cpu":2,"memory":"8G","nvidia.com/gpu":0}},{"limits":{"cpu":1,"memory":"2G","nvidia.com/gpu":0},"replicas":1,"requests":{"cpu":1,"memory":"2G","nvidia.com/gpu":0}}],"generictemplate":{"apiVersion":"ray.io/v1alpha1","kind":"RayCluster","metadata":{"labels":{"appwrapper.codeflare.dev":"quicktest2","controller-tools.k8s.io":"1.0"},"name":"quicktest2","namespace":"ns"},"spec":{"autoscalerOptions":{"idleTimeoutSeconds":60,"imagePullPolicy":"Always","resources":{"limits":{"cpu":"500m","memory":"512Mi"},"requests":{"cpu":"500m","memory":"512Mi"}},"upscalingMode":"Default"},"enableInTreeAutoscaling":false,"headGroupSpec":{"rayStartParams":{"block":"true","dashboard-host":"0.0.0.0","num-gpus":"0"},"serviceType":"ClusterIP","template":{"spec":{"containers":[{"image":"ghcr.io/foundation-model-stack/base:ray2.1.0-py38-gpu-pytorch1.12.0cu116-20221213-193103","imagePullPolicy":"Always","lifecycle":{"preStop":{"exec":{"command":["/bin/sh","-c","ray stop"]}}},"name":"ray-head","ports":[{"containerPort":6379,"name":"gcs"},{"containerPort":8265,"name":"dashboard"},{"containerPort":10001,"name":"client"}],"resources":{"limits":{"cpu":2,"memory":"8G","nvidia.com/gpu":0},"requests":{"cpu":2,"memory":"8G","nvidia.com/gpu":0}}}]}}},"rayVersion":"1.12.0","workerGroupSpecs":[{"groupName":"small-group-quicktest","maxReplicas":1,"minReplicas":1,"rayStartParams":{"block":"true","num-gpus":"0"},"replicas":1,"template":{"metadata":{"annotations":{"key":"value"},"labels":{"key":"value"}},"spec":{"containers":[{"env":[{"name":"MY_POD_IP","valueFrom":{"fieldRef":{"fieldPath":"status.podIP"}}}],"image":"ghcr.io/foundation-model-stack/base:ray2.1.0-py38-gpu-pytorch1.12.0cu116-20221213-193103","lifecycle":{"preStop":{"exec":{"command":["/bin/sh","-c","ray stop"]}}},"name":"machine-learning","resources":{"limits":{"cpu":1,"memory":"2G","nvidia.com/gpu":0},"requests":{"cpu":1,"memory":"2G","nvidia.com/gpu":0}}}],"initContainers":[{"command":["sh","-c","until nslookup $RAY_IP.$(cat /var/run/secrets/kubernetes.io/serviceaccount/namespace).svc.cluster.local; do echo waiting for myservice; sleep 2; done"],"image":"quay.io/project-codeflare/busybox:latest","name":"init-myservice"}]}}}]}},"replicas":1},{"generictemplate":{"apiVersion":"route.openshift.io/v1","kind":"Route","metadata":{"labels":{"odh-ray-cluster-service":"quicktest-head-svc"},"name":"ray-dashboard-quicktest","namespace":"default"},"spec":{"port":{"targetPort":"dashboard"},"to":{"kind":"Service","name":"quicktest-head-svc"}}},"replica":1}],"Items":[]}}}\n'
                    },
                    "creationTimestamp": "2023-02-22T16:26:07Z",
                    "generation": 4,
                    "managedFields": [
                        {
                            "apiVersion": "workload.codeflare.dev/v1beta1",
                            "fieldsType": "FieldsV1",
                            "fieldsV1": {
                                "f:spec": {
                                    "f:resources": {
                                        "f:GenericItems": {},
                                        "f:metadata": {},
                                    },
                                    "f:schedulingSpec": {},
                                    "f:service": {".": {}, "f:spec": {}},
                                },
                                "f:status": {
                                    ".": {},
                                    "f:canrun": {},
                                    "f:conditions": {},
                                    "f:controllerfirsttimestamp": {},
                                    "f:filterignore": {},
                                    "f:queuejobstate": {},
                                    "f:sender": {},
                                    "f:state": {},
                                    "f:systempriority": {},
                                },
                            },
                            "manager": "Go-http-client",
                            "operation": "Update",
                            "time": "2023-02-22T16:26:07Z",
                        },
                        {
                            "apiVersion": "workload.codeflare.dev/v1beta1",
                            "fieldsType": "FieldsV1",
                            "fieldsV1": {
                                "f:metadata": {
                                    "f:annotations": {
                                        ".": {},
                                        "f:kubectl.kubernetes.io/last-applied-configuration": {},
                                    }
                                },
                                "f:spec": {
                                    ".": {},
                                    "f:priority": {},
                                    "f:resources": {".": {}, "f:Items": {}},
                                },
                            },
                            "manager": "kubectl-client-side-apply",
                            "operation": "Update",
                            "time": "2023-02-22T16:26:07Z",
                        },
                    ],
                    "name": "quicktest2",
                    "namespace": "ns",
                    "resourceVersion": "9482384",
                    "uid": "6334fc1b-471e-4876-8e7b-0b2277679235",
                },
                "spec": {
                    "priority": 9,
                    "resources": {
                        "GenericItems": [
                            {
                                "allocated": 0,
                                "custompodresources": [
                                    {
                                        "limits": {
                                            "cpu": "2",
                                            "memory": "8G",
                                            "nvidia.com/gpu": "0",
                                        },
                                        "replicas": 1,
                                        "requests": {
                                            "cpu": "2",
                                            "memory": "8G",
                                            "nvidia.com/gpu": "0",
                                        },
                                    },
                                    {
                                        "limits": {
                                            "cpu": "1",
                                            "memory": "2G",
                                            "nvidia.com/gpu": "0",
                                        },
                                        "replicas": 1,
                                        "requests": {
                                            "cpu": "1",
                                            "memory": "2G",
                                            "nvidia.com/gpu": "0",
                                        },
                                    },
                                ],
                                "generictemplate": {
                                    "apiVersion": "ray.io/v1alpha1",
                                    "kind": "RayCluster",
                                    "metadata": {
                                        "labels": {
                                            "workload.codeflare.dev/appwrapper": "quicktest2",
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
                                                                    "nvidia.com/gpu": 0,
                                                                },
                                                                "requests": {
                                                                    "cpu": 2,
                                                                    "memory": "8G",
                                                                    "nvidia.com/gpu": 0,
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
                                                                        "nvidia.com/gpu": 0,
                                                                    },
                                                                    "requests": {
                                                                        "cpu": 1,
                                                                        "memory": "2G",
                                                                        "nvidia.com/gpu": 0,
                                                                    },
                                                                },
                                                            }
                                                        ],
                                                        "initContainers": [
                                                            {
                                                                "command": [
                                                                    "sh",
                                                                    "-c",
                                                                    "until nslookup $RAY_IP.$(cat /var/run/secrets/kubernetes.io/serviceaccount/namespace).svc.cluster.local; do echo waiting for myservice; sleep 2; done",
                                                                ],
                                                                "image": "quay.io/project-codeflare/busybox:latest",
                                                                "name": "init-myservice",
                                                            }
                                                        ],
                                                    },
                                                },
                                            }
                                        ],
                                    },
                                },
                                "metadata": {},
                                "priority": 0,
                                "priorityslope": 0,
                                "replicas": 1,
                            },
                            {
                                "allocated": 0,
                                "generictemplate": {
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
                                "metadata": {},
                                "priority": 0,
                                "priorityslope": 0,
                            },
                        ],
                        "Items": [],
                        "metadata": {},
                    },
                    "schedulingSpec": {},
                    "service": {"spec": {}},
                },
                "status": {
                    "canrun": True,
                    "conditions": [
                        {
                            "lastTransitionMicroTime": "2023-02-22T16:26:07.559447Z",
                            "lastUpdateMicroTime": "2023-02-22T16:26:07.559447Z",
                            "status": "True",
                            "type": "Init",
                        },
                        {
                            "lastTransitionMicroTime": "2023-02-22T16:26:07.559551Z",
                            "lastUpdateMicroTime": "2023-02-22T16:26:07.559551Z",
                            "reason": "AwaitingHeadOfLine",
                            "status": "True",
                            "type": "Queueing",
                        },
                        {
                            "lastTransitionMicroTime": "2023-02-22T16:26:13.220564Z",
                            "lastUpdateMicroTime": "2023-02-22T16:26:13.220564Z",
                            "reason": "AppWrapperRunnable",
                            "status": "True",
                            "type": "Dispatched",
                        },
                    ],
                    "controllerfirsttimestamp": "2023-02-22T16:26:07.559447Z",
                    "filterignore": True,
                    "queuejobstate": "Dispatched",
                    "sender": "before manageQueueJob - afterEtcdDispatching",
                    "state": "Pending",
                    "systempriority": 9,
                },
            },
        ]
    }
    return api_obj1


def test_get_cluster(mocker):
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.get_cluster_custom_object",
        return_value={"spec": {"domain": ""}},
    )
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.list_namespaced_custom_object",
        side_effect=get_ray_obj,
    )
    cluster = get_cluster("quicktest")
    cluster_config = cluster.config
    assert cluster_config.name == "quicktest" and cluster_config.namespace == "ns"
    assert (
        "m4.xlarge" in cluster_config.machine_types
        and "g4dn.xlarge" in cluster_config.machine_types
    )
    assert cluster_config.min_cpus == 1 and cluster_config.max_cpus == 1
    assert cluster_config.min_memory == 2 and cluster_config.max_memory == 2
    assert cluster_config.num_gpus == 0
    assert cluster_config.instascale
    assert (
        cluster_config.image
        == "ghcr.io/foundation-model-stack/base:ray2.1.0-py38-gpu-pytorch1.12.0cu116-20221213-193103"
    )
    assert cluster_config.num_workers == 1


def test_list_clusters(mocker, capsys):
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
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
        " │   │  1          │  │  2G~2G       1           0           │   │ \n"
        " │   │             │  │                                      │   │ \n"
        " │   ╰─────────────╯  ╰──────────────────────────────────────╯   │ \n"
        " ╰───────────────────────────────────────────────────────────────╯ \n"
    )


def test_list_queue(mocker, capsys):
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
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
        side_effect=get_aw_obj,
    )
    list_all_queued("ns")
    captured = capsys.readouterr()
    assert captured.out == (
        "╭──────────────────────────╮\n"
        "│  🚀 Cluster Queue Status │\n"
        "│            🚀            │\n"
        "│ +------------+---------+ │\n"
        "│ | Name       | Status  | │\n"
        "│ +============+=========+ │\n"
        "│ | quicktest1 | running | │\n"
        "│ |            |         | │\n"
        "│ | quicktest2 | pending | │\n"
        "│ |            |         | │\n"
        "│ +------------+---------+ │\n"
        "╰──────────────────────────╯\n"
    )


def test_cluster_status(mocker):
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.get_cluster_custom_object",
        return_value={"spec": {"domain": ""}},
    )
    fake_aw = AppWrapper(
        "test", AppWrapperStatus.FAILED, can_run=True, job_state="unused"
    )
    fake_ray = RayCluster(
        name="test",
        status=RayClusterStatus.UNKNOWN,
        workers=1,
        worker_mem_min=2,
        worker_mem_max=2,
        worker_cpu=1,
        worker_gpu=0,
        namespace="ns",
        dashboard="fake-uri",
        head_cpus=2,
        head_mem=8,
        head_gpu=0,
    )
    cf = Cluster(
        ClusterConfiguration(
            name="test",
            namespace="ns",
            image="quay.io/project-codeflare/ray:latest-py39-cu118",
        )
    )
    mocker.patch("codeflare_sdk.cluster.cluster._app_wrapper_status", return_value=None)
    mocker.patch("codeflare_sdk.cluster.cluster._ray_cluster_status", return_value=None)
    status, ready = cf.status()
    assert status == CodeFlareClusterStatus.UNKNOWN
    assert ready == False

    mocker.patch(
        "codeflare_sdk.cluster.cluster._app_wrapper_status", return_value=fake_aw
    )
    status, ready = cf.status()
    assert status == CodeFlareClusterStatus.FAILED
    assert ready == False

    fake_aw.status = AppWrapperStatus.DELETED
    status, ready = cf.status()
    assert status == CodeFlareClusterStatus.FAILED
    assert ready == False

    fake_aw.status = AppWrapperStatus.PENDING
    status, ready = cf.status()
    assert status == CodeFlareClusterStatus.QUEUED
    assert ready == False

    fake_aw.status = AppWrapperStatus.COMPLETED
    status, ready = cf.status()
    assert status == CodeFlareClusterStatus.STARTING
    assert ready == False

    fake_aw.status = AppWrapperStatus.RUNNING_HOLD_COMPLETION
    status, ready = cf.status()
    assert status == CodeFlareClusterStatus.STARTING
    assert ready == False

    fake_aw.status = AppWrapperStatus.RUNNING
    status, ready = cf.status()
    assert status == CodeFlareClusterStatus.STARTING
    assert ready == False

    mocker.patch(
        "codeflare_sdk.cluster.cluster._ray_cluster_status", return_value=fake_ray
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
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.get_cluster_custom_object",
        return_value={"spec": {"domain": ""}},
    )
    mocker.patch(
        "kubernetes.client.NetworkingV1Api.list_namespaced_ingress",
        return_value=ingress_retrieval(8265),
    )
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch("codeflare_sdk.cluster.cluster._app_wrapper_status", return_value=None)
    mocker.patch("codeflare_sdk.cluster.cluster._ray_cluster_status", return_value=None)
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
            image="quay.io/project-codeflare/ray:latest-py39-cu118",
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
        "codeflare_sdk.cluster.cluster.Cluster.status",
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


def test_jobdefinition_coverage(mocker):
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.get_cluster_custom_object",
        return_value={"spec": {"domain": ""}},
    )
    abstract = JobDefinition()
    cluster = createClusterWithConfig(mocker)
    abstract._dry_run(cluster)
    abstract.submit(cluster)


def test_job_coverage():
    abstract = Job()
    abstract.status()
    abstract.logs()


def test_DDPJobDefinition_creation():
    ddp = createTestDDP()
    assert ddp.script == "test.py"
    assert ddp.m == None
    assert ddp.script_args == ["test"]
    assert ddp.name == "test"
    assert ddp.cpu == 1
    assert ddp.gpu == 0
    assert ddp.memMB == 1024
    assert ddp.h == None
    assert ddp.j == "2x1"
    assert ddp.env == {"test": "test"}
    assert ddp.max_retries == 0
    assert ddp.mounts == []
    assert ddp.rdzv_port == 29500
    assert ddp.scheduler_args == {"requirements": "test"}


def test_DDPJobDefinition_dry_run(mocker: MockerFixture):
    """
    Test that the dry run method returns the correct type: AppDryRunInfo,
    that the attributes of the returned object are of the correct type,
    and that the values from cluster and job definition are correctly passed.
    """
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch(
        "codeflare_sdk.cluster.cluster.Cluster.cluster_dashboard_uri",
        return_value="",
    )
    mocker.patch.object(Cluster, "job_client")
    ddp = createTestDDP()
    cluster = createClusterWithConfig(mocker)
    ddp_job, _ = ddp._dry_run(cluster)
    assert type(ddp_job) == AppDryRunInfo
    assert ddp_job._fmt is not None
    assert type(ddp_job.request) == RayJob
    assert type(ddp_job._app) == AppDef
    assert type(ddp_job._cfg) == type(dict())
    assert type(ddp_job._scheduler) == type(str())

    assert ddp_job.request.app_id.startswith("test")
    assert ddp_job.request.cluster_name == "unit-test-cluster"
    assert ddp_job.request.requirements == "test"

    assert ddp_job._app.roles[0].resource.cpu == 1
    assert ddp_job._app.roles[0].resource.gpu == 0
    assert ddp_job._app.roles[0].resource.memMB == 1024

    assert ddp_job._cfg["cluster_name"] == "unit-test-cluster"
    assert ddp_job._cfg["requirements"] == "test"

    assert ddp_job._scheduler == "ray"


def test_DDPJobDefinition_dry_run_no_cluster(mocker):
    """
    Test that the dry run method returns the correct type: AppDryRunInfo,
    that the attributes of the returned object are of the correct type,
    and that the values from cluster and job definition are correctly passed.
    """

    mocker.patch(
        "codeflare_sdk.job.jobs.get_current_namespace",
        return_value="opendatahub",
    )

    ddp = createTestDDP()
    ddp.image = "fake-image"
    ddp_job, _ = ddp._dry_run_no_cluster()
    assert type(ddp_job) == AppDryRunInfo
    assert ddp_job._fmt is not None
    assert type(ddp_job.request) == KubernetesMCADJob
    assert type(ddp_job._app) == AppDef
    assert type(ddp_job._cfg) == type(dict())
    assert type(ddp_job._scheduler) == type(str())

    assert (
        ddp_job.request.resource["spec"]["resources"]["GenericItems"][0][
            "generictemplate"
        ]
        .spec.containers[0]
        .image
        == "fake-image"
    )

    assert ddp_job._app.roles[0].resource.cpu == 1
    assert ddp_job._app.roles[0].resource.gpu == 0
    assert ddp_job._app.roles[0].resource.memMB == 1024

    assert ddp_job._cfg["requirements"] == "test"

    assert ddp_job._scheduler == "kubernetes_mcad"


def test_DDPJobDefinition_dry_run_no_resource_args(mocker):
    """
    Test that the dry run correctly gets resources from the cluster object
    when the job definition does not specify resources.
    """
    mocker.patch.object(Cluster, "job_client")
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.get_cluster_custom_object",
        return_value={"spec": {"domain": ""}},
    )
    mocker.patch(
        "codeflare_sdk.cluster.cluster.Cluster.cluster_dashboard_uri",
        return_value="",
    )
    cluster = createClusterWithConfig(mocker)
    ddp = DDPJobDefinition(
        script="test.py",
        m=None,
        script_args=["test"],
        name="test",
        h=None,
        env={"test": "test"},
        max_retries=0,
        mounts=[],
        rdzv_port=29500,
        scheduler_args={"requirements": "test"},
    )
    ddp_job, _ = ddp._dry_run(cluster)

    assert ddp_job._app.roles[0].resource.cpu == cluster.config.max_cpus
    assert ddp_job._app.roles[0].resource.gpu == cluster.config.num_gpus
    assert ddp_job._app.roles[0].resource.memMB == cluster.config.max_memory * 1024
    assert (
        parse_j(ddp_job._app.roles[0].args[1])
        == f"{cluster.config.num_workers}x{cluster.config.num_gpus}"
    )


def test_DDPJobDefinition_dry_run_no_cluster_no_resource_args(mocker):
    """
    Test that the dry run method returns the correct type: AppDryRunInfo,
    that the attributes of the returned object are of the correct type,
    and that the values from cluster and job definition are correctly passed.
    """

    mocker.patch(
        "codeflare_sdk.job.jobs.get_current_namespace",
        return_value="opendatahub",
    )

    ddp = createTestDDP()
    try:
        ddp._dry_run_no_cluster()
        assert 0 == 1
    except ValueError as e:
        assert str(e) == "Job definition missing arg: image"
    ddp.image = "fake-image"
    ddp.name = None
    try:
        ddp._dry_run_no_cluster()
        assert 0 == 1
    except ValueError as e:
        assert str(e) == "Job definition missing arg: name"
    ddp.name = "fake"
    ddp.cpu = None
    try:
        ddp._dry_run_no_cluster()
        assert 0 == 1
    except ValueError as e:
        assert str(e) == "Job definition missing arg: cpu (# cpus per worker)"
    ddp.cpu = 1
    ddp.gpu = None
    try:
        ddp._dry_run_no_cluster()
        assert 0 == 1
    except ValueError as e:
        assert str(e) == "Job definition missing arg: gpu (# gpus per worker)"
    ddp.gpu = 1
    ddp.memMB = None
    try:
        ddp._dry_run_no_cluster()
        assert 0 == 1
    except ValueError as e:
        assert str(e) == "Job definition missing arg: memMB (memory in MB)"
    ddp.memMB = 1
    ddp.j = None
    try:
        ddp._dry_run_no_cluster()
        assert 0 == 1
    except ValueError as e:
        assert str(e) == "Job definition missing arg: j (`workers`x`procs`)"


def test_DDPJobDefinition_submit(mocker: MockerFixture):
    """
    Tests that the submit method returns the correct type: DDPJob
    And that the attributes of the returned object are of the correct type
    """
    mock_schedule = MagicMock()
    mocker.patch.object(Runner, "schedule", mock_schedule)
    mock_schedule.return_value = "fake-dashboard-url"
    mocker.patch.object(Cluster, "job_client")
    ddp_def = createTestDDP()
    cluster = createClusterWithConfig(mocker)
    mocker.patch(
        "codeflare_sdk.job.jobs.get_current_namespace",
        side_effect="opendatahub",
    )
    mocker.patch.object(
        Cluster, "cluster_dashboard_uri", return_value="fake-dashboard-url"
    )
    ddp_job = ddp_def.submit(cluster)
    assert type(ddp_job) == DDPJob
    assert type(ddp_job.job_definition) == DDPJobDefinition
    assert type(ddp_job.cluster) == Cluster
    assert type(ddp_job._app_handle) == str
    assert ddp_job._app_handle == "fake-dashboard-url"

    ddp_def.image = "fake-image"
    ddp_job = ddp_def.submit()
    assert type(ddp_job) == DDPJob
    assert type(ddp_job.job_definition) == DDPJobDefinition
    assert ddp_job.cluster == None
    assert type(ddp_job._app_handle) == str
    assert ddp_job._app_handle == "fake-dashboard-url"


def test_DDPJob_creation(mocker: MockerFixture):
    mocker.patch.object(Cluster, "job_client")
    mock_schedule = MagicMock()
    mocker.patch.object(Runner, "schedule", mock_schedule)
    mocker.patch.object(
        Cluster, "cluster_dashboard_uri", return_value="fake-dashboard-url"
    )
    ddp_def = createTestDDP()
    cluster = createClusterWithConfig(mocker)
    mock_schedule.return_value = "fake-dashboard-url"
    ddp_job = createDDPJob_with_cluster(mocker, ddp_def, cluster)
    assert type(ddp_job) == DDPJob
    assert type(ddp_job.job_definition) == DDPJobDefinition
    assert type(ddp_job.cluster) == Cluster
    assert type(ddp_job._app_handle) == str
    assert ddp_job._app_handle == "fake-dashboard-url"
    _, args, kwargs = mock_schedule.mock_calls[0]
    assert type(args[0]) == AppDryRunInfo
    job_info = args[0]
    assert type(job_info.request) == RayJob
    assert type(job_info._app) == AppDef
    assert type(job_info._cfg) == type(dict())
    assert type(job_info._scheduler) == type(str())


def test_DDPJob_creation_no_cluster(mocker: MockerFixture):
    ddp_def = createTestDDP()
    ddp_def.image = "fake-image"
    mocker.patch(
        "codeflare_sdk.job.jobs.get_current_namespace",
        side_effect="opendatahub",
    )
    mock_schedule = MagicMock()
    mocker.patch.object(Runner, "schedule", mock_schedule)
    mock_schedule.return_value = "fake-app-handle"
    ddp_job = createDDPJob_no_cluster(ddp_def, None)
    assert type(ddp_job) == DDPJob
    assert type(ddp_job.job_definition) == DDPJobDefinition
    assert ddp_job.cluster == None
    assert type(ddp_job._app_handle) == str
    assert ddp_job._app_handle == "fake-app-handle"
    _, args, kwargs = mock_schedule.mock_calls[0]
    assert type(args[0]) == AppDryRunInfo
    job_info = args[0]
    assert type(job_info.request) == KubernetesMCADJob
    assert type(job_info._app) == AppDef
    assert type(job_info._cfg) == type(dict())
    assert type(job_info._scheduler) == type(str())


def test_DDPJob_status(mocker: MockerFixture):
    # Setup the neccesary mock patches
    mock_status = MagicMock()
    mocker.patch.object(Runner, "status", mock_status)
    test_DDPJob_creation(mocker)
    ddp_def = createTestDDP()
    cluster = createClusterWithConfig(mocker)
    ddp_job = createDDPJob_with_cluster(mocker, ddp_def, cluster)
    mock_status.return_value = "fake-status"
    assert ddp_job.status() == "fake-status"
    _, args, kwargs = mock_status.mock_calls[0]
    assert args[0] == "fake-dashboard-url"


def test_DDPJob_logs(mocker: MockerFixture):
    mock_log = MagicMock()
    mocker.patch.object(Runner, "log_lines", mock_log)
    # Setup the neccesary mock patches
    test_DDPJob_creation(mocker)
    ddp_def = createTestDDP()
    cluster = createClusterWithConfig(mocker)
    ddp_job = createDDPJob_with_cluster(mocker, ddp_def, cluster)
    mock_log.return_value = "fake-logs"
    assert ddp_job.logs() == "fake-logs"
    _, args, kwargs = mock_log.mock_calls[0]
    assert args[0] == "fake-dashboard-url"


def arg_check_side_effect(*args):
    assert args[0] == "fake-app-handle"


def test_DDPJob_cancel(mocker: MockerFixture):
    mock_cancel = MagicMock()
    mocker.patch.object(Runner, "cancel", mock_cancel)
    # Setup the neccesary mock patches
    test_DDPJob_creation_no_cluster(mocker)
    ddp_def = createTestDDP()
    ddp_def.image = "fake-image"
    ddp_job = createDDPJob_no_cluster(ddp_def, None)
    mocker.patch(
        "openshift.get_project_name",
        return_value="opendatahub",
    )
    mock_cancel.side_effect = arg_check_side_effect
    ddp_job.cancel()


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


def test_AWManager_creation():
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
    assert version == "v1beta1"
    assert namespace == "ns"
    assert plural == "appwrappers"
    with open(f"{aw_dir}test.yaml") as f:
        aw = yaml.load(f, Loader=yaml.FullLoader)
    assert body == aw
    assert args == tuple()


def arg_check_aw_del_effect(group, version, namespace, plural, name, *args):
    assert group == "workload.codeflare.dev"
    assert version == "v1beta1"
    assert namespace == "ns"
    assert plural == "appwrappers"
    assert name == "test"
    assert args == tuple()


def test_AWManager_submit_remove(mocker, capsys):
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
    test the function codeflare_sdk.utils.generate_ca_cert generates the correct outputs
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


def test_is_openshift_cluster(mocker):
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch.object(
        client.CustomObjectsApi,
        "get_cluster_custom_object",
        side_effect=client.ApiException(status=404),
    )
    assert is_openshift_cluster() == False
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.get_cluster_custom_object",
        return_value={"spec": {"domain": ""}},
    )
    assert is_openshift_cluster() == True


def test_generate_tls_cert(mocker):
    """
    test the function codeflare_sdk.utils.generate_ca_cert generates the correct outputs
    """
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
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
    test the function codeflare_sdk.utils.export_ev generates the correct outputs
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


def test_enable_local_interactive(mocker):
    template = f"{parent}/src/codeflare_sdk/templates/base-template.yaml"
    user_yaml = read_template(template)
    aw_spec = user_yaml.get("spec", None)
    cluster_name = "test-enable-local"
    namespace = "default"
    ingress_domain = "mytest.domain"
    mocker.patch(
        "codeflare_sdk.utils.generate_yaml.is_openshift_cluster", return_value=False
    )
    volume_mounts = [
        {"name": "ca-vol", "mountPath": "/home/ray/workspace/ca", "readOnly": True},
        {
            "name": "server-cert",
            "mountPath": "/home/ray/workspace/tls",
            "readOnly": False,
        },
    ]
    volumes = [
        {
            "name": "ca-vol",
            "secret": {"secretName": f"ca-secret-{cluster_name}"},
            "optional": False,
        },
        {"name": "server-cert", "emptyDir": {}},
    ]
    tls_env = [
        {"name": "RAY_USE_TLS", "value": "1"},
        {"name": "RAY_TLS_SERVER_CERT", "value": "/home/ray/workspace/tls/server.crt"},
        {"name": "RAY_TLS_SERVER_KEY", "value": "/home/ray/workspace/tls/server.key"},
        {"name": "RAY_TLS_CA_CERT", "value": "/home/ray/workspace/tls/ca.crt"},
    ]
    assert aw_spec != None
    enable_local_interactive(aw_spec, cluster_name, namespace, ingress_domain)
    head_group_spec = aw_spec["resources"]["GenericItems"][0]["generictemplate"][
        "spec"
    ]["headGroupSpec"]
    worker_group_spec = aw_spec["resources"]["GenericItems"][0]["generictemplate"][
        "spec"
    ]["workerGroupSpecs"]
    ca_secret = aw_spec["resources"]["GenericItems"][3]["generictemplate"]
    # At a minimal, make sure the following items are presented in the appwrapper spec.resources.
    # 1. headgroup has the initContainers command to generated TLS cert from the mounted CA cert.
    #    Note: In this particular command, the DNS.5 in [alt_name] must match the exposed local_client_url: rayclient-{cluster_name}.{namespace}.{ingress_domain}
    assert (
        head_group_spec["template"]["spec"]["initContainers"][0]["command"][2]
        == f"cd /home/ray/workspace/tls && openssl req -nodes -newkey rsa:2048 -keyout server.key -out server.csr -subj '/CN=ray-head' && printf \"authorityKeyIdentifier=keyid,issuer\\nbasicConstraints=CA:FALSE\\nsubjectAltName = @alt_names\\n[alt_names]\\nDNS.1 = 127.0.0.1\\nDNS.2 = localhost\\nDNS.3 = ${{FQ_RAY_IP}}\\nDNS.4 = $(awk 'END{{print $1}}' /etc/hosts)\\nDNS.5 = rayclient-{cluster_name}-$(cat /var/run/secrets/kubernetes.io/serviceaccount/namespace).{ingress_domain}\">./domain.ext && cp /home/ray/workspace/ca/* . && openssl x509 -req -CA ca.crt -CAkey ca.key -in server.csr -out server.crt -days 365 -CAcreateserial -extfile domain.ext"
    )
    assert (
        head_group_spec["template"]["spec"]["initContainers"][0]["volumeMounts"]
        == volume_mounts
    )
    assert head_group_spec["template"]["spec"]["volumes"] == volumes

    # 2. workerGrooupSpec has the initContainers command to generated TLS cert from the mounted CA cert.
    assert (
        worker_group_spec[0]["template"]["spec"]["initContainers"][1]["command"][2]
        == "cd /home/ray/workspace/tls && openssl req -nodes -newkey rsa:2048 -keyout server.key -out server.csr -subj '/CN=ray-head' && printf \"authorityKeyIdentifier=keyid,issuer\\nbasicConstraints=CA:FALSE\\nsubjectAltName = @alt_names\\n[alt_names]\\nDNS.1 = 127.0.0.1\\nDNS.2 = localhost\\nDNS.3 = ${FQ_RAY_IP}\\nDNS.4 = $(awk 'END{print $1}' /etc/hosts)\">./domain.ext && cp /home/ray/workspace/ca/* . && openssl x509 -req -CA ca.crt -CAkey ca.key -in server.csr -out server.crt -days 365 -CAcreateserial -extfile domain.ext"
    )
    assert (
        worker_group_spec[0]["template"]["spec"]["initContainers"][1]["volumeMounts"]
        == volume_mounts
    )
    assert worker_group_spec[0]["template"]["spec"]["volumes"] == volumes

    # 3. Required Envs to enable TLS encryption between head and workers
    for i in range(len(tls_env)):
        assert (
            head_group_spec["template"]["spec"]["containers"][0]["env"][i + 1]["name"]
            == tls_env[i]["name"]
        )
        assert (
            head_group_spec["template"]["spec"]["containers"][0]["env"][i + 1]["value"]
            == tls_env[i]["value"]
        )
        assert (
            worker_group_spec[0]["template"]["spec"]["containers"][0]["env"][i + 1][
                "name"
            ]
            == tls_env[i]["name"]
        )
        assert (
            worker_group_spec[0]["template"]["spec"]["containers"][0]["env"][i + 1][
                "value"
            ]
            == tls_env[i]["value"]
        )

    # 4. Secret with ca.crt and ca.key
    assert ca_secret["kind"] == "Secret"
    assert ca_secret["data"]["ca.crt"] != None
    assert ca_secret["data"]["ca.key"] != None
    assert ca_secret["metadata"]["name"] == f"ca-secret-{cluster_name}"
    assert ca_secret["metadata"]["namespace"] == namespace

    # 5. Rayclient ingress - Kind
    rayclient_ingress = aw_spec["resources"]["GenericItems"][2]["generictemplate"]
    paths = [
        {
            "backend": {
                "service": {
                    "name": f"{cluster_name}-head-svc",
                    "port": {"number": 10001},
                }
            },
            "path": "",
            "pathType": "ImplementationSpecific",
        }
    ]

    assert rayclient_ingress["kind"] == "Ingress"
    assert rayclient_ingress["metadata"]["namespace"] == namespace
    assert rayclient_ingress["metadata"]["annotations"] == {
        "nginx.ingress.kubernetes.io/rewrite-target": "/",
        "nginx.ingress.kubernetes.io/ssl-redirect": "true",
        "nginx.ingress.kubernetes.io/ssl-passthrough": "true",
    }
    assert rayclient_ingress["metadata"]["name"] == f"rayclient-{cluster_name}"
    assert rayclient_ingress["spec"]["rules"][0] == {
        "host": f"rayclient-{cluster_name}-{namespace}.{ingress_domain}",
        "http": {"paths": paths},
    }
    # 5.1 Rayclient ingress - OCP
    user_yaml = read_template(template)
    aw_spec = user_yaml.get("spec", None)
    cluster_name = "test-ocp-enable-local"
    namespace = "default"
    ocp_cluster_domain = {"spec": {"domain": "mytest.ocp.domain"}}
    ingress_domain = ocp_cluster_domain["spec"]["domain"]
    mocker.patch(
        "codeflare_sdk.utils.generate_yaml.is_openshift_cluster", return_value=True
    )
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.get_cluster_custom_object",
        return_value=ocp_cluster_domain,
    )
    paths = [
        {
            "backend": {
                "service": {
                    "name": f"{cluster_name}-head-svc",
                    "port": {"number": 10001},
                }
            },
            "path": "",
            "pathType": "ImplementationSpecific",
        }
    ]
    enable_local_interactive(aw_spec, cluster_name, namespace, ingress_domain)
    rayclient_ocp_ingress = aw_spec["resources"]["GenericItems"][2]["generictemplate"]
    assert rayclient_ocp_ingress["kind"] == "Ingress"
    assert rayclient_ocp_ingress["metadata"]["annotations"] == {
        "nginx.ingress.kubernetes.io/rewrite-target": "/",
        "nginx.ingress.kubernetes.io/ssl-redirect": "true",
        "route.openshift.io/termination": "passthrough",
    }
    assert rayclient_ocp_ingress["metadata"]["name"] == f"rayclient-{cluster_name}"
    assert rayclient_ocp_ingress["metadata"]["namespace"] == namespace
    assert rayclient_ocp_ingress["spec"]["ingressClassName"] == "openshift-default"
    assert rayclient_ocp_ingress["spec"]["rules"][0] == {
        "host": f"rayclient-{cluster_name}-{namespace}.{ingress_domain}",
        "http": {"paths": paths},
    }


def test_create_openshift_oauth(mocker: MockerFixture):
    create_namespaced_service_account = MagicMock()
    create_cluster_role_binding = MagicMock()
    create_namespaced_service = MagicMock()
    create_namespaced_ingress = MagicMock()
    mocker.patch.object(
        client.CoreV1Api,
        "create_namespaced_service_account",
        create_namespaced_service_account,
    )
    mocker.patch.object(
        client.RbacAuthorizationV1Api,
        "create_cluster_role_binding",
        create_cluster_role_binding,
    )
    mocker.patch.object(
        client.CoreV1Api, "create_namespaced_service", create_namespaced_service
    )
    mocker.patch.object(
        client.NetworkingV1Api, "create_namespaced_ingress", create_namespaced_ingress
    )
    mocker.patch(
        "codeflare_sdk.utils.openshift_oauth._get_api_host", return_value="foo.com"
    )
    create_openshift_oauth_objects("foo", "bar")
    create_ns_sa_args = create_namespaced_service_account.call_args
    create_crb_args = create_cluster_role_binding.call_args
    create_ns_serv_args = create_namespaced_service.call_args
    create_ns_ingress_args = create_namespaced_ingress.call_args
    assert (
        create_ns_sa_args.kwargs["namespace"] == create_ns_serv_args.kwargs["namespace"]
    )
    assert (
        create_ns_serv_args.kwargs["namespace"]
        == create_ns_ingress_args.kwargs["namespace"]
    )
    assert isinstance(create_ns_sa_args.kwargs["body"], client.V1ServiceAccount)
    assert isinstance(create_crb_args.kwargs["body"], client.V1ClusterRoleBinding)
    assert isinstance(create_ns_serv_args.kwargs["body"], client.V1Service)
    assert isinstance(create_ns_ingress_args.kwargs["body"], client.V1Ingress)
    assert (
        create_ns_serv_args.kwargs["body"].spec.ports[0].name
        == create_ns_ingress_args.kwargs["body"]
        .spec.rules[0]
        .http.paths[0]
        .backend.service.port.name
    )


def test_replace_openshift_oauth(mocker: MockerFixture):
    # not_found_exception = client.ApiException(reason="Conflict")
    create_namespaced_service_account = MagicMock(
        side_effect=client.ApiException(reason="Conflict")
    )
    create_cluster_role_binding = MagicMock(
        side_effect=client.ApiException(reason="Conflict")
    )
    create_namespaced_service = MagicMock(
        side_effect=client.ApiException(reason="Conflict")
    )
    create_namespaced_ingress = MagicMock(
        side_effect=client.ApiException(reason="Conflict")
    )
    mocker.patch.object(
        client.CoreV1Api,
        "create_namespaced_service_account",
        create_namespaced_service_account,
    )
    mocker.patch.object(
        client.RbacAuthorizationV1Api,
        "create_cluster_role_binding",
        create_cluster_role_binding,
    )
    mocker.patch.object(
        client.CoreV1Api, "create_namespaced_service", create_namespaced_service
    )
    mocker.patch.object(
        client.NetworkingV1Api, "create_namespaced_ingress", create_namespaced_ingress
    )
    mocker.patch(
        "codeflare_sdk.utils.openshift_oauth._get_api_host", return_value="foo.com"
    )
    replace_namespaced_service_account = MagicMock()
    replace_cluster_role_binding = MagicMock()
    replace_namespaced_service = MagicMock()
    replace_namespaced_ingress = MagicMock()
    mocker.patch.object(
        client.CoreV1Api,
        "replace_namespaced_service_account",
        replace_namespaced_service_account,
    )
    mocker.patch.object(
        client.RbacAuthorizationV1Api,
        "replace_cluster_role_binding",
        replace_cluster_role_binding,
    )
    mocker.patch.object(
        client.CoreV1Api, "replace_namespaced_service", replace_namespaced_service
    )
    mocker.patch.object(
        client.NetworkingV1Api, "replace_namespaced_ingress", replace_namespaced_ingress
    )
    create_openshift_oauth_objects("foo", "bar")
    replace_namespaced_service_account.assert_called_once()
    replace_cluster_role_binding.assert_called_once()
    replace_namespaced_service.assert_called_once()
    replace_namespaced_ingress.assert_called_once()


def test_gen_app_wrapper_with_oauth(mocker: MockerFixture):
    mocker.patch(
        "codeflare_sdk.utils.generate_yaml._get_api_host", return_value="foo.com"
    )
    mocker.patch(
        "codeflare_sdk.cluster.cluster.get_current_namespace",
        return_value="opendatahub",
    )
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.get_cluster_custom_object",
        return_value={"spec": {"domain": ""}},
    )
    write_user_appwrapper = MagicMock()
    mocker.patch(
        "codeflare_sdk.utils.generate_yaml.write_user_appwrapper", write_user_appwrapper
    )
    Cluster(
        ClusterConfiguration(
            "test_cluster",
            openshift_oauth=True,
            image="quay.io/project-codeflare/ray:latest-py39-cu118",
        )
    )
    user_yaml = write_user_appwrapper.call_args.args[0]
    assert any(
        container["name"] == "oauth-proxy"
        for container in user_yaml["spec"]["resources"]["GenericItems"][0][
            "generictemplate"
        ]["spec"]["headGroupSpec"]["template"]["spec"]["containers"]
    )


# Make sure to always keep this function last
def test_cleanup():
    os.remove(f"{aw_dir}unit-test-cluster.yaml")
    os.remove(f"{aw_dir}prio-test-cluster.yaml")
    os.remove(f"{aw_dir}unit-test-default-cluster.yaml")
    os.remove(f"{aw_dir}test.yaml")
    os.remove(f"{aw_dir}raytest2.yaml")
    os.remove(f"{aw_dir}quicktest.yaml")
    os.remove("tls-cluster-namespace/ca.crt")
    os.remove("tls-cluster-namespace/tls.crt")
    os.remove("tls-cluster-namespace/tls.key")
    os.rmdir("tls-cluster-namespace")

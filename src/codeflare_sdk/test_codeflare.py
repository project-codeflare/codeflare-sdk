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

"""Tests for the Codeflare single entrypoint."""

import inspect
import logging
import pytest
from typing import get_overloads, get_type_hints
from unittest.mock import MagicMock
from kube_authkit import AuthConfig

from codeflare_sdk.ray.cluster.config import ClusterConfiguration
from codeflare_sdk.common.utils.unit_test_support import (
    create_rayjob_resource,
    create_rayjob_list_response,
    get_ray_obj,
)


@pytest.fixture(autouse=True)
def restore_facade_state():
    """Keep facade authentication and logging state from leaking into other tests."""
    from codeflare_sdk.common.kubernetes_cluster import auth

    original_client, original_path = auth.api_client, auth.config_path
    logger = logging.getLogger("codeflare_sdk")
    original_level = logger.level
    yield
    auth.api_client, auth.config_path = original_client, original_path
    logger.setLevel(original_level)


class TestSDKConfig:
    def test_default_config(self):
        from codeflare_sdk.codeflare import SDKConfig

        config = SDKConfig()
        assert config.namespace is None
        assert config.log_level == "WARNING"
        assert isinstance(config.auth, AuthConfig)

    def test_custom_config(self):
        from codeflare_sdk.codeflare import SDKConfig

        auth = AuthConfig(method="kubeconfig")
        config = SDKConfig(
            auth=auth,
            namespace="my-ns",
            log_level="DEBUG",
        )
        assert config.namespace == "my-ns"
        assert config.log_level == "DEBUG"
        assert config.auth is auth

    def test_invalid_log_level_raises(self):
        from codeflare_sdk.codeflare import SDKConfig

        with pytest.raises(ValueError, match="log_level"):
            SDKConfig(log_level="INVALID")


class TestCodeflare:
    def test_default_init(self, mocker):
        """Codeflare() with no args uses auto-detection."""
        from codeflare_sdk.codeflare import Codeflare, SDKConfig

        mock_get_k8s_client = mocker.patch("codeflare_sdk.codeflare.get_k8s_client")
        mock_client = MagicMock()
        mock_get_k8s_client.return_value = mock_client

        mock_set_api = mocker.patch("codeflare_sdk.codeflare.set_api_client")

        cf = Codeflare()

        assert isinstance(cf.config, SDKConfig)
        mock_get_k8s_client.assert_called_once_with(config=cf.config.auth)
        mock_set_api.assert_called_once_with(mock_client)
        assert cf._client is mock_client

    def test_custom_config_init(self, mocker):
        """Codeflare with explicit SDKConfig."""
        from codeflare_sdk.codeflare import Codeflare, SDKConfig

        mock_get_k8s_client = mocker.patch("codeflare_sdk.codeflare.get_k8s_client")
        mock_client = MagicMock()
        mock_get_k8s_client.return_value = mock_client
        mocker.patch("codeflare_sdk.codeflare.set_api_client")

        auth = AuthConfig(method="kubeconfig")
        config = SDKConfig(auth=auth, namespace="test-ns", log_level="DEBUG")
        cf = Codeflare(config=config)

        assert cf.config.namespace == "test-ns"
        assert cf.config.log_level == "DEBUG"
        mock_get_k8s_client.assert_called_once_with(config=auth)

    def test_sets_log_level(self, mocker):
        """Codeflare sets the SDK logger level."""
        from codeflare_sdk.codeflare import Codeflare, SDKConfig

        mocker.patch("codeflare_sdk.codeflare.get_k8s_client")
        mocker.patch("codeflare_sdk.codeflare.set_api_client")

        config = SDKConfig(log_level="DEBUG")
        Codeflare(config=config)

        logger = logging.getLogger("codeflare_sdk")
        assert logger.level == logging.DEBUG

    def test_has_cluster_handler(self, mocker):
        """Codeflare exposes a clusters handler."""
        from codeflare_sdk.codeflare import Codeflare, ClusterHandler

        mocker.patch("codeflare_sdk.codeflare.get_k8s_client")
        mocker.patch("codeflare_sdk.codeflare.set_api_client")

        cf = Codeflare()
        assert isinstance(cf.clusters, ClusterHandler)

    def test_has_job_handler(self, mocker):
        """Codeflare exposes a jobs handler."""
        from codeflare_sdk.codeflare import Codeflare, JobHandler

        mocker.patch("codeflare_sdk.codeflare.get_k8s_client")
        mocker.patch("codeflare_sdk.codeflare.set_api_client")

        cf = Codeflare()
        assert isinstance(cf.jobs, JobHandler)

    def test_auth_failure_propagates(self, mocker):
        """Auth failure in kube-authkit propagates to caller."""
        from codeflare_sdk.codeflare import Codeflare
        from kube_authkit.exceptions import AuthenticationError

        mocker.patch(
            "codeflare_sdk.codeflare.get_k8s_client",
            side_effect=AuthenticationError("bad token"),
        )

        with pytest.raises(AuthenticationError, match="bad token"):
            Codeflare()


class TestClusterHandler:
    @pytest.fixture
    def cf(self, mocker):
        """Create a Codeflare instance with mocked auth."""
        from codeflare_sdk.codeflare import Codeflare, SDKConfig

        mocker.patch("codeflare_sdk.codeflare.get_k8s_client")
        mocker.patch("codeflare_sdk.codeflare.set_api_client")
        return Codeflare(config=SDKConfig(namespace="default-ns"))

    def test_create_cluster(self, cf, mocker):
        """create() binds the given ClusterConfiguration to this client."""
        mock_cluster_cls = mocker.patch("codeflare_sdk.codeflare.Cluster")
        config = ClusterConfiguration(name="my-cluster", num_workers=3)

        result = cf.clusters.create(config)

        passed = mock_cluster_cls.call_args.args[0]
        assert passed.name == "my-cluster"
        assert passed.num_workers == 3
        assert passed.namespace == "default-ns"
        assert mock_cluster_cls.call_args.kwargs == {"api_client": cf.client}
        assert result is mock_cluster_cls.return_value

    def test_create_cluster_keeps_config_namespace(self, cf, mocker):
        """A namespace already on the config wins over SDKConfig."""
        mock_cluster_cls = mocker.patch("codeflare_sdk.codeflare.Cluster")
        config = ClusterConfiguration(name="my-cluster", namespace="config-ns")

        cf.clusters.create(config)

        assert mock_cluster_cls.call_args.args[0].namespace == "config-ns"

    def test_create_cluster_override_namespace(self, cf, mocker):
        """The namespace argument overrides both the config and SDKConfig."""
        mock_cluster_cls = mocker.patch("codeflare_sdk.codeflare.Cluster")
        config = ClusterConfiguration(name="my-cluster", namespace="config-ns")

        cf.clusters.create(config, namespace="other-ns")

        assert mock_cluster_cls.call_args.args[0].namespace == "other-ns"

    def test_create_does_not_mutate_the_callers_config(self, cf, mocker):
        """Injecting the namespace must not reach back into the caller's object."""
        mock_cluster_cls = mocker.patch("codeflare_sdk.codeflare.Cluster")
        config = ClusterConfiguration(name="my-cluster")

        cf.clusters.create(config, namespace="one")
        cf.clusters.create(config, namespace="two")

        assert config.namespace is None
        namespaces = [c.args[0].namespace for c in mock_cluster_cls.call_args_list]
        assert namespaces == ["one", "two"]

    def test_create_accepts_a_fully_configured_config(self, cf, mocker):
        """Namespace injection cannot re-run ClusterConfiguration.__post_init__.

        __post_init__ merges the default accelerator mapping into
        extended_resource_mapping and then rejects the merged result, so
        dataclasses.replace() raises on an already-constructed instance.
        """
        mock_cluster_cls = mocker.patch("codeflare_sdk.codeflare.Cluster")
        config = ClusterConfiguration(
            name="my-cluster",
            extended_resource_mapping={"custom.com/acc": "ACC"},
        )

        cf.clusters.create(config, namespace="ns")

        passed = mock_cluster_cls.call_args.args[0]
        assert passed.namespace == "ns"
        assert passed.extended_resource_mapping["custom.com/acc"] == "ACC"
        assert passed.extended_resource_mapping["nvidia.com/gpu"] == "GPU"

    def test_create_requires_a_cluster_name(self, cf, mocker):
        """A config without a name fails here, with a message naming the field."""
        mocker.patch("codeflare_sdk.codeflare.Cluster")

        with pytest.raises(ValueError, match="ClusterConfiguration.name is required"):
            cf.clusters.create(ClusterConfiguration())

    def test_get_cluster(self, cf, mocker):
        """get() delegates to _get_cluster_strict."""
        mock_get = mocker.patch("codeflare_sdk.codeflare._get_cluster_strict")

        result = cf.clusters.get(name="existing-cluster")

        mock_get.assert_called_once_with(
            cluster_name="existing-cluster",
            namespace="default-ns",
            verify_tls=True,
            write_to_file=False,
            api_client=cf.client,
        )
        assert result is mock_get.return_value

    def test_get_cluster_override_namespace(self, cf, mocker):
        """get() allows namespace override."""
        mock_get = mocker.patch("codeflare_sdk.codeflare._get_cluster_strict")

        cf.clusters.get(name="existing-cluster", namespace="other-ns")

        mock_get.assert_called_once_with(
            cluster_name="existing-cluster",
            namespace="other-ns",
            verify_tls=True,
            write_to_file=False,
            api_client=cf.client,
        )

    def test_get_cluster_forwards_explicit_options(self, cf, mocker):
        """get() no longer takes **kwargs; verify_tls/write_to_file are named."""
        mock_get = mocker.patch("codeflare_sdk.codeflare._get_cluster_strict")

        cf.clusters.get(name="existing-cluster", verify_tls=False, write_to_file=True)

        mock_get.assert_called_once_with(
            cluster_name="existing-cluster",
            namespace="default-ns",
            verify_tls=False,
            write_to_file=True,
            api_client=cf.client,
        )

    @pytest.mark.parametrize("status_code", [404, 403, 500])
    def test_get_cluster_raises_api_exception(self, cf, mocker, status_code):
        """Facade get() propagates the exact ApiException from K8s."""
        from kubernetes.client.exceptions import ApiException

        api = mocker.patch("kubernetes.client.CustomObjectsApi").return_value
        api.get_namespaced_custom_object.side_effect = ApiException(status=status_code)

        with pytest.raises(ApiException) as error:
            cf.clusters.get(name="missing-cluster")
        assert error.value.status == status_code

    def test_get_cluster_rejects_unknown_option(self, cf, mocker):
        """RHOAIENG-98954: an unsupported key fails here, not inside _get_cluster_strict."""
        mocker.patch("codeflare_sdk.codeflare._get_cluster_strict")

        with pytest.raises(TypeError, match="bogus"):
            cf.clusters.get(name="existing-cluster", bogus=True)

    def test_list_clusters(self, cf, mocker):
        """list() delegates to list_all_clusters for RayCluster snapshots."""
        mock_list = mocker.patch("codeflare_sdk.codeflare.list_all_clusters")
        mock_list.return_value = ["snapshot1", "snapshot2"]

        result = cf.clusters.list()

        mock_list.assert_called_once_with(
            "default-ns", print_to_console=False, api_client=cf.client
        )
        assert result == ["snapshot1", "snapshot2"]

    def test_list_queued(self, cf, mocker):
        """list_queued() delegates to list_all_queued."""
        mock_list = mocker.patch("codeflare_sdk.codeflare.list_all_queued")
        mock_list.return_value = []

        result = cf.clusters.list_queued()

        mock_list.assert_called_once_with(
            "default-ns", print_to_console=False, api_client=cf.client
        )
        assert result == []

    def test_list_uses_detected_namespace_when_none_configured(self, mocker):
        """RHOAIENG-98754 P2-8: fall back to the current context, not 'default'."""
        from codeflare_sdk.codeflare import Codeflare, SDKConfig

        mocker.patch("codeflare_sdk.codeflare.get_k8s_client")
        mocker.patch("codeflare_sdk.codeflare.set_api_client")
        mocker.patch(
            "codeflare_sdk.codeflare.get_current_namespace", return_value="detected"
        )
        mock_list = mocker.patch("codeflare_sdk.codeflare.list_all_clusters")

        cf = Codeflare(config=SDKConfig(namespace=None))
        cf.clusters.list()

        mock_list.assert_called_once_with(
            "detected", print_to_console=False, api_client=cf.client
        )

    def test_create_uses_detected_namespace_when_none_configured(self, mocker):
        """RHOAIENG-98754 P2-8: fall back to the current context, not 'default'."""
        from codeflare_sdk.codeflare import Codeflare, SDKConfig

        mocker.patch("codeflare_sdk.codeflare.get_k8s_client")
        mocker.patch("codeflare_sdk.codeflare.set_api_client")
        mocker.patch(
            "codeflare_sdk.codeflare.get_current_namespace", return_value="detected"
        )
        mock_cluster_cls = mocker.patch("codeflare_sdk.codeflare.Cluster")

        cf = Codeflare(config=SDKConfig(namespace=None))
        cf.clusters.create(ClusterConfiguration(name="test"))

        assert mock_cluster_cls.call_args.args[0].namespace == "detected"


class TestJobHandler:
    @pytest.fixture
    def cf(self, mocker):
        """Create a Codeflare instance with mocked auth."""
        from codeflare_sdk.codeflare import Codeflare, SDKConfig

        mocker.patch("codeflare_sdk.codeflare.get_k8s_client")
        mocker.patch("codeflare_sdk.codeflare.set_api_client")
        return Codeflare(config=SDKConfig(namespace="default-ns"))

    def test_submit_job(self, cf, mocker):
        """submit() creates and submits a RayJob."""
        mock_rayjob_cls = mocker.patch("codeflare_sdk.codeflare.RayJob")
        mock_job = MagicMock()
        mock_rayjob_cls.return_value = mock_job

        result = cf.jobs.submit(
            name="train",
            entrypoint="python train.py",
            cluster_name="my-cluster",
        )

        kwargs = mock_rayjob_cls.call_args.kwargs
        assert kwargs["job_name"] == "train"
        assert kwargs["entrypoint"] == "python train.py"
        assert kwargs["namespace"] == "default-ns"
        assert kwargs["cluster_name"] == "my-cluster"
        assert kwargs["api_client"] is cf.client
        mock_job.submit.assert_called_once()
        assert result is mock_job

    def test_submit_job_override_namespace(self, cf, mocker):
        """submit() allows namespace override."""
        mock_rayjob_cls = mocker.patch("codeflare_sdk.codeflare.RayJob")
        mock_rayjob_cls.return_value = MagicMock()

        cf.jobs.submit(
            name="train",
            entrypoint="python train.py",
            namespace="other-ns",
            cluster_name="my-cluster",
        )

        kwargs = mock_rayjob_cls.call_args.kwargs
        assert kwargs["job_name"] == "train"
        assert kwargs["entrypoint"] == "python train.py"
        assert kwargs["namespace"] == "other-ns"
        assert kwargs["cluster_name"] == "my-cluster"
        assert kwargs["api_client"] is cf.client

    def test_create_job_without_submit(self, cf, mocker):
        """create() returns a RayJob without submitting."""
        mock_rayjob_cls = mocker.patch("codeflare_sdk.codeflare.RayJob")
        mock_job = MagicMock()
        mock_rayjob_cls.return_value = mock_job

        result = cf.jobs.create(
            name="train",
            entrypoint="python train.py",
            cluster_name="my-cluster",
        )

        kwargs = mock_rayjob_cls.call_args.kwargs
        assert kwargs["job_name"] == "train"
        assert kwargs["entrypoint"] == "python train.py"
        assert kwargs["namespace"] == "default-ns"
        assert kwargs["cluster_name"] == "my-cluster"
        assert kwargs["api_client"] is cf.client
        mock_job.submit.assert_not_called()
        assert result is mock_job

    def test_submit_uses_detected_namespace_when_none_configured(self, mocker):
        """RHOAIENG-98754 P2-8: fall back to the current context, not 'default'."""
        from codeflare_sdk.codeflare import Codeflare, SDKConfig

        mocker.patch("codeflare_sdk.codeflare.get_k8s_client")
        mocker.patch("codeflare_sdk.codeflare.set_api_client")
        mocker.patch(
            "codeflare_sdk.codeflare.get_current_namespace", return_value="detected"
        )
        mock_rayjob_cls = mocker.patch("codeflare_sdk.codeflare.RayJob")
        mock_rayjob_cls.return_value = MagicMock()

        cf = Codeflare(config=SDKConfig(namespace=None))
        cf.jobs.submit(
            name="job", entrypoint="python run.py", cluster_name="my-cluster"
        )

        assert mock_rayjob_cls.call_args.kwargs["namespace"] == "detected"


class TestFacadeLifecycle:
    @pytest.fixture
    def cf(self, mocker):
        from codeflare_sdk import Codeflare, SDKConfig

        mocker.patch("codeflare_sdk.codeflare.get_k8s_client")
        return Codeflare(SDKConfig(namespace="default-ns"))

    @pytest.mark.parametrize("namespace", [None, "other-ns"])
    @pytest.mark.parametrize("status_code", [None, 404, 403, 500])
    def test_cluster_delete_cleans_up_via_bound_cluster(
        self, cf, mocker, namespace, status_code
    ):
        from kubernetes.client.exceptions import ApiException

        api_factory = mocker.patch("kubernetes.client.CustomObjectsApi")
        api = api_factory.return_value
        cleanup = mocker.patch(
            "codeflare_sdk.common.utils.generate_cert.cleanup_tls_cert"
        )
        if status_code is not None:
            api.delete_namespaced_custom_object.side_effect = ApiException(
                status=status_code
            )
        if status_code == 404:
            api.list_namespaced_custom_object.return_value = {"items": []}
        if status_code in (403, 500):
            with pytest.raises(ApiException):
                cf.clusters.delete("training", namespace)
            cleanup.assert_not_called()
        else:
            assert cf.clusters.delete("training", namespace) is True
            cleanup.assert_called_once_with("training", namespace or "default-ns")
        api_factory.assert_called_once_with(cf.client)
        api.get_namespaced_custom_object.assert_not_called()
        api.delete_namespaced_custom_object.assert_called_once_with(
            group="ray.io",
            version="v1",
            plural="rayclusters",
            namespace=namespace or "default-ns",
            name="training",
        )

    @pytest.mark.parametrize(
        "handler,plural,kind",
        [("clusters", "rayclusters", "RayCluster"), ("jobs", "rayjobs", "RayJob")],
    )
    def test_delete_raises_runtime_error_when_crd_missing(
        self, cf, mocker, handler, plural, kind
    ):
        from kubernetes.client.exceptions import ApiException

        api_factory = mocker.patch("kubernetes.client.CustomObjectsApi")
        api = api_factory.return_value
        api.delete_namespaced_custom_object.side_effect = ApiException(status=404)
        api.list_namespaced_custom_object.side_effect = ApiException(status=404)
        if handler == "clusters":
            mocker.patch("codeflare_sdk.common.utils.generate_cert.cleanup_tls_cert")
        with pytest.raises(RuntimeError, match=f"{kind}.*unavailable"):
            getattr(cf, handler).delete("missing")

    @pytest.mark.parametrize("method", ["get", "list", "delete"])
    @pytest.mark.parametrize("namespace", [None, "other-ns"])
    def test_job_operations_forward_namespace_and_client(
        self, cf, mocker, method, namespace
    ):
        operation = mocker.patch(f"codeflare_sdk.codeflare.RayJob._{method}")
        args = () if method == "list" else ("train",)

        result = getattr(cf.jobs, method)(*args, namespace=namespace)

        operation.assert_called_once_with(
            *args, namespace or "default-ns", api_client=cf.client
        )
        assert result is operation.return_value

    @pytest.mark.parametrize(
        "handler,method",
        [("clusters", "delete"), ("jobs", "get"), ("jobs", "list"), ("jobs", "delete")],
    )
    def test_lifecycle_resolves_detected_namespace(self, cf, mocker, handler, method):
        cf.config.namespace = None
        mocker.patch(
            "codeflare_sdk.codeflare.get_current_namespace", return_value="detected"
        )
        target = (
            "codeflare_sdk.codeflare._delete_cluster"
            if handler == "clusters"
            else f"codeflare_sdk.codeflare.RayJob._{method}"
        )
        operation = mocker.patch(target)
        args = () if method == "list" else ("train",)

        getattr(getattr(cf, handler), method)(*args)

        assert operation.call_args.args[-1] == "detected"

        mocker.patch("codeflare_sdk.codeflare.get_current_namespace", return_value=None)
        with pytest.raises(ValueError, match="could not determine"):
            getattr(getattr(cf, handler), method)(*args)

    @pytest.mark.parametrize("managed_cluster", [False, True])
    @pytest.mark.parametrize("has_entrypoint", [False, True])
    def test_get_job_returns_a_lifecycle_handle(
        self, cf, mocker, managed_cluster, has_entrypoint
    ):
        from codeflare_sdk import RayJob

        resource = create_rayjob_resource(managed_cluster=managed_cluster)
        if not has_entrypoint:
            resource["spec"].pop("entrypoint")
        api_factory = mocker.patch("kubernetes.client.CustomObjectsApi")
        api = api_factory.return_value
        api.get_namespaced_custom_object.return_value = resource
        load_config = mocker.patch("kubernetes.config.load_kube_config")
        initialize = mocker.patch.object(
            RayJob,
            "__init__",
            side_effect=AssertionError("creation constructor called"),
        )

        job = cf.jobs.get("train")

        assert isinstance(job, RayJob)
        api_factory.assert_called_once_with(cf.client)
        initialize.assert_not_called()
        load_config.assert_not_called()
        assert job.name == "train"
        assert job.cluster_name == resource["status"]["rayClusterName"]
        assert (
            job.ttl_seconds_after_finished
            == resource["spec"]["ttlSecondsAfterFinished"]
        )
        assert job.active_deadline_seconds == 300
        assert job.local_queue == "training-queue"
        assert job._api_client is cf.client
        with pytest.raises(RuntimeError, match="resubmit"):
            job.submit()
        api.create_namespaced_custom_object.assert_not_called()

    @pytest.mark.parametrize("method", ["get", "list"])
    def test_retrieved_jobs_keep_client_after_second_facade(self, cf, mocker, method):
        from codeflare_sdk import Codeflare, SDKConfig

        api_factory = mocker.patch("kubernetes.client.CustomObjectsApi")
        api = api_factory.return_value
        resource = create_rayjob_resource()
        api.get_namespaced_custom_object.return_value = resource
        api.list_namespaced_custom_object.return_value = create_rayjob_list_response(
            [resource]
        )
        api.get_namespaced_custom_object_status.return_value = resource
        job = cf.jobs.get("train") if method == "get" else cf.jobs.list()[0]
        mocker.patch("codeflare_sdk.codeflare.get_k8s_client", return_value=MagicMock())
        second = Codeflare(SDKConfig(namespace="second-ns"))
        assert second.client is not cf.client

        assert job._api_client is cf.client
        api_factory.assert_called_once_with(cf.client)
        assert job._api.api is api
        job.status(print_to_console=False)
        assert job.stop() is True
        assert job.resubmit() is True
        assert job.delete() is True
        api.get_namespaced_custom_object_status.assert_called_once_with(
            group="ray.io",
            version="v1",
            plural="rayjobs",
            namespace="default-ns",
            name="train",
        )
        assert api.patch_namespaced_custom_object.call_count == 2
        for call, suspend in zip(
            api.patch_namespaced_custom_object.call_args_list, [True, False]
        ):
            assert call.kwargs["name"] == "train"
            assert call.kwargs["namespace"] == "default-ns"
            assert call.kwargs["body"]["spec"]["suspend"] is suspend
        api.delete_namespaced_custom_object.assert_called_once_with(
            group="ray.io",
            version="v1",
            plural="rayjobs",
            namespace="default-ns",
            name="train",
        )

    @pytest.mark.parametrize(
        "shape", ["missing", "none", "wrong-type", "empty", "partial"]
    )
    def test_job_list_tolerates_partial_responses(self, cf, mocker, shape):
        response = create_rayjob_list_response()
        response.pop("items")
        if shape == "none":
            response = None
        elif shape == "wrong-type":
            response["items"] = "invalid"
        elif shape == "empty":
            response["items"] = []
        elif shape == "partial":
            partial = create_rayjob_resource()
            partial["spec"] = None
            partial["status"] = None
            partial["metadata"]["labels"] = None
            unnamed = create_rayjob_resource()
            unnamed["metadata"].pop("name")
            malformed = create_rayjob_resource()
            malformed["metadata"] = None
            response["items"] = [None, "invalid", unnamed, malformed, partial]
        api = mocker.patch("kubernetes.client.CustomObjectsApi").return_value
        api.list_namespaced_custom_object.return_value = response

        jobs = cf.jobs.list()

        assert len(jobs) == (1 if shape == "partial" else 0)
        api.list_namespaced_custom_object.assert_called_once_with(
            group="ray.io", version="v1", plural="rayjobs", namespace="default-ns"
        )
        if jobs:
            assert jobs[0].name == "train"
            assert jobs[0].cluster_name == ""

    @pytest.mark.parametrize("status_code", [None, 404, 403, 500])
    def test_job_delete_handles_absent_jobs_and_propagates_errors(
        self, cf, mocker, status_code
    ):
        from kubernetes.client.exceptions import ApiException

        api_factory = mocker.patch("kubernetes.client.CustomObjectsApi")
        api = api_factory.return_value
        if status_code is not None:
            api.delete_namespaced_custom_object.side_effect = ApiException(
                status=status_code
            )
        if status_code == 404:
            api.list_namespaced_custom_object.return_value = {"items": []}
        if status_code in (403, 500):
            with pytest.raises(ApiException):
                cf.jobs.delete("train")
        else:
            assert cf.jobs.delete("train") is True
        api_factory.assert_called_once_with(cf.client)
        api.get_namespaced_custom_object.assert_not_called()
        api.delete_namespaced_custom_object.assert_called_once_with(
            group="ray.io",
            version="v1",
            plural="rayjobs",
            namespace="default-ns",
            name="train",
        )

    @pytest.mark.parametrize("method", ["get", "list"])
    @pytest.mark.parametrize("status_code", [404, 403, 500])
    def test_job_read_errors_are_not_reported_as_empty(
        self, cf, mocker, method, status_code
    ):
        from kubernetes.client.exceptions import ApiException

        api = mocker.patch("kubernetes.client.CustomObjectsApi").return_value
        operation = getattr(api, f"{method}_namespaced_custom_object")
        operation.side_effect = ApiException(status=status_code)
        args = () if method == "list" else ("train",)
        with pytest.raises(ApiException):
            getattr(cf.jobs, method)(*args)


class TestFacadeCommonContract:
    @pytest.fixture
    def cf(self, mocker):
        from codeflare_sdk import Codeflare, SDKConfig

        mocker.patch("codeflare_sdk.codeflare.get_k8s_client")
        return Codeflare(SDKConfig(namespace="default-ns"))

    @pytest.mark.parametrize("handler", ["clusters", "jobs"])
    @pytest.mark.parametrize("status_code", [404, 403, 500])
    def test_get_api_errors_raise(self, cf, mocker, handler, status_code):
        from kubernetes.client.exceptions import ApiException

        api = mocker.patch("kubernetes.client.CustomObjectsApi").return_value
        api.get_namespaced_custom_object.side_effect = ApiException(status=status_code)
        with pytest.raises(ApiException) as error:
            getattr(getattr(cf, handler), "get")("missing")
        assert error.value.status == status_code

    @pytest.mark.parametrize("handler", ["jobs"])
    @pytest.mark.parametrize("status_code", [404, 403, 500])
    def test_list_api_errors_raise(self, cf, mocker, handler, status_code):
        from kubernetes.client.exceptions import ApiException

        api = mocker.patch("kubernetes.client.CustomObjectsApi").return_value
        api.list_namespaced_custom_object.side_effect = ApiException(status=status_code)
        with pytest.raises(ApiException) as error:
            getattr(getattr(cf, handler), "list")()
        assert error.value.status == status_code

    @pytest.mark.parametrize("handler", ["jobs"])
    @pytest.mark.parametrize(
        "shape", ["missing", "none", "wrong-type", "empty", "partial"]
    )
    def test_list_returns_usable_handles_for_partial_responses(
        self, cf, mocker, handler, shape
    ):
        from codeflare_sdk import RayJob

        resource = create_rayjob_resource()
        response = create_rayjob_list_response([resource])
        if shape == "missing":
            response.pop("items")
        elif shape == "none":
            response = None
        elif shape == "wrong-type":
            response["items"] = "invalid"
        elif shape == "empty":
            response["items"] = []
        else:
            import copy

            partial = copy.deepcopy(resource)
            partial.pop("spec", None)
            partial.pop("status", None)
            malformed = copy.deepcopy(resource)
            malformed["metadata"] = None
            unnamed = copy.deepcopy(resource)
            unnamed["metadata"].pop("name")
            response["items"] = [None, "invalid", malformed, unnamed, partial]
        api_factory = mocker.patch("kubernetes.client.CustomObjectsApi")
        api = api_factory.return_value
        api.list_namespaced_custom_object.return_value = response

        handles = getattr(cf, handler).list(namespace="other-ns")

        api_factory.assert_called_once_with(cf.client)
        api.get_namespaced_custom_object.assert_not_called()
        assert len(handles) == (1 if shape == "partial" else 0)
        if handles:
            assert isinstance(handles[0], RayJob)
            assert handles[0]._api_client is cf.client
            assert handles[0].namespace == "other-ns"

    def test_job_list_does_not_load_config_or_initialize_each_job(self, cf, mocker):
        from codeflare_sdk import RayJob

        resources = [
            create_rayjob_resource(name="first"),
            create_rayjob_resource(name="managed", managed_cluster=True),
        ]
        api_factory = mocker.patch("kubernetes.client.CustomObjectsApi")
        api_factory.return_value.list_namespaced_custom_object.return_value = (
            create_rayjob_list_response(resources)
        )
        load = mocker.patch("kubernetes.config.load_kube_config")
        initialize = mocker.patch.object(
            RayJob,
            "__init__",
            side_effect=AssertionError("creation constructor called"),
        )
        vendor_job = mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")
        vendor_cluster = mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayClusterApi")

        jobs = cf.jobs.list()

        assert [job.name for job in jobs] == ["first", "managed"]
        api_factory.assert_called_once_with(cf.client)
        load.assert_not_called()
        initialize.assert_not_called()
        vendor_job.assert_not_called()
        vendor_cluster.assert_not_called()

    def test_cluster_get_remains_bound_after_second_facade(self, cf, mocker):
        from codeflare_sdk import Codeflare, SDKConfig

        api_factory = mocker.patch("kubernetes.client.CustomObjectsApi")
        response = get_ray_obj("ray.io", "v1", "default-ns", "rayclusters")
        resource = response["items"][0]
        resource["metadata"]["namespace"] = "default-ns"
        api_factory.return_value.get_namespaced_custom_object.return_value = resource
        mocker.patch("codeflare_sdk.codeflare.get_k8s_client", return_value=MagicMock())
        Codeflare(SDKConfig(namespace="second-ns"))
        cluster = cf.clusters.get(name=resource["metadata"]["name"])
        api_factory.assert_called_once_with(cf.client)
        assert cluster._api_client is cf.client

    @pytest.mark.parametrize("handler", ["clusters", "jobs"])
    @pytest.mark.parametrize("probe_status", [403, 500])
    def test_delete_propagates_non_404_probe_errors(
        self, cf, mocker, handler, probe_status
    ):
        """_raise_if_crd_missing must propagate 403/500 from the list probe."""
        from kubernetes.client.exceptions import ApiException

        api = mocker.patch("kubernetes.client.CustomObjectsApi").return_value
        api.delete_namespaced_custom_object.side_effect = ApiException(status=404)
        api.list_namespaced_custom_object.side_effect = ApiException(
            status=probe_status
        )
        with pytest.raises(ApiException) as error:
            getattr(cf, handler).delete("test-resource")
        assert error.value.status == probe_status

    def test_cluster_delete_reports_tls_cleanup_errors(self, cf, mocker):
        mocker.patch("kubernetes.client.CustomObjectsApi")
        mocker.patch(
            "codeflare_sdk.common.utils.generate_cert.cleanup_tls_cert",
            side_effect=OSError("cleanup failed"),
        )
        with pytest.raises(OSError, match="cleanup failed"):
            cf.clusters.delete("training")

    def test_retrieved_clusters_reject_up(self, cf, mocker):
        api = mocker.patch("kubernetes.client.CustomObjectsApi").return_value
        response = get_ray_obj("ray.io", "v1", "default-ns", "rayclusters")
        resource = response["items"][0]
        resource["metadata"]["namespace"] = "default-ns"
        api.get_namespaced_custom_object.return_value = resource
        cluster = cf.clusters.get(name=resource["metadata"]["name"])
        assert cluster._retrieved is True
        with pytest.raises(RuntimeError, match="Cannot apply.*retrieved"):
            cluster.up()

    def test_retrieved_clusters_reject_apply(self, cf, mocker):
        api = mocker.patch("kubernetes.client.CustomObjectsApi").return_value
        response = get_ray_obj("ray.io", "v1", "default-ns", "rayclusters")
        resource = response["items"][0]
        resource["metadata"]["namespace"] = "default-ns"
        api.get_namespaced_custom_object.return_value = resource
        cluster = cf.clusters.get(name=resource["metadata"]["name"])
        assert cluster._retrieved is True
        with pytest.raises(RuntimeError, match="Cannot apply.*retrieved"):
            cluster.apply()

    def test_created_clusters_allow_apply(self, cf, mocker):
        from codeflare_sdk import ClusterConfiguration

        mocker.patch("kubernetes.client.CustomObjectsApi")
        cluster = cf.clusters.create(ClusterConfiguration(name="fresh", num_workers=1))
        assert cluster._retrieved is False


class TestJobLifecycleParity:
    @pytest.fixture(params=["create", "get"])
    def job_and_api(self, request, mocker):
        from codeflare_sdk import Codeflare, SDKConfig

        mocker.patch("codeflare_sdk.codeflare.get_k8s_client")
        mocker.patch("kubernetes.config.load_kube_config")
        api = mocker.patch("kubernetes.client.CustomObjectsApi").return_value
        api.get_namespaced_custom_object.return_value = create_rayjob_resource()
        cf = Codeflare(SDKConfig(namespace="default-ns"))
        if request.param == "create":
            job = cf.jobs.create("train", "python train.py", cluster_name="existing")
        else:
            job = cf.jobs.get("train")
        return job, api

    @pytest.mark.parametrize("method", ["stop", "resubmit"])
    @pytest.mark.parametrize("status_code", [404, 403, 500])
    def test_lifecycle_failures_raise_runtime_error(
        self, job_and_api, method, status_code
    ):
        from kubernetes.client.exceptions import ApiException

        job, api = job_and_api
        api.patch_namespaced_custom_object.side_effect = ApiException(
            status=status_code
        )
        with pytest.raises(RuntimeError, match="Failed to"):
            getattr(job, method)()

    def test_instance_delete_succeeds(self, job_and_api):
        """Instance delete() returns True on successful deletion."""
        job, api = job_and_api
        assert job.delete() is True
        api.delete_namespaced_custom_object.assert_called_once()

    def test_instance_delete_succeeds_on_404(self, job_and_api):
        """Instance delete() returns True when job already absent (404)."""
        from kubernetes.client.exceptions import ApiException

        job, api = job_and_api
        api.delete_namespaced_custom_object.side_effect = ApiException(status=404)
        api.list_namespaced_custom_object.return_value = {"items": []}
        assert job.delete() is True

    @pytest.mark.parametrize("status_code", [403, 500])
    def test_instance_delete_raises_on_non_404(self, job_and_api, status_code):
        """Instance delete() propagates 403/500 instead of swallowing them."""
        from kubernetes.client.exceptions import ApiException

        job, api = job_and_api
        api.delete_namespaced_custom_object.side_effect = ApiException(
            status=status_code
        )
        with pytest.raises(ApiException) as error:
            job.delete()
        assert error.value.status == status_code

    @pytest.mark.parametrize("status_code", [404, 403, 500])
    def test_status_api_failure_returns_unknown(self, job_and_api, mocker, status_code):
        from kubernetes.client.exceptions import ApiException
        from codeflare_sdk.ray.rayjobs.status import CodeflareRayJobStatus

        job, api = job_and_api
        api.get_namespaced_custom_object_status.side_effect = ApiException(
            status=status_code
        )
        no_job = mocker.patch(
            "codeflare_sdk.ray.rayjobs.rayjob.pretty_print.print_no_job_found"
        )
        sleep = mocker.patch(
            "codeflare_sdk.vendored.python_client.kuberay_job_api.time.sleep"
        )

        assert job.status() == (CodeflareRayJobStatus.UNKNOWN, False)
        no_job.assert_called_once_with("train", "default-ns")
        sleep.assert_not_called()
        api.get_namespaced_custom_object_status.assert_called_once()

    def test_status_waits_for_operator(self, job_and_api, mocker):
        from codeflare_sdk.ray.rayjobs.status import CodeflareRayJobStatus

        job, api = job_and_api
        pending = create_rayjob_resource()
        pending.pop("status")
        api.get_namespaced_custom_object_status.side_effect = [
            pending,
            create_rayjob_resource(),
        ]
        no_job = mocker.patch(
            "codeflare_sdk.ray.rayjobs.rayjob.pretty_print.print_no_job_found"
        )
        sleep = mocker.patch(
            "codeflare_sdk.vendored.python_client.kuberay_job_api.time.sleep"
        )

        assert job.status(print_to_console=False) == (
            CodeflareRayJobStatus.RUNNING,
            False,
        )
        assert api.get_namespaced_custom_object_status.call_count == 2
        sleep.assert_called_once_with(5)
        no_job.assert_not_called()

    def test_status_timeout_matches_created_jobs(self, job_and_api, mocker):
        from codeflare_sdk.ray.rayjobs.status import CodeflareRayJobStatus

        job, api = job_and_api
        pending = create_rayjob_resource()
        pending.pop("status")
        api.get_namespaced_custom_object_status.return_value = pending
        sleep = mocker.patch(
            "codeflare_sdk.vendored.python_client.kuberay_job_api.time.sleep"
        )

        assert job.status(print_to_console=False) == (
            CodeflareRayJobStatus.UNKNOWN,
            False,
        )
        assert api.get_namespaced_custom_object_status.call_count == 12
        assert sleep.call_count == 12
        assert all(call.args == (5,) for call in sleep.call_args_list)

    def test_retrieved_handle_initializes_creation_attributes(self, mocker):
        from codeflare_sdk import Codeflare, SDKConfig

        mocker.patch("codeflare_sdk.codeflare.get_k8s_client")
        api = mocker.patch("kubernetes.client.CustomObjectsApi").return_value
        api.get_namespaced_custom_object.return_value = create_rayjob_resource(
            managed_cluster=True
        )
        job = Codeflare(SDKConfig(namespace="default-ns")).jobs.get("train")

        for name in ("runtime_env", "_cluster_config", "_cluster_name", "_cluster_api"):
            assert getattr(job, name) is None

    def test_rayjob_handle_covers_all_init_attributes(self, mocker):
        """Fail when RayJob.__init__ gains an attribute that _RayJobHandle misses."""
        import ast
        import inspect
        import textwrap
        from codeflare_sdk.ray.rayjobs.rayjob import RayJob, _RayJobHandle

        def _self_assignments(cls: type) -> set:
            source = textwrap.dedent(inspect.getsource(cls.__init__))
            tree = ast.parse(source)
            attrs = set()
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Assign)
                    and len(node.targets) == 1
                    and isinstance(node.targets[0], ast.Attribute)
                    and isinstance(node.targets[0].value, ast.Name)
                    and node.targets[0].value.id == "self"
                ):
                    attrs.add(node.targets[0].attr)
            return attrs

        base_attrs = _self_assignments(RayJob)
        handle_attrs = _self_assignments(_RayJobHandle)
        missing = base_attrs - handle_attrs
        assert not missing, (
            f"_RayJobHandle.__init__ is missing attributes set by "
            f"RayJob.__init__: {sorted(missing)}. Add them to "
            f"_RayJobHandle.__init__ or the handle will break at runtime."
        )


class TestFacadeTypeSignatures:
    """RHOAIENG-98954: the facade's arguments are typed, and stay that way.

    Cluster creation takes a ClusterConfiguration, so there is nothing to keep
    in sync there — these tests just stop **kwargs from creeping back in. The
    job handler does mirror its parameters into the JobOptions TypedDict, and
    those tests fail when the two drift.
    """

    def test_cluster_create_takes_a_configuration_object(self):
        """RHOAIENG-98954: no **kwargs to mirror — the dataclass is the contract."""
        from codeflare_sdk.codeflare import ClusterHandler

        params = inspect.signature(ClusterHandler.create).parameters

        assert list(params) == ["self", "config", "namespace"]
        assert params["config"].annotation is ClusterConfiguration
        assert not any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values())

    def test_cluster_get_takes_no_var_keywords(self):
        """get()'s options are named, so an unknown key fails at the facade."""
        from codeflare_sdk.codeflare import ClusterHandler

        params = inspect.signature(ClusterHandler.get).parameters

        assert list(params) == [
            "self",
            "name",
            "namespace",
            "verify_tls",
            "write_to_file",
        ]
        assert not any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values())

    def test_job_options_match_create_signature(self):
        """JobOptions holds exactly create()'s non-target keyword arguments."""
        from codeflare_sdk.codeflare import JobHandler, JobOptions

        params = inspect.signature(JobHandler.create).parameters
        expected = {
            name
            for name, p in params.items()
            if p.kind is inspect.Parameter.KEYWORD_ONLY
            and name not in ("cluster_name", "cluster_config")
        }

        assert set(get_type_hints(JobOptions)) == expected

    def test_job_options_types_match_create_signature(self):
        """An option's type cannot drift from the parameter it stands in for."""
        from codeflare_sdk.codeflare import JobHandler, JobOptions

        params = inspect.signature(JobHandler.create).parameters
        hints = get_type_hints(JobOptions)

        mismatched = {
            key: (params[key].annotation, hints[key])
            for key in hints
            if key in params and params[key].annotation != hints[key]
        }
        assert mismatched == {}

    def test_job_overloads_cover_both_execution_targets(self):
        """create() and submit() each declare the cluster_name/cluster_config pair."""
        from codeflare_sdk.codeflare import JobHandler

        for method in (JobHandler.create, JobHandler.submit):
            overloads = get_overloads(method)
            assert len(overloads) == 2, f"{method.__name__} lost an overload"

            targets = [
                set(inspect.signature(o).parameters)
                & {"cluster_name", "cluster_config"}
                for o in overloads
            ]
            assert targets == [{"cluster_name"}, {"cluster_config"}]

    def test_cluster_config_reaches_the_facade_unchanged(self, mocker):
        """Every configured field survives the handler, not just the namespace."""
        from codeflare_sdk.codeflare import Codeflare, SDKConfig

        mocker.patch("codeflare_sdk.codeflare.get_k8s_client")
        mocker.patch("codeflare_sdk.codeflare.set_api_client")
        mock_cluster_cls = mocker.patch("codeflare_sdk.codeflare.Cluster")

        cf = Codeflare(config=SDKConfig(namespace="ns"))
        config = ClusterConfiguration(
            name="c",
            num_workers=4,
            enable_autoscaling=True,
            min_workers=1,
            max_workers=4,
            labels={"team": "ml"},
            image_pull_secrets=["my-secret"],
        )

        cf.clusters.create(config)

        passed = mock_cluster_cls.call_args.args[0]
        for field_name in (
            "num_workers",
            "enable_autoscaling",
            "min_workers",
            "max_workers",
            "labels",
            "image_pull_secrets",
        ):
            assert getattr(passed, field_name) == getattr(config, field_name)


class TestLegacyAuthRemoved:
    # The legacy auth classes are no longer removed. RHOAIENG-98947: the team
    # decided to restore TokenAuthentication, KubeConfigFileAuthentication and
    # their two abstract bases with deprecation warnings, because v0.39.x
    # documentation promised they would survive and told token users to stay
    # on TokenAuthentication. set_api_client came back for the same reason —
    # it never warned at all. All five are covered by test_compat.py; what
    # remains here is the entrypoint surface that replaces them.

    def test_codeflare_importable(self):
        """Codeflare is importable from codeflare_sdk."""
        from codeflare_sdk import Codeflare  # noqa: F401

    def test_sdk_config_importable(self):
        """SDKConfig is importable from codeflare_sdk."""
        from codeflare_sdk import SDKConfig  # noqa: F401

    def test_job_options_importable(self):
        """JobOptions is exported so callers can annotate their own wrappers."""
        from codeflare_sdk import JobOptions  # noqa: F401

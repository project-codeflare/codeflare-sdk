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

"""
The cluster sub-module contains the definition of the Cluster object, which represents
the resources requested by the user. It also contains functions for checking the
cluster setup queue, a list of all existing clusters, and the user's working namespace.
"""

from time import sleep
from typing import List, Optional, Tuple, Dict
import copy

from ray.job_submission import JobSubmissionClient, JobStatus
import time
import uuid
import warnings

from ...common.kubernetes_cluster.auth import (
    config_check,
    get_api_client,
)
from . import pretty_print
from .build_ray_cluster import build_ray_cluster, head_worker_gpu_count_from_cluster
from .build_ray_cluster import write_to_file as write_cluster_to_file
from ...common import _kube_api_error_handling

from .config import ClusterConfiguration
from .status import (
    CodeFlareClusterStatus,
    RayCluster,
    RayClusterStatus,
)
from ..appwrapper import (
    AppWrapper,
    AppWrapperStatus,
)
from ...common.widgets.widgets import (
    cluster_up_down_buttons,
    is_notebook,
)
from kubernetes import client
import yaml
import os
import requests

from kubernetes import config
from kubernetes.dynamic import DynamicClient
from kubernetes import client as k8s_client
from kubernetes.client.rest import ApiException

from kubernetes.client.rest import ApiException

CF_SDK_FIELD_MANAGER = "codeflare-sdk"


class Cluster:
    """
    An object for requesting, bringing up, and taking down resources.
    Can also be used for seeing the resource cluster status and details.

    Note that currently, the underlying implementation is a Ray cluster.
    """

    def __init__(self, config: ClusterConfiguration):
        """
        Create the resource cluster object by passing in a ClusterConfiguration
        (defined in the config sub-module). An AppWrapper will then be generated
        based off of the configured resources to represent the desired cluster
        request.
        """
        self.config = config
        self._job_submission_client = None
        if self.config is None:
            warnings.warn(
                "Please provide a ClusterConfiguration to initialise the Cluster object"
            )
            return
        else:
            self.resource_yaml = self.create_resource()

        if is_notebook():
            cluster_up_down_buttons(self)

    def get_dynamic_client(self):  # pragma: no cover
        return DynamicClient(get_api_client())

    def config_check(self):
        return config_check()

    @property
    def _client_headers(self):
        k8_client = get_api_client()
        return {
            "Authorization": k8_client.configuration.get_api_key_with_prefix(
                "authorization"
            )
        }

    @property
    def _client_verify_tls(self):
        return _is_openshift_cluster and self.config.verify_tls

    @property
    def job_client(self):
        k8client = get_api_client()
        if self._job_submission_client:
            return self._job_submission_client
        if _is_openshift_cluster():
            self._job_submission_client = JobSubmissionClient(
                self.cluster_dashboard_uri(),
                headers=self._client_headers,
                verify=self._client_verify_tls,
            )
        else:
            self._job_submission_client = JobSubmissionClient(
                self.cluster_dashboard_uri()
            )
        return self._job_submission_client

    def create_resource(self):
        """
        Called upon cluster object creation, creates an AppWrapper yaml based on
        the specifications of the ClusterConfiguration.
        """
        if self.config.namespace is None:
            self.config.namespace = get_current_namespace()
            if self.config.namespace is None:
                print("Please specify with namespace=<your_current_namespace>")
            elif type(self.config.namespace) is not str:
                raise TypeError(
                    f"Namespace {self.config.namespace} is of type {type(self.config.namespace)}. Check your Kubernetes Authentication."
                )
        return build_ray_cluster(self)

    # creates a new cluster with the provided or default spec
    def up(self):
        """
        Applies the Cluster yaml, pushing the resource request onto
        the Kueue localqueue.
        """
        print(
            "WARNING: The up() function is planned for deprecation in favor of apply()."
        )
        # check if RayCluster CustomResourceDefinition exists if not throw RuntimeError
        self._throw_for_no_raycluster()
        namespace = self.config.namespace

        try:
            config_check()
            api_instance = client.CustomObjectsApi(get_api_client())
            if self.config.appwrapper:
                if self.config.write_to_file:
                    with open(self.resource_yaml) as f:
                        aw = yaml.load(f, Loader=yaml.FullLoader)
                        api_instance.create_namespaced_custom_object(
                            group="workload.codeflare.dev",
                            version="v1beta2",
                            namespace=namespace,
                            plural="appwrappers",
                            body=aw,
                        )
                else:
                    api_instance.create_namespaced_custom_object(
                        group="workload.codeflare.dev",
                        version="v1beta2",
                        namespace=namespace,
                        plural="appwrappers",
                        body=self.resource_yaml,
                    )
                print(f"AppWrapper: '{self.config.name}' has successfully been created")
            else:
                self._component_resources_up(namespace, api_instance)
                print(
                    f"Ray Cluster: '{self.config.name}' has successfully been created"
                )
        except Exception as e:  # pragma: no cover
            if e.status == 422:
                print(
                    "WARNING: RayCluster creation rejected due to invalid Kueue configuration. Please contact your administrator."
                )
            else:
                print(
                    "WARNING: Failed to create RayCluster due to unexpected error. Please contact your administrator."
                )
            return _kube_api_error_handling(e)

    # Applies a new cluster with the provided or default spec
    def apply(self, force=False):
        """
        Applies the Cluster yaml using server-side apply.
        If 'force' is set to True, conflicts will be forced.
        """
        # check if RayCluster CustomResourceDefinition exists if not throw RuntimeError
        self._throw_for_no_raycluster()
        namespace = self.config.namespace
        name = self.config.name
        try:
            self.config_check()
            api_instance = client.CustomObjectsApi(get_api_client())
            crds = self.get_dynamic_client().resources
            if self.config.appwrapper:
                api_version = "workload.codeflare.dev/v1beta2"
                api_instance = crds.get(api_version=api_version, kind="AppWrapper")
                # defaulting body to resource_yaml
                body = self.resource_yaml
                if self.config.write_to_file:
                    # if write_to_file is True, load the file from AppWrapper yaml and update body
                    with open(self.resource_yaml) as f:
                        aw = yaml.load(f, Loader=yaml.FullLoader)
                    body = aw
                api_instance.server_side_apply(
                    field_manager=CF_SDK_FIELD_MANAGER,
                    group="workload.codeflare.dev",
                    version="v1beta2",
                    namespace=namespace,
                    plural="appwrappers",
                    body=body,
                    force_conflicts=force,
                )
                print(
                    f"AppWrapper: '{name}' configuration has successfully been applied. For optimal resource management, you should delete this Ray Cluster when no longer in use."
                )
            else:
                api_version = "ray.io/v1"
                api_instance = crds.get(api_version=api_version, kind="RayCluster")
                self._component_resources_apply(
                    namespace=namespace, api_instance=api_instance
                )
                print(
                    f"Ray Cluster: '{name}' has successfully been applied. For optimal resource management, you should delete this Ray Cluster when no longer in use."
                )
        except AttributeError as e:
            raise RuntimeError(f"Failed to initialize DynamicClient: {e}")
        except Exception as e:  # pragma: no cover
            if e.status == 422:
                print(
                    "WARNING: RayCluster creation rejected due to invalid Kueue configuration. Please contact your administrator."
                )
            else:
                print(
                    "WARNING: Failed to create RayCluster due to unexpected error. Please contact your administrator."
                )
            return _kube_api_error_handling(e)

    def _throw_for_no_raycluster(self):
        api_instance = client.CustomObjectsApi(get_api_client())
        try:
            api_instance.list_namespaced_custom_object(
                group="ray.io",
                version="v1",
                namespace=self.config.namespace,
                plural="rayclusters",
            )
        except ApiException as e:
            if e.status == 404:
                raise RuntimeError(
                    "RayCluster CustomResourceDefinition unavailable contact your administrator."
                )
            else:
                raise RuntimeError(
                    "Failed to get RayCluster CustomResourceDefinition: " + str(e)
                )

    def down(self):
        """
        Deletes the AppWrapper yaml, scaling-down and deleting all resources
        associated with the cluster.
        """
        namespace = self.config.namespace
        resource_name = self.config.name
        self._throw_for_no_raycluster()
        try:
            self.config_check()
            api_instance = client.CustomObjectsApi(get_api_client())
            if self.config.appwrapper:
                api_instance.delete_namespaced_custom_object(
                    group="workload.codeflare.dev",
                    version="v1beta2",
                    namespace=namespace,
                    plural="appwrappers",
                    name=resource_name,
                )
                print(f"AppWrapper: '{resource_name}' has successfully been deleted")
            else:
                _delete_resources(resource_name, namespace, api_instance)
                print(
                    f"Ray Cluster: '{self.config.name}' has successfully been deleted"
                )
        except Exception as e:  # pragma: no cover
            return _kube_api_error_handling(e)

    def status(
        self, print_to_console: bool = True
    ) -> Tuple[CodeFlareClusterStatus, bool]:
        """
        Returns the requested cluster's status, as well as whether or not
        it is ready for use.
        """
        ready = False
        status = CodeFlareClusterStatus.UNKNOWN
        if self.config.appwrapper:
            # check the app wrapper status
            appwrapper = _app_wrapper_status(self.config.name, self.config.namespace)
            if appwrapper:
                if appwrapper.status in [
                    AppWrapperStatus.RESUMING,
                    AppWrapperStatus.RESETTING,
                ]:
                    ready = False
                    status = CodeFlareClusterStatus.STARTING
                elif appwrapper.status in [
                    AppWrapperStatus.FAILED,
                ]:
                    ready = False
                    status = CodeFlareClusterStatus.FAILED  # should deleted be separate
                    return status, ready  # exit early, no need to check ray status
                elif appwrapper.status in [
                    AppWrapperStatus.SUSPENDED,
                    AppWrapperStatus.SUSPENDING,
                ]:
                    ready = False
                    if appwrapper.status == AppWrapperStatus.SUSPENDED:
                        status = CodeFlareClusterStatus.QUEUED
                    else:
                        status = CodeFlareClusterStatus.QUEUEING
                    if print_to_console:
                        pretty_print.print_app_wrappers_status([appwrapper])
                    return (
                        status,
                        ready,
                    )  # no need to check the ray status since still in queue

        # check the ray cluster status
        cluster = _ray_cluster_status(self.config.name, self.config.namespace)
        if cluster:
            if cluster.status == RayClusterStatus.SUSPENDED:
                ready = False
                status = CodeFlareClusterStatus.SUSPENDED
            if cluster.status == RayClusterStatus.UNKNOWN:
                ready = False
                status = CodeFlareClusterStatus.STARTING
            if cluster.status == RayClusterStatus.READY:
                ready = True
                status = CodeFlareClusterStatus.READY
            elif cluster.status in [
                RayClusterStatus.UNHEALTHY,
                RayClusterStatus.FAILED,
            ]:
                ready = False
                status = CodeFlareClusterStatus.FAILED

            if print_to_console:
                # overriding the number of gpus with requested
                _, cluster.worker_gpu = head_worker_gpu_count_from_cluster(self)
                pretty_print.print_cluster_status(cluster)
        elif print_to_console:
            if status == CodeFlareClusterStatus.UNKNOWN:
                pretty_print.print_no_resources_found()
            else:
                pretty_print.print_app_wrappers_status([appwrapper], starting=True)

        return status, ready

    def is_dashboard_ready(self) -> bool:
        """
        Checks if the cluster's dashboard is ready and accessible.

        This method attempts to send a GET request to the cluster dashboard URI.
        If the request is successful (HTTP status code 200), it returns True.
        If an SSL error occurs, it returns False, indicating the dashboard is not ready.

        Returns:
            bool:
                True if the dashboard is ready, False otherwise.
        """
        try:
            response = requests.get(
                self.cluster_dashboard_uri(),
                headers=self._client_headers,
                timeout=5,
                verify=self._client_verify_tls,
            )
        except requests.exceptions.SSLError:  # pragma no cover
            # SSL exception occurs when oauth ingress has been created but cluster is not up
            return False
        if response.status_code == 200:
            return True
        else:
            return False

    def wait_ready(self, timeout: Optional[int] = None, dashboard_check: bool = True):
        """
        Waits for the requested cluster to be ready, up to an optional timeout.

        This method checks the status of the cluster every five seconds until it is
        ready or the timeout is reached. If dashboard_check is enabled, it will also
        check for the readiness of the dashboard.

        Args:
            timeout (Optional[int]):
                The maximum time to wait for the cluster to be ready in seconds. If None, waits indefinitely.
            dashboard_check (bool):
                Flag to determine if the dashboard readiness should
                be checked. Defaults to True.

        Raises:
            TimeoutError:
                If the timeout is reached before the cluster or dashboard is ready.
        """
        print("Waiting for requested resources to be set up...")
        time = 0
        while True:
            if timeout and time >= timeout:
                raise TimeoutError(
                    f"wait() timed out after waiting {timeout}s for cluster to be ready"
                )
            status, ready = self.status(print_to_console=False)
            if status == CodeFlareClusterStatus.UNKNOWN:
                print(
                    "WARNING: Current cluster status is unknown, have you run cluster.up yet?"
                )
            if ready:
                break
            sleep(5)
            time += 5
        print("Requested cluster is up and running!")

        while dashboard_check:
            if timeout and time >= timeout:
                raise TimeoutError(
                    f"wait() timed out after waiting {timeout}s for dashboard to be ready"
                )
            if self.is_dashboard_ready():
                print("Dashboard is ready!")
                break
            sleep(5)
            time += 5

    def details(self, print_to_console: bool = True) -> RayCluster:
        """
        Retrieves details about the Ray Cluster.

        This method returns a copy of the Ray Cluster information and optionally prints
        the details to the console.

        Args:
            print_to_console (bool):
                Flag to determine if the cluster details should be
                printed to the console. Defaults to True.

        Returns:
            RayCluster:
                A copy of the Ray Cluster details.
        """
        cluster = _copy_to_ray(self)
        if print_to_console:
            pretty_print.print_clusters([cluster])
        return cluster

    def cluster_uri(self) -> str:
        """
        Returns a string containing the cluster's URI.
        """
        return f"ray://{self.config.name}-head-svc.{self.config.namespace}.svc:10001"

    def cluster_dashboard_uri(self) -> str:
        """
        Returns a string containing the cluster's dashboard URI.
        """
        config_check()
        if _is_openshift_cluster():
            try:
                api_instance = client.CustomObjectsApi(get_api_client())
                routes = api_instance.list_namespaced_custom_object(
                    group="route.openshift.io",
                    version="v1",
                    namespace=self.config.namespace,
                    plural="routes",
                )
            except Exception as e:  # pragma: no cover
                return _kube_api_error_handling(e)

            for route in routes["items"]:
                if route["metadata"][
                    "name"
                ] == f"ray-dashboard-{self.config.name}" or route["metadata"][
                    "name"
                ].startswith(
                    f"{self.config.name}-ingress"
                ):
                    protocol = "https" if route["spec"].get("tls") else "http"
                    return f"{protocol}://{route['spec']['host']}"
        else:
            try:
                api_instance = client.NetworkingV1Api(get_api_client())
                ingresses = api_instance.list_namespaced_ingress(self.config.namespace)
            except Exception as e:  # pragma no cover
                return _kube_api_error_handling(e)

            for ingress in ingresses.items:
                annotations = ingress.metadata.annotations
                protocol = "http"
                if (
                    ingress.metadata.name == f"ray-dashboard-{self.config.name}"
                    or ingress.metadata.name.startswith(f"{self.config.name}-ingress")
                ):
                    if annotations == None:
                        protocol = "http"
                    elif "route.openshift.io/termination" in annotations:
                        protocol = "https"
                return f"{protocol}://{ingress.spec.rules[0].host}"
        return "Dashboard not available yet, have you run cluster.up()?"

    def list_jobs(self) -> List:
        """
        This method accesses the head ray node in your cluster and lists the running jobs.
        """
        return self.job_client.list_jobs()

    def job_status(self, job_id: str) -> str:
        """
        This method accesses the head ray node in your cluster and returns the job status for the provided job id.
        """
        return self.job_client.get_job_status(job_id)

    def job_logs(self, job_id: str) -> str:
        """
        This method accesses the head ray node in your cluster and returns the logs for the provided job id.
        """
        return self.job_client.get_job_logs(job_id)

    @staticmethod
    def _head_worker_extended_resources_from_rc_dict(rc: Dict) -> Tuple[dict, dict]:
        head_extended_resources, worker_extended_resources = {}, {}
        for resource in rc["spec"]["workerGroupSpecs"][0]["template"]["spec"][
            "containers"
        ][0]["resources"]["limits"].keys():
            if resource in ["memory", "cpu"]:
                continue
            worker_extended_resources[resource] = rc["spec"]["workerGroupSpecs"][0][
                "template"
            ]["spec"]["containers"][0]["resources"]["limits"][resource]

        for resource in rc["spec"]["headGroupSpec"]["template"]["spec"]["containers"][
            0
        ]["resources"]["limits"].keys():
            if resource in ["memory", "cpu"]:
                continue
            head_extended_resources[resource] = rc["spec"]["headGroupSpec"]["template"][
                "spec"
            ]["containers"][0]["resources"]["limits"][resource]

        return head_extended_resources, worker_extended_resources

    def local_client_url(self):
        """
        Constructs the URL for the local Ray client.

        Returns:
            str:
                The Ray client URL based on the ingress domain.
        """
        ingress_domain = _get_ingress_domain(self)
        return f"ray://{ingress_domain}"

    def _component_resources_up(
        self, namespace: str, api_instance: client.CustomObjectsApi
    ):
        if self.config.write_to_file:
            with open(self.resource_yaml) as f:
                ray_cluster = yaml.safe_load(f)
                _create_resources(ray_cluster, namespace, api_instance)
        else:
            _create_resources(self.resource_yaml, namespace, api_instance)

    def _component_resources_apply(
        self, namespace: str, api_instance: client.CustomObjectsApi
    ):
        if self.config.write_to_file:
            with open(self.resource_yaml) as f:
                ray_cluster = yaml.safe_load(f)
                _apply_ray_cluster(ray_cluster, namespace, api_instance)
        else:
            _apply_ray_cluster(self.resource_yaml, namespace, api_instance)

    def _component_resources_down(
        self, namespace: str, api_instance: client.CustomObjectsApi
    ):
        cluster_name = self.config.name
        if self.config.write_to_file:
            with open(self.resource_yaml) as f:
                yamls = yaml.load_all(f, Loader=yaml.FullLoader)
                _delete_resources(yamls, namespace, api_instance, cluster_name)
        else:
            yamls = yaml.safe_load_all(self.resource_yaml)
            _delete_resources(yamls, namespace, api_instance, cluster_name)

    @staticmethod
    def run_job_with_managed_cluster(
        cluster_config: ClusterConfiguration,
        entrypoint: str,
        job_cr_name: Optional[str] = None, # Name for the RayJob CR itself
        runtime_env: Optional[Dict] = None,
        job_submission_id: Optional[str] = None, # For Ray's internal job tracking (spec.jobId)
        ray_job_metadata: Optional[Dict[str, str]] = None, # For Ray's internal job (spec.metadata)
        submission_mode: str = "K8sJobMode", # "K8sJobMode" or "RayClientMode"
        shutdown_after_job_finishes: bool = True,
        ttl_seconds_after_finished: Optional[int] = None,
        suspend_rayjob_creation: bool = False, # To create RayJob in suspended state
        wait_for_completion: bool = True,
        job_timeout_seconds: Optional[int] = 3600, # Default 1 hour
        job_polling_interval_seconds: int = 10,
    ):
        """
        Manages the lifecycle of a Ray cluster and a job by creating a RayJob custom resource.
        KubeRay operator will then create/delete the RayCluster based on the RayJob definition.

        This method will:
        1. Generate a RayCluster specification from the provided 'cluster_config'.
        2. Construct a RayJob custom resource definition, embedding the RayCluster spec.
        3. Create the RayJob resource in Kubernetes.
        4. Optionally, wait for the RayJob to complete or timeout, monitoring its status.
        5. The RayCluster lifecycle (creation and deletion) is managed by KubeRay
           based on the RayJob's 'shutdownAfterJobFinishes' field.

        Args:
            cluster_config: Configuration for the Ray cluster to be created by RayJob.
            entrypoint: The command to run for the job.
            job_cr_name: Name for the RayJob Custom Resource. If None, a unique name is generated.
            runtime_env: Runtime environment for the job, as a dictionary. Will be converted to YAML string.
            job_submission_id: Custom ID for the Ray job (spec.jobId in RayJob).
            ray_job_metadata: Metadata for the Ray job (spec.metadata in RayJob).
            submission_mode: How the job is submitted ("K8sJobMode" or "RayClientMode").
            shutdown_after_job_finishes: If True, RayCluster is deleted after job finishes.
            ttl_seconds_after_finished: TTL for RayJob after it's finished.
            suspend_rayjob_creation: If True, creates the RayJob in a suspended state.
            wait_for_completion: If True, waits for the job to finish.
            job_timeout_seconds: Timeout for waiting for job completion.
            job_polling_interval_seconds: Interval for polling job status.

        Returns:
            A dictionary containing details like RayJob CR name, reported job submission ID,
            final job status, dashboard URL, and the RayCluster name.
            Example: {
                "job_cr_name": "my-rayjob-abc",
                "job_submission_id": "raysubmit_123",
                "job_status": "SUCCEEDED",
                "dashboard_url": "http://...",
                "ray_cluster_name": "my-rayjob-abc-cluster"
            }

        Raises:
            TimeoutError: If the job doesn't complete within the specified timeout.
            ApiException: For Kubernetes API errors.
            ValueError: For configuration issues.
        """
        config_check()
        k8s_co_api = k8s_client.CustomObjectsApi(get_api_client())
        namespace = cluster_config.namespace

        # Generate rayClusterSpec from ClusterConfiguration
        # Create a temporary Cluster instance with appwrapper=False to leverage
        # build_ray_cluster logic, which produces the RayCluster CR dict.
        temp_config_for_spec = copy.deepcopy(cluster_config) # Standard library deepcopy
        temp_config_for_spec.appwrapper = False
        
        # Suppress warning about missing ClusterConfiguration during this internal step
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            # Cluster constructor calls create_resource() which calls build_ray_cluster()
            dummy_cluster_for_spec = Cluster(temp_config_for_spec)

        ray_cluster_cr_dict = dummy_cluster_for_spec.resource_yaml
        if not isinstance(ray_cluster_cr_dict, dict) or "spec" not in ray_cluster_cr_dict:
            raise ValueError(
                "Failed to generate RayCluster CR dictionary from ClusterConfiguration. "
                f"Got: {type(ray_cluster_cr_dict)}"
            )
        ray_cluster_spec = ray_cluster_cr_dict["spec"]

        # Ensure cluster_config.name (original one) is used in the embedded spec if not overridden by KubeRay
        # KubeRay might generate its own name for the cluster if not specified in rayClusterSpec.metadata.name
        # However, our build_ray_cluster sets metadata.name in the CRD it builds.
        # We can also explicitly set it here if needed for clarity.
        # ray_cluster_spec.setdefault("metadata", {}).setdefault("name", cluster_config.name)
        # For RayJob, the cluster name is often derived by KubeRay. Let's rely on that or what build_ray_cluster does.


        # Prepare RayJob CR
        actual_job_cr_name = job_cr_name or f"rayjob-{uuid.uuid4().hex[:10]}"
        
        runtime_env_yaml_str = ""
        if runtime_env:
            try:
                runtime_env_yaml_str = yaml.dump(runtime_env)
            except yaml.YAMLError as e:
                raise ValueError(f"Invalid runtime_env, failed to dump to YAML: {e}")

        ray_job_cr = {
            "apiVersion": "ray.io/v1",
            "kind": "RayJob",
            "metadata": {
                "name": actual_job_cr_name,
                "namespace": namespace,
            },
            "spec": {
                "entrypoint": entrypoint,
                "shutdownAfterJobFinishes": shutdown_after_job_finishes,
                "rayClusterSpec": ray_cluster_spec,
                "submissionMode": submission_mode,
            },
        }

        if runtime_env_yaml_str:
            ray_job_cr["spec"]["runtimeEnvYAML"] = runtime_env_yaml_str
        if job_submission_id: # This is Ray's internal job ID, not the CR name
            ray_job_cr["spec"]["jobId"] = job_submission_id
        if ray_job_metadata:
            ray_job_cr["spec"]["metadata"] = ray_job_metadata
        if ttl_seconds_after_finished is not None:
            ray_job_cr["spec"]["ttlSecondsAfterFinished"] = ttl_seconds_after_finished
        if suspend_rayjob_creation:
            ray_job_cr["spec"]["suspend"] = True
        
        # Remove sensitive or SDK-specific fields from cluster_config before logging or if ever returned
        # For now, we only use it to generate ray_cluster_spec

        returned_job_submission_id = None
        final_job_status = "UNKNOWN" # Corresponds to Ray's JobStatus strings
        dashboard_url = None
        ray_cluster_name_actual = None

        try:
            print(f"Submitting RayJob '{actual_job_cr_name}' to namespace '{namespace}'...")
            k8s_co_api.create_namespaced_custom_object(
                group="ray.io",
                version="v1",
                namespace=namespace,
                plural="rayjobs",
                body=ray_job_cr,
            )
            print(f"RayJob '{actual_job_cr_name}' created successfully.")

            if wait_for_completion:
                print(f"Waiting for RayJob '{actual_job_cr_name}' to complete...")
                start_time = time.time()
                while True:
                    try:
                        ray_job_status_cr = k8s_co_api.get_namespaced_custom_object_status(
                            group="ray.io",
                            version="v1",
                            namespace=namespace,
                            plural="rayjobs",
                            name=actual_job_cr_name,
                        )
                    except ApiException as e:
                        if e.status == 404: # Still creating or transient issue
                            print(f"RayJob '{actual_job_cr_name}' status not found yet, retrying...")
                            time.sleep(job_polling_interval_seconds)
                            continue
                        raise # Other API errors should be raised

                    status_field = ray_job_status_cr.get("status", {})
                    job_deployment_status = status_field.get("jobDeploymentStatus", "UNKNOWN")
                    current_job_status = status_field.get("jobStatus", "PENDING") # PENDING, RUNNING, SUCCEEDED, FAILED, STOPPED
                    
                    dashboard_url = status_field.get("dashboardURL", dashboard_url)
                    ray_cluster_name_actual = status_field.get("rayClusterName", ray_cluster_name_actual)
                    # Ray's internal job submission ID might also appear in status
                    returned_job_submission_id = status_field.get("jobId", job_submission_id)


                    final_job_status = current_job_status
                    print(
                        f"RayJob '{actual_job_cr_name}' status: JobDeployment='{job_deployment_status}', Job='{current_job_status}'"
                    )

                    if current_job_status in ["SUCCEEDED", "FAILED", "STOPPED"]:
                        break
                    
                    # Check for overall timeout
                    if job_timeout_seconds and (time.time() - start_time) > job_timeout_seconds:
                        # Try to get one last status update before raising timeout
                        try:
                            ray_job_status_cr_final = k8s_co_api.get_namespaced_custom_object_status(
                                group="ray.io", version="v1", namespace=namespace, plural="rayjobs", name=actual_job_cr_name
                            )
                            status_field_final = ray_job_status_cr_final.get("status", {})
                            final_job_status = status_field_final.get("jobStatus", final_job_status)
                            returned_job_submission_id = status_field_final.get("jobId", returned_job_submission_id)
                            dashboard_url = status_field_final.get("dashboardURL", dashboard_url)
                            ray_cluster_name_actual = status_field_final.get("rayClusterName", ray_cluster_name_actual)
                        except Exception:
                            pass # Ignore if final status fetch fails
                        raise TimeoutError(
                            f"RayJob '{actual_job_cr_name}' timed out after {job_timeout_seconds} seconds. Last status: {final_job_status}"
                        )

                    time.sleep(job_polling_interval_seconds)
                
                print(f"RayJob '{actual_job_cr_name}' finished with status: {final_job_status}")
            else:
                # If not waiting, we don't have a definitive final status yet.
                # We can try to fetch current status once.
                try:
                    ray_job_status_cr = k8s_co_api.get_namespaced_custom_object_status(
                        group="ray.io", version="v1", namespace=namespace, plural="rayjobs", name=actual_job_cr_name
                    )
                    status_field = ray_job_status_cr.get("status", {})
                    final_job_status = status_field.get("jobStatus", "SUBMITTED") # Or PENDING
                    returned_job_submission_id = status_field.get("jobId", job_submission_id)
                    dashboard_url = status_field.get("dashboardURL", dashboard_url)
                    ray_cluster_name_actual = status_field.get("rayClusterName", ray_cluster_name_actual)
                except ApiException as e:
                    if e.status == 404:
                        final_job_status = "SUBMITTED_NOT_FOUND" # CR created but status not immediately available
                    else:
                        print(f"Warning: Could not fetch initial status for RayJob '{actual_job_cr_name}': {e}")
                        final_job_status = "UNKNOWN_API_ERROR"

            return {
                "job_cr_name": actual_job_cr_name,
                "job_submission_id": returned_job_submission_id, # This is Ray's internal job id
                "job_status": final_job_status,
                "dashboard_url": dashboard_url,
                "ray_cluster_name": ray_cluster_name_actual,
            }

        except ApiException as e:
            print(f"Kubernetes API error during RayJob '{actual_job_cr_name}' management: {e.reason} (status: {e.status})")
            # Attempt to get final status if job was created
            final_status_on_error = "ERROR_BEFORE_SUBMISSION"
            if actual_job_cr_name: # if name was generated, implies we tried to create
                try:
                    ray_job_status_cr = k8s_co_api.get_namespaced_custom_object_status(
                        group="ray.io", version="v1", namespace=namespace, plural="rayjobs", name=actual_job_cr_name
                    )
                    status_field = ray_job_status_cr.get("status", {})
                    final_status_on_error = status_field.get("jobStatus", "UNKNOWN_AFTER_K8S_ERROR")
                except Exception: # Nested try-except for cleanup status fetch
                    final_status_on_error = "UNKNOWN_FINAL_STATUS_FETCH_FAILED"
            
            # If the RayJob CR was created and shutdown_after_job_finishes is false, it might be left orphaned.
            # This function does not manage deletion of the RayJob CR itself if shutdown_after_job_finishes is false.
            # KubeRay handles RayCluster deletion based on RayJob's shutdown_after_job_finishes.
            raise # Re-raise the original ApiException
        except Exception as e:
            print(f"An unexpected error occurred during managed RayJob execution for '{actual_job_cr_name}': {e}")
            # Similar logic for trying to get final status
            raise


def list_all_clusters(namespace: str, print_to_console: bool = True):
    """
    Returns (and prints by default) a list of all clusters in a given namespace.
    """
    clusters = _get_ray_clusters(namespace)
    if print_to_console:
        pretty_print.print_clusters(clusters)
    return clusters


def list_all_queued(
    namespace: str, print_to_console: bool = True, appwrapper: bool = False
):
    """
    Returns (and prints by default) a list of all currently queued-up Ray Clusters
    in a given namespace.
    """
    if appwrapper:
        resources = _get_app_wrappers(namespace, filter=[AppWrapperStatus.SUSPENDED])
        if print_to_console:
            pretty_print.print_app_wrappers_status(resources)
    else:
        resources = _get_ray_clusters(
            namespace, filter=[RayClusterStatus.READY, RayClusterStatus.SUSPENDED]
        )
        if print_to_console:
            pretty_print.print_ray_clusters_status(resources)
    return resources


def get_current_namespace():  # pragma: no cover
    """
    Retrieves the current Kubernetes namespace.

    Returns:
        str:
            The current namespace or None if not found.
    """
    if os.path.isfile("/var/run/secrets/kubernetes.io/serviceaccount/namespace"):
        try:
            file = open("/var/run/secrets/kubernetes.io/serviceaccount/namespace", "r")
            active_context = file.readline().strip("\n")
            return active_context
        except Exception as e:
            print("Unable to find current namespace")
    print("trying to gather from current context")
    try:
        _, active_context = config.list_kube_config_contexts(config_check())
    except Exception as e:
        return _kube_api_error_handling(e)
    try:
        return active_context["context"]["namespace"]
    except KeyError:
        return None


def get_cluster(
    cluster_name: str,
    namespace: str = "default",
    verify_tls: bool = True,
    write_to_file: bool = False,
):
    """
    Retrieves an existing Ray Cluster or AppWrapper as a Cluster object.

    This function fetches an existing Ray Cluster or AppWrapper from the Kubernetes cluster and returns
    it as a `Cluster` object, including its YAML configuration under `Cluster.resource_yaml`.

    Args:
        cluster_name (str):
            The name of the Ray Cluster or AppWrapper.
        namespace (str, optional):
            The Kubernetes namespace where the Ray Cluster or AppWrapper is located. Default is "default".
        verify_tls (bool, optional):
            Whether to verify TLS when connecting to the cluster. Default is True.
        write_to_file (bool, optional):
            If True, writes the resource configuration to a YAML file. Default is False.

    Returns:
        Cluster:
            A Cluster object representing the retrieved Ray Cluster or AppWrapper.

    Raises:
        Exception:
            If the Ray Cluster or AppWrapper cannot be found or does not exist.
    """
    config_check()
    api_instance = client.CustomObjectsApi(get_api_client())
    # Check/Get the AppWrapper if it exists
    is_appwrapper = _check_aw_exists(cluster_name, namespace)
    if is_appwrapper:
        try:
            resource = api_instance.get_namespaced_custom_object(
                group="workload.codeflare.dev",
                version="v1beta2",
                namespace=namespace,
                plural="appwrappers",
                name=cluster_name,
            )
            resource_extraction = resource["spec"]["components"][0]["template"]
        except Exception as e:
            return _kube_api_error_handling(e)
    else:
        # Get the Ray Cluster
        try:
            resource = api_instance.get_namespaced_custom_object(
                group="ray.io",
                version="v1",
                namespace=namespace,
                plural="rayclusters",
                name=cluster_name,
            )
            resource_extraction = resource
        except Exception as e:
            return _kube_api_error_handling(e)

    (
        head_extended_resources,
        worker_extended_resources,
    ) = Cluster._head_worker_extended_resources_from_rc_dict(resource_extraction)
    # Create a Cluster Configuration with just the necessary provided parameters
    cluster_config = ClusterConfiguration(
        name=cluster_name,
        namespace=namespace,
        verify_tls=verify_tls,
        write_to_file=write_to_file,
        appwrapper=is_appwrapper,
        head_cpu_limits=resource_extraction["spec"]["headGroupSpec"]["template"][
            "spec"
        ]["containers"][0]["resources"]["requests"]["cpu"],
        head_cpu_requests=resource_extraction["spec"]["headGroupSpec"]["template"][
            "spec"
        ]["containers"][0]["resources"]["limits"]["cpu"],
        head_memory_limits=resource_extraction["spec"]["headGroupSpec"]["template"][
            "spec"
        ]["containers"][0]["resources"]["requests"]["memory"],
        head_memory_requests=resource_extraction["spec"]["headGroupSpec"]["template"][
            "spec"
        ]["containers"][0]["resources"]["limits"]["memory"],
        num_workers=resource_extraction["spec"]["workerGroupSpecs"][0]["minReplicas"],
        worker_cpu_limits=resource_extraction["spec"]["workerGroupSpecs"][0][
            "template"
        ]["spec"]["containers"][0]["resources"]["limits"]["cpu"],
        worker_cpu_requests=resource_extraction["spec"]["workerGroupSpecs"][0][
            "template"
        ]["spec"]["containers"][0]["resources"]["requests"]["cpu"],
        worker_memory_limits=resource_extraction["spec"]["workerGroupSpecs"][0][
            "template"
        ]["spec"]["containers"][0]["resources"]["requests"]["memory"],
        worker_memory_requests=resource_extraction["spec"]["workerGroupSpecs"][0][
            "template"
        ]["spec"]["containers"][0]["resources"]["limits"]["memory"],
        head_extended_resource_requests=head_extended_resources,
        worker_extended_resource_requests=worker_extended_resources,
    )
    # 1. Prepare RayClusterSpec from ClusterConfiguration
    # Create a temporary config with appwrapper=False to ensure build_ray_cluster returns RayCluster YAML
    temp_cluster_config_dict = cluster_config.dict(exclude_none=True) # Assuming Pydantic V1 or similar .dict() method
    temp_cluster_config_dict['appwrapper'] = False
    temp_cluster_config_for_spec = ClusterConfiguration(**temp_cluster_config_dict)
    # Ignore the warning here for the lack of a ClusterConfiguration
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="Please provide a ClusterConfiguration to initialise the Cluster object",
        )
        cluster = Cluster(None)
        cluster.config = temp_cluster_config_for_spec

        # Remove auto-generated fields like creationTimestamp, uid and etc.
        remove_autogenerated_fields(resource)

        if write_to_file:
            cluster.resource_yaml = write_cluster_to_file(cluster, resource)
        else:
            # Update the Cluster's resource_yaml to reflect the retrieved Ray Cluster/AppWrapper
            cluster.resource_yaml = resource
            print(f"Yaml resources loaded for {cluster.config.name}")

        return cluster


def remove_autogenerated_fields(resource):
    """Recursively remove autogenerated fields from a dictionary."""
    if isinstance(resource, dict):
        for key in list(resource.keys()):
            if key in [
                "creationTimestamp",
                "resourceVersion",
                "uid",
                "selfLink",
                "managedFields",
                "finalizers",
                "generation",
                "status",
                "suspend",
                "workload.codeflare.dev/user",  # AppWrapper field
                "workload.codeflare.dev/userid",  # AppWrapper field
                "podSetInfos",  # AppWrapper field
            ]:
                del resource[key]
            else:
                remove_autogenerated_fields(resource[key])
    elif isinstance(resource, list):
        for item in resource:
            remove_autogenerated_fields(item)


# private methods
def _delete_resources(name: str, namespace: str, api_instance: client.CustomObjectsApi):
    api_instance.delete_namespaced_custom_object(
        group="ray.io",
        version="v1",
        namespace=namespace,
        plural="rayclusters",
        name=name,
    )


def _create_resources(yamls, namespace: str, api_instance: client.CustomObjectsApi):
    api_instance.create_namespaced_custom_object(
        group="ray.io",
        version="v1",
        namespace=namespace,
        plural="rayclusters",
        body=yamls,
    )


def _apply_ray_cluster(
    yamls, namespace: str, api_instance: client.CustomObjectsApi, force=False
):
    api_instance.server_side_apply(
        field_manager=CF_SDK_FIELD_MANAGER,
        group="ray.io",
        version="v1",
        namespace=namespace,
        plural="rayclusters",
        body=yamls,
        force_conflicts=force,  # Allow forcing conflicts if needed
    )


def _check_aw_exists(name: str, namespace: str) -> bool:
    try:
        config_check()
        api_instance = client.CustomObjectsApi(get_api_client())
        aws = api_instance.list_namespaced_custom_object(
            group="workload.codeflare.dev",
            version="v1beta2",
            namespace=namespace,
            plural="appwrappers",
        )
    except Exception as e:  # pragma: no cover
        return _kube_api_error_handling(e, print_error=False)
    for aw in aws["items"]:
        if aw["metadata"]["name"] == name:
            return True
    return False


# Cant test this until get_current_namespace is fixed and placed in this function over using `self`
def _get_ingress_domain(self):  # pragma: no cover
    config_check()

    if self.config.namespace != None:
        namespace = self.config.namespace
    else:
        namespace = get_current_namespace()
    domain = None

    if _is_openshift_cluster():
        try:
            api_instance = client.CustomObjectsApi(get_api_client())

            routes = api_instance.list_namespaced_custom_object(
                group="route.openshift.io",
                version="v1",
                namespace=namespace,
                plural="routes",
            )
        except Exception as e:  # pragma: no cover
            return _kube_api_error_handling(e)

        for route in routes["items"]:
            if (
                route["spec"]["port"]["targetPort"] == "client"
                or route["spec"]["port"]["targetPort"] == 10001
            ):
                domain = route["spec"]["host"]
    else:
        try:
            api_client = client.NetworkingV1Api(get_api_client())
            ingresses = api_client.list_namespaced_ingress(namespace)
        except Exception as e:  # pragma: no cover
            return _kube_api_error_handling(e)

        for ingress in ingresses.items:
            if ingress.spec.rules[0].http.paths[0].backend.service.port.number == 10001:
                domain = ingress.spec.rules[0].host
    return domain


def _app_wrapper_status(name, namespace="default") -> Optional[AppWrapper]:
    try:
        config_check()
        api_instance = client.CustomObjectsApi(get_api_client())
        aws = api_instance.list_namespaced_custom_object(
            group="workload.codeflare.dev",
            version="v1beta2",
            namespace=namespace,
            plural="appwrappers",
        )
    except Exception as e:  # pragma: no cover
        return _kube_api_error_handling(e)

    for aw in aws["items"]:
        if aw["metadata"]["name"] == name:
            return _map_to_app_wrapper(aw)
    return None


def _ray_cluster_status(name, namespace="default") -> Optional[RayCluster]:
    try:
        config_check()
        api_instance = client.CustomObjectsApi(get_api_client())
        rcs = api_instance.list_namespaced_custom_object(
            group="ray.io",
            version="v1",
            namespace=namespace,
            plural="rayclusters",
        )
    except Exception as e:  # pragma: no cover
        return _kube_api_error_handling(e)

    for rc in rcs["items"]:
        if rc["metadata"]["name"] == name:
            return _map_to_ray_cluster(rc)
    return None


def _get_ray_clusters(
    namespace="default", filter: Optional[List[RayClusterStatus]] = None
) -> List[RayCluster]:
    list_of_clusters = []
    try:
        config_check()
        api_instance = client.CustomObjectsApi(get_api_client())
        rcs = api_instance.list_namespaced_custom_object(
            group="ray.io",
            version="v1",
            namespace=namespace,
            plural="rayclusters",
        )
    except Exception as e:  # pragma: no cover
        return _kube_api_error_handling(e)

    # Get a list of RCs with the filter if it is passed to the function
    if filter is not None:
        for rc in rcs["items"]:
            ray_cluster = _map_to_ray_cluster(rc)
            if filter and ray_cluster.status in filter:
                list_of_clusters.append(ray_cluster)
    else:
        for rc in rcs["items"]:
            list_of_clusters.append(_map_to_ray_cluster(rc))
    return list_of_clusters


def _get_app_wrappers(
    namespace="default", filter=List[AppWrapperStatus]
) -> List[AppWrapper]:
    list_of_app_wrappers = []

    try:
        config_check()
        api_instance = client.CustomObjectsApi(get_api_client())
        aws = api_instance.list_namespaced_custom_object(
            group="workload.codeflare.dev",
            version="v1beta2",
            namespace=namespace,
            plural="appwrappers",
        )
    except Exception as e:  # pragma: no cover
        return _kube_api_error_handling(e)

    for item in aws["items"]:
        app_wrapper = _map_to_app_wrapper(item)
        if filter and app_wrapper.status in filter:
            list_of_app_wrappers.append(app_wrapper)
        else:
            # Unsure what the purpose of the filter is
            list_of_app_wrappers.append(app_wrapper)
    return list_of_app_wrappers


def _map_to_ray_cluster(rc) -> Optional[RayCluster]:
    if "status" in rc and "state" in rc["status"]:
        status = RayClusterStatus(rc["status"]["state"].lower())
    else:
        status = RayClusterStatus.UNKNOWN
    config_check()
    dashboard_url = None
    if _is_openshift_cluster():
        try:
            api_instance = client.CustomObjectsApi(get_api_client())
            routes = api_instance.list_namespaced_custom_object(
                group="route.openshift.io",
                version="v1",
                namespace=rc["metadata"]["namespace"],
                plural="routes",
            )
        except Exception as e:  # pragma: no cover
            return _kube_api_error_handling(e)

        for route in routes["items"]:
            rc_name = rc["metadata"]["name"]
            if route["metadata"]["name"] == f"ray-dashboard-{rc_name}" or route[
                "metadata"
            ]["name"].startswith(f"{rc_name}-ingress"):
                protocol = "https" if route["spec"].get("tls") else "http"
                dashboard_url = f"{protocol}://{route['spec']['host']}"
    else:
        try:
            api_instance = client.NetworkingV1Api(get_api_client())
            ingresses = api_instance.list_namespaced_ingress(
                rc["metadata"]["namespace"]
            )
        except Exception as e:  # pragma no cover
            return _kube_api_error_handling(e)
        for ingress in ingresses.items:
            annotations = ingress.metadata.annotations
            protocol = "http"
            if (
                ingress.metadata.name == f"ray-dashboard-{rc['metadata']['name']}"
                or ingress.metadata.name.startswith(f"{rc['metadata']['name']}-ingress")
            ):
                if annotations == None:
                    protocol = "http"
                elif "route.openshift.io/termination" in annotations:
                    protocol = "https"
            dashboard_url = f"{protocol}://{ingress.spec.rules[0].host}"

    (
        head_extended_resources,
        worker_extended_resources,
    ) = Cluster._head_worker_extended_resources_from_rc_dict(rc)

    return RayCluster(
        name=rc["metadata"]["name"],
        status=status,
        # for now we are not using autoscaling so same replicas is fine
        num_workers=rc["spec"]["workerGroupSpecs"][0]["replicas"],
        worker_mem_limits=rc["spec"]["workerGroupSpecs"][0]["template"]["spec"][
            "containers"
        ][0]["resources"]["limits"]["memory"],
        worker_mem_requests=rc["spec"]["workerGroupSpecs"][0]["template"]["spec"][
            "containers"
        ][0]["resources"]["requests"]["memory"],
        worker_cpu_requests=rc["spec"]["workerGroupSpecs"][0]["template"]["spec"][
            "containers"
        ][0]["resources"]["requests"]["cpu"],
        worker_cpu_limits=rc["spec"]["workerGroupSpecs"][0]["template"]["spec"][
            "containers"
        ][0]["resources"]["limits"]["cpu"],
        worker_extended_resources=worker_extended_resources,
        namespace=rc["metadata"]["namespace"],
        head_cpu_requests=rc["spec"]["headGroupSpec"]["template"]["spec"]["containers"][
            0
        ]["resources"]["requests"]["cpu"],
        head_cpu_limits=rc["spec"]["headGroupSpec"]["template"]["spec"]["containers"][
            0
        ]["resources"]["limits"]["cpu"],
        head_mem_requests=rc["spec"]["headGroupSpec"]["template"]["spec"]["containers"][
            0
        ]["resources"]["requests"]["memory"],
        head_mem_limits=rc["spec"]["headGroupSpec"]["template"]["spec"]["containers"][
            0
        ]["resources"]["limits"]["memory"],
        head_extended_resources=head_extended_resources,
        dashboard=dashboard_url,
    )


def _map_to_app_wrapper(aw) -> AppWrapper:
    if "status" in aw:
        return AppWrapper(
            name=aw["metadata"]["name"],
            status=AppWrapperStatus(aw["status"]["phase"].lower()),
        )
    return AppWrapper(
        name=aw["metadata"]["name"],
        status=AppWrapperStatus("suspended"),
    )


def _copy_to_ray(cluster: Cluster) -> RayCluster:
    ray = RayCluster(
        name=cluster.config.name,
        status=cluster.status(print_to_console=False)[0],
        num_workers=cluster.config.num_workers,
        worker_mem_requests=cluster.config.worker_memory_requests,
        worker_mem_limits=cluster.config.worker_memory_limits,
        worker_cpu_requests=cluster.config.worker_cpu_requests,
        worker_cpu_limits=cluster.config.worker_cpu_limits,
        worker_extended_resources=cluster.config.worker_extended_resource_requests,
        namespace=cluster.config.namespace,
        dashboard=cluster.cluster_dashboard_uri(),
        head_mem_requests=cluster.config.head_memory_requests,
        head_mem_limits=cluster.config.head_memory_limits,
        head_cpu_requests=cluster.config.head_cpu_requests,
        head_cpu_limits=cluster.config.head_cpu_limits,
        head_extended_resources=cluster.config.head_extended_resource_requests,
    )
    if ray.status == CodeFlareClusterStatus.READY:
        ray.status = RayClusterStatus.READY
    return ray


# Check if the routes api exists
def _is_openshift_cluster():
    try:
        config_check()
        for api in client.ApisApi(get_api_client()).get_api_versions().groups:
            for v in api.versions:
                if "route.openshift.io/v1" in v.group_version:
                    return True
        else:
            return False
    except Exception as e:  # pragma: no cover
        return _kube_api_error_handling(e)

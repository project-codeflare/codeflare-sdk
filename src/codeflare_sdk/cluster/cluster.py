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

"""
The cluster sub-module contains the definition of the Cluster object, which represents
the resources requested by the user. It also contains functions for checking the
cluster setup queue, a list of all existing clusters, and the user's working namespace.
"""

import re
from time import sleep
from typing import List, Optional, Tuple, Dict

from kubernetes import config
from ray.job_submission import JobSubmissionClient

from .auth import config_check, api_config_handler
from ..utils import pretty_print
from ..utils.generate_yaml import (
    generate_appwrapper,
    head_worker_gpu_count_from_cluster,
)
from ..utils.kube_api_helpers import _kube_api_error_handling
from ..utils.generate_yaml import is_openshift_cluster

from .config import ClusterConfiguration
from .model import (
    AppWrapper,
    AppWrapperStatus,
    CodeFlareClusterStatus,
    RayCluster,
    RayClusterStatus,
)
from kubernetes import client, config
from kubernetes.utils import parse_quantity
import yaml
import os
import requests

from kubernetes import config
from kubernetes.client.rest import ApiException


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
        self.app_wrapper_yaml = self.create_app_wrapper()
        self._job_submission_client = None
        self.app_wrapper_name = self.config.name

    @property
    def _client_headers(self):
        k8_client = api_config_handler() or client.ApiClient()
        return {
            "Authorization": k8_client.configuration.get_api_key_with_prefix(
                "authorization"
            )
        }

    @property
    def _client_verify_tls(self):
        if not is_openshift_cluster or not self.config.verify_tls:
            return False
        return True

    @property
    def job_client(self):
        k8client = api_config_handler() or client.ApiClient()
        if self._job_submission_client:
            return self._job_submission_client
        if is_openshift_cluster():
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

    def create_app_wrapper(self):
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

        return generate_appwrapper(self)

    # creates a new cluster with the provided or default spec
    def up(self):
        """
        Applies the Cluster yaml, pushing the resource request onto
        the Kueue localqueue.
        """

        # check if RayCluster CustomResourceDefinition exists if not throw RuntimeError
        self._throw_for_no_raycluster()

        namespace = self.config.namespace

        try:
            config_check()
            api_instance = client.CustomObjectsApi(api_config_handler())
            if self.config.appwrapper:
                if self.config.write_to_file:
                    with open(self.app_wrapper_yaml) as f:
                        aw = yaml.load(f, Loader=yaml.FullLoader)
                        api_instance.create_namespaced_custom_object(
                            group="workload.codeflare.dev",
                            version="v1beta2",
                            namespace=namespace,
                            plural="appwrappers",
                            body=aw,
                        )
                else:
                    aw = yaml.safe_load(self.app_wrapper_yaml)
                    api_instance.create_namespaced_custom_object(
                        group="workload.codeflare.dev",
                        version="v1beta2",
                        namespace=namespace,
                        plural="appwrappers",
                        body=aw,
                    )
            else:
                self._component_resources_up(namespace, api_instance)
        except Exception as e:  # pragma: no cover
            return _kube_api_error_handling(e)

    def _throw_for_no_raycluster(self):
        api_instance = client.CustomObjectsApi(api_config_handler())
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
        self._throw_for_no_raycluster()
        try:
            config_check()
            api_instance = client.CustomObjectsApi(api_config_handler())
            if self.config.appwrapper:
                api_instance.delete_namespaced_custom_object(
                    group="workload.codeflare.dev",
                    version="v1beta2",
                    namespace=namespace,
                    plural="appwrappers",
                    name=self.app_wrapper_name,
                )
            else:
                self._component_resources_down(namespace, api_instance)
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
        Waits for requested cluster to be ready, up to an optional timeout (s).
        Checks every five seconds.
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
        if is_openshift_cluster():
            try:
                api_instance = client.CustomObjectsApi(api_config_handler())
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
                api_instance = client.NetworkingV1Api(api_config_handler())
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

    def from_k8_cluster_object(
        rc,
        appwrapper=True,
        write_to_file=False,
        verify_tls=True,
    ):
        config_check()
        machine_types = (
            rc["metadata"]["labels"]["orderedinstance"].split("_")
            if "orderedinstance" in rc["metadata"]["labels"]
            else []
        )

        (
            head_extended_resources,
            worker_extended_resources,
        ) = Cluster._head_worker_extended_resources_from_rc_dict(rc)

        cluster_config = ClusterConfiguration(
            name=rc["metadata"]["name"],
            namespace=rc["metadata"]["namespace"],
            machine_types=machine_types,
            num_workers=rc["spec"]["workerGroupSpecs"][0]["minReplicas"],
            worker_cpu_requests=rc["spec"]["workerGroupSpecs"][0]["template"]["spec"][
                "containers"
            ][0]["resources"]["requests"]["cpu"],
            worker_cpu_limits=rc["spec"]["workerGroupSpecs"][0]["template"]["spec"][
                "containers"
            ][0]["resources"]["limits"]["cpu"],
            worker_memory_requests=rc["spec"]["workerGroupSpecs"][0]["template"][
                "spec"
            ]["containers"][0]["resources"]["requests"]["memory"],
            worker_memory_limits=rc["spec"]["workerGroupSpecs"][0]["template"]["spec"][
                "containers"
            ][0]["resources"]["limits"]["memory"],
            worker_extended_resource_requests=worker_extended_resources,
            head_extended_resource_requests=head_extended_resources,
            image=rc["spec"]["workerGroupSpecs"][0]["template"]["spec"]["containers"][
                0
            ]["image"],
            appwrapper=appwrapper,
            write_to_file=write_to_file,
            verify_tls=verify_tls,
            local_queue=rc["metadata"]
            .get("labels", dict())
            .get("kueue.x-k8s.io/queue-name", None),
        )
        return Cluster(cluster_config)

    def local_client_url(self):
        ingress_domain = _get_ingress_domain(self)
        return f"ray://{ingress_domain}"

    def _component_resources_up(
        self, namespace: str, api_instance: client.CustomObjectsApi
    ):
        if self.config.write_to_file:
            with open(self.app_wrapper_yaml) as f:
                yamls = list(yaml.load_all(f, Loader=yaml.FullLoader))
                for resource in yamls:
                    enable_ingress = (
                        resource.get("spec", {})
                        .get("headGroupSpec", {})
                        .get("enableIngress")
                    )
                    if resource["kind"] == "RayCluster" and enable_ingress is True:
                        name = resource["metadata"]["name"]
                        print(
                            f"Forbidden: RayCluster '{name}' has 'enableIngress' set to 'True'."
                        )
                        return
                _create_resources(yamls, namespace, api_instance)
        else:
            yamls = yaml.load_all(self.app_wrapper_yaml, Loader=yaml.FullLoader)
            _create_resources(yamls, namespace, api_instance)

    def _component_resources_down(
        self, namespace: str, api_instance: client.CustomObjectsApi
    ):
        cluster_name = self.config.name
        if self.config.write_to_file:
            with open(self.app_wrapper_yaml) as f:
                yamls = yaml.load_all(f, Loader=yaml.FullLoader)
                _delete_resources(yamls, namespace, api_instance, cluster_name)
        else:
            yamls = yaml.safe_load_all(self.app_wrapper_yaml)
            _delete_resources(yamls, namespace, api_instance, cluster_name)


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
    if api_config_handler() != None:
        if os.path.isfile("/var/run/secrets/kubernetes.io/serviceaccount/namespace"):
            try:
                file = open(
                    "/var/run/secrets/kubernetes.io/serviceaccount/namespace", "r"
                )
                active_context = file.readline().strip("\n")
                return active_context
            except Exception as e:
                print("Unable to find current namespace")
                return None
        else:
            print("Unable to find current namespace")
            return None
    else:
        if os.path.isfile("/var/run/secrets/kubernetes.io/serviceaccount/namespace"):
            try:
                file = open(
                    "/var/run/secrets/kubernetes.io/serviceaccount/namespace", "r"
                )
                active_context = file.readline().strip("\n")
                return active_context
            except Exception as e:
                print(
                    "unable to gather namespace from /var/run/secrets/kubernetes.io/serviceaccount/namespace trying to gather from current context"
                )
        else:
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
    write_to_file: bool = False,
    verify_tls: bool = True,
):
    try:
        config_check()
        api_instance = client.CustomObjectsApi(api_config_handler())
        rcs = api_instance.list_namespaced_custom_object(
            group="ray.io",
            version="v1",
            namespace=namespace,
            plural="rayclusters",
        )
    except Exception as e:
        return _kube_api_error_handling(e)

    for rc in rcs["items"]:
        if rc["metadata"]["name"] == cluster_name:
            appwrapper = _check_aw_exists(cluster_name, namespace)
            return Cluster.from_k8_cluster_object(
                rc,
                appwrapper=appwrapper,
                write_to_file=write_to_file,
                verify_tls=verify_tls,
            )
    raise FileNotFoundError(
        f"Cluster {cluster_name} is not found in {namespace} namespace"
    )


# private methods
def _delete_resources(
    yamls, namespace: str, api_instance: client.CustomObjectsApi, cluster_name: str
):
    for resource in yamls:
        if resource["kind"] == "RayCluster":
            name = resource["metadata"]["name"]
            api_instance.delete_namespaced_custom_object(
                group="ray.io",
                version="v1",
                namespace=namespace,
                plural="rayclusters",
                name=name,
            )


def _create_resources(yamls, namespace: str, api_instance: client.CustomObjectsApi):
    for resource in yamls:
        if resource["kind"] == "RayCluster":
            api_instance.create_namespaced_custom_object(
                group="ray.io",
                version="v1",
                namespace=namespace,
                plural="rayclusters",
                body=resource,
            )


def _check_aw_exists(name: str, namespace: str) -> bool:
    try:
        config_check()
        api_instance = client.CustomObjectsApi(api_config_handler())
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

    if is_openshift_cluster():
        try:
            api_instance = client.CustomObjectsApi(api_config_handler())

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
            api_client = client.NetworkingV1Api(api_config_handler())
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
        api_instance = client.CustomObjectsApi(api_config_handler())
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
        api_instance = client.CustomObjectsApi(api_config_handler())
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
        api_instance = client.CustomObjectsApi(api_config_handler())
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
        api_instance = client.CustomObjectsApi(api_config_handler())
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
    if is_openshift_cluster():
        try:
            api_instance = client.CustomObjectsApi(api_config_handler())
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
            api_instance = client.NetworkingV1Api(api_config_handler())
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
        workers=rc["spec"]["workerGroupSpecs"][0]["replicas"],
        worker_mem_max=rc["spec"]["workerGroupSpecs"][0]["template"]["spec"][
            "containers"
        ][0]["resources"]["limits"]["memory"],
        worker_mem_min=rc["spec"]["workerGroupSpecs"][0]["template"]["spec"][
            "containers"
        ][0]["resources"]["requests"]["memory"],
        worker_cpu=rc["spec"]["workerGroupSpecs"][0]["template"]["spec"]["containers"][
            0
        ]["resources"]["limits"]["cpu"],
        worker_extended_resources=worker_extended_resources,
        namespace=rc["metadata"]["namespace"],
        head_cpus=rc["spec"]["headGroupSpec"]["template"]["spec"]["containers"][0][
            "resources"
        ]["limits"]["cpu"],
        head_mem=rc["spec"]["headGroupSpec"]["template"]["spec"]["containers"][0][
            "resources"
        ]["limits"]["memory"],
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
        workers=cluster.config.num_workers,
        worker_mem_min=cluster.config.worker_memory_requests,
        worker_mem_max=cluster.config.worker_memory_limits,
        worker_cpu=cluster.config.worker_cpu_requests,
        worker_extended_resources=cluster.config.worker_extended_resource_requests,
        namespace=cluster.config.namespace,
        dashboard=cluster.cluster_dashboard_uri(),
        head_cpus=cluster.config.head_cpus,
        head_mem=cluster.config.head_memory,
        head_extended_resources=cluster.config.head_extended_resource_requests,
    )
    if ray.status == CodeFlareClusterStatus.READY:
        ray.status = RayClusterStatus.READY
    return ray

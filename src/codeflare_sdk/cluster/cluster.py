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

from os import stat
from time import sleep
from typing import List, Optional, Tuple, Dict

import openshift as oc
from ray.job_submission import JobSubmissionClient

from ..utils import pretty_print
from ..utils.generate_yaml import generate_appwrapper
from .config import ClusterConfiguration
from .model import (
    AppWrapper,
    AppWrapperStatus,
    CodeFlareClusterStatus,
    RayCluster,
    RayClusterStatus,
)


class Cluster:
    """
    An object for requesting, bringing up, and taking down resources.
    Can also be used for seeing the resource cluster status and details.

    Note that currently, the underlying implementation is a Ray cluster.
    """

    torchx_scheduler = "ray"

    def __init__(self, config: ClusterConfiguration):
        """
        Create the resource cluster object by passing in a ClusterConfiguration
        (defined in the config sub-module). An AppWrapper will then be generated
        based off of the configured resources to represent the desired cluster
        request.
        """
        self.config = config
        self.app_wrapper_yaml = self.create_app_wrapper()
        self.app_wrapper_name = self.app_wrapper_yaml.split(".")[0]

    def create_app_wrapper(self):
        """
        Called upon cluster object creation, creates an AppWrapper yaml based on
        the specifications of the ClusterConfiguration.
        """

        if self.config.namespace is None:
            self.config.namespace = oc.get_project_name()
            if type(self.config.namespace) is not str:
                raise TypeError(
                    f"Namespace {self.config.namespace} is of type {type(self.config.namespace)}. Check your Kubernetes Authentication."
                )

        name = self.config.name
        namespace = self.config.namespace
        min_cpu = self.config.min_cpus
        max_cpu = self.config.max_cpus
        min_memory = self.config.min_memory
        max_memory = self.config.max_memory
        gpu = self.config.gpu
        workers = self.config.max_worker
        template = self.config.template
        image = self.config.image
        instascale = self.config.instascale
        instance_types = self.config.machine_types
        env = self.config.envs
        return generate_appwrapper(
            name=name,
            namespace=namespace,
            min_cpu=min_cpu,
            max_cpu=max_cpu,
            min_memory=min_memory,
            max_memory=max_memory,
            gpu=gpu,
            workers=workers,
            template=template,
            image=image,
            instascale=instascale,
            instance_types=instance_types,
            env=env,
        )

    # creates a new cluster with the provided or default spec
    def up(self):
        """
        Applies the AppWrapper yaml, pushing the resource request onto
        the MCAD queue.
        """
        namespace = self.config.namespace
        try:
            with oc.project(namespace):
                oc.invoke("apply", ["-f", self.app_wrapper_yaml])
        except oc.OpenShiftPythonException as osp:  # pragma: no cover
            error_msg = osp.result.err()
            if "Unauthorized" in error_msg:
                raise PermissionError(
                    "Action not permitted, have you put in correct/up-to-date auth credentials?"
                )
            raise osp

    def down(self):
        """
        Deletes the AppWrapper yaml, scaling-down and deleting all resources
        associated with the cluster.
        """
        namespace = self.config.namespace
        try:
            with oc.project(namespace):
                oc.invoke("delete", ["AppWrapper", self.app_wrapper_name])
        except oc.OpenShiftPythonException as osp:  # pragma: no cover
            error_msg = osp.result.err()
            if (
                'the server doesn\'t have a resource type "AppWrapper"' in error_msg
                or "forbidden" in error_msg
                or "Unauthorized" in error_msg
                or "Missing or incomplete configuration" in error_msg
            ):
                raise PermissionError(
                    "Action not permitted, have you run auth.login()/cluster.up() yet?"
                )
            elif "not found" in error_msg:
                print("Cluster not found, have you run cluster.up() yet?")
            else:
                raise osp

    def status(
        self, print_to_console: bool = True
    ) -> Tuple[CodeFlareClusterStatus, bool]:
        """
        Returns the requested cluster's status, as well as whether or not
        it is ready for use.
        """
        ready = False
        status = CodeFlareClusterStatus.UNKNOWN
        # check the app wrapper status
        appwrapper = _app_wrapper_status(self.config.name, self.config.namespace)
        if appwrapper:
            if appwrapper.status in [
                AppWrapperStatus.RUNNING,
                AppWrapperStatus.COMPLETED,
                AppWrapperStatus.RUNNING_HOLD_COMPLETION,
            ]:
                ready = False
                status = CodeFlareClusterStatus.STARTING
            elif appwrapper.status in [
                AppWrapperStatus.FAILED,
                AppWrapperStatus.DELETED,
            ]:
                ready = False
                status = CodeFlareClusterStatus.FAILED  # should deleted be separate
                return status, ready  # exit early, no need to check ray status
            elif appwrapper.status in [AppWrapperStatus.PENDING]:
                ready = False
                status = CodeFlareClusterStatus.QUEUED
                if print_to_console:
                    pretty_print.print_app_wrappers_status([appwrapper])
                return (
                    status,
                    ready,
                )  # no need to check the ray status since still in queue

        # check the ray cluster status
        cluster = _ray_cluster_status(self.config.name, self.config.namespace)
        if cluster and not cluster.status == RayClusterStatus.UNKNOWN:
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
                cluster.worker_gpu = self.config.gpu
                pretty_print.print_cluster_status(cluster)
        elif print_to_console:
            if status == CodeFlareClusterStatus.UNKNOWN:
                pretty_print.print_no_resources_found()
            else:
                pretty_print.print_app_wrappers_status([appwrapper], starting=True)

        return status, ready

    def wait_ready(self, timeout: Optional[int] = None):
        """
        Waits for requested cluster to be ready, up to an optional timeout (s).
        Checks every five seconds.
        """
        print("Waiting for requested resources to be set up...")
        ready = False
        status = None
        time = 0
        while not ready:
            status, ready = self.status(print_to_console=False)
            if status == CodeFlareClusterStatus.UNKNOWN:
                print(
                    "WARNING: Current cluster status is unknown, have you run cluster.up yet?"
                )
            if not ready:
                if timeout and time >= timeout:
                    raise TimeoutError(f"wait() timed out after waiting {timeout}s")
                sleep(5)
                time += 5
        print("Requested cluster up and running!")

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
        try:
            with oc.project(self.config.namespace):
                route = oc.invoke(
                    "get", ["route", "-o", "jsonpath='{$.items[*].spec.host}'"]
                )
                route = route.out().split(" ")
                route = [x for x in route if f"ray-dashboard-{self.config.name}" in x]
                route = route[0].strip().strip("'")
            return f"http://{route}"
        except:
            return "Dashboard route not available yet, have you run cluster.up()?"

    def list_jobs(self) -> List:
        """
        This method accesses the head ray node in your cluster and lists the running jobs.
        """
        dashboard_route = self.cluster_dashboard_uri()
        client = JobSubmissionClient(dashboard_route)
        return client.list_jobs()

    def job_status(self, job_id: str) -> str:
        """
        This method accesses the head ray node in your cluster and returns the job status for the provided job id.
        """
        dashboard_route = self.cluster_dashboard_uri()
        client = JobSubmissionClient(dashboard_route)
        return client.get_job_status(job_id)

    def job_logs(self, job_id: str) -> str:
        """
        This method accesses the head ray node in your cluster and returns the logs for the provided job id.
        """
        dashboard_route = self.cluster_dashboard_uri()
        client = JobSubmissionClient(dashboard_route)
        return client.get_job_logs(job_id)

    def torchx_config(
        self, working_dir: str = None, requirements: str = None
    ) -> Dict[str, str]:
        dashboard_address = f"{self.cluster_dashboard_uri().lstrip('http://')}"
        to_return = {
            "cluster_name": self.config.name,
            "dashboard_address": dashboard_address,
        }
        if working_dir:
            to_return["working_dir"] = working_dir
        if requirements:
            to_return["requirements"] = requirements
        return to_return


def list_all_clusters(namespace: str, print_to_console: bool = True):
    """
    Returns (and prints by default) a list of all clusters in a given namespace.
    """
    clusters = _get_ray_clusters(namespace)
    if print_to_console:
        pretty_print.print_clusters(clusters)
    return clusters


def list_all_queued(namespace: str, print_to_console: bool = True):
    """
    Returns (and prints by default) a list of all currently queued-up AppWrappers
    in a given namespace.
    """
    app_wrappers = _get_app_wrappers(
        namespace, filter=[AppWrapperStatus.RUNNING, AppWrapperStatus.PENDING]
    )
    if print_to_console:
        pretty_print.print_app_wrappers_status(app_wrappers)
    return app_wrappers


# private methods


def _app_wrapper_status(name, namespace="default") -> Optional[AppWrapper]:
    cluster = None
    try:
        with oc.project(namespace), oc.timeout(10 * 60):
            cluster = oc.selector(f"appwrapper/{name}").object()
    except oc.OpenShiftPythonException as osp:  # pragma: no cover
        msg = osp.msg
        if "Expected a single object, but selected 0" in msg:
            return cluster
        error_msg = osp.result.err()
        if not (
            'the server doesn\'t have a resource type "appwrapper"' in error_msg
            or "forbidden" in error_msg
            or "Unauthorized" in error_msg
            or "Missing or incomplete configuration" in error_msg
        ):
            raise osp

    if cluster:
        return _map_to_app_wrapper(cluster)

    return cluster


def _ray_cluster_status(name, namespace="default") -> Optional[RayCluster]:
    cluster = None
    try:
        with oc.project(namespace), oc.timeout(10 * 60):
            cluster = oc.selector(f"rayclusters/{name}").object()
    except oc.OpenShiftPythonException as osp:  # pragma: no cover
        msg = osp.msg
        if "Expected a single object, but selected 0" in msg:
            return cluster
        error_msg = osp.result.err()
        if not (
            'the server doesn\'t have a resource type "rayclusters"' in error_msg
            or "forbidden" in error_msg
            or "Unauthorized" in error_msg
            or "Missing or incomplete configuration" in error_msg
        ):
            raise osp

    if cluster:
        return _map_to_ray_cluster(cluster)

    return cluster


def _get_ray_clusters(namespace="default") -> List[RayCluster]:
    list_of_clusters = []
    try:
        with oc.project(namespace), oc.timeout(10 * 60):
            ray_clusters = oc.selector("rayclusters").objects()
    except oc.OpenShiftPythonException as osp:  # pragma: no cover
        error_msg = osp.result.err()
        if (
            'the server doesn\'t have a resource type "rayclusters"' in error_msg
            or "forbidden" in error_msg
            or "Unauthorized" in error_msg
            or "Missing or incomplete configuration" in error_msg
        ):
            raise PermissionError(
                "Action not permitted, have you put in correct/up-to-date auth credentials?"
            )
        else:
            raise osp

    for cluster in ray_clusters:
        list_of_clusters.append(_map_to_ray_cluster(cluster))
    return list_of_clusters


def _get_app_wrappers(
    namespace="default", filter=List[AppWrapperStatus]
) -> List[AppWrapper]:
    list_of_app_wrappers = []

    try:
        with oc.project(namespace), oc.timeout(10 * 60):
            app_wrappers = oc.selector("appwrappers").objects()
    except oc.OpenShiftPythonException as osp:  # pragma: no cover
        error_msg = osp.result.err()
        if (
            'the server doesn\'t have a resource type "appwrappers"' in error_msg
            or "forbidden" in error_msg
            or "Unauthorized" in error_msg
            or "Missing or incomplete configuration" in error_msg
        ):
            raise PermissionError(
                "Action not permitted, have you put in correct/up-to-date auth credentials?"
            )
        else:
            raise osp

    for item in app_wrappers:
        app_wrapper = _map_to_app_wrapper(item)
        if filter and app_wrapper.status in filter:
            list_of_app_wrappers.append(app_wrapper)
        else:
            # Unsure what the purpose of the filter is
            list_of_app_wrappers.append(app_wrapper)
    return list_of_app_wrappers


def _map_to_ray_cluster(cluster) -> Optional[RayCluster]:
    cluster_model = cluster.model
    if type(cluster_model.status.state) == oc.model.MissingModel:
        status = RayClusterStatus.UNKNOWN
    else:
        status = RayClusterStatus(cluster_model.status.state.lower())

    with oc.project(cluster.namespace()), oc.timeout(10 * 60):
        route = (
            oc.selector(f"route/ray-dashboard-{cluster.name()}")
            .object()
            .model.spec.host
        )

    return RayCluster(
        name=cluster.name(),
        status=status,
        # for now we are not using autoscaling so same replicas is fine
        min_workers=cluster_model.spec.workerGroupSpecs[0].replicas,
        max_workers=cluster_model.spec.workerGroupSpecs[0].replicas,
        worker_mem_max=cluster_model.spec.workerGroupSpecs[0]
        .template.spec.containers[0]
        .resources.limits.memory,
        worker_mem_min=cluster_model.spec.workerGroupSpecs[0]
        .template.spec.containers[0]
        .resources.requests.memory,
        worker_cpu=cluster_model.spec.workerGroupSpecs[0]
        .template.spec.containers[0]
        .resources.limits.cpu,
        worker_gpu=0,  # hard to detect currently how many gpus, can override it with what the user asked for
        namespace=cluster.namespace(),
        dashboard=route,
    )


def _map_to_app_wrapper(cluster) -> AppWrapper:
    cluster_model = cluster.model
    return AppWrapper(
        name=cluster.name(),
        status=AppWrapperStatus(cluster_model.status.state.lower()),
        can_run=cluster_model.status.canrun,
        job_state=cluster_model.status.queuejobstate,
    )


def _copy_to_ray(cluster: Cluster) -> RayCluster:
    ray = RayCluster(
        name=cluster.config.name,
        status=cluster.status(print_to_console=False)[0],
        min_workers=cluster.config.min_worker,
        max_workers=cluster.config.max_worker,
        worker_mem_min=cluster.config.min_memory,
        worker_mem_max=cluster.config.max_memory,
        worker_cpu=cluster.config.min_cpus,
        worker_gpu=cluster.config.gpu,
        namespace=cluster.config.namespace,
        dashboard=cluster.cluster_dashboard_uri(),
    )
    if ray.status == CodeFlareClusterStatus.READY:
        ray.status = RayClusterStatus.READY
    return ray

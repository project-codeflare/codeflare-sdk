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
from typing import List, Optional, Tuple

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
        self.config.auth.login()
        namespace = self.config.namespace
        with oc.project(namespace):
            oc.invoke("apply", ["-f", self.app_wrapper_yaml])

    def down(self):
        """
        Deletes the AppWrapper yaml, scaling-down and deleting all resources
        associated with the cluster.
        """
        namespace = self.config.namespace
        with oc.project(namespace):
            oc.invoke("delete", ["AppWrapper", self.app_wrapper_name])
        self.config.auth.logout()

    def status(self, print_to_console: bool = True):
        """
        TO BE UPDATED: Will soon return (and print by default) the cluster's
        status, from AppWrapper submission to setup completion. All resource
        details will be moved to cluster.details().
        """
        cluster = _ray_cluster_status(self.config.name, self.config.namespace)
        if cluster:
            # overriding the number of gpus with requested
            cluster.worker_gpu = self.config.gpu
            if print_to_console:
                pretty_print.print_clusters([cluster])
            return cluster.status
        else:
            if print_to_console:
                pretty_print.print_no_resources_found()
            return None

    def cluster_uri(self) -> str:
        """
        Returns a string containing the cluster's URI.
        """
        return f"ray://{self.config.name}-head-svc.{self.config.namespace}.svc:10001"

    def cluster_dashboard_uri(self, namespace: str = "default") -> str:
        """
        Returns a string containing the cluster's dashboard URI.
        """
        try:
            with oc.project(namespace):
                route = oc.invoke(
                    "get", ["route", "-o", "jsonpath='{$.items[*].spec.host}'"]
                )
                route = route.out().split(" ")
                route = [x for x in route if f"ray-dashboard-{self.config.name}" in x]
                route = route[0].strip().strip("'")
            return f"http://{route}"
        except:
            return "Dashboard route not available yet. Did you run cluster.up()?"

    # checks whether the ray cluster is ready
    def is_ready(self, print_to_console: bool = True):
        """
        TO BE DEPRECATED: functionality will be added into cluster.status().
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
                status = CodeFlareClusterStatus.QUEUED
            elif appwrapper.status in [
                AppWrapperStatus.FAILED,
                AppWrapperStatus.DELETED,
            ]:
                ready = False
                status = CodeFlareClusterStatus.FAILED  # should deleted be separate
                return ready, status  # exit early, no need to check ray status
            elif appwrapper.status in [AppWrapperStatus.PENDING]:
                ready = False
                status = CodeFlareClusterStatus.QUEUED
                if print_to_console:
                    pretty_print.print_app_wrappers_status([appwrapper])
                return (
                    ready,
                    status,
                )  # no need to check the ray status since still in queue

        # check the ray cluster status
        cluster = _ray_cluster_status(self.config.name, self.config.namespace)
        if cluster:
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
                pretty_print.print_clusters([cluster])
        return status, ready

    def list_jobs(self) -> List:
        """
        This method accesses the head ray node in your cluster and lists the running jobs.
        """
        dashboard_route = self.cluster_dashboard_uri(namespace=self.config.namespace)
        client = JobSubmissionClient(dashboard_route)
        return client.list_jobs()

    def job_status(self, job_id: str) -> str:
        """
        This method accesses the head ray node in your cluster and returns the job status for the provided job id.
        """
        dashboard_route = self.cluster_dashboard_uri(namespace=self.config.namespace)
        client = JobSubmissionClient(dashboard_route)
        return client.get_job_status(job_id)

    def job_logs(self, job_id: str) -> str:
        """
        This method accesses the head ray node in your cluster and returns the logs for the provided job id.
        """
        dashboard_route = self.cluster_dashboard_uri(namespace=self.config.namespace)
        client = JobSubmissionClient(dashboard_route)
        return client.get_job_logs(job_id)


def get_current_namespace() -> str:
    """
    Returns the user's current working namespace.
    """
    namespace = oc.invoke("project", ["-q"]).actions()[0].out.strip()
    return namespace


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
    with oc.project(namespace), oc.timeout(10 * 60):
        cluster = oc.selector(f"appwrapper/{name}").object()
    if cluster:
        return _map_to_app_wrapper(cluster)


def _ray_cluster_status(name, namespace="default") -> Optional[RayCluster]:
    # FIXME should we check the appwrapper first
    cluster = None
    try:
        with oc.project(namespace), oc.timeout(10 * 60):
            cluster = oc.selector(f"rayclusters/{name}").object()

        if cluster:
            return _map_to_ray_cluster(cluster)
    except:
        pass
    return cluster


def _get_ray_clusters(namespace="default") -> List[RayCluster]:
    list_of_clusters = []

    with oc.project(namespace), oc.timeout(10 * 60):
        ray_clusters = oc.selector("rayclusters").objects()

    for cluster in ray_clusters:
        list_of_clusters.append(_map_to_ray_cluster(cluster))
    return list_of_clusters


def _get_app_wrappers(
    namespace="default", filter=List[AppWrapperStatus]
) -> List[AppWrapper]:
    list_of_app_wrappers = []

    with oc.project(namespace), oc.timeout(10 * 60):
        app_wrappers = oc.selector("appwrappers").objects()

    for item in app_wrappers:
        app_wrapper = _map_to_app_wrapper(item)
        if filter and app_wrapper.status in filter:
            list_of_app_wrappers.append(app_wrapper)
        else:
            list_of_app_wrappers.append(app_wrapper)
    return list_of_app_wrappers


def _map_to_ray_cluster(cluster) -> RayCluster:
    cluster_model = cluster.model

    with oc.project(cluster.namespace()), oc.timeout(10 * 60):
        route = (
            oc.selector(f"route/ray-dashboard-{cluster.name()}")
            .object()
            .model.spec.host
        )

    return RayCluster(
        name=cluster.name(),
        status=RayClusterStatus(cluster_model.status.state.lower()),
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

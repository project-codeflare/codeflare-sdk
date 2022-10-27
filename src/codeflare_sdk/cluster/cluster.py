from os import stat
from typing import List, Optional, Tuple

import openshift as oc

from ..utils import pretty_print
from ..utils.generate_yaml import generate_appwrapper
from .config import ClusterConfiguration
from .model import (AppWrapper, AppWrapperStatus, CodeFlareClusterStatus,
                    RayCluster, RayClusterStatus)


class Cluster:
    def __init__(self, config: ClusterConfiguration):
        self.config = config
        self.app_wrapper_yaml = self.create_app_wrapper()
        self.app_wrapper_name = self.app_wrapper_yaml.split(".")[0]

    def create_app_wrapper(self):
        name=self.config.name
        min_cpu=self.config.min_cpus
        max_cpu=self.config.max_cpus
        min_memory=self.config.min_memory
        max_memory=self.config.max_memory
        gpu=self.config.gpu
        workers=self.config.max_worker
        template=self.config.template
        image=self.config.image
        instascale=self.config.instascale
        instance_types=self.config.machine_types
        env=self.config.envs
        return generate_appwrapper(name=name, min_cpu=min_cpu, max_cpu=max_cpu, min_memory=min_memory, 
                                   max_memory=max_memory, gpu=gpu, workers=workers, template=template,
                                   image=image, instascale=instascale, instance_types=instance_types, env=env)

    # creates a new cluster with the provided or default spec
    def up(self, namespace='default'):
        with oc.project(namespace):
            oc.invoke("apply", ["-f", self.app_wrapper_yaml])

    def down(self, namespace='default'):
        with oc.project(namespace):
            oc.invoke("delete", ["AppWrapper", self.app_wrapper_name])

    def status(self, print_to_console=True):
        cluster = _ray_cluster_status(self.config.name)
        if cluster:
            #overriding the number of gpus with requested
            cluster.worker_gpu = self.config.gpu
            if print_to_console:
                pretty_print.print_clusters([cluster])
            return cluster.status
        else:
            if print_to_console:
                pretty_print.print_no_resources_found()
            return None
    
    def cluster_uri(self, namespace='default'):
        return f'ray://{self.config.name}-head-svc.{namespace}.svc:10001'

    def cluster_dashboard_uri(self, namespace='default'):
        return f'http://{self.config.name}-head-svc.{namespace}.svc:8265'


    # checks whether the ray cluster is ready
    def is_ready(self, print_to_console=True):
        ready = False
        status = CodeFlareClusterStatus.UNKNOWN
        # check the app wrapper status
        appwrapper = _app_wrapper_status(self.config.name)
        if appwrapper:
            if appwrapper.status in [AppWrapperStatus.RUNNING, AppWrapperStatus.COMPLETED, AppWrapperStatus.RUNNING_HOLD_COMPLETION]:
                ready = False
                status = CodeFlareClusterStatus.QUEUED
            elif appwrapper.status in [AppWrapperStatus.FAILED, AppWrapperStatus.DELETED]:
                ready = False
                status = CodeFlareClusterStatus.FAILED #should deleted be separate
                return ready, status #exit early, no need to check ray status
            elif appwrapper.status in [AppWrapperStatus.PENDING]:
                ready = False
                status = CodeFlareClusterStatus.QUEUED 
                if print_to_console:
                    pretty_print.print_app_wrappers_status([appwrapper])
                return ready, status# no need to check the ray status since still in queue

        # check the ray cluster status
        cluster = _ray_cluster_status(self.config.name)
        if cluster:
            if cluster.status == RayClusterStatus.READY:
                ready = True
                status = CodeFlareClusterStatus.READY                
            elif cluster.status in [RayClusterStatus.UNHEALTHY, RayClusterStatus.FAILED]:
                ready = False
                status = CodeFlareClusterStatus.FAILED
            
            if print_to_console:
                    #overriding the number of gpus with requested
                    cluster.worker_gpu = self.config.gpu
                    pretty_print.print_clusters([cluster])
        return status, ready


def list_all_clusters(print_to_console=True):
    clusters = _get_ray_clusters()
    if print_to_console:
        pretty_print.print_clusters(clusters)
    return clusters


def list_all_queued(print_to_console=True):
    app_wrappers = _get_app_wrappers(filter=[AppWrapperStatus.RUNNING, AppWrapperStatus.PENDING])
    if print_to_console:
        pretty_print.print_app_wrappers_status(app_wrappers)
    return app_wrappers
   


# private methods


def _app_wrapper_status(name, namespace='default') -> Optional[AppWrapper]:
    with oc.project(namespace), oc.timeout(10*60):
        cluster = oc.selector(f'appwrapper/{name}').object()
    if cluster:
        return _map_to_app_wrapper(cluster)


def _ray_cluster_status(name, namespace='default') -> Optional[RayCluster]:
    # FIXME should we check the appwrapper first
    cluster = None
    try:
        with oc.project(namespace), oc.timeout(10*60):
            cluster = oc.selector(f'rayclusters/{name}').object()
        
        if cluster:
            return _map_to_ray_cluster(cluster)
    except:
        pass
    return cluster


def _get_ray_clusters(namespace='default') -> List[RayCluster]:
    list_of_clusters = []

    with oc.project(namespace), oc.timeout(10*60):
        ray_clusters = oc.selector('rayclusters').objects()

    for cluster in ray_clusters:
        list_of_clusters.append(_map_to_ray_cluster(cluster))
    return list_of_clusters



def _get_app_wrappers(filter:List[AppWrapperStatus], namespace='default') -> List[AppWrapper]:
    list_of_app_wrappers = []

    with oc.project(namespace), oc.timeout(10*60):
        app_wrappers = oc.selector('appwrappers').objects()

    for item in app_wrappers:
        app_wrapper = _map_to_app_wrapper(item)
        if filter and app_wrapper.status in filter:
            list_of_app_wrappers.append(app_wrapper)
        else:
            list_of_app_wrappers.append(app_wrapper)
    return list_of_app_wrappers


def _map_to_ray_cluster(cluster) -> RayCluster:
    cluster_model = cluster.model
    return RayCluster(
        name=cluster.name(), status=RayClusterStatus(cluster_model.status.state.lower()),
        #for now we are not using autoscaling so same replicas is fine
        min_workers=cluster_model.spec.workerGroupSpecs[0].replicas,
        max_workers=cluster_model.spec.workerGroupSpecs[0].replicas,
        worker_mem_max=cluster_model.spec.workerGroupSpecs[
            0].template.spec.containers[0].resources.limits.memory,
        worker_mem_min=cluster_model.spec.workerGroupSpecs[
            0].template.spec.containers[0].resources.requests.memory,
        worker_cpu=cluster_model.spec.workerGroupSpecs[0].template.spec.containers[0].resources.limits.cpu,
        worker_gpu=0, #hard to detect currently how many gpus, can override it with what the user asked for
        namespace=cluster.namespace())


def _map_to_app_wrapper(cluster) -> AppWrapper:
    cluster_model = cluster.model
    return AppWrapper(
        name=cluster.name(), status=AppWrapperStatus(cluster_model.status.state.lower()),
        can_run=cluster_model.status.canrun,
        job_state=cluster_model.status.queuejobstate)

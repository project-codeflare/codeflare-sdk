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
Cluster spec building and file volume helpers for RayJobs.

Uses ClusterConfiguration from ray.cluster.config as the single config object.
"""

import logging
from typing import Dict, Any, Tuple

from kubernetes.client import (
    V1Container,
    V1EnvVar,
    V1ExecAction,
    V1Lifecycle,
    V1LifecycleHandler,
    V1LocalObjectReference,
    V1ObjectMeta,
    V1PodSpec,
    V1PodTemplateSpec,
    V1SecretVolumeSource,
    V1Volume,
    V1VolumeMount,
)

from ...common.utils.constants import MOUNT_PATH, RAY_VERSION
from ...common.utils.utils import update_image
from codeflare_sdk.ray.cluster.config import ClusterConfiguration, WorkerGroup

# RHOAIENG-98942: the pieces below are shared with the standalone
# RayCluster builder; both paths must render them identically.
from ..cluster.raycluster_spec import (
    ODH_VOLUMES as _ODH_VOLUMES,
    ODH_VOLUME_MOUNTS as _ODH_VOLUME_MOUNTS,
    build_head_container as _build_head_container,
    build_resource_requirements as _build_resource_requirements,
    build_worker_container as _build_worker_container,
    cpu_limit_to_num_cpus as _cpu_limit_to_num_cpus,
    extended_resources as _extended_resources,
    format_resources_param as _format_resources_param,
    gpu_counts as _gpu_counts,
    merge_storage as _merge_storage,
    worker_replica_counts,
)

logger = logging.getLogger(__name__)


def build_ray_cluster_spec(
    config: ClusterConfiguration, cluster_name: str
) -> Dict[str, Any]:
    """
    Build the inner RayCluster spec dict from a ClusterConfiguration for embedding in a RayJob.

    Produces the same CRD structure as build_ray_cluster.py but returns only
    the spec portion (no apiVersion/kind/metadata) and sets restartPolicy: Never.

    Args:
        config: The cluster configuration.
        cluster_name: Name for the cluster (derived from the RayJob name).

    Returns:
        Dict containing the RayCluster spec for embedding in RayJob CR.
    """
    head_gpu_count, worker_gpu_count = _gpu_counts(config)
    head_resources, worker_resources = _extended_resources(config)

    head_resources_str = _format_resources_param(head_resources)
    worker_resources_str = _format_resources_param(worker_resources)

    autoscaling_enabled = config.enable_autoscaling
    worker_replicas, worker_min_replicas, worker_max_replicas = worker_replica_counts(
        config
    )

    ray_cluster_spec = {
        "rayVersion": RAY_VERSION,
        "enableInTreeAutoscaling": autoscaling_enabled,
        "autoscalerOptions": {
            "upscalingMode": "Default",
            "idleTimeoutSeconds": 60,
            "resources": _build_resource_requirements("500m", "500m", "512Mi", "512Mi"),
        },
        "headGroupSpec": {
            "serviceType": "ClusterIP",
            "enableIngress": False,
            "rayStartParams": {
                "dashboard-host": "0.0.0.0",
                "block": "true",
                "num-cpus": _cpu_limit_to_num_cpus(config.head_cpu_limits),
                "num-gpus": str(head_gpu_count),
                "resources": head_resources_str,
            },
            "template": _build_pod_template(
                container=_build_head_container(config),
                tolerations=config.head_tolerations,
                image_pull_secrets=config.image_pull_secrets,
                volumes=config.volumes,
                annotations=config.annotations,
                labels=config.labels,
            ),
        },
        "workerGroupSpecs": [
            {
                "replicas": worker_replicas,
                "minReplicas": worker_min_replicas,
                "maxReplicas": worker_max_replicas,
                "groupName": f"small-group-{cluster_name}",
                "rayStartParams": {
                    "block": "true",
                    "num-cpus": _cpu_limit_to_num_cpus(config.worker_cpu_limits),
                    "num-gpus": str(worker_gpu_count),
                    "resources": worker_resources_str,
                },
                "template": _build_pod_template(
                    container=_build_worker_container(config),
                    tolerations=config.worker_tolerations,
                    image_pull_secrets=config.image_pull_secrets,
                    volumes=config.volumes,
                    annotations=config.annotations,
                    labels=config.labels,
                ),
            }
        ],
    }

    for wg in config.additional_worker_groups:
        ray_cluster_spec["workerGroupSpecs"].append(
            _build_additional_worker_group_spec(config, wg)
        )

    # No gcsFaultToleranceOptions here, deliberately. RHOAIENG-30720 removed
    # GCS fault tolerance from the lifecycled path in 52a351a because the
    # feature did not work — head pod restarts lost state — and scoped its fix
    # to standalone RayCluster only. #1091 then made ClusterConfiguration the
    # shared config object, so the four GCS FT fields are now accepted and
    # validated here and silently ignored. Emitting them would re-enable an
    # unvalidated feature; rejecting them would restore the old contract.
    # RHOAIENG-98943 owns that decision.

    return ray_cluster_spec


# --- Private helpers for spec building ---


def _build_pod_template(
    container,
    tolerations,
    image_pull_secrets,
    volumes,
    annotations,
    labels=None,
) -> V1PodTemplateSpec:
    pod_spec = V1PodSpec(
        containers=[container],
        volumes=_merge_storage(volumes, _ODH_VOLUMES),
        tolerations=tolerations or None,
        restart_policy="Never",
    )
    if image_pull_secrets:
        pod_spec.image_pull_secrets = [
            V1LocalObjectReference(name=s) for s in image_pull_secrets
        ]
    metadata = None
    if annotations or labels:
        metadata = V1ObjectMeta(
            annotations=annotations if annotations else None,
            labels=labels if labels else None,
        )
    return V1PodTemplateSpec(metadata=metadata, spec=pod_spec)


# --- File volume helpers ---


def validate_secret_size(files: Dict[str, str]) -> None:
    """Validate that combined file size doesn't exceed Kubernetes Secret 1MB limit."""
    total_size = sum(len(content.encode("utf-8")) for content in files.values())
    if total_size > 1024 * 1024:
        raise ValueError(
            f"Secret size exceeds 1MB limit. Total size: {total_size} bytes"
        )


def build_file_secret_spec(
    job_name: str, namespace: str, files: Dict[str, str]
) -> Dict[str, Any]:
    """Build Secret specification for RayJob files."""
    secret_name = f"{job_name}-files"
    return {
        "apiVersion": "v1",
        "kind": "Secret",
        "type": "Opaque",
        "metadata": {
            "name": secret_name,
            "namespace": namespace,
            "labels": {
                "ray.io/job-name": job_name,
                "app.kubernetes.io/managed-by": "codeflare-sdk",
                "app.kubernetes.io/component": "rayjob-files",
            },
        },
        "data": files,
    }


def build_file_volume_specs(
    secret_name: str, mount_path: str = MOUNT_PATH
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Build volume and mount specs for RayJob files."""
    volume_spec = {"name": "ray-job-files", "secret": {"secretName": secret_name}}
    mount_spec = {"name": "ray-job-files", "mountPath": mount_path}
    return volume_spec, mount_spec


def add_file_volumes(
    config: ClusterConfiguration, secret_name: str, mount_path: str = MOUNT_PATH
) -> None:
    """Add file volume and mount to a ClusterConfiguration."""
    volume_name = "ray-job-files"
    if any(getattr(v, "name", None) == volume_name for v in config.volumes):
        logger.debug(f"File volume '{volume_name}' already exists, skipping...")
        return
    if any(getattr(m, "name", None) == volume_name for m in config.volume_mounts):
        logger.debug(f"File volume mount '{volume_name}' already exists, skipping...")
        return
    config.volumes.append(
        V1Volume(name=volume_name, secret=V1SecretVolumeSource(secret_name=secret_name))
    )
    config.volume_mounts.append(V1VolumeMount(name=volume_name, mount_path=mount_path))
    logger.info(
        f"Added file volume '{secret_name}' to cluster config: mount_path={mount_path}"
    )


def _build_additional_worker_group_spec(
    config: ClusterConfiguration, wg: WorkerGroup
) -> dict:
    """Build a single workerGroupSpec dict from a WorkerGroup for embedding in a RayJob."""
    replicas = wg.replicas
    min_replicas = wg.min_replicas if wg.min_replicas is not None else replicas
    max_replicas = wg.max_replicas if wg.max_replicas is not None else replicas

    gpu_count = wg.gpu_count or 0
    extended_resources = dict(wg.extended_resource_requests)
    if wg.gpu_type and wg.gpu_count:
        extended_resources[wg.gpu_type] = wg.gpu_count

    ray_resources: dict = {}
    if wg.gpu_type and wg.gpu_count:
        mapping = config.extended_resource_mapping
        rtype = mapping.get(wg.gpu_type, "GPU")
        if rtype not in {"GPU", "CPU", "memory"}:
            ray_resources[rtype] = wg.gpu_count
    ray_resources_str = _format_resources_param(ray_resources)

    image = wg.image if wg.image else update_image(config.image)
    merged_envs = {**config.envs, **wg.envs}
    tolerations = (
        wg.tolerations if wg.tolerations is not None else config.worker_tolerations
    )

    container = V1Container(
        name="machine-learning",
        image=image,
        image_pull_policy="Always",
        lifecycle=V1Lifecycle(
            pre_stop=V1LifecycleHandler(
                _exec=V1ExecAction(command=["/bin/sh", "-c", "ray stop"])
            )
        ),
        resources=_build_resource_requirements(
            wg.cpu_requests,
            wg.cpu_limits,
            wg.memory_requests,
            wg.memory_limits,
            extended_resources or None,
        ),
        volume_mounts=_merge_storage(config.volume_mounts, _ODH_VOLUME_MOUNTS),
    )

    if merged_envs:
        container.env = [V1EnvVar(name=k, value=v) for k, v in merged_envs.items()]

    merged_labels = {**config.labels, **wg.labels}

    return {
        "replicas": replicas,
        "minReplicas": min_replicas,
        "maxReplicas": max_replicas,
        "groupName": wg.group_name,
        "rayStartParams": {
            "block": "true",
            "num-cpus": _cpu_limit_to_num_cpus(wg.cpu_limits),
            "num-gpus": str(gpu_count),
            "resources": ray_resources_str,
        },
        "template": _build_pod_template(
            container=container,
            tolerations=tolerations,
            image_pull_secrets=config.image_pull_secrets,
            volumes=config.volumes,
            annotations=config.annotations,
            labels=merged_labels,
        ),
    }

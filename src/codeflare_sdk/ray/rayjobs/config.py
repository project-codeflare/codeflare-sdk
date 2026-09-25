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

import json
import logging
from typing import Dict, Any, Tuple, Union

from kubernetes.client import (
    V1ConfigMapVolumeSource,
    V1Container,
    V1ContainerPort,
    V1EnvVar,
    V1ExecAction,
    V1KeyToPath,
    V1Lifecycle,
    V1LifecycleHandler,
    V1LocalObjectReference,
    V1ObjectMeta,
    V1PodSpec,
    V1PodTemplateSpec,
    V1ResourceRequirements,
    V1SecretVolumeSource,
    V1Volume,
    V1VolumeMount,
)

from ...common.utils.constants import MOUNT_PATH, RAY_VERSION
from ...common.utils.utils import update_image
from codeflare_sdk.ray.cluster.config import ClusterConfiguration

logger = logging.getLogger(__name__)


# --- ODH CA cert volumes (same as build_ray_cluster.py) ---

_ODH_VOLUME_MOUNTS = [
    V1VolumeMount(
        mount_path="/etc/pki/tls/certs/odh-trusted-ca-bundle.crt",
        name="odh-trusted-ca-cert",
        sub_path="odh-trusted-ca-bundle.crt",
    ),
    V1VolumeMount(
        mount_path="/etc/ssl/certs/odh-trusted-ca-bundle.crt",
        name="odh-trusted-ca-cert",
        sub_path="odh-trusted-ca-bundle.crt",
    ),
    V1VolumeMount(
        mount_path="/etc/pki/tls/certs/odh-ca-bundle.crt",
        name="odh-ca-cert",
        sub_path="odh-ca-bundle.crt",
    ),
    V1VolumeMount(
        mount_path="/etc/ssl/certs/odh-ca-bundle.crt",
        name="odh-ca-cert",
        sub_path="odh-ca-bundle.crt",
    ),
]

_ODH_VOLUMES = [
    V1Volume(
        name="odh-trusted-ca-cert",
        config_map=V1ConfigMapVolumeSource(
            name="odh-trusted-ca-bundle",
            items=[V1KeyToPath(key="ca-bundle.crt", path="odh-trusted-ca-bundle.crt")],
            optional=True,
        ),
    ),
    V1Volume(
        name="odh-ca-cert",
        config_map=V1ConfigMapVolumeSource(
            name="odh-trusted-ca-bundle",
            items=[V1KeyToPath(key="odh-ca-bundle.crt", path="odh-ca-bundle.crt")],
            optional=True,
        ),
    ),
]


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
    if autoscaling_enabled:
        worker_replicas = config.min_workers
        worker_min_replicas = config.min_workers
        worker_max_replicas = config.max_workers
    else:
        worker_replicas = config.num_workers
        worker_min_replicas = config.num_workers
        worker_max_replicas = config.num_workers

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
                ),
            }
        ],
    }

    return ray_cluster_spec


# --- Private helpers for spec building ---


def _cpu_limit_to_num_cpus(cpu_limit: Union[int, str]) -> str:
    if isinstance(cpu_limit, int):
        return str(max(cpu_limit, 0))
    s = str(cpu_limit).strip()
    if s.endswith("m"):
        return str(max(int(float(s[:-1]) / 1000), 1))
    return str(max(int(float(s)), 1))


def _gpu_counts(config: ClusterConfiguration) -> Tuple[int, int]:
    head_gpus = 0
    worker_gpus = 0
    for k, v in config.head_extended_resource_requests.items():
        if config.extended_resource_mapping.get(k) == "GPU":
            head_gpus += int(v)
    for k, v in config.worker_extended_resource_requests.items():
        if config.extended_resource_mapping.get(k) == "GPU":
            worker_gpus += int(v)
    return head_gpus, worker_gpus


def _extended_resources(config: ClusterConfiguration) -> Tuple[dict, dict]:
    FORBIDDEN = {"GPU", "CPU", "memory"}
    head_res, worker_res = {}, {}
    for k, v in config.head_extended_resource_requests.items():
        rtype = config.extended_resource_mapping.get(k, k)
        if rtype not in FORBIDDEN:
            head_res[rtype] = v + head_res.get(rtype, 0)
    for k, v in config.worker_extended_resource_requests.items():
        rtype = config.extended_resource_mapping.get(k, k)
        if rtype not in FORBIDDEN:
            worker_res[rtype] = v + worker_res.get(rtype, 0)
    return head_res, worker_res


def _format_resources_param(resources: dict) -> str:
    s = json.dumps(resources).replace('"', '\\"')
    return f'"{s}"'


def _build_resource_requirements(
    cpu_requests, cpu_limits, mem_requests, mem_limits, extended=None
):
    reqs = V1ResourceRequirements(
        requests={"cpu": cpu_requests, "memory": mem_requests},
        limits={"cpu": cpu_limits, "memory": mem_limits},
    )
    if extended:
        for k, v in extended.items():
            reqs.limits[k] = v
            reqs.requests[k] = v
    return reqs


def _merge_storage(provided: list, defaults: list) -> list:
    storage = provided.copy()
    if not storage:
        return list(defaults)
    storage.extend(defaults)
    return storage


def _build_head_container(config: ClusterConfiguration) -> V1Container:
    container = V1Container(
        name="ray-head",
        image=update_image(config.image),
        image_pull_policy="Always",
        ports=[
            V1ContainerPort(name="gcs", container_port=6379),
            V1ContainerPort(name="dashboard", container_port=8265),
            V1ContainerPort(name="client", container_port=10001),
        ],
        lifecycle=V1Lifecycle(
            pre_stop=V1LifecycleHandler(
                _exec=V1ExecAction(["/bin/sh", "-c", "ray stop"])
            )
        ),
        resources=_build_resource_requirements(
            config.head_cpu_requests,
            config.head_cpu_limits,
            config.head_memory_requests,
            config.head_memory_limits,
            config.head_extended_resource_requests or None,
        ),
        volume_mounts=_merge_storage(config.volume_mounts, _ODH_VOLUME_MOUNTS),
    )
    if config.envs:
        container.env = [V1EnvVar(name=k, value=v) for k, v in config.envs.items()]
    return container


def _build_worker_container(config: ClusterConfiguration) -> V1Container:
    container = V1Container(
        name="machine-learning",
        image=update_image(config.image),
        image_pull_policy="Always",
        lifecycle=V1Lifecycle(
            pre_stop=V1LifecycleHandler(
                _exec=V1ExecAction(["/bin/sh", "-c", "ray stop"])
            )
        ),
        resources=_build_resource_requirements(
            config.worker_cpu_requests,
            config.worker_cpu_limits,
            config.worker_memory_requests,
            config.worker_memory_limits,
            config.worker_extended_resource_requests or None,
        ),
        volume_mounts=_merge_storage(config.volume_mounts, _ODH_VOLUME_MOUNTS),
    )
    if config.envs:
        container.env = [V1EnvVar(name=k, value=v) for k, v in config.envs.items()]
    return container


def _build_pod_template(
    container, tolerations, image_pull_secrets, volumes, annotations
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
    metadata = V1ObjectMeta(annotations=annotations) if annotations else None
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

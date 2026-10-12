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

"""
Canonical, side-effect-free pieces of a RayCluster spec (RHOAIENG-98942).

Both spec builders consume ``ClusterConfiguration`` and used to carry their own
copy of everything below — ``build_ray_cluster.py`` for a standalone
RayCluster, ``rayjobs/config.py`` for the ``rayClusterSpec`` embedded in a
RayJob. The copies had already drifted, which is what RHOAIENG-98942 is for, so
the shared pieces live here and both builders delegate.

Nothing in this module touches the Kubernetes API. That matters: the standalone
builder resolves Kueue LocalQueues while rendering and the RayJob builder does
not, so anything that needs the cluster has to stay in the caller rather than
move in here.
"""

import json
from typing import Dict, List, Optional, Tuple, Union

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
    V1ResourceRequirements,
    V1Volume,
    V1VolumeMount,
)

from ...common.utils.utils import update_image
from .config import ClusterConfiguration

# Resource types Ray already models natively, so they must not be repeated as
# custom resources in rayStartParams.
FORBIDDEN_CUSTOM_RESOURCE_TYPES = ["GPU", "CPU", "memory"]

# ODH trusted CA bundle, mounted into every head and worker pod. Previously
# duplicated verbatim in both builders.
ODH_VOLUME_MOUNTS: List[V1VolumeMount] = [
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

ODH_VOLUMES: List[V1Volume] = [
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


def cpu_limit_to_num_cpus(cpu_limit: Union[int, str]) -> str:
    """Render a CPU limit as the integer string Ray's ``num-cpus`` expects."""
    if isinstance(cpu_limit, int):
        return str(max(cpu_limit, 0))
    s = str(cpu_limit).strip()
    if s.endswith("m"):
        return str(max(int(float(s[:-1]) / 1000), 1))
    return str(max(int(float(s)), 1))


def merge_storage(provided: list, defaults: list) -> list:
    """Append the default volumes/mounts to whatever the user supplied."""
    storage = provided.copy()
    if not storage:
        return list(defaults)
    storage.extend(defaults)
    return storage


def build_resource_requirements(
    cpu_requests: Union[int, str],
    cpu_limits: Union[int, str],
    memory_requests: Union[int, str],
    memory_limits: Union[int, str],
    extended: Optional[Dict[str, int]] = None,
) -> V1ResourceRequirements:
    """CPU/memory requests and limits, plus any extended resources.

    Memory is stringified so the Kubernetes client serialises quantities such
    as ``16`` as ``"16G"`` rather than a bare number; CPU is then written back
    unstringified, because Ray accepts the numeric form. Both builders carried
    this shape (RHOAIENG-59978) before it moved here.
    """
    requirements = V1ResourceRequirements(
        requests={"cpu": str(cpu_requests), "memory": str(memory_requests)},
        limits={"cpu": str(cpu_limits), "memory": str(memory_limits)},
    )
    requirements.requests["cpu"] = cpu_requests
    requirements.limits["cpu"] = cpu_limits
    if extended:
        for name, quantity in extended.items():
            requirements.limits[name] = quantity
            requirements.requests[name] = quantity
    return requirements


def gpu_counts(config: ClusterConfiguration) -> Tuple[int, int]:
    """Total GPUs requested for the head and for a worker, respectively."""
    head_gpus = 0
    worker_gpus = 0
    for name, quantity in config.head_extended_resource_requests.items():
        if config.extended_resource_mapping.get(name) == "GPU":
            head_gpus += int(quantity)
    for name, quantity in config.worker_extended_resource_requests.items():
        if config.extended_resource_mapping.get(name) == "GPU":
            worker_gpus += int(quantity)
    return head_gpus, worker_gpus


def extended_resources(config: ClusterConfiguration) -> Tuple[dict, dict]:
    """Non-GPU/CPU/memory resources for the head and worker ``rayStartParams``.

    Keyed by the mapped resource type, so two accelerators sharing a type are
    summed. ``__post_init__`` has already rejected an unmapped key, so the
    fallback to the raw key below never fires in practice.
    """
    head: dict = {}
    worker: dict = {}
    for name, quantity in config.head_extended_resource_requests.items():
        resource_type = config.extended_resource_mapping.get(name, name)
        if resource_type in FORBIDDEN_CUSTOM_RESOURCE_TYPES:
            continue
        head[resource_type] = quantity + head.get(resource_type, 0)
    for name, quantity in config.worker_extended_resource_requests.items():
        resource_type = config.extended_resource_mapping.get(name, name)
        if resource_type in FORBIDDEN_CUSTOM_RESOURCE_TYPES:
            continue
        worker[resource_type] = quantity + worker.get(resource_type, 0)
    return head, worker


def format_resources_param(resources: dict) -> str:
    """Serialise a resources dict the way ``rayStartParams`` expects it."""
    escaped = json.dumps(resources).replace('"', '\\"')
    return f'"{escaped}"'


def image_pull_secrets(config: ClusterConfiguration) -> List[V1LocalObjectReference]:
    """Secret references for pulling the Ray image."""
    return [V1LocalObjectReference(name=name) for name in config.image_pull_secrets]


def env_vars(config: ClusterConfiguration) -> List[V1EnvVar]:
    """User-supplied environment variables, for the head and worker alike."""
    return [V1EnvVar(name=key, value=value) for key, value in config.envs.items()]


def _ray_stop_lifecycle() -> V1Lifecycle:
    return V1Lifecycle(
        pre_stop=V1LifecycleHandler(
            _exec=V1ExecAction(command=["/bin/sh", "-c", "ray stop"])
        )
    )


def build_head_container(config: ClusterConfiguration) -> V1Container:
    """The ``ray-head`` container."""
    container = V1Container(
        name="ray-head",
        image=update_image(config.image),
        image_pull_policy="Always",
        ports=[
            V1ContainerPort(name="gcs", container_port=6379),
            V1ContainerPort(name="dashboard", container_port=8265),
            V1ContainerPort(name="client", container_port=10001),
        ],
        lifecycle=_ray_stop_lifecycle(),
        resources=build_resource_requirements(
            config.head_cpu_requests,
            config.head_cpu_limits,
            config.head_memory_requests,
            config.head_memory_limits,
            config.head_extended_resource_requests or None,
        ),
        volume_mounts=merge_storage(config.volume_mounts, ODH_VOLUME_MOUNTS),
    )
    if config.envs:
        container.env = env_vars(config)
    return container


def build_worker_container(config: ClusterConfiguration) -> V1Container:
    """The ``machine-learning`` worker container."""
    container = V1Container(
        name="machine-learning",
        image=update_image(config.image),
        image_pull_policy="Always",
        lifecycle=_ray_stop_lifecycle(),
        resources=build_resource_requirements(
            config.worker_cpu_requests,
            config.worker_cpu_limits,
            config.worker_memory_requests,
            config.worker_memory_limits,
            config.worker_extended_resource_requests or None,
        ),
        volume_mounts=merge_storage(config.volume_mounts, ODH_VOLUME_MOUNTS),
    )
    if config.envs:
        container.env = env_vars(config)
    return container


def gcs_fault_tolerance_options(config: ClusterConfiguration) -> Optional[dict]:
    """``gcsFaultToleranceOptions``, or None when GCS FT is off.

    Shared so the RayJob path stops dropping it (RHOAIENG-98943).
    """
    if not config.enable_gcs_ft:
        return None

    if not config.redis_address:
        raise ValueError("redis_address must be provided when enable_gcs_ft is True")

    options: dict = {"redisAddress": config.redis_address}

    if config.external_storage_namespace:
        options["externalStorageNamespace"] = config.external_storage_namespace

    if config.redis_password_secret:
        options["redisPassword"] = {
            "valueFrom": {
                "secretKeyRef": {
                    "name": config.redis_password_secret["name"],
                    "key": config.redis_password_secret["key"],
                }
            }
        }

    return options


def worker_replica_counts(config: ClusterConfiguration) -> Tuple[int, int, int]:
    """``(replicas, minReplicas, maxReplicas)`` for the default worker group.

    Autoscaling hands the range to the autoscaler; otherwise all three are
    ``num_workers``.
    """
    if config.enable_autoscaling:
        return config.min_workers, config.min_workers, config.max_workers
    return config.num_workers, config.num_workers, config.num_workers

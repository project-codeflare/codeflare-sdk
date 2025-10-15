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
The config sub-module contains the definition of the ManagedClusterConfig dataclass,
which is used to specify resource requirements and other details when creating a
Cluster object.
"""

import pathlib
from dataclasses import dataclass, field, fields
from typing import Dict, List, Optional, Union, get_args, get_origin, Any, Tuple
from kubernetes.client import (
    V1LocalObjectReference,
    V1SecretVolumeSource,
    V1Toleration,
    V1Volume,
    V1VolumeMount,
    V1ObjectMeta,
    V1Container,
    V1ContainerPort,
    V1Lifecycle,
    V1ExecAction,
    V1LifecycleHandler,
    V1EnvVar,
    V1PodTemplateSpec,
    V1PodSpec,
    V1ResourceRequirements,
)

import logging

from ...common.utils.constants import MOUNT_PATH, RAY_VERSION
from ...common.utils.utils import update_image

logger = logging.getLogger(__name__)

dir = pathlib.Path(__file__).parent.parent.resolve()

# https://docs.ray.io/en/latest/ray-core/scheduling/accelerators.html
DEFAULT_ACCELERATORS = {
    "nvidia.com/gpu": "GPU",
    "intel.com/gpu": "GPU",
    "amd.com/gpu": "GPU",
    "aws.amazon.com/neuroncore": "neuron_cores",
    "google.com/tpu": "TPU",
    "habana.ai/gaudi": "HPU",
    "huawei.com/Ascend910": "NPU",
    "huawei.com/Ascend310": "NPU",
}


@dataclass
class ManagedClusterConfig:
    """
    This dataclass is used to specify resource requirements and other details for RayJobs.
    The cluster name and namespace are automatically derived from the RayJob configuration.

    Args:
        head_accelerators:
            A dictionary of extended resource requests for the head node. ex: {"nvidia.com/gpu": 1}
        head_tolerations:
            List of tolerations for head nodes.
        num_workers:
            The number of workers to create.
        worker_tolerations:
            List of tolerations for worker nodes.
        envs:
            A dictionary of environment variables to set for the cluster.
        image:
            The image to use for the cluster.
        image_pull_secrets:
            A list of image pull secrets to use for the cluster.
        labels:
            A dictionary of labels to apply to the cluster.
        worker_accelerators:
            A dictionary of extended resource requests for each worker. ex: {"nvidia.com/gpu": 1}
        accelerator_configs:
            A dictionary of custom resource mappings to map extended resource requests to RayCluster resource names.
            Defaults to DEFAULT_ACCELERATORS but can be overridden with custom mappings.
        annotations:
            A dictionary of annotations to apply to the Job.
        volumes:
            A list of V1Volume objects to add to the Cluster
        volume_mounts:
            A list of V1VolumeMount objects to add to the Cluster
    """

    head_cpu_requests: Union[int, str] = 2
    head_cpu_limits: Union[int, str] = 2
    head_memory_requests: Union[int, str] = 8
    head_memory_limits: Union[int, str] = 8
    head_accelerators: Dict[str, Union[str, int]] = field(default_factory=dict)
    head_tolerations: Optional[List[V1Toleration]] = None
    worker_cpu_requests: Union[int, str] = 1
    worker_cpu_limits: Union[int, str] = 1
    num_workers: int = 1
    worker_memory_requests: Union[int, str] = 2
    worker_memory_limits: Union[int, str] = 2
    worker_tolerations: Optional[List[V1Toleration]] = None
    envs: Dict[str, str] = field(default_factory=dict)
    image: str = ""
    image_pull_secrets: List[str] = field(default_factory=list)
    labels: Dict[str, str] = field(default_factory=dict)
    worker_accelerators: Dict[str, Union[str, int]] = field(default_factory=dict)
    accelerator_configs: Dict[str, str] = field(
        default_factory=lambda: DEFAULT_ACCELERATORS.copy()
    )
    annotations: Dict[str, str] = field(default_factory=dict)
    volumes: list[V1Volume] = field(default_factory=list)
    volume_mounts: list[V1VolumeMount] = field(default_factory=list)

    def __post_init__(self):
        self.envs["RAY_USAGE_STATS_ENABLED"] = "0"

        self._validate_types()
        self._memory_to_string()
        self._validate_gpu_config(self.head_accelerators)
        self._validate_gpu_config(self.worker_accelerators)

    def _validate_gpu_config(self, gpu_config: Dict[str, int]):
        for k in gpu_config.keys():
            if k not in self.accelerator_configs.keys():
                raise ValueError(
                    f"GPU configuration '{k}' not found in accelerator_configs, available resources are {list(self.accelerator_configs.keys())}, to add more supported resources use accelerator_configs. i.e. accelerator_configs = {{'{k}': 'FOO_BAR'}}"
                )

    def _memory_to_string(self):
        if isinstance(self.head_memory_requests, int):
            self.head_memory_requests = f"{self.head_memory_requests}G"
        if isinstance(self.head_memory_limits, int):
            self.head_memory_limits = f"{self.head_memory_limits}G"
        if isinstance(self.worker_memory_requests, int):
            self.worker_memory_requests = f"{self.worker_memory_requests}G"
        if isinstance(self.worker_memory_limits, int):
            self.worker_memory_limits = f"{self.worker_memory_limits}G"

    def _validate_types(self):
        """Validate the types of all fields in the ManagedClusterConfig dataclass."""
        errors = []
        for field_info in fields(self):
            value = getattr(self, field_info.name)
            expected_type = field_info.type
            if not self._is_type(value, expected_type):
                errors.append(f"'{field_info.name}' should be of type {expected_type}.")

        if errors:
            raise TypeError("Type validation failed:\n" + "\n".join(errors))

    @staticmethod
    def _is_type(value, expected_type):
        """Check if the value matches the expected type."""

        def check_type(value, expected_type):
            origin_type = get_origin(expected_type)
            args = get_args(expected_type)
            if origin_type is Union:
                return any(check_type(value, union_type) for union_type in args)
            if origin_type is list:
                if value is not None:
                    return all(check_type(elem, args[0]) for elem in (value or []))
                else:
                    return True
            if origin_type is dict:
                if value is not None:
                    return all(
                        check_type(k, args[0]) and check_type(v, args[1])
                        for k, v in value.items()
                    )
                else:
                    return True
            if origin_type is tuple:
                return all(check_type(elem, etype) for elem, etype in zip(value, args))
            if expected_type is int:
                return isinstance(value, int) and not isinstance(value, bool)
            if expected_type is bool:
                return isinstance(value, bool)
            return isinstance(value, expected_type)

        return check_type(value, expected_type)

    def build_ray_cluster_spec(self, cluster_name: str) -> Dict[str, Any]:
        """
        Build the RayCluster spec from ManagedClusterConfig for embedding in RayJob.

        Args:
            self: The cluster configuration object (ManagedClusterConfig)
            cluster_name: The name for the cluster (derived from RayJob name)

        Returns:
            Dict containing the RayCluster spec for embedding in RayJob
        """
        ray_cluster_spec = {
            "rayVersion": RAY_VERSION,
            "enableInTreeAutoscaling": False,  # Required for Kueue-managed jobs
            "headGroupSpec": self._build_head_group_spec(),
            "workerGroupSpecs": [self._build_worker_group_spec(cluster_name)],
        }

        return ray_cluster_spec

    def _build_head_group_spec(self) -> Dict[str, Any]:
        """Build the head group specification."""
        return {
            "serviceType": "ClusterIP",
            "enableIngress": False,
            "rayStartParams": self._build_head_ray_params(),
            "template": V1PodTemplateSpec(
                metadata=V1ObjectMeta(annotations=self.annotations),
                spec=self._build_pod_spec(self._build_head_container(), is_head=True),
            ),
        }

    def _build_worker_group_spec(self, cluster_name: str) -> Dict[str, Any]:
        """Build the worker group specification."""
        return {
            "replicas": self.num_workers,
            "minReplicas": self.num_workers,
            "maxReplicas": self.num_workers,
            "groupName": f"worker-group-{cluster_name}",
            "rayStartParams": self._build_worker_ray_params(),
            "template": V1PodTemplateSpec(
                metadata=V1ObjectMeta(annotations=self.annotations),
                spec=self._build_pod_spec(
                    self._build_worker_container(),
                    is_head=False,
                ),
            ),
        }

    def _build_head_ray_params(self) -> Dict[str, str]:
        """Build Ray start parameters for head node."""
        params = {
            "dashboard-host": "0.0.0.0",
            "block": "true",
        }

        # Add GPU count if specified
        if self.head_accelerators:
            gpu_count = sum(
                count
                for resource_type, count in self.head_accelerators.items()
                if "gpu" in resource_type.lower()
            )
            if gpu_count > 0:
                params["num-gpus"] = str(gpu_count)

        return params

    def _build_worker_ray_params(self) -> Dict[str, str]:
        """Build Ray start parameters for worker nodes."""
        params = {
            "block": "true",
        }

        # Add GPU count if specified
        if self.worker_accelerators:
            gpu_count = sum(
                count
                for resource_type, count in self.worker_accelerators.items()
                if "gpu" in resource_type.lower()
            )
            if gpu_count > 0:
                params["num-gpus"] = str(gpu_count)

        return params

    def _build_head_container(self) -> V1Container:
        """Build the head container specification."""
        container = V1Container(
            name="ray-head",
            image=update_image(self.image),
            image_pull_policy="IfNotPresent",  # Always IfNotPresent for RayJobs
            ports=[
                V1ContainerPort(name="gcs", container_port=6379),
                V1ContainerPort(name="dashboard", container_port=8265),
                V1ContainerPort(name="client", container_port=10001),
            ],
            lifecycle=V1Lifecycle(
                pre_stop=V1LifecycleHandler(
                    _exec=V1ExecAction(command=["/bin/sh", "-c", "ray stop"])
                )
            ),
            resources=self._build_resource_requirements(
                self.head_cpu_requests,
                self.head_cpu_limits,
                self.head_memory_requests,
                self.head_memory_limits,
                self.head_accelerators,
            ),
            volume_mounts=self._generate_volume_mounts(),
            env=self._build_env_vars() if hasattr(self, "envs") and self.envs else None,
        )

        return container

    def _build_worker_container(self) -> V1Container:
        """Build the worker container specification."""
        container = V1Container(
            name="ray-worker",
            image=update_image(self.image),
            image_pull_policy="IfNotPresent",  # Always IfNotPresent for RayJobs
            lifecycle=V1Lifecycle(
                pre_stop=V1LifecycleHandler(
                    _exec=V1ExecAction(command=["/bin/sh", "-c", "ray stop"])
                )
            ),
            resources=self._build_resource_requirements(
                self.worker_cpu_requests,
                self.worker_cpu_limits,
                self.worker_memory_requests,
                self.worker_memory_limits,
                self.worker_accelerators,
            ),
            volume_mounts=self._generate_volume_mounts(),
            env=self._build_env_vars() if hasattr(self, "envs") and self.envs else None,
        )

        return container

    def _build_resource_requirements(
        self,
        cpu_requests: Union[int, str],
        cpu_limits: Union[int, str],
        memory_requests: Union[int, str],
        memory_limits: Union[int, str],
        extended_resource_requests: Dict[str, Union[int, str]] = None,
    ) -> V1ResourceRequirements:
        """Build Kubernetes resource requirements."""
        resource_requirements = V1ResourceRequirements(
            requests={"cpu": cpu_requests, "memory": memory_requests},
            limits={"cpu": cpu_limits, "memory": memory_limits},
        )

        # Add extended resources (e.g., GPUs)
        if extended_resource_requests:
            for resource_type, amount in extended_resource_requests.items():
                resource_requirements.limits[resource_type] = amount
                resource_requirements.requests[resource_type] = amount

        return resource_requirements

    def _build_pod_spec(self, container: V1Container, is_head: bool) -> V1PodSpec:
        """Build the pod specification."""
        pod_spec = V1PodSpec(
            containers=[container],
            volumes=self._generate_volumes(),
            restart_policy="Never",  # RayJobs should not restart
        )

        # Add tolerations if specified
        if is_head and hasattr(self, "head_tolerations") and self.head_tolerations:
            pod_spec.tolerations = self.head_tolerations
        elif (
            not is_head
            and hasattr(self, "worker_tolerations")
            and self.worker_tolerations
        ):
            pod_spec.tolerations = self.worker_tolerations

        # Add image pull secrets if specified
        if hasattr(self, "image_pull_secrets") and self.image_pull_secrets:
            pod_spec.image_pull_secrets = [
                V1LocalObjectReference(name=secret)
                for secret in self.image_pull_secrets
            ]

        return pod_spec

    def _generate_volume_mounts(self) -> list:
        """Generate volume mounts for the container."""
        volume_mounts = []

        # Add custom volume mounts if specified
        if hasattr(self, "volume_mounts") and self.volume_mounts:
            volume_mounts.extend(self.volume_mounts)

        return volume_mounts

    def _generate_volumes(self) -> list:
        """Generate volumes for the pod."""
        volumes = []

        # Add custom volumes if specified
        if hasattr(self, "volumes") and self.volumes:
            volumes.extend(self.volumes)

        return volumes

    def _build_env_vars(self) -> list:
        """Build environment variables list."""
        return [V1EnvVar(name=key, value=value) for key, value in self.envs.items()]

    def add_file_volumes(self, secret_name: str, mount_path: str = MOUNT_PATH):
        """
        Add file volume and mount references to cluster configuration.

        Args:
            secret_name: Name of the Secret containing files
            mount_path: Where to mount files in containers (default: /home/ray/scripts)
        """
        # Check if file volume already exists
        volume_name = "ray-job-files"
        existing_volume = next(
            (v for v in self.volumes if getattr(v, "name", None) == volume_name), None
        )
        if existing_volume:
            logger.debug(f"File volume '{volume_name}' already exists, skipping...")
            return

        # Check if file mount already exists
        existing_mount = next(
            (m for m in self.volume_mounts if getattr(m, "name", None) == volume_name),
            None,
        )
        if existing_mount:
            logger.debug(
                f"File volume mount '{volume_name}' already exists, skipping..."
            )
            return

        # Add file volume to cluster configuration
        file_volume = V1Volume(
            name=volume_name, secret=V1SecretVolumeSource(secret_name=secret_name)
        )
        self.volumes.append(file_volume)

        # Add file volume mount to cluster configuration
        file_mount = V1VolumeMount(name=volume_name, mount_path=mount_path)
        self.volume_mounts.append(file_mount)

        logger.info(
            f"Added file volume '{secret_name}' to cluster config: mount_path={mount_path}"
        )

    def validate_secret_size(self, files: Dict[str, str]) -> None:
        total_size = sum(len(content.encode("utf-8")) for content in files.values())
        if total_size > 1024 * 1024:  # 1MB
            raise ValueError(
                f"Secret size exceeds 1MB limit. Total size: {total_size} bytes"
            )

    def build_file_secret_spec(
        self, job_name: str, namespace: str, files: Dict[str, str]
    ) -> Dict[str, Any]:
        """
        Build Secret specification for files

        Args:
            job_name: Name of the RayJob (used for Secret naming)
            namespace: Kubernetes namespace
            files: Dictionary of file_name -> file_content

        Returns:
            Dict: Secret specification ready for Kubernetes API
        """
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
        self, secret_name: str, mount_path: str = MOUNT_PATH
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Build volume and mount specifications for files

        Args:
            secret_name: Name of the Secret containing files
            mount_path: Where to mount files in containers

        Returns:
            Tuple of (volume_spec, mount_spec) as dictionaries
        """
        volume_spec = {"name": "ray-job-files", "secret": {"secretName": secret_name}}

        mount_spec = {"name": "ray-job-files", "mountPath": mount_path}

        return volume_spec, mount_spec

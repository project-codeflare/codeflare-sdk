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
Spec builders for RayCluster.

This mixin contains all code that builds Kubernetes resources, including
standalone RayCluster specs, RayJob-embedded specs, and file handling helpers.
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional, Tuple, Union

import yaml
from kubernetes import client
from kubernetes.client import (
    V1Container,
    V1ContainerPort,
    V1EnvVar,
    V1ExecAction,
    V1Lifecycle,
    V1LifecycleHandler,
    V1LocalObjectReference,
    V1ObjectMeta,
    V1PodSpec,
    V1PodTemplateSpec,
    V1ResourceRequirements,
    V1SecretVolumeSource,
    V1Toleration,
    V1Volume,
    V1VolumeMount,
)
from ...common.kubernetes_cluster.auth import config_check, get_api_client
from ...common.utils.constants import MOUNT_PATH, RAY_VERSION
from ...common.utils.utils import update_image
from .constants import _ODH_VOLUME_MOUNTS, _ODH_VOLUMES

logger = logging.getLogger(__name__)


class RayClusterBuildersMixin:
    """
    Mixin containing spec builders and file handling helpers.

    Methods here construct Kubernetes resource specs. This mixin focuses on
    pure data construction and does not perform Kubernetes API calls.
    Any Kubernetes API queries needed during building (e.g., queue validation)
    are handled by the RayClusterKubernetesHelpersMixin.
    """

    # -------------------------------------------------------------------------
    # RayJob Cluster Spec Building Methods
    # -------------------------------------------------------------------------

    def build_ray_cluster_spec(self, cluster_name: str) -> Dict[str, Any]:
        """
        Build the RayCluster spec for embedding in RayJob.

        Args:
            cluster_name: The name for the cluster (derived from RayJob name).

        Returns:
            Dict containing the RayCluster spec for embedding in RayJob.
        """
        ray_cluster_spec = {
            "rayVersion": RAY_VERSION,
            "enableInTreeAutoscaling": False,  # Required for Kueue-managed jobs.
            "headGroupSpec": self._build_head_group_spec_for_rayjob(),
            "workerGroupSpecs": [
                self._build_worker_group_spec_for_rayjob(cluster_name)
            ],
        }

        return ray_cluster_spec

    def _build_head_group_spec_for_rayjob(self) -> Dict[str, Any]:
        """Build the head group specification for RayJob."""
        return {
            "serviceType": "ClusterIP",
            "enableIngress": False,
            "rayStartParams": self._build_head_ray_params(),
            "template": V1PodTemplateSpec(
                metadata=V1ObjectMeta(annotations=self.annotations),
                spec=self._build_pod_spec_for_rayjob(
                    self._build_head_container_for_rayjob(), is_head=True
                ),
            ),
        }

    def _build_worker_group_spec_for_rayjob(self, cluster_name: str) -> Dict[str, Any]:
        """Build the worker group specification for RayJob."""
        return {
            "replicas": self.num_workers,
            "minReplicas": self.num_workers,
            "maxReplicas": self.num_workers,
            "groupName": f"worker-group-{cluster_name}",
            "rayStartParams": self._build_worker_ray_params(),
            "template": V1PodTemplateSpec(
                metadata=V1ObjectMeta(annotations=self.annotations),
                spec=self._build_pod_spec_for_rayjob(
                    self._build_worker_container_for_rayjob(),
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

        # Add GPU count if specified.
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

        # Add GPU count if specified.
        if self.worker_accelerators:
            gpu_count = sum(
                count
                for resource_type, count in self.worker_accelerators.items()
                if "gpu" in resource_type.lower()
            )
            if gpu_count > 0:
                params["num-gpus"] = str(gpu_count)

        return params

    def _build_head_container_for_rayjob(self) -> V1Container:
        """Build the head container specification for RayJob."""
        container = V1Container(
            name="ray-head",
            image=update_image(self.image),
            image_pull_policy="IfNotPresent",
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
            volume_mounts=self._generate_volume_mounts_for_rayjob(),
            env=self._build_env_vars() if self.envs else None,
        )

        return container

    def _build_worker_container_for_rayjob(self) -> V1Container:
        """Build the worker container specification for RayJob."""
        container = V1Container(
            name="ray-worker",
            image=update_image(self.image),
            image_pull_policy="IfNotPresent",
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
            volume_mounts=self._generate_volume_mounts_for_rayjob(),
            env=self._build_env_vars() if self.envs else None,
        )

        return container

    def _build_resource_requirements(
        self,
        cpu_requests: Union[int, str],
        cpu_limits: Union[int, str],
        memory_requests: Union[int, str],
        memory_limits: Union[int, str],
        extended_resource_requests: Optional[Dict[str, Union[int, str]]] = None,
    ) -> V1ResourceRequirements:
        """Build Kubernetes resource requirements."""
        # Convert integer memory values to strings with 'Gi' suffix (Kubernetes standard).
        # Integer values represent GB and need to be converted to Gi format.
        if isinstance(memory_requests, int):
            memory_requests = f"{memory_requests}Gi"
        if isinstance(memory_limits, int):
            memory_limits = f"{memory_limits}Gi"

        # Convert integer CPU values to strings if needed.
        if isinstance(cpu_requests, int):
            cpu_requests = str(cpu_requests)
        if isinstance(cpu_limits, int):
            cpu_limits = str(cpu_limits)

        resource_requirements = V1ResourceRequirements(
            requests={"cpu": cpu_requests, "memory": memory_requests},
            limits={"cpu": cpu_limits, "memory": memory_limits},
        )

        # Add extended resources (e.g., GPUs).
        if extended_resource_requests:
            for resource_type, amount in extended_resource_requests.items():
                resource_requirements.limits[resource_type] = amount
                resource_requirements.requests[resource_type] = amount

        return resource_requirements

    def _build_pod_spec_for_rayjob(
        self, container: V1Container, is_head: bool
    ) -> V1PodSpec:
        """Build the pod specification for RayJob."""
        pod_spec = V1PodSpec(
            containers=[container],
            volumes=self._generate_volumes_for_rayjob(),
            restart_policy="Never",  # RayJobs should not restart.
        )

        # Add tolerations if specified.
        if is_head and self.head_tolerations:
            pod_spec.tolerations = self.head_tolerations
        elif not is_head and self.worker_tolerations:
            pod_spec.tolerations = self.worker_tolerations

        # Add image pull secrets if specified.
        if self.image_pull_secrets:
            pod_spec.image_pull_secrets = [
                V1LocalObjectReference(name=secret)
                for secret in self.image_pull_secrets
            ]

        return pod_spec

    def _generate_volume_mounts_for_rayjob(self) -> List[V1VolumeMount]:
        """Generate volume mounts for RayJob container."""
        volume_mounts = []
        if self.volume_mounts:
            volume_mounts.extend(self.volume_mounts)
        return volume_mounts

    def _generate_volumes_for_rayjob(self) -> List[V1Volume]:
        """Generate volumes for RayJob pod."""
        volumes = []
        if self.volumes:
            volumes.extend(self.volumes)
        return volumes

    def _build_env_vars(self) -> List[V1EnvVar]:
        """Build environment variables list."""
        return [V1EnvVar(name=key, value=value) for key, value in self.envs.items()]

    # -------------------------------------------------------------------------
    # RayJob File Handling Methods
    # -------------------------------------------------------------------------

    def add_file_volumes(self, secret_name: str, mount_path: str = MOUNT_PATH):
        """
        Add file volume and mount references to cluster configuration.

        Args:
            secret_name: Name of the Secret containing files.
            mount_path: Where to mount files in containers (default: /home/ray/files).
        """
        volume_name = "ray-job-files"

        # Check if file volume already exists.
        existing_volume = next(
            (v for v in self.volumes if getattr(v, "name", None) == volume_name), None
        )
        if existing_volume:
            logger.debug(f"File volume '{volume_name}' already exists, skipping...")
            return

        # Check if file mount already exists.
        existing_mount = next(
            (m for m in self.volume_mounts if getattr(m, "name", None) == volume_name),
            None,
        )
        if existing_mount:
            logger.debug(
                f"File volume mount '{volume_name}' already exists, skipping..."
            )
            return

        # Add file volume to cluster configuration.
        file_volume = V1Volume(
            name=volume_name, secret=V1SecretVolumeSource(secret_name=secret_name)
        )
        self.volumes.append(file_volume)

        # Add file volume mount to cluster configuration.
        file_mount = V1VolumeMount(name=volume_name, mount_path=mount_path)
        self.volume_mounts.append(file_mount)

        logger.info(
            f"Added file volume '{secret_name}' to cluster config: mount_path={mount_path}"
        )

    def validate_secret_size(self, files: Dict[str, str]) -> None:
        """
        Validate that file content doesn't exceed Kubernetes Secret size limit.

        Args:
            files: Dictionary of file_name -> file_content.

        Raises:
            ValueError: If total size exceeds 1MB limit.
        """
        total_size = sum(len(content.encode("utf-8")) for content in files.values())
        if total_size > 1024 * 1024:  # 1MB
            raise ValueError(
                f"Secret size exceeds 1MB limit. Total size: {total_size} bytes"
            )

    def build_file_secret_spec(
        self, job_name: str, namespace: str, files: Dict[str, str]
    ) -> Dict[str, Any]:
        """
        Build Secret specification for files.

        Args:
            job_name: Name of the RayJob (used for Secret naming).
            namespace: Kubernetes namespace.
            files: Dictionary of file_name -> file_content.

        Returns:
            Dict: Secret specification ready for Kubernetes API.
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
        Build volume and mount specifications for files.

        Args:
            secret_name: Name of the Secret containing files.
            mount_path: Where to mount files in containers.

        Returns:
            Tuple of (volume_spec, mount_spec) as dictionaries.
        """
        volume_spec = {"name": "ray-job-files", "secret": {"secretName": secret_name}}
        mount_spec = {"name": "ray-job-files", "mountPath": mount_path}
        return volume_spec, mount_spec

    # -------------------------------------------------------------------------
    # Standalone Cluster Building Methods
    # -------------------------------------------------------------------------

    def _build_standalone_ray_cluster(self) -> Union[Dict, str]:
        """
        Build a standalone RayCluster resource for Kubernetes.

        Returns:
            Dict or str (filename if write_to_file is True) containing the RayCluster spec.
        """
        # GPU/accelerator related variables.
        head_gpu_count, worker_gpu_count = self._head_worker_gpu_count()
        head_resources, worker_resources = self._head_worker_accelerators()

        # Format resources as JSON string for Ray.
        head_resources_str = json.dumps(head_resources).replace('"', '\\"')
        head_resources_str = f'"{head_resources_str}"'
        worker_resources_str = json.dumps(worker_resources).replace('"', '\\"')
        worker_resources_str = f'"{worker_resources_str}"'

        # Create the Ray Cluster resource.
        resource = {
            "apiVersion": "ray.io/v1",
            "kind": "RayCluster",
            "metadata": self._build_metadata(),
            "spec": {
                "rayVersion": RAY_VERSION,
                "enableInTreeAutoscaling": False,
                "autoscalerOptions": {
                    "upscalingMode": "Default",
                    "idleTimeoutSeconds": 60,
                    "resources": self._build_resource_requirements(
                        "500m", "500m", "512Mi", "512Mi"
                    ),
                },
                "headGroupSpec": {
                    "serviceType": "ClusterIP",
                    "enableIngress": False,
                    "rayStartParams": {
                        "dashboard-host": "0.0.0.0",
                        "block": "true",
                        "num-gpus": str(head_gpu_count),
                        "resources": head_resources_str,
                    },
                    "template": V1PodTemplateSpec(
                        metadata=V1ObjectMeta(self.annotations)
                        if self.annotations
                        else None,
                        spec=self._build_standalone_pod_spec(
                            [self._build_head_container_for_standalone()],
                            self.head_tolerations,
                        ),
                    ),
                },
                "workerGroupSpecs": [
                    {
                        "replicas": self.num_workers,
                        "minReplicas": self.num_workers,
                        "maxReplicas": self.num_workers,
                        "groupName": f"small-group-{self.name}",
                        "rayStartParams": {
                            "block": "true",
                            "num-gpus": str(worker_gpu_count),
                            "resources": worker_resources_str,
                        },
                        "template": V1PodTemplateSpec(
                            metadata=V1ObjectMeta(self.annotations)
                            if self.annotations
                            else None,
                            spec=self._build_standalone_pod_spec(
                                [self._build_worker_container_for_standalone()],
                                self.worker_tolerations,
                            ),
                        ),
                    }
                ],
            },
        }

        # Add GCS fault tolerance options if enabled.
        if self.enable_gcs_ft:
            gcs_ft_options = {"redisAddress": self.redis_address}

            if self.external_storage_namespace:
                gcs_ft_options[
                    "externalStorageNamespace"
                ] = self.external_storage_namespace

            if self.redis_password_secret:
                gcs_ft_options["redisPassword"] = {
                    "valueFrom": {
                        "secretKeyRef": {
                            "name": self.redis_password_secret["name"],
                            "key": self.redis_password_secret["key"],
                        }
                    }
                }

            resource["spec"]["gcsFaultToleranceOptions"] = gcs_ft_options

        # Sanitize for Kubernetes API.
        config_check()
        k8s_client = get_api_client() or client.ApiClient()
        resource = k8s_client.sanitize_for_serialization(resource)

        # Write to file if requested.
        if self.write_to_file:
            return self._write_to_file(resource)

        return resource

    def _build_metadata(self) -> V1ObjectMeta:
        """Build metadata for the standalone RayCluster."""
        labels = {
            "controller-tools.k8s.io": "1.0",
            "ray.io/cluster": self.name,
        }
        if self.labels:
            labels.update(self.labels)

        # Add local queue label if Kueue is available.
        self._add_queue_label(labels)

        object_meta = V1ObjectMeta(
            name=self.name,
            namespace=self.namespace,
            labels=labels,
        )

        # Add annotations including NB prefix if in notebook.
        annotations = self._with_nb_annotations(self.annotations.copy())
        if annotations:
            object_meta.annotations = annotations

        return object_meta

    def _with_nb_annotations(self, annotations: dict) -> dict:
        """Add notebook annotations if running in a notebook."""
        nb_prefix = os.environ.get("NB_PREFIX")
        if nb_prefix:
            annotations["app.kubernetes.io/managed-by"] = nb_prefix
        return annotations

    def _add_queue_label(self, labels: dict):
        """
        Add Kueue local queue label if available.

        This method uses Kubernetes API calls (via RayClusterKubernetesHelpersMixin)
        to validate and find the appropriate queue name before adding it to labels.
        """
        # These methods are provided by RayClusterKubernetesHelpersMixin
        # which is part of the RayCluster class via multiple inheritance.
        lq_name = self.local_queue or self._get_default_local_queue()
        if lq_name is None:
            return
        if not self._local_queue_exists():
            print(
                "local_queue provided does not exist or is not in this namespace. "
                "Please provide the correct local_queue name in Cluster Configuration"
            )
            return
        labels["kueue.x-k8s.io/queue-name"] = lq_name

    def _build_standalone_pod_spec(
        self,
        containers: List[V1Container],
        tolerations: Optional[List[V1Toleration]],
    ) -> V1PodSpec:
        """Build pod spec for standalone cluster."""
        # Combine custom volumes with ODH volumes.
        all_volumes = self.volumes.copy() if self.volumes else []
        all_volumes.extend(_ODH_VOLUMES)

        pod_spec = V1PodSpec(
            containers=containers,
            volumes=all_volumes,
            tolerations=tolerations or None,
        )

        if self.image_pull_secrets:
            pod_spec.image_pull_secrets = [
                V1LocalObjectReference(name=secret)
                for secret in self.image_pull_secrets
            ]

        return pod_spec

    def _build_head_container_for_standalone(self) -> V1Container:
        """Build head container for standalone cluster."""
        # Combine custom volume mounts with ODH volume mounts.
        all_volume_mounts = self.volume_mounts.copy() if self.volume_mounts else []
        all_volume_mounts.extend(_ODH_VOLUME_MOUNTS)

        head_container = V1Container(
            name="ray-head",
            image=update_image(self.image),
            image_pull_policy="Always",
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
            volume_mounts=all_volume_mounts,
        )
        if self.envs:
            head_container.env = self._build_env_vars()

        return head_container

    def _build_worker_container_for_standalone(self) -> V1Container:
        """Build worker container for standalone cluster."""
        # Combine custom volume mounts with ODH volume mounts.
        all_volume_mounts = self.volume_mounts.copy() if self.volume_mounts else []
        all_volume_mounts.extend(_ODH_VOLUME_MOUNTS)

        worker_container = V1Container(
            name="ray-worker",
            image=update_image(self.image),
            image_pull_policy="Always",
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
            volume_mounts=all_volume_mounts,
        )

        if self.envs:
            worker_container.env = self._build_env_vars()

        return worker_container

    def _write_to_file(self, resource: dict) -> str:
        """Write the RayCluster resource to a file."""
        directory_path = os.path.expanduser("~/.codeflare/resources/")
        output_file_name = os.path.join(directory_path, self.name + ".yaml")

        directory_path = os.path.dirname(output_file_name)
        if not os.path.exists(directory_path):
            os.makedirs(directory_path)

        with open(output_file_name, "w") as outfile:
            yaml.dump(resource, outfile, default_flow_style=False)

        print(f"Written to: {output_file_name}")
        return output_file_name

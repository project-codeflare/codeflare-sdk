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
Unified cluster configuration model for RayCluster specs.

Merges all parameters from ``ClusterConfiguration`` (ray/cluster/config.py)
and ``ManagedClusterConfig`` (ray/rayjobs/config.py) into a single pydantic v2
model with KubeRay CRD-aligned naming. Consumed by workload wrappers
(``Cluster``, ``RayJob``, future ``RayService``) via composition.
"""

import re
import warnings
from typing import Optional, Union

from kubernetes.client import V1Toleration, V1Volume, V1VolumeMount
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# Canonical accelerator-to-Ray-resource mapping.
# Replaces DEFAULT_RESOURCE_MAPPING in ray/cluster/config.py and
# DEFAULT_ACCELERATORS in ray/rayjobs/config.py (identical content).
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

# Kubernetes metadata.name must be a lowercase RFC 1123 subdomain.
_RFC1123_SUBDOMAIN = re.compile(
    r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?(\.[a-z0-9]([-a-z0-9]*[a-z0-9])?)*$"
)


class RayClusterConfig(BaseModel):
    """
    Unified pydantic v2 configuration model describing a RayCluster spec.

    This model covers the ``rayClusterSpec`` portion embedded in any KubeRay
    custom resource (RayCluster, RayJob, or future RayService). Workload
    wrappers consume it via composition::

        Cluster(config=RayClusterConfig(...))
        RayJob(cluster_config=RayClusterConfig(...))

    Args:
        name:
            Cluster name (RFC 1123 subdomain). Optional because RayJob
            derives the name from the job name.
        namespace:
            Kubernetes namespace. Can be derived from context.
        head_cpu_requests:
            CPU requests for the head node.
        head_cpu_limits:
            CPU limits for the head node.
        head_memory_requests:
            Memory requests for the head node. Bare ints and decimal strings
            are normalized to ``"<value>G"`` format.
        head_memory_limits:
            Memory limits for the head node. Same normalization as requests.
        head_accelerators:
            Extended resource requests for the head node.
            Keys must exist in ``accelerator_configs``.
        head_tolerations:
            Kubernetes tolerations for the head pod.
        worker_cpu_requests:
            CPU requests for each worker node.
        worker_cpu_limits:
            CPU limits for each worker node.
        worker_memory_requests:
            Memory requests for each worker. Same normalization as head.
        worker_memory_limits:
            Memory limits for each worker. Same normalization as head.
        worker_accelerators:
            Extended resource requests for each worker.
            Keys must exist in ``accelerator_configs``.
        worker_tolerations:
            Kubernetes tolerations for worker pods.
        num_workers:
            Number of workers in the single worker group.
        enable_autoscaling:
            Enable Ray in-tree autoscaling. When True, ``min_workers``
            and ``max_workers`` are required.
        min_workers:
            Minimum worker count for autoscaling. Required when
            ``enable_autoscaling`` is True.
        max_workers:
            Maximum worker count for autoscaling. Required when
            ``enable_autoscaling`` is True.
        accelerator_configs:
            Mapping of Kubernetes extended resource names to Ray resource
            names. Defaults to ``DEFAULT_ACCELERATORS``.
        envs:
            Environment variables for cluster pods.
        image:
            Container image. Empty string triggers auto-detection.
        image_pull_secrets:
            Image pull secret names.
        local_queue:
            Kueue LocalQueue name for workload admission.
        priority_class:
            Kueue workload priority class name.
        labels:
            Kubernetes labels for the cluster.
        annotations:
            Kubernetes annotations for the cluster.
        volumes:
            Kubernetes volumes for cluster pods.
        volume_mounts:
            Kubernetes volume mounts for cluster containers.
        write_to_file:
            Write cluster YAML to file for inspection.
        verify_tls:
            Verify TLS when connecting to the cluster.
        enable_usage_stats:
            Capture and send Ray usage stats externally.
        enable_gcs_ft:
            Enable GCS fault tolerance. Requires ``redis_address``.
        redis_address:
            Redis server address for GCS fault tolerance.
        redis_password_secret:
            Kubernetes secret reference for Redis password.
            Must contain ``"name"`` and ``"key"`` keys.
        external_storage_namespace:
            Storage namespace for GCS fault tolerance.
    """

    model_config = ConfigDict(
        extra="forbid", arbitrary_types_allowed=True, validate_default=True
    )

    # --- Identity ---
    name: Optional[str] = None
    namespace: Optional[str] = None

    # --- Head node resources ---
    head_cpu_requests: Union[int, str] = 2
    head_cpu_limits: Union[int, str] = 2
    head_memory_requests: Union[int, str] = 8
    head_memory_limits: Union[int, str] = 8
    head_accelerators: dict[str, Union[str, int]] = Field(default_factory=dict)
    head_tolerations: Optional[list[V1Toleration]] = None

    # --- Worker node resources (flat, single worker group) ---
    worker_cpu_requests: Union[int, str] = 1
    worker_cpu_limits: Union[int, str] = 1
    worker_memory_requests: Union[int, str] = 2
    worker_memory_limits: Union[int, str] = 2
    worker_accelerators: dict[str, Union[str, int]] = Field(default_factory=dict)
    worker_tolerations: Optional[list[V1Toleration]] = None
    num_workers: int = 1

    # --- Autoscaling ---
    enable_autoscaling: bool = False
    min_workers: Optional[int] = None
    max_workers: Optional[int] = None

    # --- Accelerator mapping ---
    accelerator_configs: dict[str, str] = Field(
        default_factory=lambda: DEFAULT_ACCELERATORS.copy()
    )

    # --- Environment and images ---
    envs: dict[str, str] = Field(default_factory=dict)
    image: str = ""
    image_pull_secrets: list[str] = Field(default_factory=list)

    # --- Kueue integration ---
    local_queue: Optional[str] = None
    priority_class: Optional[str] = None

    # --- Kubernetes metadata ---
    labels: dict[str, str] = Field(default_factory=dict)
    annotations: dict[str, str] = Field(default_factory=dict)
    volumes: list[V1Volume] = Field(default_factory=list)
    volume_mounts: list[V1VolumeMount] = Field(default_factory=list)

    # --- Cluster behavior ---
    write_to_file: bool = False
    verify_tls: bool = True
    enable_usage_stats: bool = False

    # --- GCS fault tolerance ---
    enable_gcs_ft: bool = False
    redis_address: Optional[str] = None
    redis_password_secret: Optional[dict[str, str]] = None
    external_storage_namespace: Optional[str] = None

    # ---- Field validators ----

    @field_validator(
        "head_memory_requests",
        "head_memory_limits",
        "worker_memory_requests",
        "worker_memory_limits",
        mode="before",
    )
    @classmethod
    def normalize_memory(cls, v: Union[int, str]) -> str:
        """Normalize bare int or decimal-string memory values to '<N>G' format."""
        if isinstance(v, int):
            return f"{v}G"
        if isinstance(v, str) and v.isdecimal():
            return f"{v}G"
        return v

    @field_validator("name")
    @classmethod
    def validate_cluster_name(cls, v: Optional[str]) -> Optional[str]:
        """Validate cluster name is a valid RFC 1123 subdomain, if provided."""
        if v is not None:
            if not v or not _RFC1123_SUBDOMAIN.match(v):
                raise ValueError(
                    "Cluster name must be a valid RFC 1123 subdomain "
                    "(lowercase, numbers, hyphens/dots; "
                    "start and end with letter or number)."
                )
        return v

    # ---- Model validators ----

    @model_validator(mode="after")
    def _validate_autoscaling(self) -> "RayClusterConfig":
        """Enforce autoscaling constraints on min/max workers."""
        if self.enable_autoscaling:
            if self.min_workers is None or self.max_workers is None:
                raise ValueError(
                    "min_workers and max_workers must be provided "
                    "when enable_autoscaling is True"
                )
            if self.min_workers < 0:
                raise ValueError("min_workers must be >= 0")
            if self.max_workers < self.min_workers:
                raise ValueError("max_workers must be >= min_workers")
        else:
            if self.min_workers is not None or self.max_workers is not None:
                warnings.warn(
                    "min_workers and max_workers are ignored "
                    "when enable_autoscaling is False",
                    UserWarning,
                    stacklevel=2,
                )
        return self

    @model_validator(mode="after")
    def _validate_gcs_ft(self) -> "RayClusterConfig":
        """Enforce GCS fault tolerance constraints."""
        if self.enable_gcs_ft:
            if not self.redis_address:
                raise ValueError(
                    "redis_address must be provided when enable_gcs_ft is True"
                )
        if self.redis_password_secret is not None:
            if (
                "name" not in self.redis_password_secret
                or "key" not in self.redis_password_secret
            ):
                raise ValueError(
                    "redis_password_secret must contain both 'name' and 'key' fields"
                )
        return self

    @model_validator(mode="after")
    def _validate_accelerators(self) -> "RayClusterConfig":
        """Validate accelerator keys exist in accelerator_configs."""
        for k in self.head_accelerators:
            if k not in self.accelerator_configs:
                raise ValueError(
                    f"accelerator '{k}' not found in accelerator_configs, "
                    f"available resources are "
                    f"{list(self.accelerator_configs.keys())}"
                )
        for k in self.worker_accelerators:
            if k not in self.accelerator_configs:
                raise ValueError(
                    f"accelerator '{k}' not found in accelerator_configs, "
                    f"available resources are "
                    f"{list(self.accelerator_configs.keys())}"
                )
        return self

    @model_validator(mode="after")
    def _set_usage_stats_env(self) -> "RayClusterConfig":
        """Set RAY_USAGE_STATS_ENABLED env var based on enable_usage_stats."""
        self.envs["RAY_USAGE_STATS_ENABLED"] = "1" if self.enable_usage_stats else "0"
        return self

    @model_validator(mode="after")
    def _warn_tls_disabled(self) -> "RayClusterConfig":
        """Emit warning when TLS verification is disabled."""
        if not self.verify_tls:
            warnings.warn(
                "TLS verification has been disabled - Endpoint checks will be bypassed",
                UserWarning,
                stacklevel=2,
            )
        return self

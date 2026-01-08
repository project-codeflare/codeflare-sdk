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
Unified RayCluster class that supports both standalone Ray clusters
and RayJob-managed clusters.

This module provides a single class that can be used for:
- Standalone clusters with apply(), down(), status(), wait_ready() methods
- RayJob-managed clusters (passed to RayJob(cluster_config=...))

Usage:
    # Standalone cluster
    cluster = RayCluster(name="my-cluster", namespace="default", num_workers=2)
    cluster.apply()
    cluster.wait_ready()
    cluster.down()

    # RayJob-managed cluster
    cluster_config = RayCluster(num_workers=2, worker_accelerators={"nvidia.com/gpu": 1})
    job = RayJob(job_name="my-job", entrypoint="python train.py", cluster_config=cluster_config)
    job.submit()
"""

import json
import logging
import os
import warnings
import yaml
from dataclasses import dataclass, field, fields
from time import sleep
from typing import Any, Dict, List, Optional, Tuple, Union, get_args, get_origin

import requests
from kubernetes import client
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
    V1Toleration,
    V1Volume,
    V1VolumeMount,
)
from kubernetes.client.rest import ApiException
from kubernetes.dynamic import DynamicClient
from ray.job_submission import JobSubmissionClient

from .status import (
    CodeFlareClusterStatus,
    RayClusterStatus,
)

from ...common import _kube_api_error_handling
from ...common.kubernetes_cluster.auth import config_check, get_api_client
from ...common.utils import get_current_namespace
from ...common.utils.constants import MOUNT_PATH, RAY_VERSION
from ...common.utils.utils import update_image
from ...common.widgets.widgets import cluster_apply_down_buttons, is_notebook

logger = logging.getLogger(__name__)

# Field manager for server-side apply
CF_SDK_FIELD_MANAGER = "codeflare-sdk"

# Forbidden custom resource types (reserved by Ray)
FORBIDDEN_CUSTOM_RESOURCE_TYPES = ["GPU", "CPU", "memory"]

# Default accelerator/extended resource mappings
# https://docs.ray.io/en/latest/ray-core/scheduling/accelerators.html
DEFAULT_ACCELERATOR_CONFIGS = {
    "nvidia.com/gpu": "GPU",
    "intel.com/gpu": "GPU",
    "amd.com/gpu": "GPU",
    "aws.amazon.com/neuroncore": "neuron_cores",
    "google.com/tpu": "TPU",
    "habana.ai/gaudi": "HPU",
    "huawei.com/Ascend910": "NPU",
    "huawei.com/Ascend310": "NPU",
}

# Default ODH certificate volume mounts for OpenShift deployments
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

# Default ODH certificate volumes for OpenShift deployments
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


@dataclass
class RayCluster:
    """
    Unified Ray cluster class supporting both standalone clusters and RayJob-managed clusters.

    This class consolidates functionality from ClusterConfiguration and ManagedClusterConfig,
    providing a single interface for defining and managing Ray clusters.

    For standalone clusters: name is required, use apply()/down()/status()/wait_ready().
    For RayJob-managed clusters: name is optional (auto-generated from job name).

    Args:
        name:
            The name of the cluster. Required for standalone clusters,
            optional for RayJob-managed clusters.
        namespace:
            The Kubernetes namespace for the cluster.
        head_cpu_requests:
            CPU requests for the head node.
        head_cpu_limits:
            CPU limits for the head node.
        head_memory_requests:
            Memory requests for the head node. Integer values are treated as GB.
        head_memory_limits:
            Memory limits for the head node. Integer values are treated as GB.
        head_accelerators:
            Extended resource requests for the head node. ex: {"nvidia.com/gpu": 1}
        head_tolerations:
            List of Kubernetes tolerations for head nodes.
        worker_cpu_requests:
            CPU requests for each worker node.
        worker_cpu_limits:
            CPU limits for each worker node.
        num_workers:
            The number of worker nodes to create.
        worker_memory_requests:
            Memory requests for each worker. Integer values are treated as GB.
        worker_memory_limits:
            Memory limits for each worker. Integer values are treated as GB.
        worker_accelerators:
            Extended resource requests for each worker. ex: {"nvidia.com/gpu": 1}
        worker_tolerations:
            List of Kubernetes tolerations for worker nodes.
        envs:
            Environment variables to set for all cluster pods.
        image:
            Container image for the Ray cluster.
        image_pull_secrets:
            List of Kubernetes secret names for pulling container images.
        labels:
            Labels to apply to the cluster resources.
        annotations:
            Annotations to apply to the cluster pods.
        volumes:
            List of V1Volume objects to add to the cluster.
        volume_mounts:
            List of V1VolumeMount objects to add to the cluster.
        accelerator_configs:
            Mapping of extended resource names to Ray resource names.
            Defaults to DEFAULT_ACCELERATOR_CONFIGS.
        overwrite_default_accelerator_configs:
            Whether to allow overwriting default accelerator configs.
        write_to_file:
            Whether to write cluster configuration to a file (standalone only).
        verify_tls:
            Whether to verify TLS when connecting to the cluster (standalone only).
        local_queue:
            The Kueue LocalQueue name for the cluster.
        enable_gcs_ft:
            Whether to enable GCS fault tolerance (standalone only).
        redis_address:
            Redis address for GCS fault tolerance (required when enable_gcs_ft=True).
        redis_password_secret:
            Kubernetes secret reference for Redis password.
            ex: {"name": "secret-name", "key": "password-key"}
        external_storage_namespace:
            Storage namespace for GCS fault tolerance.
        enable_usage_stats:
            Whether to enable Ray usage statistics collection.
    """

    # Core identification
    name: Optional[str] = None
    namespace: Optional[str] = None

    # Head node resources
    head_cpu_requests: Union[int, str] = 1
    head_cpu_limits: Union[int, str] = 2
    head_memory_requests: Union[int, str] = 5
    head_memory_limits: Union[int, str] = 8
    head_accelerators: Dict[str, Union[str, int]] = field(default_factory=dict)
    head_tolerations: Optional[List[V1Toleration]] = None

    # Worker node resources
    worker_cpu_requests: Union[int, str] = 1
    worker_cpu_limits: Union[int, str] = 1
    num_workers: int = 1
    worker_memory_requests: Union[int, str] = 3
    worker_memory_limits: Union[int, str] = 6
    worker_accelerators: Dict[str, Union[str, int]] = field(default_factory=dict)
    worker_tolerations: Optional[List[V1Toleration]] = None

    # Shared configuration
    envs: Dict[str, str] = field(default_factory=dict)
    image: str = ""
    image_pull_secrets: List[str] = field(default_factory=list)
    labels: Dict[str, str] = field(default_factory=dict)
    annotations: Dict[str, str] = field(default_factory=dict)
    volumes: List[V1Volume] = field(default_factory=list)
    volume_mounts: List[V1VolumeMount] = field(default_factory=list)

    # Accelerator configuration
    accelerator_configs: Dict[str, str] = field(
        default_factory=lambda: DEFAULT_ACCELERATOR_CONFIGS.copy()
    )
    overwrite_default_accelerator_configs: bool = False

    # Standalone cluster specific options
    write_to_file: bool = False
    verify_tls: bool = True
    local_queue: Optional[str] = None

    # GCS fault tolerance options (standalone only)
    enable_gcs_ft: bool = False
    redis_address: Optional[str] = None
    redis_password_secret: Optional[Dict[str, str]] = None
    external_storage_namespace: Optional[str] = None

    # Usage statistics
    enable_usage_stats: bool = False

    def __post_init__(self):
        """Post-initialization validation and processing."""
        # Internal state for standalone cluster lifecycle
        self._resource_yaml = None
        self._job_submission_client = None

        # TLS verification warning
        if not self.verify_tls:
            print(
                "Warning: TLS verification has been disabled - Endpoint checks will be bypassed"
            )

        # Set usage stats environment variable
        if self.enable_usage_stats:
            self.envs["RAY_USAGE_STATS_ENABLED"] = "1"
        else:
            self.envs["RAY_USAGE_STATS_ENABLED"] = "0"

        # Validate GCS fault tolerance configuration
        if self.enable_gcs_ft:
            if not self.redis_address:
                raise ValueError(
                    "redis_address must be provided when enable_gcs_ft is True"
                )

            if self.redis_password_secret and not isinstance(
                self.redis_password_secret, dict
            ):
                raise ValueError(
                    "redis_password_secret must be a dictionary with 'name' and 'key' fields"
                )

            if self.redis_password_secret and (
                "name" not in self.redis_password_secret
                or "key" not in self.redis_password_secret
            ):
                raise ValueError(
                    "redis_password_secret must contain both 'name' and 'key' fields"
                )

        # Run validation and processing
        self._validate_types()
        self._memory_to_string()
        self._str_mem_no_unit_add_GB()
        self._combine_accelerator_configs()
        self._validate_accelerator_config(self.head_accelerators)
        self._validate_accelerator_config(self.worker_accelerators)

        # Display widget if in notebook environment
        if is_notebook():
            cluster_apply_down_buttons(self)

    # -------------------------------------------------------------------------
    # Runtime Properties
    # -------------------------------------------------------------------------

    def _get_current_status(self) -> RayClusterStatus:
        """
        Get the current status of the RayCluster from Kubernetes.

        This method queries the Kubernetes API to get the live cluster state.
        For standalone clusters, this requires name to be set.

        Returns:
            RayClusterStatus enum value representing the current cluster state.
        """
        if not self.name:
            return RayClusterStatus.UNKNOWN

        self._ensure_namespace()
        cluster_status = self._ray_cluster_status(self.name, self.namespace)
        return cluster_status if cluster_status else RayClusterStatus.UNKNOWN

    @property
    def dashboard(self) -> str:
        """
        Get the dashboard URL for the cluster.

        Returns:
            The dashboard URL, or an error message if not available.
        """
        if not self.name:
            return "Dashboard not available - cluster name not set"
        return self.cluster_dashboard_uri()

    # -------------------------------------------------------------------------
    # Validation Methods
    # -------------------------------------------------------------------------

    def _validate_types(self):
        """Validate the types of all fields in the RayCluster dataclass."""
        errors = []
        for field_info in fields(self):
            value = getattr(self, field_info.name)
            expected_type = field_info.type
            if not self._is_type(value, expected_type):
                errors.append(f"'{field_info.name}' should be of type {expected_type}.")

        if errors:
            raise TypeError("Type validation failed:\n" + "\n".join(errors))

    @staticmethod
    def _is_type(value, expected_type) -> bool:
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

    def _memory_to_string(self):
        """Convert integer memory values to string with 'G' suffix."""
        if isinstance(self.head_memory_requests, int):
            self.head_memory_requests = f"{self.head_memory_requests}G"
        if isinstance(self.head_memory_limits, int):
            self.head_memory_limits = f"{self.head_memory_limits}G"
        if isinstance(self.worker_memory_requests, int):
            self.worker_memory_requests = f"{self.worker_memory_requests}G"
        if isinstance(self.worker_memory_limits, int):
            self.worker_memory_limits = f"{self.worker_memory_limits}G"

    def _str_mem_no_unit_add_GB(self):
        """Add 'G' suffix to string memory values that are just numbers."""
        if (
            isinstance(self.worker_memory_requests, str)
            and self.worker_memory_requests.isdecimal()
        ):
            self.worker_memory_requests = f"{self.worker_memory_requests}G"
        if (
            isinstance(self.worker_memory_limits, str)
            and self.worker_memory_limits.isdecimal()
        ):
            self.worker_memory_limits = f"{self.worker_memory_limits}G"

    def _combine_accelerator_configs(self):
        """Combine user accelerator configs with defaults."""
        if overwritten := set(self.accelerator_configs.keys()).intersection(
            DEFAULT_ACCELERATOR_CONFIGS.keys()
        ):
            # Check if user provided custom configs that override defaults
            user_provided_different = any(
                self.accelerator_configs.get(k) != DEFAULT_ACCELERATOR_CONFIGS.get(k)
                for k in overwritten
            )
            if user_provided_different:
                if self.overwrite_default_accelerator_configs:
                    warnings.warn(
                        f"Overwriting default accelerator configs for {overwritten}",
                        UserWarning,
                    )
                else:
                    raise ValueError(
                        f"Accelerator config already exists for {overwritten}, "
                        "set overwrite_default_accelerator_configs=True to overwrite"
                    )
        # Merge defaults with user configs (user configs take precedence)
        self.accelerator_configs = {
            **DEFAULT_ACCELERATOR_CONFIGS,
            **self.accelerator_configs,
        }

    def _validate_accelerator_config(self, accelerators: Dict[str, int]):
        """Validate that accelerator resources are in the config mapping."""
        for k in accelerators.keys():
            if k not in self.accelerator_configs.keys():
                raise ValueError(
                    f"Accelerator '{k}' not found in accelerator_configs, "
                    f"available resources are {list(self.accelerator_configs.keys())}, "
                    f"to add more supported resources use accelerator_configs. "
                    f"i.e. accelerator_configs = {{'{k}': 'FOO_BAR'}}"
                )

    # -------------------------------------------------------------------------
    # Standalone Cluster Lifecycle Methods
    # -------------------------------------------------------------------------

    def apply(self, force: bool = False):
        """
        Apply the RayCluster to Kubernetes using server-side apply.

        This creates or updates the RayCluster in the Kubernetes cluster.
        For standalone cluster management, this is the primary method to
        deploy the cluster.

        Args:
            force: If True, force conflicts during server-side apply.

        Raises:
            ValueError: If name is not set for standalone cluster.
            RuntimeError: If RayCluster CRD is not available.
        """
        if not self.name:
            raise ValueError("name is required for standalone cluster apply()")

        # Ensure namespace is set
        self._ensure_namespace()

        # Build the resource yaml
        self._resource_yaml = self._build_standalone_ray_cluster()

        # Check if RayCluster CRD exists
        self._throw_for_no_raycluster()

        try:
            config_check()
            dynamic_client = DynamicClient(get_api_client())
            crds = dynamic_client.resources
            api_version = "ray.io/v1"
            api_instance = crds.get(api_version=api_version, kind="RayCluster")

            self._apply_ray_cluster(
                self._resource_yaml, self.namespace, api_instance, force=force
            )
            print(
                f"Ray Cluster: '{self.name}' has successfully been applied. "
                "For optimal resource management, you should delete this Ray Cluster when no longer in use."
            )
        except AttributeError as e:
            raise RuntimeError(f"Failed to initialize DynamicClient: {e}")
        except Exception as e:  # pragma: no cover
            if hasattr(e, "status") and e.status == 422:
                print(
                    "WARNING: RayCluster creation rejected due to invalid Kueue configuration. "
                    "Please contact your administrator."
                )
            else:
                print(
                    "WARNING: Failed to create RayCluster due to unexpected error. "
                    "Please contact your administrator."
                )
            return _kube_api_error_handling(e)

    def down(self):
        """
        Delete the RayCluster from Kubernetes.

        This scales down and deletes all resources associated with the cluster.

        Raises:
            ValueError: If name is not set.
            RuntimeError: If RayCluster CRD is not available.
        """
        if not self.name:
            raise ValueError("name is required for standalone cluster down()")

        self._ensure_namespace()
        self._throw_for_no_raycluster()

        try:
            config_check()
            api_instance = client.CustomObjectsApi(get_api_client())
            self._delete_resources(self.name, self.namespace, api_instance)
            print(f"Ray Cluster: '{self.name}' has successfully been deleted")
        except Exception as e:  # pragma: no cover
            return _kube_api_error_handling(e)

    def status(self, print_to_console: bool = True) -> Tuple[str, bool]:
        """
        Get the current status of the RayCluster.

        Args:
            print_to_console: Whether to print status to console.

        Returns:
            Tuple of (status, ready) where status is a CodeFlareClusterStatus
            and ready is True if the cluster is ready for use.
        """
        if not self.name:
            raise ValueError("name is required to check cluster status")

        self._ensure_namespace()
        ready = False
        status = CodeFlareClusterStatus.UNKNOWN

        # Query the cluster status from Kubernetes
        # _ray_cluster_status returns RayClusterStatus enum or None if not found
        ray_status = self._ray_cluster_status(self.name, self.namespace)

        if ray_status is not None:
            # Cluster exists - map RayClusterStatus to CodeFlareClusterStatus
            if ray_status == RayClusterStatus.SUSPENDED:
                ready = False
                status = CodeFlareClusterStatus.SUSPENDED
            elif ray_status == RayClusterStatus.UNKNOWN:
                ready = False
                status = CodeFlareClusterStatus.STARTING
            elif ray_status == RayClusterStatus.READY:
                ready = True
                status = CodeFlareClusterStatus.READY
            elif ray_status in [RayClusterStatus.UNHEALTHY, RayClusterStatus.FAILED]:
                ready = False
                status = CodeFlareClusterStatus.FAILED

            # Print status using self directly
            if print_to_console:
                from . import pretty_print

                pretty_print.print_cluster_status(self)
        elif print_to_console:
            # No cluster found in Kubernetes
            from . import pretty_print

            pretty_print.print_no_resources_found()

        return status, ready

    def wait_ready(self, timeout: Optional[int] = None, dashboard_check: bool = True):
        """
        Wait for the cluster to be ready.

        This method checks the status of the cluster every five seconds until it is
        ready or the timeout is reached. If dashboard_check is enabled, it will also
        check for the readiness of the dashboard.

        Args:
            timeout: Maximum time to wait in seconds. If None, waits indefinitely.
            dashboard_check: Whether to also wait for the dashboard to be ready.

        Raises:
            ValueError: If name is not set.
            TimeoutError: If timeout is reached before the cluster is ready.
        """
        if not self.name:
            raise ValueError("name is required for wait_ready()")

        print("Waiting for requested resources to be set up...")
        time_elapsed = 0

        while True:
            if timeout and time_elapsed >= timeout:
                raise TimeoutError(
                    f"wait() timed out after waiting {timeout}s for cluster to be ready"
                )
            status, ready = self.status(print_to_console=False)
            if status == CodeFlareClusterStatus.UNKNOWN:
                print(
                    "WARNING: Current cluster status is unknown, have you run cluster.apply() yet? "
                    "Run cluster.details() to check if it's ready."
                )
            if ready:
                break
            sleep(5)
            time_elapsed += 5

        print("Requested cluster is up and running!")

        dashboard_wait_logged = False
        while dashboard_check:
            if timeout and time_elapsed >= timeout:
                raise TimeoutError(
                    f"wait() timed out after waiting {timeout}s for dashboard to be ready"
                )
            if self.is_dashboard_ready():
                print("Dashboard is ready!")
                break
            if not dashboard_wait_logged:
                dashboard_uri = self.cluster_dashboard_uri()
                if not dashboard_uri.startswith(("http://", "https://")):
                    print("Waiting for dashboard route/HTTPRoute to be created...")
                else:
                    print(
                        f"Waiting for dashboard to become accessible: {dashboard_uri}"
                    )
                dashboard_wait_logged = True
            sleep(5)
            time_elapsed += 5

    def is_dashboard_ready(self) -> bool:
        """
        Check if the cluster's dashboard is ready and accessible.

        Returns:
            True if the dashboard is ready, False otherwise.
        """
        dashboard_uri = self.cluster_dashboard_uri()
        if dashboard_uri is None:
            return False

        # Check if dashboard_uri is an error message rather than a valid URL
        if not dashboard_uri.startswith(("http://", "https://")):
            return False

        try:
            # Don't follow redirects - we want to see the redirect response
            # A 302 redirect from OAuth proxy indicates the dashboard is ready
            response = requests.get(
                dashboard_uri,
                headers=self._client_headers,
                timeout=5,
                verify=self._client_verify_tls,
                allow_redirects=False,
            )
        except requests.exceptions.SSLError:  # pragma no cover
            # SSL exception occurs when oauth ingress has been created but cluster is not up
            return False
        except Exception:  # pragma no cover
            # Any other exception (connection errors, timeouts, etc.)
            return False

        # Dashboard is ready if:
        # - 200: Dashboard is accessible (no auth required or already authenticated)
        # - 302: OAuth redirect - dashboard and OAuth proxy are ready, just needs authentication
        # - 401/403: OAuth is working and blocking unauthenticated requests - dashboard is ready
        return response.status_code in (200, 302, 401, 403)

    def cluster_uri(self) -> str:
        """
        Get the Ray client URI for the cluster.

        Returns:
            The Ray client URI (ray://<cluster-name>-head-svc.<namespace>.svc:10001)
        """
        if not self.name:
            raise ValueError("name is required to get cluster URI")
        self._ensure_namespace()
        return f"ray://{self.name}-head-svc.{self.namespace}.svc:10001"

    def cluster_dashboard_uri(self) -> str:
        """
        Get the dashboard URI for the cluster.

        Tries HTTPRoute first (RHOAI v3.0+), then falls back to OpenShift Routes or Ingresses.

        Returns:
            The dashboard URL, or an error message if not available.
        """
        if not self.name:
            raise ValueError("name is required to get dashboard URI")

        self._ensure_namespace()
        config_check()

        # Try HTTPRoute first (RHOAI v3.0+)
        httproute_url = self._get_dashboard_url_from_httproute(
            self.name, self.namespace
        )
        if httproute_url:
            return httproute_url

        # Fall back to OpenShift Routes (pre-v3.0) or Ingresses (Kind)
        if self._is_openshift_cluster():
            try:
                api_instance = client.CustomObjectsApi(get_api_client())
                routes = api_instance.list_namespaced_custom_object(
                    group="route.openshift.io",
                    version="v1",
                    namespace=self.namespace,
                    plural="routes",
                )
            except Exception as e:  # pragma: no cover
                return _kube_api_error_handling(e)

            for route in routes["items"]:
                if route["metadata"]["name"] == f"ray-dashboard-{self.name}" or route[
                    "metadata"
                ]["name"].startswith(f"{self.name}-ingress"):
                    protocol = "https" if route["spec"].get("tls") else "http"
                    return f"{protocol}://{route['spec']['host']}"

            return "Dashboard not available yet, have you run cluster.apply()?"
        else:
            try:
                api_instance = client.NetworkingV1Api(get_api_client())
                ingresses = api_instance.list_namespaced_ingress(self.namespace)
            except Exception as e:  # pragma no cover
                return _kube_api_error_handling(e)

            for ingress in ingresses.items:
                annotations = ingress.metadata.annotations
                protocol = "http"
                if (
                    ingress.metadata.name == f"ray-dashboard-{self.name}"
                    or ingress.metadata.name.startswith(f"{self.name}-ingress")
                ):
                    if annotations is None:
                        protocol = "http"
                    elif "route.openshift.io/termination" in annotations:
                        protocol = "https"
                    return f"{protocol}://{ingress.spec.rules[0].host}"

        return (
            "Dashboard not available yet, have you run cluster.apply()? "
            "Run cluster.details() to check if it's ready."
        )

    def details(self, print_to_console: bool = True) -> "RayCluster":
        """
        Get details about the Ray Cluster.

        Returns `self` directly, allowing access to all cluster configuration
        and runtime properties.

        Args:
            print_to_console: Whether to print details to console.

        Returns:
            This RayCluster instance with all configuration and runtime info.
        """
        if not self.name:
            raise ValueError("name is required to get cluster details")

        if print_to_console:
            from . import pretty_print

            pretty_print.print_clusters([self])
        return self

    # -------------------------------------------------------------------------
    # Job Client Methods
    # -------------------------------------------------------------------------

    @property
    def _client_headers(self):
        """Get authorization headers for HTTP requests."""
        k8_client = get_api_client()
        return {
            "Authorization": k8_client.configuration.get_api_key_with_prefix(
                "authorization"
            )
        }

    @property
    def _client_verify_tls(self):
        """Get TLS verification setting."""
        return self._is_openshift_cluster() and self.verify_tls

    @property
    def job_client(self) -> JobSubmissionClient:
        """
        Get a Ray JobSubmissionClient for the cluster.

        Returns:
            JobSubmissionClient connected to the cluster's dashboard.
        """
        if self._job_submission_client:
            return self._job_submission_client

        if self._is_openshift_cluster():
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

    def list_jobs(self) -> List:
        """
        List all jobs on the cluster.

        Returns:
            List of jobs from the Ray job client.
        """
        return self.job_client.list_jobs()

    def job_status(self, job_id: str) -> str:
        """
        Get the status of a specific job.

        Args:
            job_id: The job ID to check.

        Returns:
            The job status.
        """
        return self.job_client.get_job_status(job_id)

    def job_logs(self, job_id: str) -> str:
        """
        Get the logs for a specific job.

        Args:
            job_id: The job ID to get logs for.

        Returns:
            The job logs.
        """
        return self.job_client.get_job_logs(job_id)

    # -------------------------------------------------------------------------
    # RayJob Cluster Spec Building Methods
    # -------------------------------------------------------------------------

    def build_ray_cluster_spec(self, cluster_name: str) -> Dict[str, Any]:
        """
        Build the RayCluster spec for embedding in RayJob.

        Args:
            cluster_name: The name for the cluster (derived from RayJob name)

        Returns:
            Dict containing the RayCluster spec for embedding in RayJob
        """
        ray_cluster_spec = {
            "rayVersion": RAY_VERSION,
            "enableInTreeAutoscaling": False,  # Required for Kueue-managed jobs
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
        # Convert integer memory values to strings with 'Gi' suffix (Kubernetes standard)
        # Integer values represent GB and need to be converted to Gi format
        if isinstance(memory_requests, int):
            memory_requests = f"{memory_requests}Gi"
        if isinstance(memory_limits, int):
            memory_limits = f"{memory_limits}Gi"

        # Convert integer CPU values to strings if needed
        if isinstance(cpu_requests, int):
            cpu_requests = str(cpu_requests)
        if isinstance(cpu_limits, int):
            cpu_limits = str(cpu_limits)

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

    def _build_pod_spec_for_rayjob(
        self, container: V1Container, is_head: bool
    ) -> V1PodSpec:
        """Build the pod specification for RayJob."""
        pod_spec = V1PodSpec(
            containers=[container],
            volumes=self._generate_volumes_for_rayjob(),
            restart_policy="Never",  # RayJobs should not restart
        )

        # Add tolerations if specified
        if is_head and self.head_tolerations:
            pod_spec.tolerations = self.head_tolerations
        elif not is_head and self.worker_tolerations:
            pod_spec.tolerations = self.worker_tolerations

        # Add image pull secrets if specified
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
            secret_name: Name of the Secret containing files
            mount_path: Where to mount files in containers (default: /home/ray/files)
        """
        volume_name = "ray-job-files"

        # Check if file volume already exists
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
        """
        Validate that file content doesn't exceed Kubernetes Secret size limit.

        Args:
            files: Dictionary of file_name -> file_content

        Raises:
            ValueError: If total size exceeds 1MB limit
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
        Build volume and mount specifications for files.

        Args:
            secret_name: Name of the Secret containing files
            mount_path: Where to mount files in containers

        Returns:
            Tuple of (volume_spec, mount_spec) as dictionaries
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
        # GPU/accelerator related variables
        head_gpu_count, worker_gpu_count = self._head_worker_gpu_count()
        head_resources, worker_resources = self._head_worker_accelerators()

        # Format resources as JSON string for Ray
        head_resources_str = json.dumps(head_resources).replace('"', '\\"')
        head_resources_str = f'"{head_resources_str}"'
        worker_resources_str = json.dumps(worker_resources).replace('"', '\\"')
        worker_resources_str = f'"{worker_resources_str}"'

        # Create the Ray Cluster resource
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

        # Add GCS fault tolerance options if enabled
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

        # Sanitize for Kubernetes API
        config_check()
        k8s_client = get_api_client() or client.ApiClient()
        resource = k8s_client.sanitize_for_serialization(resource)

        # Write to file if requested
        if self.write_to_file:
            return self._write_to_file(resource)
        else:
            print(f"Yaml resources loaded for {self.name}")
            return resource

    def _build_metadata(self) -> V1ObjectMeta:
        """Build metadata for the standalone RayCluster."""
        labels = {
            "controller-tools.k8s.io": "1.0",
            "ray.io/cluster": self.name,
        }
        if self.labels:
            labels.update(self.labels)

        # Add local queue label if Kueue is available
        self._add_queue_label(labels)

        object_meta = V1ObjectMeta(
            name=self.name,
            namespace=self.namespace,
            labels=labels,
        )

        # Add annotations including NB prefix if in notebook
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
        """Add Kueue local queue label if available."""
        lq_name = self.local_queue or self._get_default_local_queue()
        if lq_name is None:
            return
        elif not self._local_queue_exists():
            print(
                "local_queue provided does not exist or is not in this namespace. "
                "Please provide the correct local_queue name in Cluster Configuration"
            )
            return
        labels["kueue.x-k8s.io/queue-name"] = lq_name

    def _local_queue_exists(self) -> bool:
        """Check if the specified local queue exists."""
        try:
            config_check()
            api_instance = client.CustomObjectsApi(get_api_client())
            local_queues = api_instance.list_namespaced_custom_object(
                group="kueue.x-k8s.io",
                version="v1beta1",
                namespace=self.namespace,
                plural="localqueues",
            )
        except Exception as e:  # pragma: no cover
            return _kube_api_error_handling(e)

        for lq in local_queues["items"]:
            if lq["metadata"]["name"] == self.local_queue:
                return True
        return False

    def _get_default_local_queue(self) -> Optional[str]:
        """Get the default local queue if one is configured."""
        try:
            config_check()
            api_instance = client.CustomObjectsApi(get_api_client())
            local_queues = api_instance.list_namespaced_custom_object(
                group="kueue.x-k8s.io",
                version="v1beta1",
                namespace=self.namespace,
                plural="localqueues",
            )
        except ApiException as e:  # pragma: no cover
            if e.status in (404, 403):
                return None
            else:
                return _kube_api_error_handling(e)

        for lq in local_queues["items"]:
            if (
                "annotations" in lq["metadata"]
                and "kueue.x-k8s.io/default-queue" in lq["metadata"]["annotations"]
                and lq["metadata"]["annotations"][
                    "kueue.x-k8s.io/default-queue"
                ].lower()
                == "true"
            ):
                return lq["metadata"]["name"]
        return None

    def _build_standalone_pod_spec(
        self,
        containers: List[V1Container],
        tolerations: Optional[List[V1Toleration]],
    ) -> V1PodSpec:
        """Build pod spec for standalone cluster."""
        # Combine custom volumes with ODH volumes
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
        # Combine custom volume mounts with ODH volume mounts
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
                    _exec=V1ExecAction(["/bin/sh", "-c", "ray stop"])
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
        # Combine custom volume mounts with ODH volume mounts
        all_volume_mounts = self.volume_mounts.copy() if self.volume_mounts else []
        all_volume_mounts.extend(_ODH_VOLUME_MOUNTS)

        worker_container = V1Container(
            name="machine-learning",
            image=update_image(self.image),
            image_pull_policy="Always",
            lifecycle=V1Lifecycle(
                pre_stop=V1LifecycleHandler(
                    _exec=V1ExecAction(["/bin/sh", "-c", "ray stop"])
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

    # -------------------------------------------------------------------------
    # GPU and Extended Resource Helpers
    # -------------------------------------------------------------------------

    def _head_worker_gpu_count(self) -> Tuple[int, int]:
        """Get GPU counts for head and worker nodes."""
        head_gpus = 0
        worker_gpus = 0

        for k in self.head_accelerators.keys():
            resource_type = self.accelerator_configs.get(k, "")
            if resource_type == "GPU":
                head_gpus += int(self.head_accelerators[k])

        for k in self.worker_accelerators.keys():
            resource_type = self.accelerator_configs.get(k, "")
            if resource_type == "GPU":
                worker_gpus += int(self.worker_accelerators[k])

        return head_gpus, worker_gpus

    def _head_worker_accelerators(self) -> Tuple[dict, dict]:
        """Get accelerator mapping for head and worker nodes."""
        head_resources = {}
        worker_resources = {}

        for k in self.head_accelerators.keys():
            resource_type = self.accelerator_configs.get(k, "")
            if resource_type in FORBIDDEN_CUSTOM_RESOURCE_TYPES:
                continue
            head_resources[resource_type] = self.head_accelerators[
                k
            ] + head_resources.get(resource_type, 0)

        for k in self.worker_accelerators.keys():
            resource_type = self.accelerator_configs.get(k, "")
            if resource_type in FORBIDDEN_CUSTOM_RESOURCE_TYPES:
                continue
            worker_resources[resource_type] = self.worker_accelerators[
                k
            ] + worker_resources.get(resource_type, 0)

        return head_resources, worker_resources

    # -------------------------------------------------------------------------
    # Kubernetes Helper Methods
    # -------------------------------------------------------------------------

    def _ensure_namespace(self):
        """Ensure namespace is set, defaulting to current namespace."""
        if self.namespace is None:
            self.namespace = get_current_namespace()
            if self.namespace is None:
                print("Please specify with namespace=<your_current_namespace>")
            elif not isinstance(self.namespace, str):
                raise TypeError(
                    f"Namespace {self.namespace} is of type {type(self.namespace)}. "
                    "Check your Kubernetes Authentication."
                )

    def _throw_for_no_raycluster(self):
        """Check if RayCluster CRD is available."""
        api_instance = client.CustomObjectsApi(get_api_client())
        try:
            api_instance.list_namespaced_custom_object(
                group="ray.io",
                version="v1",
                namespace=self.namespace,
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

    @staticmethod
    def _apply_ray_cluster(yamls, namespace: str, api_instance, force: bool = False):
        """Apply RayCluster using server-side apply."""
        api_instance.server_side_apply(
            field_manager=CF_SDK_FIELD_MANAGER,
            group="ray.io",
            version="v1",
            namespace=namespace,
            plural="rayclusters",
            body=yamls,
            force_conflicts=force,
        )

    @staticmethod
    def _delete_resources(
        name: str, namespace: str, api_instance: client.CustomObjectsApi
    ):
        """Delete a RayCluster resource."""
        api_instance.delete_namespaced_custom_object(
            group="ray.io",
            version="v1",
            namespace=namespace,
            plural="rayclusters",
            name=name,
        )

    def _ray_cluster_status(
        self, name: str, namespace: str
    ) -> Optional[RayClusterStatus]:
        """
        Get status of a RayCluster from Kubernetes.

        Args:
            name: The name of the RayCluster.
            namespace: The namespace of the RayCluster.

        Returns:
            RayClusterStatus enum value, or None if cluster not found.
        """
        try:
            config_check()
            api_instance = client.CustomObjectsApi(get_api_client())
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
                return self._extract_status_from_rc(rc)
        return None

    @staticmethod
    def _extract_status_from_rc(rc: dict) -> RayClusterStatus:
        """
        Extract the RayClusterStatus from a RayCluster resource dict.

        Args:
            rc: The RayCluster resource dictionary from Kubernetes API.

        Returns:
            RayClusterStatus enum value.
        """
        if "status" in rc and "state" in rc["status"]:
            try:
                return RayClusterStatus(rc["status"]["state"].lower())
            except ValueError:
                return RayClusterStatus.UNKNOWN
        return RayClusterStatus.UNKNOWN

    @staticmethod
    def _head_worker_extended_resources_from_rc_dict(rc: dict) -> Tuple[dict, dict]:
        """Extract extended resources from RayCluster dict."""
        head_extended_resources = {}
        worker_extended_resources = {}

        # Worker resources
        for resource in rc["spec"]["workerGroupSpecs"][0]["template"]["spec"][
            "containers"
        ][0]["resources"]["limits"].keys():
            if resource in ["memory", "cpu"]:
                continue
            worker_extended_resources[resource] = rc["spec"]["workerGroupSpecs"][0][
                "template"
            ]["spec"]["containers"][0]["resources"]["limits"][resource]

        # Head resources
        for resource in rc["spec"]["headGroupSpec"]["template"]["spec"]["containers"][
            0
        ]["resources"]["limits"].keys():
            if resource in ["memory", "cpu"]:
                continue
            head_extended_resources[resource] = rc["spec"]["headGroupSpec"]["template"][
                "spec"
            ]["containers"][0]["resources"]["limits"][resource]

        return head_extended_resources, worker_extended_resources

    @staticmethod
    def _is_openshift_cluster() -> bool:
        """Check if running on OpenShift."""
        try:
            config_check()
            for api in client.ApisApi(get_api_client()).get_api_versions().groups:
                for v in api.versions:
                    if "route.openshift.io/v1" in v.group_version:
                        return True
            return False
        except Exception:  # pragma: no cover
            return False

    @staticmethod
    def _get_dashboard_url_from_httproute(
        cluster_name: str, namespace: str
    ) -> Optional[str]:
        """
        Get the Ray dashboard URL from an HTTPRoute (RHOAI v3.0+ Gateway API).

        Args:
            cluster_name: Ray cluster name
            namespace: Ray cluster namespace

        Returns:
            Dashboard URL if found, else None
        """
        try:
            config_check()
            api_instance = client.CustomObjectsApi(get_api_client())

            label_selector = f"ray.io/cluster-name={cluster_name},ray.io/cluster-namespace={namespace}"

            # Try cluster-wide search first (if permissions allow)
            try:
                httproutes = api_instance.list_cluster_custom_object(
                    group="gateway.networking.k8s.io",
                    version="v1",
                    plural="httproutes",
                    label_selector=label_selector,
                )
                items = httproutes.get("items", [])
                if items:
                    httproute = items[0]
                else:
                    return None
            except Exception:
                # No cluster-wide permissions, try namespace-specific search
                search_namespaces = [
                    namespace,
                    "redhat-ods-applications",
                    "opendatahub",
                    "default",
                    "ray-system",
                ]

                httproute = None
                for ns in search_namespaces:
                    try:
                        httproutes = api_instance.list_namespaced_custom_object(
                            group="gateway.networking.k8s.io",
                            version="v1",
                            namespace=ns,
                            plural="httproutes",
                            label_selector=label_selector,
                        )
                        items = httproutes.get("items", [])
                        if items:
                            httproute = items[0]
                            break
                    except ApiException:
                        continue

                if not httproute:
                    return None

            # Extract Gateway reference and construct dashboard URL
            parent_refs = httproute.get("spec", {}).get("parentRefs", [])
            if not parent_refs:
                return None

            gateway_ref = parent_refs[0]
            gateway_name = gateway_ref.get("name")
            gateway_namespace = gateway_ref.get("namespace")

            if not gateway_name or not gateway_namespace:
                return None

            # Get the Gateway to retrieve the hostname
            gateway = api_instance.get_namespaced_custom_object(
                group="gateway.networking.k8s.io",
                version="v1",
                namespace=gateway_namespace,
                plural="gateways",
                name=gateway_name,
            )

            # Try to get hostname from multiple locations
            hostname = None

            # First try spec.listeners[].hostname
            listeners = gateway.get("spec", {}).get("listeners", [])
            if listeners:
                hostname = listeners[0].get("hostname")

            # If no hostname in listeners, try to find OpenShift Route exposing the Gateway
            if not hostname:
                try:
                    routes = api_instance.list_namespaced_custom_object(
                        group="route.openshift.io",
                        version="v1",
                        namespace=gateway_namespace,
                        plural="routes",
                    )
                    for route in routes.get("items", []):
                        if route["metadata"]["name"] == gateway_name:
                            hostname = route.get("spec", {}).get("host")
                            break
                except Exception:
                    pass

            # If still no hostname, try status.addresses
            if not hostname:
                addresses = gateway.get("status", {}).get("addresses", [])
                if addresses:
                    addr_value = addresses[0].get("value")
                    if addr_value and not addr_value.endswith(".svc.cluster.local"):
                        hostname = addr_value

            if not hostname:
                return None

            # Construct dashboard URL
            return f"https://{hostname}/ray/{namespace}/{cluster_name}"

        except Exception:  # pragma: no cover
            return None


def list_all_clusters(
    namespace: str, print_to_console: bool = True
) -> List["RayCluster"]:
    """
    Returns (and prints by default) a list of all clusters in a given namespace.

    Args:
        namespace: The Kubernetes namespace to list clusters from.
        print_to_console: Whether to print the clusters to console.

    Returns:
        List of RayCluster objects representing the clusters.
    """
    from . import pretty_print

    clusters = _get_ray_clusters(namespace)
    if print_to_console:
        pretty_print.print_clusters(clusters)
    return clusters


def list_all_queued(
    namespace: str, print_to_console: bool = True
) -> List["RayCluster"]:
    """
    Returns (and prints by default) a list of all currently queued-up Ray Clusters
    in a given namespace.

    Args:
        namespace: The Kubernetes namespace to list clusters from.
        print_to_console: Whether to print the clusters to console.

    Returns:
        List of RayCluster objects representing the queued clusters.
    """
    from . import pretty_print

    resources = _get_ray_clusters(
        namespace, filter=[RayClusterStatus.READY, RayClusterStatus.SUSPENDED]
    )
    if print_to_console:
        pretty_print.print_ray_clusters_status(resources)
    return resources


def get_cluster(
    cluster_name: str,
    namespace: str = "default",
    verify_tls: bool = True,
    write_to_file: bool = False,
) -> RayCluster:
    """
    Retrieves an existing Ray Cluster as a RayCluster object.

    This function fetches an existing Ray Cluster from the Kubernetes cluster and returns
    it as a `RayCluster` object.

    Args:
        cluster_name: The name of the Ray Cluster.
        namespace: The Kubernetes namespace where the Ray Cluster is located.
        verify_tls: Whether to verify TLS when connecting to the cluster.
        write_to_file: If True, writes the resource configuration to a YAML file.

    Returns:
        RayCluster object representing the retrieved Ray Cluster.

    Raises:
        Exception: If the Ray Cluster cannot be found or does not exist.
    """
    config_check()
    api_instance = client.CustomObjectsApi(get_api_client())

    # Get the Ray Cluster
    try:
        resource = api_instance.get_namespaced_custom_object(
            group="ray.io",
            version="v1",
            namespace=namespace,
            plural="rayclusters",
            name=cluster_name,
        )
    except Exception as e:
        return _kube_api_error_handling(e)

    # Extract extended resources from the retrieved cluster
    (
        head_extended_resources,
        worker_extended_resources,
    ) = RayCluster._head_worker_extended_resources_from_rc_dict(resource)

    # Create a RayCluster with the retrieved parameters
    cluster = RayCluster(
        name=cluster_name,
        namespace=namespace,
        verify_tls=verify_tls,
        write_to_file=write_to_file,
        head_cpu_limits=resource["spec"]["headGroupSpec"]["template"]["spec"][
            "containers"
        ][0]["resources"]["limits"]["cpu"],
        head_cpu_requests=resource["spec"]["headGroupSpec"]["template"]["spec"][
            "containers"
        ][0]["resources"]["requests"]["cpu"],
        head_memory_limits=resource["spec"]["headGroupSpec"]["template"]["spec"][
            "containers"
        ][0]["resources"]["limits"]["memory"],
        head_memory_requests=resource["spec"]["headGroupSpec"]["template"]["spec"][
            "containers"
        ][0]["resources"]["requests"]["memory"],
        num_workers=resource["spec"]["workerGroupSpecs"][0]["minReplicas"],
        worker_cpu_limits=resource["spec"]["workerGroupSpecs"][0]["template"]["spec"][
            "containers"
        ][0]["resources"]["limits"]["cpu"],
        worker_cpu_requests=resource["spec"]["workerGroupSpecs"][0]["template"]["spec"][
            "containers"
        ][0]["resources"]["requests"]["cpu"],
        worker_memory_limits=resource["spec"]["workerGroupSpecs"][0]["template"][
            "spec"
        ]["containers"][0]["resources"]["limits"]["memory"],
        worker_memory_requests=resource["spec"]["workerGroupSpecs"][0]["template"][
            "spec"
        ]["containers"][0]["resources"]["requests"]["memory"],
        head_accelerators=head_extended_resources,
        worker_accelerators=worker_extended_resources,
    )

    # Remove auto-generated fields like creationTimestamp, uid and etc.
    _remove_autogenerated_fields(resource)

    if write_to_file:
        cluster._resource_yaml = cluster._write_to_file(resource)
    else:
        # Update the Cluster's resource_yaml to reflect the retrieved Ray Cluster
        cluster._resource_yaml = resource
        print(f"Yaml resources loaded for {cluster.name}")

    return cluster


def _get_ray_clusters(
    namespace: str = "default", filter: Optional[List[RayClusterStatus]] = None
) -> List[RayCluster]:
    """
    Get a list of RayCluster objects from the Kubernetes cluster.

    Args:
        namespace: The Kubernetes namespace to list clusters from.
        filter: Optional list of RayClusterStatus values to filter by.

    Returns:
        List of RayCluster objects.
    """
    list_of_clusters = []
    try:
        config_check()
        api_instance = client.CustomObjectsApi(get_api_client())
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
            if ray_cluster:
                # Get status from the resource and check against filter
                status = RayCluster._extract_status_from_rc(rc)
                if status in filter:
                    list_of_clusters.append(ray_cluster)
    else:
        for rc in rcs["items"]:
            ray_cluster = _map_to_ray_cluster(rc)
            if ray_cluster:
                list_of_clusters.append(ray_cluster)
    return list_of_clusters


def _map_to_ray_cluster(rc: dict) -> Optional[RayCluster]:
    """
    Map a RayCluster Kubernetes resource to a RayCluster object.

    Args:
        rc: The RayCluster resource dictionary from Kubernetes API.

    Returns:
        RayCluster object, or None if mapping fails.
    """
    # Extract extended resources from the RC
    (
        head_extended_resources,
        worker_extended_resources,
    ) = RayCluster._head_worker_extended_resources_from_rc_dict(rc)

    # Create RayCluster object from the Kubernetes resource
    return RayCluster(
        name=rc["metadata"]["name"],
        namespace=rc["metadata"]["namespace"],
        num_workers=rc["spec"]["workerGroupSpecs"][0]["replicas"],
        worker_memory_limits=rc["spec"]["workerGroupSpecs"][0]["template"]["spec"][
            "containers"
        ][0]["resources"]["limits"]["memory"],
        worker_memory_requests=rc["spec"]["workerGroupSpecs"][0]["template"]["spec"][
            "containers"
        ][0]["resources"]["requests"]["memory"],
        worker_cpu_requests=rc["spec"]["workerGroupSpecs"][0]["template"]["spec"][
            "containers"
        ][0]["resources"]["requests"]["cpu"],
        worker_cpu_limits=rc["spec"]["workerGroupSpecs"][0]["template"]["spec"][
            "containers"
        ][0]["resources"]["limits"]["cpu"],
        worker_accelerators=worker_extended_resources,
        head_cpu_requests=rc["spec"]["headGroupSpec"]["template"]["spec"]["containers"][
            0
        ]["resources"]["requests"]["cpu"],
        head_cpu_limits=rc["spec"]["headGroupSpec"]["template"]["spec"]["containers"][
            0
        ]["resources"]["limits"]["cpu"],
        head_memory_requests=rc["spec"]["headGroupSpec"]["template"]["spec"][
            "containers"
        ][0]["resources"]["requests"]["memory"],
        head_memory_limits=rc["spec"]["headGroupSpec"]["template"]["spec"][
            "containers"
        ][0]["resources"]["limits"]["memory"],
        head_accelerators=head_extended_resources,
    )


def _remove_autogenerated_fields(resource):
    """Recursively remove autogenerated fields from a dictionary."""
    if isinstance(resource, dict):
        for key in list(resource.keys()):
            if key in [
                "creationTimestamp",
                "resourceVersion",
                "uid",
                "selfLink",
                "managedFields",
                "finalizers",
                "generation",
                "status",
                "suspend",
            ]:
                del resource[key]
            else:
                _remove_autogenerated_fields(resource[key])

    elif isinstance(resource, list):
        for item in resource:
            _remove_autogenerated_fields(item)

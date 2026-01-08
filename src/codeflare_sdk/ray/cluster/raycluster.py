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
The RayCluster class provides a unified interface for creating and managing Ray clusters.
It combines configuration and operational methods in a single object.
"""

from time import sleep
from typing import List, Optional, Tuple, Dict, Union, Any, get_args, get_origin
import warnings

from ray.job_submission import JobSubmissionClient
import requests

from kubernetes import client
from kubernetes.dynamic import DynamicClient
from kubernetes.client.rest import ApiException
from kubernetes.client import (
    V1Toleration,
    V1Volume,
    V1VolumeMount,
    V1LocalObjectReference,
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
import yaml

from ...common.utils import get_current_namespace
from ...common.utils.constants import RAY_VERSION
from ...common.utils.utils import update_image
from ...common.kubernetes_cluster.auth import config_check, get_api_client
from ...common import _kube_api_error_handling
from ...common.widgets.widgets import cluster_apply_down_buttons, is_notebook

from . import pretty_print
from .build_ray_cluster import build_ray_cluster, head_worker_gpu_count_from_cluster
from .build_ray_cluster import write_to_file as write_cluster_to_file
from .status import CodeFlareClusterStatus, RayClusterInfo, RayClusterStatus
from ..appwrapper import AppWrapper, AppWrapperStatus


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

CF_SDK_FIELD_MANAGER = "codeflare-sdk"


class RayCluster:
    """
    A unified object for configuring, requesting, bringing up, and taking down Ray clusters.

    This is the recommended way to create and manage Ray clusters. It combines configuration
    and operational methods in a single object, replacing the previous pattern of
    Cluster(ClusterConfiguration(...)).

    Example:
        cluster = RayCluster(
            name='my-cluster',
            namespace='default',
            num_workers=2,
            worker_accelerators={'nvidia.com/gpu': 1}
        )
        cluster.apply()
        cluster.wait_ready()
        # ... use cluster ...
        cluster.down()

    Args:
        name:
            The name of the cluster. Required.
        namespace:
            The namespace in which the cluster should be created.
        head_cpu_requests:
            CPU requests for the head node.
        head_cpu_limits:
            CPU limits for the head node.
        head_memory_requests:
            Memory requests for the head node (int for GB, or string with unit).
        head_memory_limits:
            Memory limits for the head node (int for GB, or string with unit).
        head_accelerators:
            A dictionary of accelerator requests for the head node. ex: {"nvidia.com/gpu": 1}
        head_tolerations:
            List of tolerations for head nodes.
        worker_cpu_requests:
            CPU requests for each worker.
        worker_cpu_limits:
            CPU limits for each worker.
        num_workers:
            The number of workers to create.
        worker_memory_requests:
            Memory requests for each worker.
        worker_memory_limits:
            Memory limits for each worker.
        worker_tolerations:
            List of tolerations for worker nodes.
        worker_accelerators:
            A dictionary of accelerator requests for each worker. ex: {"nvidia.com/gpu": 1}
        envs:
            A dictionary of environment variables to set for the cluster.
        image:
            The image to use for the cluster.
        image_pull_secrets:
            A list of image pull secrets to use for the cluster.
        verify_tls:
            A boolean indicating whether to verify TLS when connecting to the cluster.
        labels:
            A dictionary of labels to apply to the cluster.
        accelerator_configs:
            A dictionary mapping accelerator resource names to Ray resource names.
        overwrite_default_accelerator_configs:
            A boolean indicating whether to overwrite the default accelerator configs.
        local_queue:
            The Kueue local queue to use for scheduling.
        annotations:
            A dictionary of annotations to apply to the cluster.
        volumes:
            A list of V1Volume objects to add to the Cluster.
        volume_mounts:
            A list of V1VolumeMount objects to add to the Cluster.
        enable_gcs_ft:
            A boolean indicating whether to enable GCS fault tolerance.
        enable_usage_stats:
            A boolean indicating whether to capture and send Ray usage stats externally.
        redis_address:
            The address of the Redis server for GCS fault tolerance.
        redis_password_secret:
            Kubernetes secret reference for Redis password.
        external_storage_namespace:
            The storage namespace for GCS fault tolerance.
    """

    def __init__(
        self,
        name: str,
        namespace: Optional[str] = None,
        head_cpu_requests: Union[int, str] = 1,
        head_cpu_limits: Union[int, str] = 2,
        head_memory_requests: Union[int, str] = 5,
        head_memory_limits: Union[int, str] = 8,
        head_accelerators: Optional[Dict[str, Union[str, int]]] = None,
        head_tolerations: Optional[List[V1Toleration]] = None,
        worker_cpu_requests: Union[int, str] = 1,
        worker_cpu_limits: Union[int, str] = 1,
        num_workers: int = 1,
        worker_memory_requests: Union[int, str] = 3,
        worker_memory_limits: Union[int, str] = 6,
        worker_tolerations: Optional[List[V1Toleration]] = None,
        worker_accelerators: Optional[Dict[str, Union[str, int]]] = None,
        envs: Optional[Dict[str, str]] = None,
        image: str = "",
        image_pull_secrets: Optional[List[str]] = None,
        verify_tls: bool = True,
        labels: Optional[Dict[str, str]] = None,
        accelerator_configs: Optional[Dict[str, str]] = None,
        overwrite_default_accelerator_configs: bool = False,
        local_queue: Optional[str] = None,
        annotations: Optional[Dict[str, str]] = None,
        volumes: Optional[List[V1Volume]] = None,
        volume_mounts: Optional[List[V1VolumeMount]] = None,
        enable_gcs_ft: bool = False,
        enable_usage_stats: bool = False,
        redis_address: Optional[str] = None,
        redis_password_secret: Optional[Dict[str, str]] = None,
        external_storage_namespace: Optional[str] = None,
        write_to_file: bool = False,
    ):
        # Store all configuration as instance attributes
        self.name = name
        self.namespace = namespace
        self.head_cpu_requests = head_cpu_requests
        self.head_cpu_limits = head_cpu_limits
        self.head_memory_requests = head_memory_requests
        self.head_memory_limits = head_memory_limits
        self.head_accelerators = (
            head_accelerators if head_accelerators is not None else {}
        )
        self.head_tolerations = head_tolerations
        self.worker_cpu_requests = worker_cpu_requests
        self.worker_cpu_limits = worker_cpu_limits
        self.num_workers = num_workers
        self.worker_memory_requests = worker_memory_requests
        self.worker_memory_limits = worker_memory_limits
        self.worker_tolerations = worker_tolerations
        self.worker_accelerators = (
            worker_accelerators if worker_accelerators is not None else {}
        )
        self.envs = envs if envs is not None else {}
        self.image = image
        self.image_pull_secrets = (
            image_pull_secrets if image_pull_secrets is not None else []
        )
        self.verify_tls = verify_tls
        self.labels = labels if labels is not None else {}
        self.accelerator_configs = (
            accelerator_configs
            if accelerator_configs is not None
            else DEFAULT_ACCELERATORS.copy()
        )
        self.overwrite_default_accelerator_configs = (
            overwrite_default_accelerator_configs
        )
        self.local_queue = local_queue
        self.annotations = annotations if annotations is not None else {}
        self.volumes = volumes if volumes is not None else []
        self.volume_mounts = volume_mounts if volume_mounts is not None else []
        self.enable_gcs_ft = enable_gcs_ft
        self.enable_usage_stats = enable_usage_stats
        self.redis_address = redis_address
        self.redis_password_secret = redis_password_secret
        self.external_storage_namespace = external_storage_namespace

        # Internal state
        self._job_submission_client = None
        self.resource_yaml = None

        # For backward compatibility - RayCluster doesn't support AppWrapper
        # Users needing AppWrapper should use deprecated ClusterConfiguration
        self.appwrapper = False
        self.write_to_file = write_to_file

        # Run validation and initialization
        self._post_init()

        # Create resource yaml
        self.resource_yaml = self._create_resource()

        # Display widgets if in notebook
        if is_notebook():
            cluster_apply_down_buttons(self)

    def _post_init(self):
        """Post-initialization validation and setup."""
        # Type validation
        errors = []
        if not isinstance(self.num_workers, int) or isinstance(self.num_workers, bool):
            errors.append(f"'num_workers' should be of type int.")
        if not isinstance(self.worker_cpu_requests, (int, str)) or isinstance(
            self.worker_cpu_requests, bool
        ):
            errors.append(f"'worker_cpu_requests' should be of type Union[int, str].")
        if self.labels and not all(
            isinstance(k, str) and isinstance(v, str) for k, v in self.labels.items()
        ):
            errors.append(f"'labels' should be of type Dict[str, str].")

        if errors:
            raise TypeError("Type validation failed:\n" + "\n".join(errors))

        if not self.verify_tls:
            print(
                "Warning: TLS verification has been disabled - Endpoint checks will be bypassed"
            )

        if self.enable_usage_stats:
            self.envs["RAY_USAGE_STATS_ENABLED"] = "1"
        else:
            self.envs["RAY_USAGE_STATS_ENABLED"] = "0"

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

        self._memory_to_string()
        self._str_mem_no_unit_add_GB()
        self._combine_accelerator_configs()
        self._validate_accelerators(self.head_accelerators)
        self._validate_accelerators(self.worker_accelerators)

    def _combine_accelerator_configs(self):
        """Combine user accelerator configs with defaults."""
        if overwritten := set(self.accelerator_configs.keys()).intersection(
            DEFAULT_ACCELERATORS.keys()
        ):
            if self.overwrite_default_accelerator_configs:
                warnings.warn(
                    f"Overwriting default accelerator configs for {overwritten}",
                    UserWarning,
                )
        self.accelerator_configs = {
            **DEFAULT_ACCELERATORS,
            **self.accelerator_configs,
        }

    def _validate_accelerators(self, accelerators: Dict[str, int]):
        """Validate that accelerators are in the config."""
        for k in accelerators.keys():
            if k not in self.accelerator_configs.keys():
                raise ValueError(
                    f"Accelerator '{k}' not found in accelerator_configs, available resources are {list(self.accelerator_configs.keys())}, to add more supported resources use accelerator_configs. i.e. accelerator_configs = {{'{k}': 'FOO_BAR'}}"
                )

    def _str_mem_no_unit_add_GB(self):
        """Add GB unit to string memory values without units."""
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

    def _memory_to_string(self):
        """Convert integer memory values to strings with GB unit."""
        if isinstance(self.head_memory_requests, int):
            self.head_memory_requests = f"{self.head_memory_requests}G"
        if isinstance(self.head_memory_limits, int):
            self.head_memory_limits = f"{self.head_memory_limits}G"
        if isinstance(self.worker_memory_requests, int):
            self.worker_memory_requests = f"{self.worker_memory_requests}G"
        if isinstance(self.worker_memory_limits, int):
            self.worker_memory_limits = f"{self.worker_memory_limits}G"

    # Properties for backward compatibility with ClusterConfiguration field names
    @property
    def head_extended_resource_requests(self) -> Dict[str, Union[str, int]]:
        """Backward compatibility alias for head_accelerators."""
        return self.head_accelerators

    @property
    def worker_extended_resource_requests(self) -> Dict[str, Union[str, int]]:
        """Backward compatibility alias for worker_accelerators."""
        return self.worker_accelerators

    @property
    def extended_resource_mapping(self) -> Dict[str, str]:
        """Backward compatibility alias for accelerator_configs."""
        return self.accelerator_configs

    @property
    def overwrite_default_resource_mapping(self) -> bool:
        """Backward compatibility alias for overwrite_default_accelerator_configs."""
        return self.overwrite_default_accelerator_configs

    # Provide config property that returns self for compatibility with Cluster interface
    @property
    def config(self):
        """Return self for compatibility with code expecting cluster.config."""
        return self

    # ==================== Operational Methods (from Cluster) ====================

    def get_dynamic_client(self):  # pragma: no cover
        """Get a DynamicClient for Kubernetes API access."""
        return DynamicClient(get_api_client())

    def config_check(self):
        """Check Kubernetes configuration."""
        return config_check()

    @property
    def _client_headers(self):
        """Get authorization headers for API requests."""
        k8_client = get_api_client()
        return {
            "Authorization": k8_client.configuration.get_api_key_with_prefix(
                "authorization"
            )
        }

    @property
    def _client_verify_tls(self):
        """Get TLS verification setting."""
        return _is_openshift_cluster() and self.verify_tls

    @property
    def job_client(self):
        """Get the Ray Job Submission Client."""
        if self._job_submission_client:
            return self._job_submission_client
        if _is_openshift_cluster():
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

    def _create_resource(self):
        """
        Create the RayCluster yaml based on the configuration.
        """
        if self.namespace is None:
            self.namespace = get_current_namespace()
            if self.namespace is None:
                print("Please specify with namespace=<your_current_namespace>")
            elif type(self.namespace) is not str:
                raise TypeError(
                    f"Namespace {self.namespace} is of type {type(self.namespace)}. Check your Kubernetes Authentication."
                )
        return build_ray_cluster(self)

    def apply(self, force=False):
        """
        Applies the RayCluster yaml using server-side apply.
        If 'force' is set to True, conflicts will be forced.
        """
        self._throw_for_no_raycluster()
        namespace = self.namespace
        name = self.name

        # Regenerate resource_yaml to reflect any configuration changes
        self.resource_yaml = self._create_resource()

        try:
            self.config_check()
            crds = self.get_dynamic_client().resources
            api_version = "ray.io/v1"
            api_instance = crds.get(api_version=api_version, kind="RayCluster")
            self._component_resources_apply(
                namespace=namespace, api_instance=api_instance
            )
            print(
                f"Ray Cluster: '{name}' has successfully been applied. For optimal resource management, you should delete this Ray Cluster when no longer in use."
            )
        except AttributeError as e:
            raise RuntimeError(f"Failed to initialize DynamicClient: {e}")
        except Exception as e:  # pragma: no cover
            if hasattr(e, "status") and e.status == 422:
                print(
                    "WARNING: RayCluster creation rejected due to invalid Kueue configuration. Please contact your administrator."
                )
            else:
                print(
                    "WARNING: Failed to create RayCluster due to unexpected error. Please contact your administrator."
                )
            return _kube_api_error_handling(e)

    def _throw_for_no_raycluster(self):
        """Check if RayCluster CRD exists."""
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

    def down(self):
        """
        Deletes the RayCluster, scaling-down and deleting all resources
        associated with the cluster.
        """
        namespace = self.namespace
        resource_name = self.name
        self._throw_for_no_raycluster()
        try:
            self.config_check()
            api_instance = client.CustomObjectsApi(get_api_client())
            _delete_resources(resource_name, namespace, api_instance)
            print(f"Ray Cluster: '{self.name}' has successfully been deleted")
        except Exception as e:  # pragma: no cover
            return _kube_api_error_handling(e)

    def status(
        self, print_to_console: bool = True
    ) -> Tuple[CodeFlareClusterStatus, bool]:
        """
        Returns the requested cluster's status, as well as whether or not
        it is ready for use.
        """
        ready = False
        status = CodeFlareClusterStatus.UNKNOWN

        # check the ray cluster status
        cluster = _ray_cluster_status(self.name, self.namespace)
        if cluster:
            if cluster.status == RayClusterStatus.SUSPENDED:
                ready = False
                status = CodeFlareClusterStatus.SUSPENDED
            if cluster.status == RayClusterStatus.UNKNOWN:
                ready = False
                status = CodeFlareClusterStatus.STARTING
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
                _, cluster.worker_gpu = head_worker_gpu_count_from_cluster(self)
                pretty_print.print_cluster_status(cluster)
        elif print_to_console:
            if status == CodeFlareClusterStatus.UNKNOWN:
                pretty_print.print_no_resources_found()

        return status, ready

    def is_dashboard_ready(self) -> bool:
        """
        Checks if the cluster's dashboard is ready and accessible.

        Returns:
            bool: True if the dashboard is ready, False otherwise.
        """
        dashboard_uri = self.cluster_dashboard_uri()
        if dashboard_uri is None:
            return False

        try:
            response = requests.get(
                dashboard_uri,
                headers=self._client_headers,
                timeout=5,
                verify=self._client_verify_tls,
                allow_redirects=False,
            )
        except requests.exceptions.SSLError:  # pragma no cover
            return False
        except Exception:  # pragma no cover
            return False

        if response.status_code in (200, 302, 401, 403):
            return True
        else:
            return False

    def wait_ready(self, timeout: Optional[int] = None, dashboard_check: bool = True):
        """
        Waits for the requested cluster to be ready, up to an optional timeout.

        Args:
            timeout (Optional[int]):
                The maximum time to wait for the cluster to be ready in seconds.
            dashboard_check (bool):
                Flag to determine if the dashboard readiness should be checked.
        """
        print("Waiting for requested resources to be set up...")
        time = 0
        while True:
            if timeout and time >= timeout:
                raise TimeoutError(
                    f"wait() timed out after waiting {timeout}s for cluster to be ready"
                )
            status, ready = self.status(print_to_console=False)
            if status == CodeFlareClusterStatus.UNKNOWN:
                print(
                    "WARNING: Current cluster status is unknown, have you run cluster.apply() yet? Run cluster.details() to check if it's ready."
                )
            if ready:
                break
            sleep(5)
            time += 5
        print("Requested cluster is up and running!")

        while dashboard_check:
            if timeout and time >= timeout:
                raise TimeoutError(
                    f"wait() timed out after waiting {timeout}s for dashboard to be ready"
                )
            if self.is_dashboard_ready():
                print("Dashboard is ready!")
                break
            # Check if dashboard URI is available (not an error message)
            dashboard_uri = self.cluster_dashboard_uri()
            if (
                "not available" in dashboard_uri.lower()
                or "not ready" in dashboard_uri.lower()
            ):
                print("Waiting for dashboard route/HTTPRoute to be created...")
            elif dashboard_uri.startswith("http://") or dashboard_uri.startswith(
                "https://"
            ):
                print(f"Waiting for dashboard to become accessible: {dashboard_uri}")
            sleep(5)
            time += 5

    def details(self, print_to_console: bool = True) -> RayClusterInfo:
        """
        Retrieves details about the Ray Cluster.

        Args:
            print_to_console (bool): Flag to determine if details should be printed.

        Returns:
            RayClusterInfo: A copy of the Ray Cluster details.
        """
        cluster = _copy_to_ray(self)
        if print_to_console:
            pretty_print.print_clusters([cluster])
        return cluster

    def cluster_uri(self) -> str:
        """Returns a string containing the cluster's URI."""
        return f"ray://{self.name}-head-svc.{self.namespace}.svc:10001"

    def cluster_dashboard_uri(self) -> str:
        """
        Returns a string containing the cluster's dashboard URI.
        """
        config_check()

        # Try HTTPRoute first (RHOAI v3.0+)
        httproute_url = _get_dashboard_url_from_httproute(self.name, self.namespace)
        if httproute_url:
            return httproute_url

        # Fall back to OpenShift Routes or Ingresses
        if _is_openshift_cluster():
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
        return "Dashboard not available yet, have you run cluster.apply()? Run cluster.details() to check if it's ready."

    def list_jobs(self) -> List:
        """Lists the running jobs on the cluster."""
        return self.job_client.list_jobs()

    def job_status(self, job_id: str) -> str:
        """Returns the job status for the provided job id."""
        return self.job_client.get_job_status(job_id)

    def job_logs(self, job_id: str) -> str:
        """Returns the logs for the provided job id."""
        return self.job_client.get_job_logs(job_id)

    @staticmethod
    def _head_worker_extended_resources_from_rc_dict(rc: Dict) -> Tuple[dict, dict]:
        """Extract extended resources from a RayCluster dict."""
        head_extended_resources, worker_extended_resources = {}, {}
        for resource in rc["spec"]["workerGroupSpecs"][0]["template"]["spec"][
            "containers"
        ][0]["resources"]["limits"].keys():
            if resource in ["memory", "cpu"]:
                continue
            worker_extended_resources[resource] = rc["spec"]["workerGroupSpecs"][0][
                "template"
            ]["spec"]["containers"][0]["resources"]["limits"][resource]

        for resource in rc["spec"]["headGroupSpec"]["template"]["spec"]["containers"][
            0
        ]["resources"]["limits"].keys():
            if resource in ["memory", "cpu"]:
                continue
            head_extended_resources[resource] = rc["spec"]["headGroupSpec"]["template"][
                "spec"
            ]["containers"][0]["resources"]["limits"][resource]

        return head_extended_resources, worker_extended_resources

    def local_client_url(self):
        """Returns the Ray client URL based on the ingress domain."""
        ingress_domain = _get_ingress_domain(self)
        return f"ray://{ingress_domain}"

    def _component_resources_apply(
        self, namespace: str, api_instance: client.CustomObjectsApi
    ):
        """Apply RayCluster resources."""
        _apply_ray_cluster(self.resource_yaml, namespace, api_instance)

    # ==================== RayJob Integration Methods ====================

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
            "enableInTreeAutoscaling": False,
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
            volume_mounts=self._generate_volume_mounts(),
            env=self._build_env_vars() if self.envs else None,
        )
        return container

    def _build_worker_container(self) -> V1Container:
        """Build the worker container specification."""
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
            volume_mounts=self._generate_volume_mounts(),
            env=self._build_env_vars() if self.envs else None,
        )
        return container

    def _build_resource_requirements(
        self,
        cpu_requests: Union[int, str],
        cpu_limits: Union[int, str],
        memory_requests: Union[int, str],
        memory_limits: Union[int, str],
        accelerators: Dict[str, Union[int, str]] = None,
    ) -> V1ResourceRequirements:
        """Build Kubernetes resource requirements."""
        resource_requirements = V1ResourceRequirements(
            requests={"cpu": cpu_requests, "memory": memory_requests},
            limits={"cpu": cpu_limits, "memory": memory_limits},
        )

        if accelerators:
            for resource_type, amount in accelerators.items():
                resource_requirements.limits[resource_type] = amount
                resource_requirements.requests[resource_type] = amount

        return resource_requirements

    def _build_pod_spec(self, container: V1Container, is_head: bool) -> V1PodSpec:
        """Build the pod specification."""
        pod_spec = V1PodSpec(
            containers=[container],
            volumes=self._generate_volumes(),
            restart_policy="Never",
        )

        if is_head and self.head_tolerations:
            pod_spec.tolerations = self.head_tolerations
        elif not is_head and self.worker_tolerations:
            pod_spec.tolerations = self.worker_tolerations

        if self.image_pull_secrets:
            pod_spec.image_pull_secrets = [
                V1LocalObjectReference(name=secret)
                for secret in self.image_pull_secrets
            ]

        return pod_spec

    def _generate_volume_mounts(self) -> list:
        """Generate volume mounts for the container."""
        volume_mounts = []
        if self.volume_mounts:
            volume_mounts.extend(self.volume_mounts)
        return volume_mounts

    def _generate_volumes(self) -> list:
        """Generate volumes for the pod."""
        volumes = []
        if self.volumes:
            volumes.extend(self.volumes)
        return volumes

    def _build_env_vars(self) -> list:
        """Build environment variables list."""
        return [V1EnvVar(name=key, value=value) for key, value in self.envs.items()]


# ==================== Module-level functions ====================


def _delete_resources(name: str, namespace: str, api_instance: client.CustomObjectsApi):
    """Delete a RayCluster resource."""
    api_instance.delete_namespaced_custom_object(
        group="ray.io",
        version="v1",
        namespace=namespace,
        plural="rayclusters",
        name=name,
    )


def _apply_ray_cluster(
    yamls, namespace: str, api_instance: client.CustomObjectsApi, force=False
):
    """Apply a RayCluster resource."""
    api_instance.server_side_apply(
        field_manager=CF_SDK_FIELD_MANAGER,
        group="ray.io",
        version="v1",
        namespace=namespace,
        plural="rayclusters",
        body=yamls,
        force_conflicts=force,
    )


def _ray_cluster_status(name, namespace="default") -> Optional[RayClusterInfo]:
    """Get the status of a RayCluster."""
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
            return _map_to_ray_cluster(rc)
    return None


def _map_to_ray_cluster(rc) -> Optional[RayClusterInfo]:
    """Map a RayCluster dict to RayClusterInfo."""
    if "status" in rc and "state" in rc["status"]:
        status = RayClusterStatus(rc["status"]["state"].lower())
    else:
        status = RayClusterStatus.UNKNOWN
    config_check()
    dashboard_url = None

    rc_name = rc["metadata"]["name"]
    rc_namespace = rc["metadata"]["namespace"]
    dashboard_url = _get_dashboard_url_from_httproute(rc_name, rc_namespace)

    if not dashboard_url:
        if _is_openshift_cluster():
            try:
                api_instance = client.CustomObjectsApi(get_api_client())
                routes = api_instance.list_namespaced_custom_object(
                    group="route.openshift.io",
                    version="v1",
                    namespace=rc_namespace,
                    plural="routes",
                )
            except Exception as e:  # pragma: no cover
                return _kube_api_error_handling(e)

            for route in routes["items"]:
                if route["metadata"]["name"] == f"ray-dashboard-{rc_name}" or route[
                    "metadata"
                ]["name"].startswith(f"{rc_name}-ingress"):
                    protocol = "https" if route["spec"].get("tls") else "http"
                    dashboard_url = f"{protocol}://{route['spec']['host']}"
                    break
        else:
            try:
                api_instance = client.NetworkingV1Api(get_api_client())
                ingresses = api_instance.list_namespaced_ingress(rc_namespace)
            except Exception as e:  # pragma no cover
                return _kube_api_error_handling(e)
            for ingress in ingresses.items:
                annotations = ingress.metadata.annotations
                protocol = "http"
                if (
                    ingress.metadata.name == f"ray-dashboard-{rc_name}"
                    or ingress.metadata.name.startswith(f"{rc_name}-ingress")
                ):
                    if annotations is None:
                        protocol = "http"
                    elif "route.openshift.io/termination" in annotations:
                        protocol = "https"
                dashboard_url = f"{protocol}://{ingress.spec.rules[0].host}"

    (
        head_extended_resources,
        worker_extended_resources,
    ) = RayCluster._head_worker_extended_resources_from_rc_dict(rc)

    return RayClusterInfo(
        name=rc["metadata"]["name"],
        status=status,
        num_workers=rc["spec"]["workerGroupSpecs"][0]["replicas"],
        worker_mem_limits=rc["spec"]["workerGroupSpecs"][0]["template"]["spec"][
            "containers"
        ][0]["resources"]["limits"]["memory"],
        worker_mem_requests=rc["spec"]["workerGroupSpecs"][0]["template"]["spec"][
            "containers"
        ][0]["resources"]["requests"]["memory"],
        worker_cpu_requests=rc["spec"]["workerGroupSpecs"][0]["template"]["spec"][
            "containers"
        ][0]["resources"]["requests"]["cpu"],
        worker_cpu_limits=rc["spec"]["workerGroupSpecs"][0]["template"]["spec"][
            "containers"
        ][0]["resources"]["limits"]["cpu"],
        worker_extended_resources=worker_extended_resources,
        namespace=rc["metadata"]["namespace"],
        head_cpu_requests=rc["spec"]["headGroupSpec"]["template"]["spec"]["containers"][
            0
        ]["resources"]["requests"]["cpu"],
        head_cpu_limits=rc["spec"]["headGroupSpec"]["template"]["spec"]["containers"][
            0
        ]["resources"]["limits"]["cpu"],
        head_mem_requests=rc["spec"]["headGroupSpec"]["template"]["spec"]["containers"][
            0
        ]["resources"]["requests"]["memory"],
        head_mem_limits=rc["spec"]["headGroupSpec"]["template"]["spec"]["containers"][
            0
        ]["resources"]["limits"]["memory"],
        head_extended_resources=head_extended_resources,
        dashboard=dashboard_url,
    )


def _copy_to_ray(cluster: "RayCluster") -> RayClusterInfo:
    """Copy cluster config to RayClusterInfo."""
    ray = RayClusterInfo(
        name=cluster.name,
        status=cluster.status(print_to_console=False)[0],
        num_workers=cluster.num_workers,
        worker_mem_requests=cluster.worker_memory_requests,
        worker_mem_limits=cluster.worker_memory_limits,
        worker_cpu_requests=cluster.worker_cpu_requests,
        worker_cpu_limits=cluster.worker_cpu_limits,
        worker_extended_resources=cluster.worker_accelerators,
        namespace=cluster.namespace,
        dashboard=cluster.cluster_dashboard_uri(),
        head_mem_requests=cluster.head_memory_requests,
        head_mem_limits=cluster.head_memory_limits,
        head_cpu_requests=cluster.head_cpu_requests,
        head_cpu_limits=cluster.head_cpu_limits,
        head_extended_resources=cluster.head_accelerators,
    )
    if ray.status == CodeFlareClusterStatus.READY:
        ray.status = RayClusterStatus.READY
    return ray


def _is_openshift_cluster():
    """Check if running on OpenShift cluster."""
    try:
        config_check()
        for api in client.ApisApi(get_api_client()).get_api_versions().groups:
            for v in api.versions:
                if "route.openshift.io/v1" in v.group_version:
                    return True
        else:
            return False
    except Exception as e:  # pragma: no cover
        return _kube_api_error_handling(e)


def _get_dashboard_url_from_httproute(
    cluster_name: str, namespace: str
) -> Optional[str]:
    """Get the Ray dashboard URL from an HTTPRoute."""
    try:
        config_check()
        api_instance = client.CustomObjectsApi(get_api_client())

        label_selector = (
            f"ray.io/cluster-name={cluster_name},ray.io/cluster-namespace={namespace}"
        )

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
            search_namespaces = [
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
                except client.ApiException:
                    continue

            if not httproute:
                return None

        parent_refs = httproute.get("spec", {}).get("parentRefs", [])
        if not parent_refs:
            return None

        gateway_ref = parent_refs[0]
        gateway_name = gateway_ref.get("name")
        gateway_namespace = gateway_ref.get("namespace")

        if not gateway_name or not gateway_namespace:
            return None

        gateway = api_instance.get_namespaced_custom_object(
            group="gateway.networking.k8s.io",
            version="v1",
            namespace=gateway_namespace,
            plural="gateways",
            name=gateway_name,
        )

        listeners = gateway.get("spec", {}).get("listeners", [])
        if not listeners:
            return None

        hostname = listeners[0].get("hostname")
        if not hostname:
            return None

        return f"https://{hostname}/ray/{namespace}/{cluster_name}"

    except Exception:  # pragma: no cover
        return None


def _get_ingress_domain(cluster):  # pragma: no cover
    """Get ingress domain for local client URL."""
    config_check()

    if cluster.namespace is not None:
        namespace = cluster.namespace
    else:
        namespace = get_current_namespace()
    domain = None

    if _is_openshift_cluster():
        try:
            api_instance = client.CustomObjectsApi(get_api_client())
            routes = api_instance.list_namespaced_custom_object(
                group="route.openshift.io",
                version="v1",
                namespace=namespace,
                plural="routes",
            )
        except Exception as e:  # pragma: no cover
            return _kube_api_error_handling(e)

        for route in routes["items"]:
            if (
                route["spec"]["port"]["targetPort"] == "client"
                or route["spec"]["port"]["targetPort"] == 10001
            ):
                domain = route["spec"]["host"]
    else:
        try:
            api_client = client.NetworkingV1Api(get_api_client())
            ingresses = api_client.list_namespaced_ingress(namespace)
        except Exception as e:  # pragma: no cover
            return _kube_api_error_handling(e)

        for ingress in ingresses.items:
            if ingress.spec.rules[0].http.paths[0].backend.service.port.number == 10001:
                domain = ingress.spec.rules[0].host
    return domain

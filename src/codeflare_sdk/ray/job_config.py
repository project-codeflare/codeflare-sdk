"""
Defines the RayJobConfiguration dataclass for specifying KubeRay RayJob custom resources.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Union

from codeflare_sdk.ray.cluster.config import ClusterConfiguration
import corev1_client # Placeholder for kubernetes.client.models.V1PodTemplateSpec

# Placeholder for V1PodTemplateSpec until actual import is resolved
# from kubernetes.client.models import V1PodTemplateSpec
# For now, using a generic Dict as a placeholder
V1PodTemplateSpec = Dict[str, Any]


@dataclass
class RayJobConfiguration:
    """
    Configuration for a KubeRay RayJob.

    Args:
        name: Name of the RayJob.
        namespace: Namespace for the RayJob.
        entrypoint: Command to execute for the job.
        runtime_env_yaml: Runtime environment configuration as a YAML string.
        job_id: Optional ID for the job. Auto-generated if not set.
        active_deadline_seconds: Duration in seconds the job may be active.
        backoff_limit: Number of retries before marking job as failed.
        deletion_policy: Policy for resource deletion on job completion.
                         Valid values: "DeleteCluster", "DeleteWorkers", "DeleteSelf", "DeleteNone".
        submission_mode: How the Ray job is submitted to the RayCluster.
                         Valid values: "K8sJobMode", "HTTPMode", "InteractiveMode".
        managed_by: Controller managing the RayJob (e.g., "kueue.x-k8s.io/multikueue").
        ray_cluster_spec: Specification for the RayCluster if created by this RayJob.
        cluster_selector: Labels to select an existing RayCluster.
        submitter_pod_template: Pod template for the job submitter (if K8sJobMode).
        shutdown_after_job_finishes: Whether to delete the RayCluster after job completion.
        ttl_seconds_after_finished: TTL for RayCluster cleanup after job completion.
        suspend: Whether to suspend the RayJob (prevents RayCluster creation).
        metadata: Metadata for the RayJob.
        submitter_config_backoff_limit: BackoffLimit for the submitter Kubernetes Job.
    """
    name: str
    namespace: Optional[str] = None
    entrypoint: str
    runtime_env_yaml: Optional[str] = None
    job_id: Optional[str] = None
    active_deadline_seconds: Optional[int] = None
    backoff_limit: int = 0 # KubeRay default is 0
    deletion_policy: Optional[str] = None # Needs validation: DeleteCluster, DeleteWorkers, DeleteSelf, DeleteNone
    submission_mode: str = "K8sJobMode" # KubeRay default
    managed_by: Optional[str] = None
    ray_cluster_spec: Optional[ClusterConfiguration] = None
    cluster_selector: Dict[str, str] = field(default_factory=dict)
    submitter_pod_template: Optional[V1PodTemplateSpec] = None # Kubernetes V1PodTemplateSpec
    shutdown_after_job_finishes: bool = True # Common default, KubeRay itself doesn't default this in RayJobSpec directly
    ttl_seconds_after_finished: int = 0 # KubeRay default
    suspend: bool = False
    metadata: Dict[str, str] = field(default_factory=dict)
    submitter_config_backoff_limit: Optional[int] = None


    def __post_init__(self):
        if self.deletion_policy and self.deletion_policy not in [
            "DeleteCluster",
            "DeleteWorkers",
            "DeleteSelf",
            "DeleteNone",
        ]:
            raise ValueError(
                "deletion_policy must be one of 'DeleteCluster', 'DeleteWorkers', 'DeleteSelf', or 'DeleteNone'"
            )

        if self.submission_mode not in ["K8sJobMode", "HTTPMode", "InteractiveMode"]:
            raise ValueError(
                "submission_mode must be one of 'K8sJobMode', 'HTTPMode', or 'InteractiveMode'"
            )

        if self.managed_by and self.managed_by not in [
            "ray.io/kuberay-operator",
            "kueue.x-k8s.io/multikueue",
        ]:
            raise ValueError(
                "managed_by field value must be either 'ray.io/kuberay-operator' or 'kueue.x-k8s.io/multikueue'"
            )

        if self.ray_cluster_spec and self.cluster_selector:
            raise ValueError("Only one of ray_cluster_spec or cluster_selector can be provided.")

        if not self.ray_cluster_spec and not self.cluster_selector and self.submission_mode != "InteractiveMode":
             # In interactive mode, a cluster might already exist and the user connects to it.
             # Otherwise, a RayJob needs either a spec to create a cluster or a selector to find one.
            raise ValueError(
                "Either ray_cluster_spec (to create a new cluster) or cluster_selector (to use an existing one) must be specified unless in InteractiveMode."
            )

        # TODO: Add validation for submitter_pod_template if submission_mode is K8sJobMode
        # TODO: Add type validation for all fields
        pass 
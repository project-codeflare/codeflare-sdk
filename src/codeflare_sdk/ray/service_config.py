"""
Defines the RayServiceConfiguration dataclass for specifying KubeRay RayService custom resources.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from codeflare_sdk.ray.cluster.config import ClusterConfiguration
import corev1_client # Placeholder for kubernetes.client.models.V1Service

# Placeholder for V1Service until actual import is resolved
# from kubernetes.client.models import V1Service
# For now, using a generic Dict as a placeholder
V1Service = Dict[str, Any]

@dataclass
class RayServiceConfiguration:
    """
    Configuration for a KubeRay RayService.

    Args:
        name: Name of the RayService.
        namespace: Namespace for the RayService.
        serve_config_v2: YAML string defining the applications and deployments to deploy.
        ray_cluster_spec: Specification for the RayCluster underpinning the RayService.
        upgrade_strategy_type: Strategy for upgrading the RayService ("NewCluster" or "None").
        serve_service: Optional Kubernetes service definition for the serve endpoints.
        exclude_head_pod_from_serve_svc: If true, head pod won't be part of the K8s serve service.
        metadata: Metadata for the RayService.
        annotations: Annotations for the RayService.
    """
    name: str
    namespace: Optional[str] = None
    serve_config_v2: str
    ray_cluster_spec: ClusterConfiguration # A RayService always needs a RayClusterSpec
    upgrade_strategy_type: Optional[str] = "NewCluster" # KubeRay default if not specified, but good to be explicit.
    serve_service: Optional[V1Service] = None # Kubernetes V1Service
    exclude_head_pod_from_serve_svc: bool = False
    metadata: Dict[str, str] = field(default_factory=dict)
    annotations: Dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        if self.upgrade_strategy_type and self.upgrade_strategy_type not in [
            "NewCluster",
            "None",
        ]:
            raise ValueError(
                "upgrade_strategy_type must be one of 'NewCluster' or 'None'"
            )
        
        if not self.serve_config_v2:
            raise ValueError("serve_config_v2 must be provided.")

        # TODO: Add type validation for all fields
        pass 
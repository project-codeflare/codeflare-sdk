from dataclasses import dataclass, field
from typing import Dict, Any, Optional, Union, List
from enum import Enum


class RayJobStatus(str, Enum):
    """Status of a RayJob"""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    STOPPED = "STOPPED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


@dataclass
class RayJobSpec:
    """Specification for a RayJob Custom Resource"""

    # Required fields
    entrypoint: str
    """The command to execute for this job (e.g., "python script.py")"""

    # Optional fields
    submission_id: Optional[str] = None
    """Unique ID for the job submission. If not provided, one will be generated."""

    runtime_env: Optional[Dict[str, Any]] = None
    """Runtime environment configuration for the job, including:
    - working_dir: Directory containing files that your job will run in
    - pip: List of pip packages to install
    - conda: Conda environment specification
    - env_vars: Environment variables to set
    - py_modules: Python modules to include
    """

    metadata: Optional[Dict[str, str]] = None
    """Arbitrary metadata to store with the job"""

    entrypoint_num_cpus: Optional[Union[int, float]] = None
    """Number of CPU cores to reserve for the entrypoint command"""

    entrypoint_num_gpus: Optional[Union[int, float]] = None
    """Number of GPUs to reserve for the entrypoint command"""

    entrypoint_memory: Optional[int] = None
    """Amount of memory to reserve for the entrypoint command"""

    entrypoint_resources: Optional[Dict[str, float]] = None
    """Custom resources to reserve for the entrypoint command"""

    cluster_name: Optional[str] = None
    """Name of the RayCluster to run this job on"""

    cluster_namespace: Optional[str] = None
    """Namespace of the RayCluster to run this job on"""

    # Status fields (managed by the controller)
    status: RayJobStatus = field(default=RayJobStatus.PENDING)
    """Current status of the job"""

    message: Optional[str] = None
    """Detailed status message"""

    start_time: Optional[str] = None
    """Time when the job started"""

    end_time: Optional[str] = None
    """Time when the job ended"""

    driver_info: Optional[Dict[str, str]] = None
    """Information about the job driver, including:
    - id: Driver ID
    - node_ip_address: IP address of the node running the driver
    - pid: Process ID of the driver
    """


@dataclass
class RayJob:
    """RayJob Custom Resource Definition"""

    metadata: Dict[str, Any]
    """Kubernetes metadata for the job"""

    spec: RayJobSpec
    """Job specification"""

    api_version: str = "ray.io/v1"
    kind: str = "RayJob"

    status: Optional[Dict[str, Any]] = None
    """Status of the job (managed by the controller)"""

    def to_dict(self) -> Dict[str, Any]:
        """Convert the RayJob to a dictionary suitable for Kubernetes API"""
        return {
            "apiVersion": self.api_version,
            "kind": self.kind,
            "metadata": self.metadata,
            "spec": {
                "entrypoint": self.spec.entrypoint,
                "submission_id": self.spec.submission_id,
                "runtime_env": self.spec.runtime_env,
                "metadata": self.spec.metadata,
                "entrypoint_num_cpus": self.spec.entrypoint_num_cpus,
                "entrypoint_num_gpus": self.spec.entrypoint_num_gpus,
                "entrypoint_memory": self.spec.entrypoint_memory,
                "entrypoint_resources": self.spec.entrypoint_resources,
                "cluster_name": self.spec.cluster_name,
                "cluster_namespace": self.spec.cluster_namespace,
            },
            "status": {
                "status": self.spec.status,
                "message": self.spec.message,
                "start_time": self.spec.start_time,
                "end_time": self.spec.end_time,
                "driver_info": self.spec.driver_info,
            }
            if self.status is None
            else self.status,
        }

    def apply(self, force=False):
        """
        Applies the RayJob using server-side apply.
        If 'force' is set to True, conflicts will be forced.

        Args:
            force (bool): If True, force conflicts during server-side apply.
        """
        from kubernetes import client
        from kubernetes.dynamic import DynamicClient
        from ...common.kubernetes_cluster.auth import get_api_client, config_check
        from ...common import _kube_api_error_handling

        CF_SDK_FIELD_MANAGER = "codeflare-sdk"

        try:
            # Check Kubernetes configuration
            config_check()

            # Get the dynamic client
            crds = DynamicClient(get_api_client()).resources

            # Get the RayJob API instance
            api_version = "ray.io/v1"
            api_instance = crds.get(api_version=api_version, kind="RayJob")

            # Get namespace from metadata
            namespace = self.metadata.get("namespace", "default")
            name = self.metadata.get("name")

            # Convert job to dictionary
            body = self.to_dict()

            # Apply the job using server-side apply
            api_instance.server_side_apply(
                field_manager=CF_SDK_FIELD_MANAGER,
                group="ray.io",
                version="v1",
                namespace=namespace,
                plural="rayjobs",
                body=body,
                force_conflicts=force,
            )

            print(f"RayJob: '{name}' has successfully been applied")

        except AttributeError as e:
            raise RuntimeError(f"Failed to initialize DynamicClient: {e}")
        except Exception as e:
            return _kube_api_error_handling(e)

import os
import random
import string
import subprocess
from time import sleep
from codeflare_sdk import get_cluster
from kubernetes import client, config
from kubernetes.client import V1Toleration
from codeflare_sdk.common.kubernetes_cluster.kube_api_helpers import (
    _kube_api_error_handling,
)
from codeflare_sdk.common.utils import constants
from codeflare_sdk.common.utils.utils import get_ray_image_for_python_version


def get_ray_cluster(cluster_name, namespace):
    api = client.CustomObjectsApi()
    try:
        return api.get_namespaced_custom_object(
            group="ray.io",
            version="v1",
            namespace=namespace,
            plural="rayclusters",
            name=cluster_name,
        )
    except client.exceptions.ApiException as e:
        if e.status == 404:
            return None
        raise


def is_openshift():
    """Detect if running on OpenShift by checking for OpenShift-specific API resources."""
    try:
        api = client.ApiClient()
        discovery = client.ApisApi(api)
        # Check for OpenShift-specific API group
        groups = discovery.get_api_versions().groups
        for group in groups:
            if group.name == "image.openshift.io":
                return True
        return False
    except Exception:
        # If we can't determine, assume it's not OpenShift
        return False


def get_ray_image():
    """
    Get appropriate Ray image based on platform (OpenShift vs Kind/vanilla K8s).

    The tests marked with @pytest.mark.openshift can run on both OpenShift and Kind clusters
    with Kueue installed. This function automatically selects the appropriate image:
    - OpenShift: Uses the CUDA runtime image (quay.io/modh/ray:...)
    - Kind/K8s: Uses the standard Ray image (rayproject/ray:VERSION)

    You can override this behavior by setting the RAY_IMAGE environment variable.
    """
    # Allow explicit override via environment variable
    if "RAY_IMAGE" in os.environ:
        return os.environ["RAY_IMAGE"]

    # Auto-detect platform and return appropriate image
    if is_openshift():
        return get_ray_image_for_python_version()
    else:
        # Use standard Ray image for Kind/vanilla K8s
        return f"rayproject/ray:{constants.RAY_VERSION}"


def get_platform_appropriate_resources():
    """
    Get appropriate resource configurations based on platform.

    OpenShift with MODH images requires more memory than Kind with standard Ray images.

    Returns:
        dict: Resource configurations with keys:
            - head_cpu_requests, head_cpu_limits
            - head_memory_requests, head_memory_limits
            - worker_cpu_requests, worker_cpu_limits
            - worker_memory_requests, worker_memory_limits
    """
    if is_openshift():
        # MODH runtime images require more memory
        return {
            "head_cpu_requests": "1",
            "head_cpu_limits": "1.5",
            "head_memory_requests": 7,
            "head_memory_limits": 8,
            "worker_cpu_requests": "1",
            "worker_cpu_limits": "1",
            "worker_memory_requests": 5,
            "worker_memory_limits": 6,
        }
    else:
        # Standard Ray images require less memory
        return {
            "head_cpu_requests": "1",
            "head_cpu_limits": "1.5",
            "head_memory_requests": 7,
            "head_memory_limits": 8,
            "worker_cpu_requests": "1",
            "worker_cpu_limits": "1",
            "worker_memory_requests": 2,
            "worker_memory_limits": 3,
        }


def get_setup_env_variables(**kwargs):
    env_vars = dict()

    # Use input parameters provided for this function as environment variables
    for key, value in kwargs.items():
        env_vars[str(key)] = value

    # Use specified pip index url instead of default(https://pypi.org/simple) if related environment variables exists
    if (
        "PIP_INDEX_URL" in os.environ
        and os.environ.get("PIP_INDEX_URL") != None
        and os.environ.get("PIP_INDEX_URL") != ""
    ):
        env_vars["PIP_INDEX_URL"] = os.environ.get("PIP_INDEX_URL")
        env_vars["PIP_TRUSTED_HOST"] = os.environ.get("PIP_TRUSTED_HOST")
    else:
        env_vars["PIP_INDEX_URL"] = "https://pypi.org/simple/"
        env_vars["PIP_TRUSTED_HOST"] = "pypi.org"

    # Use specified storage bucket reference from which to download datasets
    if (
        "AWS_DEFAULT_ENDPOINT" in os.environ
        and os.environ.get("AWS_DEFAULT_ENDPOINT") != None
        and os.environ.get("AWS_DEFAULT_ENDPOINT") != ""
    ):
        env_vars["AWS_DEFAULT_ENDPOINT"] = os.environ.get("AWS_DEFAULT_ENDPOINT")
        env_vars["AWS_ACCESS_KEY_ID"] = os.environ.get("AWS_ACCESS_KEY_ID")
        env_vars["AWS_SECRET_ACCESS_KEY"] = os.environ.get("AWS_SECRET_ACCESS_KEY")
        env_vars["AWS_STORAGE_BUCKET"] = os.environ.get("AWS_STORAGE_BUCKET")
        env_vars["AWS_STORAGE_BUCKET_MNIST_DIR"] = os.environ.get(
            "AWS_STORAGE_BUCKET_MNIST_DIR"
        )
    return env_vars


def random_choice():
    alphabet = string.ascii_lowercase + string.digits
    return "".join(random.choices(alphabet, k=5))


def _parse_label_env(env_var, default):
    """Parse label from environment variable (format: 'key=value')."""
    label_str = os.getenv(env_var, default)
    return label_str.split("=")


def get_master_taint_key(self):
    """
    Detect the actual master/control-plane taint key from nodes.
    Returns the taint key if found, or defaults to control-plane.
    """
    # Check env var first (most efficient)
    if os.getenv("TOLERATION_KEY"):
        return os.getenv("TOLERATION_KEY")

    # Try to detect from cluster nodes
    try:
        nodes = self.api_instance.list_node()
        taint_key = next(
            (
                taint.key
                for node in nodes.items
                if node.spec.taints
                for taint in node.spec.taints
                if taint.key
                in [
                    "node-role.kubernetes.io/master",
                    "node-role.kubernetes.io/control-plane",
                ]
            ),
            None,
        )
        if taint_key:
            return taint_key
    except Exception as e:
        print(f"Warning: Could not detect master taint key: {e}")

    # Default fallback
    return "node-role.kubernetes.io/control-plane"


def ensure_nodes_labeled_for_flavors(self, num_flavors, with_labels):
    """
    Check if required node labels exist for ResourceFlavor targeting.
    This handles both default (worker-1=true) and non-default (ingress-ready=true) flavors.

    NOTE: This function does NOT modify cluster nodes. It only checks if required labels exist.
    If labels don't exist, the test will use whatever labels are available on the cluster.
    For shared clusters, set WORKER_LABEL and CONTROL_LABEL env vars to match existing labels.
    """
    if not with_labels:
        return

    worker_label, worker_value = _parse_label_env("WORKER_LABEL", "worker-1=true")
    control_label, control_value = _parse_label_env(
        "CONTROL_LABEL", "ingress-ready=true"
    )

    try:
        worker_nodes = self.api_instance.list_node(
            label_selector="node-role.kubernetes.io/worker"
        )

        if not worker_nodes.items:
            print("Warning: No worker nodes found")
            return

        # Check labels based on num_flavors
        labels_to_check = [("WORKER_LABEL", worker_label, worker_value)]
        if num_flavors > 1:
            labels_to_check.append(("CONTROL_LABEL", control_label, control_value))

        for env_var, label, value in labels_to_check:
            has_label = any(
                node.metadata.labels and node.metadata.labels.get(label) == value
                for node in worker_nodes.items
            )
            if not has_label:
                print(
                    f"Warning: Label {label}={value} not found (set {env_var} env var to match existing labels)"
                )

    except Exception as e:
        print(f"Warning: Could not check existing labels: {e}")


def create_namespace(self):
    try:
        self.namespace = f"test-ns-{random_choice()}"
        namespace_body = client.V1Namespace(
            metadata=client.V1ObjectMeta(name=self.namespace)
        )
        self.api_instance.create_namespace(namespace_body)
    except Exception as e:
        return RuntimeError(e)


def create_new_resource_flavor(self, num_flavors, with_labels, with_tolerations):
    self.resource_flavors = []
    for i in range(num_flavors):
        default = i < 1
        resource_flavor = f"test-resource-flavor-{random_choice()}"
        create_resource_flavor(
            self, resource_flavor, default, with_labels, with_tolerations
        )
        self.resource_flavors.append(resource_flavor)


def create_new_cluster_queue(self, num_queues):
    self.cluster_queues = []
    for i in range(num_queues):
        cluster_queue_name = f"test-cluster-queue-{random_choice()}"
        create_cluster_queue(self, cluster_queue_name, self.resource_flavors[i])
        self.cluster_queues.append(cluster_queue_name)


def create_new_local_queue(self, num_queues):
    self.local_queues = []
    for i in range(num_queues):
        is_default = i == 0
        local_queue_name = f"test-local-queue-{random_choice()}"
        create_local_queue(self, self.cluster_queues[i], local_queue_name, is_default)
        self.local_queues.append(local_queue_name)


def create_namespace_with_name(self, namespace_name):
    self.namespace = namespace_name
    try:
        namespace_body = client.V1Namespace(
            metadata=client.V1ObjectMeta(name=self.namespace)
        )
        self.api_instance.create_namespace(namespace_body)
    except Exception as e:
        # Check if it's an AlreadyExists error (409 Conflict) and ignore it
        if hasattr(e, "status") and e.status == 409:
            # Namespace already exists, which is fine - just continue
            print(
                f"Warning: Namespace '{namespace_name}' already exists, continuing..."
            )
            return
        return _kube_api_error_handling(e)


def delete_namespace(self):
    if hasattr(self, "namespace"):
        self.api_instance.delete_namespace(self.namespace)


def initialize_kubernetes_client(self):
    config.load_kube_config()
    # Initialize Kubernetes client
    self.api_instance = client.CoreV1Api()
    self.custom_api = client.CustomObjectsApi(self.api_instance.api_client)


def run_oc_command(args):
    try:
        result = subprocess.run(
            ["oc"] + args, capture_output=True, text=True, check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Error executing 'oc {' '.join(args)}': {e}")
        return None


def run_kubectl_command(args):
    try:
        result = subprocess.run(
            ["kubectl"] + args, capture_output=True, text=True, check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Error executing 'kubectl {' '.join(args)}': {e}")
        return None


def create_cluster_queue(self, cluster_queue, flavor):
    cluster_queue_json = {
        "apiVersion": "kueue.x-k8s.io/v1beta1",
        "kind": "ClusterQueue",
        "metadata": {"name": cluster_queue},
        "spec": {
            "namespaceSelector": {},
            "resourceGroups": [
                {
                    "coveredResources": ["cpu", "memory", "nvidia.com/gpu"],
                    "flavors": [
                        {
                            "name": flavor,
                            "resources": [
                                {"name": "cpu", "nominalQuota": 20},
                                {"name": "memory", "nominalQuota": "80Gi"},
                                {"name": "nvidia.com/gpu", "nominalQuota": 2},
                            ],
                        },
                    ],
                }
            ],
        },
    }

    try:
        # Check if cluster-queue exists
        self.custom_api.get_cluster_custom_object(
            group="kueue.x-k8s.io",
            plural="clusterqueues",
            version="v1beta1",
            name=cluster_queue,
        )
        print(f"'{cluster_queue}' already exists")
    except:
        # create cluster-queue
        self.custom_api.create_cluster_custom_object(
            group="kueue.x-k8s.io",
            plural="clusterqueues",
            version="v1beta1",
            body=cluster_queue_json,
        )
        print(f"'{cluster_queue}' created")

    self.cluster_queue = cluster_queue


def create_resource_flavor(
    self, flavor, default=True, with_labels=False, with_tolerations=False
):
    worker_label, worker_value = _parse_label_env("WORKER_LABEL", "worker-1=true")
    control_label, control_value = _parse_label_env(
        "CONTROL_LABEL", "ingress-ready=true"
    )

    toleration_key = os.getenv("TOLERATION_KEY") or get_master_taint_key(self)

    node_labels = {}
    if with_labels:
        node_labels = (
            {worker_label: worker_value} if default else {control_label: control_value}
        )

    resource_flavor_json = {
        "apiVersion": "kueue.x-k8s.io/v1beta1",
        "kind": "ResourceFlavor",
        "metadata": {"name": flavor},
        "spec": {
            "nodeLabels": node_labels,
            **(
                {
                    "tolerations": [
                        {
                            "key": toleration_key,
                            "operator": "Exists",
                            "effect": "NoSchedule",
                        }
                    ]
                }
                if with_tolerations
                else {}
            ),
        },
    }

    try:
        # Check if resource flavor exists
        self.custom_api.get_cluster_custom_object(
            group="kueue.x-k8s.io",
            plural="resourceflavors",
            version="v1beta1",
            name=flavor,
        )
        print(f"'{flavor}' already exists")
    except:
        # create kueue resource flavor
        self.custom_api.create_cluster_custom_object(
            group="kueue.x-k8s.io",
            plural="resourceflavors",
            version="v1beta1",
            body=resource_flavor_json,
        )
        print(f"'{flavor}' created!")

    self.resource_flavor = flavor


def create_local_queue(self, cluster_queue, local_queue, is_default=True):
    local_queue_json = {
        "apiVersion": "kueue.x-k8s.io/v1beta1",
        "kind": "LocalQueue",
        "metadata": {
            "namespace": self.namespace,
            "name": local_queue,
            "annotations": {"kueue.x-k8s.io/default-queue": str(is_default).lower()},
        },
        "spec": {"clusterQueue": cluster_queue},
    }

    try:
        # Check if local-queue exists in given namespace
        self.custom_api.get_namespaced_custom_object(
            group="kueue.x-k8s.io",
            namespace=self.namespace,
            plural="localqueues",
            version="v1beta1",
            name=local_queue,
        )
        print(f"'{local_queue}' already exists in namespace '{self.namespace}'")
    except:
        # create local-queue
        self.custom_api.create_namespaced_custom_object(
            group="kueue.x-k8s.io",
            namespace=self.namespace,
            plural="localqueues",
            version="v1beta1",
            body=local_queue_json,
        )
        print(f"'{local_queue}' created in namespace '{self.namespace}'")

    self.local_queue = local_queue


def create_kueue_resources(
    self, resource_ammount=1, with_labels=False, with_tolerations=False
):
    print("creating Kueue resources ...")
    create_new_resource_flavor(self, resource_ammount, with_labels, with_tolerations)
    create_new_cluster_queue(self, resource_ammount)
    create_new_local_queue(self, resource_ammount)


def delete_kueue_resources(self):
    for cq in self.cluster_queues:
        try:
            self.custom_api.delete_cluster_custom_object(
                group="kueue.x-k8s.io",
                plural="clusterqueues",
                version="v1beta1",
                name=cq,
            )
            print(f"\n'{cq}' cluster-queue deleted")
        except Exception as e:
            print(f"\nError deleting cluster-queue '{cq}' : {e}")

    # Delete if given resource-flavor exists
    for flavor in self.resource_flavors:
        try:
            self.custom_api.delete_cluster_custom_object(
                group="kueue.x-k8s.io",
                plural="resourceflavors",
                version="v1beta1",
                name=flavor,
            )
            print(f"'{flavor}' resource-flavor deleted")
        except Exception as e:
            print(f"\nError deleting resource-flavor '{flavor}': {e}")


def get_pod_node(self, namespace, name):
    label_selector = f"ray.io/cluster={name}"
    pods = self.api_instance.list_namespaced_pod(
        namespace, label_selector=label_selector
    )
    if not pods.items:
        raise ValueError(
            f"Unable to retrieve node name for pod '{name}' in namespace '{namespace}'"
        )
    pod = pods.items[0]
    node_name = pod.spec.node_name
    if node_name is None:
        raise ValueError(
            f"No node selected for pod '{name}' in namespace '{namespace}'"
        )
    return node_name


def get_flavor_spec(self, flavor_name):
    try:
        flavor = self.custom_api.get_cluster_custom_object(
            group="kueue.x-k8s.io",
            version="v1beta1",
            plural="resourceflavors",
            name=flavor_name,
        )
        return flavor
    except client.exceptions.ApiException as e:
        if e.status == 404:
            print(f"ResourceFlavor '{flavor_name}' not found.")
        else:
            print(f"Error retrieving ResourceFlavor '{flavor_name}': {e}")
        raise


def get_nodes_by_label(self, node_labels):
    label_selector = ",".join(f"{k}={v}" for k, v in node_labels.items())
    nodes = self.api_instance.list_node(label_selector=label_selector)
    return [node.metadata.name for node in nodes.items]


def get_tolerations_from_flavor(self, flavor_name):
    """
    Extract tolerations from a ResourceFlavor and convert them to V1Toleration objects.
    Returns a list of V1Toleration objects, or empty list if no tolerations found.
    """
    flavor_spec = get_flavor_spec(self, flavor_name)
    tolerations_spec = flavor_spec.get("spec", {}).get("tolerations", [])

    return [
        V1Toleration(
            key=tol_spec.get("key"),
            operator=tol_spec.get("operator", "Equal"),
            value=tol_spec.get("value"),
            effect=tol_spec.get("effect"),
        )
        for tol_spec in tolerations_spec
    ]


def assert_get_cluster_and_jobsubmit(
    self, cluster_name, accelerator=None, number_of_gpus=None
):
    # Retrieve the cluster
    cluster = get_cluster(cluster_name, self.namespace, False)

    cluster.details()

    # Initialize the job client
    client = cluster.job_client

    # Submit a job and get the submission ID
    env_vars = (
        get_setup_env_variables(ACCELERATOR=accelerator)
        if accelerator
        else get_setup_env_variables()
    )
    submission_id = client.submit_job(
        entrypoint="python mnist.py",
        runtime_env={
            "working_dir": "./tests/e2e/",
            "pip": "./tests/e2e/mnist_pip_requirements.txt",
            "env_vars": env_vars,
        },
        entrypoint_num_cpus=1 if number_of_gpus is None else None,
        entrypoint_num_gpus=number_of_gpus,
    )
    print(f"Submitted job with ID: {submission_id}")

    # Fetch the list of jobs and validate
    job_list = client.list_jobs()
    print(f"List of Jobs: {job_list}")

    # Validate the number of jobs in the list
    assert len(job_list) == 1

    # Validate the submission ID matches
    assert job_list[0].submission_id == submission_id

    cluster.down()


def wait_for_kueue_admission(self, job_api, job_name, namespace, timeout=120):
    print(f"Waiting for Kueue admission of job '{job_name}'...")
    elapsed_time = 0
    check_interval = 5

    while elapsed_time < timeout:
        try:
            job_cr = job_api.get_job(name=job_name, k8s_namespace=namespace)

            # Check if the job is no longer suspended
            is_suspended = job_cr.get("spec", {}).get("suspend", False)

            if not is_suspended:
                print(f"✓ Job '{job_name}' admitted by Kueue (no longer suspended)")
                return True

            # Debug: Check workload status every 10 seconds
            if elapsed_time % 10 == 0:
                workload = get_kueue_workload_for_job(self, job_name, namespace)
                if workload:
                    conditions = workload.get("status", {}).get("conditions", [])
                    print(f"DEBUG: Workload conditions for '{job_name}':")
                    for condition in conditions:
                        print(
                            f"    - {condition.get('type')}: {condition.get('status')} - {condition.get('reason', '')} - {condition.get('message', '')}"
                        )

            # Optional: Check status conditions for more details
            conditions = job_cr.get("status", {}).get("conditions", [])
            for condition in conditions:
                if (
                    condition.get("type") == "Suspended"
                    and condition.get("status") == "False"
                ):
                    print(
                        f"✓ Job '{job_name}' admitted by Kueue (Suspended=False condition)"
                    )
                    return True

        except Exception as e:
            print(f"Error checking job status: {e}")

        sleep(check_interval)
        elapsed_time += check_interval

    print(f"✗ Timeout waiting for Kueue admission of job '{job_name}'")
    return False


def create_limited_kueue_resources(self):
    print("Creating limited Kueue resources for preemption testing...")

    # Create a resource flavor with default (no special labels/tolerations)
    resource_flavor = f"limited-flavor-{random_choice()}"
    create_resource_flavor(
        self, resource_flavor, default=True, with_labels=False, with_tolerations=False
    )
    self.resource_flavors = [resource_flavor]

    # Create a cluster queue with very limited resources
    # Adjust quota based on platform - OpenShift needs more memory
    if is_openshift():
        # MODH images need more memory, so higher quota but still limited to allow only 1 job
        cpu_quota = 3
        memory_quota = "15Gi"  # One job needs ~8Gi head, allow some buffer
    else:
        # Standard Ray images - one job needs ~8G head + 500m submitter
        cpu_quota = 3
        memory_quota = "10Gi"  # Enough for one job (8G head + submitter), but not two

    cluster_queue_name = f"limited-cq-{random_choice()}"
    cluster_queue_json = {
        "apiVersion": "kueue.x-k8s.io/v1beta1",
        "kind": "ClusterQueue",
        "metadata": {"name": cluster_queue_name},
        "spec": {
            "namespaceSelector": {},
            "resourceGroups": [
                {
                    "coveredResources": ["cpu", "memory"],
                    "flavors": [
                        {
                            "name": resource_flavor,
                            "resources": [
                                {
                                    "name": "cpu",
                                    "nominalQuota": cpu_quota,
                                },
                                {
                                    "name": "memory",
                                    "nominalQuota": memory_quota,
                                },
                            ],
                        }
                    ],
                }
            ],
        },
    }

    try:
        self.custom_api.create_cluster_custom_object(
            group="kueue.x-k8s.io",
            plural="clusterqueues",
            version="v1beta1",
            body=cluster_queue_json,
        )
        print(f"✓ Created limited ClusterQueue: {cluster_queue_name}")
    except Exception as e:
        print(f"Error creating limited ClusterQueue: {e}")
        raise

    self.cluster_queues = [cluster_queue_name]

    # Create a local queue
    local_queue_name = f"limited-lq-{random_choice()}"
    create_local_queue(self, cluster_queue_name, local_queue_name, is_default=True)
    self.local_queues = [local_queue_name]

    print("✓ Limited Kueue resources created successfully")


def get_kueue_workload_for_job(self, job_name, namespace):
    try:
        # List all workloads in the namespace
        workloads = self.custom_api.list_namespaced_custom_object(
            group="kueue.x-k8s.io",
            version="v1beta1",
            plural="workloads",
            namespace=namespace,
        )

        # Find workload with matching RayJob owner reference
        for workload in workloads.get("items", []):
            owner_refs = workload.get("metadata", {}).get("ownerReferences", [])

            for owner_ref in owner_refs:
                if (
                    owner_ref.get("kind") == "RayJob"
                    and owner_ref.get("name") == job_name
                ):
                    workload_name = workload.get("metadata", {}).get("name")
                    print(
                        f"✓ Found Kueue workload '{workload_name}' for RayJob '{job_name}'"
                    )
                    return workload

        print(f"✗ No Kueue workload found for RayJob '{job_name}'")
        return None

    except Exception as e:
        print(f"Error getting Kueue workload for job '{job_name}': {e}")
        return None


def wait_for_job_status(
    job_api, rayjob_name: str, namespace: str, expected_status: str, timeout: int = 30
) -> bool:
    """
    Wait for a RayJob to reach a specific deployment status.

    Args:
        job_api: RayjobApi instance
        rayjob_name: Name of the RayJob
        namespace: Namespace of the RayJob
        expected_status: Expected jobDeploymentStatus value
        timeout: Maximum time to wait in seconds

    Returns:
        bool: True if status reached, False if timeout
    """
    elapsed_time = 0
    check_interval = 2

    while elapsed_time < timeout:
        status = job_api.get_job_status(name=rayjob_name, k8s_namespace=namespace)
        if status and status.get("jobDeploymentStatus") == expected_status:
            return True

        sleep(check_interval)
        elapsed_time += check_interval

    return False


def verify_rayjob_cluster_cleanup(
    cluster_api, rayjob_name: str, namespace: str, timeout: int = 60
):
    """
    Verify that the RayCluster created by a RayJob has been cleaned up.
    Handles KubeRay's automatic suffix addition to cluster names.

    Args:
        cluster_api: RayClusterApi instance
        rayjob_name: Name of the RayJob
        namespace: Namespace to check
        timeout: Maximum time to wait in seconds

    Raises:
        TimeoutError: If cluster is not cleaned up within timeout
    """
    elapsed_time = 0
    check_interval = 5

    while elapsed_time < timeout:
        # List all RayClusters in the namespace
        clusters = cluster_api.list_ray_clusters(
            k8s_namespace=namespace, async_req=False
        )

        # Check if any cluster exists that starts with our job name
        found = False
        for cluster in clusters.get("items", []):
            cluster_name = cluster.get("metadata", {}).get("name", "")
            # KubeRay creates clusters with pattern: {job_name}-raycluster-{suffix}
            if cluster_name.startswith(f"{rayjob_name}-raycluster"):
                found = True
                break

        if not found:
            # No cluster found, cleanup successful
            return

        sleep(check_interval)
        elapsed_time += check_interval

    raise TimeoutError(
        f"RayCluster for job '{rayjob_name}' was not cleaned up within {timeout} seconds"
    )


# =============================================================================
# Gateway API Resource Helper Functions
# =============================================================================


def get_reference_grant(
    custom_api,
    namespace: str,
    name: str = "kuberay-gateway-access",
):
    """
    Get a ReferenceGrant resource by name from a namespace.

    Args:
        custom_api: Kubernetes CustomObjectsApi instance
        namespace: Namespace to search in
        name: Name of the ReferenceGrant (default: "kuberay-gateway-access")

    Returns:
        ReferenceGrant resource dict if found, None otherwise
    """
    try:
        return custom_api.get_namespaced_custom_object(
            group="gateway.networking.k8s.io",
            version="v1beta1",
            namespace=namespace,
            plural="referencegrants",
            name=name,
        )
    except client.exceptions.ApiException as e:
        if e.status == 404:
            return None
        raise


def list_reference_grants(
    custom_api,
    namespace: str,
):
    """
    List all ReferenceGrant resources in a namespace.

    Args:
        custom_api: Kubernetes CustomObjectsApi instance
        namespace: Namespace to search in

    Returns:
        List of ReferenceGrant resources
    """
    try:
        result = custom_api.list_namespaced_custom_object(
            group="gateway.networking.k8s.io",
            version="v1beta1",
            namespace=namespace,
            plural="referencegrants",
        )
        return result.get("items", [])
    except client.exceptions.ApiException as e:
        if e.status == 404:
            return []
        raise


def get_httproutes_for_cluster(
    custom_api,
    cluster_name: str,
    namespace: str,
):
    """
    Get HTTPRoute resources for a specific RayCluster.

    HTTPRoutes for RayClusters are typically labeled with:
    - ray.io/cluster-name=<cluster_name>
    - ray.io/cluster-namespace=<namespace>

    Args:
        custom_api: Kubernetes CustomObjectsApi instance
        cluster_name: Name of the RayCluster
        namespace: Namespace of the RayCluster

    Returns:
        List of matching HTTPRoute resources
    """
    label_selector = (
        f"ray.io/cluster-name={cluster_name},ray.io/cluster-namespace={namespace}"
    )

    # Try cluster-wide search first (if permissions allow)
    try:
        result = custom_api.list_cluster_custom_object(
            group="gateway.networking.k8s.io",
            version="v1",
            plural="httproutes",
            label_selector=label_selector,
        )
        return result.get("items", [])
    except client.exceptions.ApiException:
        # Fall back to searching specific namespaces
        search_namespaces = [
            namespace,
            "redhat-ods-applications",
            "opendatahub",
            "default",
            "ray-system",
        ]

        httproutes = []
        for ns in search_namespaces:
            try:
                result = custom_api.list_namespaced_custom_object(
                    group="gateway.networking.k8s.io",
                    version="v1",
                    namespace=ns,
                    plural="httproutes",
                    label_selector=label_selector,
                )
                httproutes.extend(result.get("items", []))
            except client.exceptions.ApiException:
                continue

        return httproutes


def get_network_policies_for_cluster(
    networking_api,
    cluster_name: str,
    namespace: str,
):
    """
    Get NetworkPolicy resources related to a RayCluster.

    NetworkPolicies for RayClusters typically have labels or name patterns
    that match the cluster name.

    Args:
        networking_api: Kubernetes NetworkingV1Api instance
        cluster_name: Name of the RayCluster
        namespace: Namespace of the RayCluster

    Returns:
        List of matching NetworkPolicy resources
    """
    try:
        # List all network policies in the namespace
        all_policies = networking_api.list_namespaced_network_policy(namespace)

        # Filter policies that are related to the cluster
        # KubeRay typically creates policies with the cluster name in the name or labels
        matching_policies = []
        for policy in all_policies.items:
            policy_name = policy.metadata.name
            policy_labels = policy.metadata.labels or {}

            # Check if policy name contains cluster name
            if cluster_name in policy_name:
                matching_policies.append(policy)
                continue

            # Check if policy has ray.io/cluster label
            if policy_labels.get("ray.io/cluster") == cluster_name:
                matching_policies.append(policy)
                continue

            # Check if policy has ray.io/cluster-name label
            if policy_labels.get("ray.io/cluster-name") == cluster_name:
                matching_policies.append(policy)
                continue

        return matching_policies
    except client.exceptions.ApiException as e:
        if e.status == 404:
            return []
        raise


def wait_for_reference_grant(
    custom_api,
    namespace: str,
    name: str = "kuberay-gateway-access",
    timeout: int = 120,
):
    """
    Wait for a ReferenceGrant to be created.

    Args:
        custom_api: Kubernetes CustomObjectsApi instance
        namespace: Namespace to search in
        name: Name of the ReferenceGrant
        timeout: Maximum time to wait in seconds

    Returns:
        ReferenceGrant resource if found within timeout, None otherwise
    """
    elapsed = 0
    interval = 5

    while elapsed < timeout:
        grant = get_reference_grant(custom_api, namespace, name)
        if grant:
            return grant

        sleep(interval)
        elapsed += interval

    return None


def wait_for_httproute(
    custom_api,
    cluster_name: str,
    namespace: str,
    timeout: int = 120,
):
    """
    Wait for HTTPRoute(s) to be created for a RayCluster.

    Args:
        custom_api: Kubernetes CustomObjectsApi instance
        cluster_name: Name of the RayCluster
        namespace: Namespace of the RayCluster
        timeout: Maximum time to wait in seconds

    Returns:
        List of HTTPRoute resources if found within timeout, empty list otherwise
    """
    elapsed = 0
    interval = 5

    while elapsed < timeout:
        routes = get_httproutes_for_cluster(custom_api, cluster_name, namespace)
        if routes:
            return routes

        sleep(interval)
        elapsed += interval

    return []


def wait_for_network_policies(
    networking_api,
    cluster_name: str,
    namespace: str,
    timeout: int = 120,
):
    """
    Wait for NetworkPolicy resources to be created for a RayCluster.

    Args:
        networking_api: Kubernetes NetworkingV1Api instance
        cluster_name: Name of the RayCluster
        namespace: Namespace of the RayCluster
        timeout: Maximum time to wait in seconds

    Returns:
        List of NetworkPolicy resources if found within timeout, empty list otherwise
    """
    elapsed = 0
    interval = 5

    while elapsed < timeout:
        policies = get_network_policies_for_cluster(
            networking_api, cluster_name, namespace
        )
        if policies:
            return policies

        sleep(interval)
        elapsed += interval

    return []


# =============================================================================
# Resource Cleanup Verification Helper Functions
# =============================================================================


def wait_for_reference_grant_deletion(
    custom_api,
    namespace: str,
    name: str = "kuberay-gateway-access",
    timeout: int = 120,
) -> bool:
    """
    Wait for a ReferenceGrant to be deleted.

    Args:
        custom_api: Kubernetes CustomObjectsApi instance
        namespace: Namespace to check
        name: Name of the ReferenceGrant
        timeout: Maximum time to wait in seconds

    Returns:
        True if deleted within timeout, False otherwise
    """
    elapsed = 0
    interval = 5

    while elapsed < timeout:
        grant = get_reference_grant(custom_api, namespace, name)
        if grant is None:
            return True

        sleep(interval)
        elapsed += interval

    return False


def wait_for_httproute_deletion(
    custom_api,
    cluster_name: str,
    namespace: str,
    timeout: int = 120,
) -> bool:
    """
    Wait for HTTPRoute(s) to be deleted for a RayCluster.

    Args:
        custom_api: Kubernetes CustomObjectsApi instance
        cluster_name: Name of the RayCluster
        namespace: Namespace of the RayCluster
        timeout: Maximum time to wait in seconds

    Returns:
        True if all HTTPRoutes deleted within timeout, False otherwise
    """
    elapsed = 0
    interval = 5

    while elapsed < timeout:
        routes = get_httproutes_for_cluster(custom_api, cluster_name, namespace)
        if not routes:
            return True

        sleep(interval)
        elapsed += interval

    return False


def wait_for_network_policies_deletion(
    networking_api,
    cluster_name: str,
    namespace: str,
    timeout: int = 120,
):
    """
    Wait for NetworkPolicy resources to be deleted for a RayCluster.

    Args:
        networking_api: Kubernetes NetworkingV1Api instance
        cluster_name: Name of the RayCluster
        namespace: Namespace of the RayCluster
        timeout: Maximum time to wait in seconds

    Returns:
        Empty list if all deleted, otherwise list of remaining policies
    """
    elapsed = 0
    interval = 5

    while elapsed < timeout:
        policies = get_network_policies_for_cluster(
            networking_api, cluster_name, namespace
        )
        if not policies:
            return []

        sleep(interval)
        elapsed += interval

    # Return remaining policies that weren't deleted
    return policies


def verify_reference_grant_spec(
    reference_grant,
    expected_from_namespaces=None,
) -> bool:
    """
    Verify the ReferenceGrant has correct spec configuration.

    A valid ReferenceGrant for KubeRay Gateway access should have:
    - 'from' entries specifying which namespaces/groups can reference services
    - 'to' entries specifying what resources can be referenced

    Args:
        reference_grant: ReferenceGrant resource dict
        expected_from_namespaces: Optional list of expected source namespaces

    Returns:
        True if spec is valid, False otherwise
    """
    spec = reference_grant.get("spec", {})

    # Verify 'from' entries exist
    from_entries = spec.get("from", [])
    if not from_entries:
        print("ReferenceGrant has no 'from' entries")
        return False

    # Verify 'to' entries exist
    to_entries = spec.get("to", [])
    if not to_entries:
        print("ReferenceGrant has no 'to' entries")
        return False

    # Verify 'to' contains Service kind
    has_service_to = any(
        entry.get("kind") == "Service" or entry.get("group") == ""
        for entry in to_entries
    )
    if not has_service_to:
        print("ReferenceGrant does not allow Service references")
        return False

    # If expected namespaces specified, verify they are present
    if expected_from_namespaces:
        from_namespaces = set()
        for entry in from_entries:
            ns = entry.get("namespace")
            if ns:
                from_namespaces.add(ns)

        for expected_ns in expected_from_namespaces:
            if expected_ns not in from_namespaces:
                print(
                    f"Expected namespace '{expected_ns}' not in ReferenceGrant 'from'"
                )
                return False

    return True


def verify_httproute_spec(
    httproute,
    cluster_name: str,
    namespace: str,
) -> bool:
    """
    Verify the HTTPRoute has correct spec configuration for a RayCluster.

    A valid HTTPRoute for Ray dashboard access should have:
    - parentRefs pointing to a Gateway
    - rules with backendRefs pointing to the cluster's service
    - hostnames or path matching for routing

    Args:
        httproute: HTTPRoute resource dict
        cluster_name: Expected cluster name
        namespace: Expected namespace

    Returns:
        True if spec is valid, False otherwise
    """
    spec = httproute.get("spec", {})
    metadata = httproute.get("metadata", {})
    labels = metadata.get("labels", {})

    # Verify labels match the cluster
    if labels.get("ray.io/cluster-name") != cluster_name:
        print(f"HTTPRoute cluster-name label mismatch: expected {cluster_name}")
        return False

    if labels.get("ray.io/cluster-namespace") != namespace:
        print(f"HTTPRoute cluster-namespace label mismatch: expected {namespace}")
        return False

    # Verify parentRefs exist (points to Gateway)
    parent_refs = spec.get("parentRefs", [])
    if not parent_refs:
        print("HTTPRoute has no parentRefs")
        return False

    # Verify rules exist
    rules = spec.get("rules", [])
    if not rules:
        print("HTTPRoute has no rules")
        return False

    # Verify at least one rule has backendRefs
    has_backend_refs = any(rule.get("backendRefs") for rule in rules)
    if not has_backend_refs:
        print("HTTPRoute rules have no backendRefs")
        return False

    return True


def verify_network_policy_spec(
    policy,
    cluster_name: str,
):
    """
    Verify a NetworkPolicy has appropriate selectors and ports.

    Returns a dict with verification results:
    - has_pod_selector: True if policy has a pod selector
    - has_ingress_rules: True if policy has ingress rules
    - has_egress_rules: True if policy has egress rules
    - allowed_ports: List of allowed port numbers
    - policy_types: List of policy types (Ingress/Egress)

    Args:
        policy: NetworkPolicy resource
        cluster_name: Expected cluster name

    Returns:
        Dict with verification results
    """
    result = {
        "name": policy.metadata.name,
        "has_pod_selector": False,
        "has_ingress_rules": False,
        "has_egress_rules": False,
        "allowed_ports": [],
        "policy_types": [],
        "pod_selector_labels": {},
    }

    spec = policy.spec

    # Check pod selector
    if spec.pod_selector:
        match_labels = spec.pod_selector.match_labels or {}
        result["has_pod_selector"] = bool(match_labels)
        result["pod_selector_labels"] = match_labels

    # Check policy types
    if spec.policy_types:
        result["policy_types"] = spec.policy_types

    # Check ingress rules
    if spec.ingress:
        result["has_ingress_rules"] = True
        for ingress_rule in spec.ingress:
            if ingress_rule.ports:
                for port in ingress_rule.ports:
                    if port.port:
                        result["allowed_ports"].append(port.port)

    # Check egress rules
    if spec.egress:
        result["has_egress_rules"] = True
        for egress_rule in spec.egress:
            if egress_rule.ports:
                for port in egress_rule.ports:
                    if port.port:
                        result["allowed_ports"].append(port.port)

    return result

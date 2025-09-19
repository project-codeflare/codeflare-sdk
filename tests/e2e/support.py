import os
import random
import string
import subprocess
from time import sleep
from codeflare_sdk import get_cluster
from kubernetes import client, config
from codeflare_sdk.common.kubernetes_cluster.kube_api_helpers import (
    _kube_api_error_handling,
)
from codeflare_sdk.common.utils import constants


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
        return constants.CUDA_RUNTIME_IMAGE
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
            "head_memory_requests": 3,
            "head_memory_limits": 4,
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
                                {"name": "cpu", "nominalQuota": 10},
                                {"name": "memory", "nominalQuota": "36Gi"},
                                {"name": "nvidia.com/gpu", "nominalQuota": 0},
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
    worker_label, worker_value = os.getenv("WORKER_LABEL", "worker-1=true").split("=")
    control_label, control_value = os.getenv(
        "CONTROL_LABEL", "ingress-ready=true"
    ).split("=")
    toleration_key = os.getenv(
        "TOLERATION_KEY", "node-role.kubernetes.io/control-plane"
    )

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
    # Delete if given cluster-queue exists
    if not hasattr(self, "cluster_queues"):
        return
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
                    print(f"  DEBUG: Workload conditions for '{job_name}':")
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
        memory_quota = "8Gi"  # Reduced from 15Gi to ensure second job is suspended (1 job needs 7Gi)
    else:
        # Standard Ray images need less memory
        cpu_quota = 3
        memory_quota = "4Gi"

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

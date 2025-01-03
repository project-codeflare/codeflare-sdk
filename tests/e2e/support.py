import json
import os
import random
import string
import subprocess
from codeflare_sdk import get_cluster
from kubernetes import client, config
import kubernetes.client
from codeflare_sdk.common.kubernetes_cluster.kube_api_helpers import (
    _kube_api_error_handling,
)


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


def get_ray_image():
    default_ray_image = "quay.io/modh/ray@sha256:0d715f92570a2997381b7cafc0e224cfa25323f18b9545acfd23bc2b71576d06"
    return os.getenv("RAY_IMAGE", default_ray_image)


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
                                {"name": "cpu", "nominalQuota": 9},
                                {"name": "memory", "nominalQuota": "36Gi"},
                                {"name": "nvidia.com/gpu", "nominalQuota": 1},
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

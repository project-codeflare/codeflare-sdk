import os
import random
import string
import subprocess
from kubernetes import client, config
import kubernetes.client
from codeflare_sdk.utils.kube_api_helpers import _kube_api_error_handling


def get_ray_image():
    default_ray_image = "quay.io/modh/ray@sha256:83084b89885232e5733027b2ee45b83d3642ce32ae0b8e18b79ed45b6e734283"
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


def create_new_resource_flavor(self):
    self.resource_flavor = f"test-resource-flavor-{random_choice()}"
    create_resource_flavor(self, self.resource_flavor)


def create_new_cluster_queue(self):
    self.cluster_queue = f"test-cluster-queue-{random_choice()}"
    create_cluster_queue(self, self.cluster_queue, self.resource_flavor)


def create_new_local_queue(self):
    self.local_queue = f"test-local-queue-{random_choice()}"
    create_local_queue(self, self.cluster_queue, self.local_queue)


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
                        }
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


def create_resource_flavor(self, flavor):
    resource_flavor_json = {
        "apiVersion": "kueue.x-k8s.io/v1beta1",
        "kind": "ResourceFlavor",
        "metadata": {"name": flavor},
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


def create_local_queue(self, cluster_queue, local_queue):
    local_queue_json = {
        "apiVersion": "kueue.x-k8s.io/v1beta1",
        "kind": "LocalQueue",
        "metadata": {
            "namespace": self.namespace,
            "name": local_queue,
            "annotations": {"kueue.x-k8s.io/default-queue": "true"},
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


def create_kueue_resources(self):
    print("creating Kueue resources ...")
    create_new_resource_flavor(self)
    create_new_cluster_queue(self)
    create_new_local_queue(self)


def delete_kueue_resources(self):
    # Delete if given cluster-queue exists
    try:
        self.custom_api.delete_cluster_custom_object(
            group="kueue.x-k8s.io",
            plural="clusterqueues",
            version="v1beta1",
            name=self.cluster_queue,
        )
        print(f"\n'{self.cluster_queue}' cluster-queue deleted")
    except Exception as e:
        print(f"\nError deleting cluster-queue '{self.cluster_queue}' : {e}")

    # Delete if given resource-flavor exists
    try:
        self.custom_api.delete_cluster_custom_object(
            group="kueue.x-k8s.io",
            plural="resourceflavors",
            version="v1beta1",
            name=self.resource_flavor,
        )
        print(f"'{self.resource_flavor}' resource-flavor deleted")
    except Exception as e:
        print(f"\nError deleting resource-flavor '{self.resource_flavor}' : {e}")

import os
import random
import string
from kubernetes import client, config
import kubernetes.client
import subprocess


def get_ray_image():
    default_ray_image = "quay.io/project-codeflare/ray:latest-py39-cu118"
    return os.getenv("RAY_IMAGE", default_ray_image)


def random_choice():
    alphabet = string.ascii_lowercase + string.digits
    return "".join(random.choices(alphabet, k=5))


def create_namespace(self):
    self.namespace = f"test-ns-{random_choice()}"
    namespace_body = client.V1Namespace(
        metadata=client.V1ObjectMeta(name=self.namespace)
    )
    self.api_instance.create_namespace(namespace_body)


def delete_namespace(self):
    if hasattr(self, "namespace"):
        self.api_instance.delete_namespace(self.namespace)


def initialize_kubernetes_client(self):
    config.load_kube_config()
    # Initialize Kubernetes client
    self.api_instance = client.CoreV1Api()
    self.custom_api = kubernetes.client.CustomObjectsApi(self.api_instance.api_client)


def run_oc_command(args):
    try:
        result = subprocess.run(
            ["oc"] + args, capture_output=True, text=True, check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Error executing 'oc {' '.join(args)}': {e}")
        return None

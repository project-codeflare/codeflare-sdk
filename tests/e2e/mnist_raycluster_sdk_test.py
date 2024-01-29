import base64
import logging
import os
import sys
from kubernetes import client, config
from kubernetes.client import V1Job, V1ObjectMeta, V1JobSpec, V1PodTemplateSpec, V1PodSpec, V1Container, V1VolumeMount, V1Volume, V1ConfigMapVolumeSource, V1EmptyDirVolumeSource, V1EnvVar, V1SecurityContext, V1SeccompProfile, V1Capabilities
from kubernetes.client.rest import ApiException
import time
import subprocess

import pytest

from support import random_choice, read_file

class TestMNISTRayClusterSDK:
    def setup_method(self):
        # Load the kube config from the environment or Kube config file.
        config.load_kube_config()

        # Initialize Kubernetes client
        self.api_instance = client.CoreV1Api()
        self.batch_api = client.BatchV1Api()
        self.cmap = client.V1ConfigMap()

    def teardown_method(self):
        if hasattr(self, 'namespace'):
            self.api_instance.delete_namespace(self.namespace)
        if hasattr(self, 'configmap'):
            self.api_instance.delete_namespaced_config_map(self.configmap.metadata.name, self.namespace)


    def test_mnist_ray_cluster_sdk(self):
        namespace = self.create_test_namespace()

        file_paths = [
            "./tests/e2e/mnist_raycluster_sdk_test.py",
            "./tests/e2e/requirements.txt",
            "./tests/e2e/mnist.py",
            "./tests/e2e/install-codeflare-sdk.sh"
        ]
        self.create_config_map(namespace, file_paths)

        self.run_mnist_raycluster_sdk()


    def create_test_namespace(self):
        self.namespace = f"test-ns-{random_choice()}"
        namespace_body = client.V1Namespace(metadata=client.V1ObjectMeta(name=self.namespace))
        self.api_instance.create_namespace(namespace_body)
        return self.namespace

    def create_config_map(self, namespace, file_paths):
        data = {os.path.basename(path): read_file(path) for path in file_paths}
        binary_data = {key: base64.b64encode(value).decode('utf-8') for key, value in data.items()}
        config_map = client.V1ConfigMap(
            api_version="v1",
            kind="ConfigMap",
            metadata=client.V1ObjectMeta(
                generate_name="config-",
                namespace=namespace,
            ),
            binary_data=binary_data,
            immutable=True,
        )
        # config_map = client.V1ConfigMap(data=data)
        self.api_instance.create_namespaced_config_map(namespace=namespace, body=config_map)

    def run_mnist_raycluster_sdk(self):
        script_path = './tests/e2e/mnist_raycluster_sdk.py'
        result = subprocess.run(['python', script_path, self.namespace])
        output = result.stdout
        errors = result.stderr
        if result.returncode != 0:
            raise subprocess.CalledProcessError(result.returncode, 'python', output=output, stderr=errors)
        return output

# # Specifically used on KinD clusters
#     def configure_pods(self):
#         hostname = os.getenv('CLUSTER_HOSTNAME')
#         node = self.get_first_node()
#         node_ip = self.get_node_internal_ip(node)
#         host_alias = client.V1HostAlias(ip=node_ip, hostnames=[hostname])

#         pods = self.find_mnist_head_pod(self.namespace)
#         for pod in pods:
#             container = pod.spec.containers[0]
#             if not pod.spec.host_aliases:
#                 pod.spec.host_aliases = []
#             pod.spec.host_aliases.append(host_alias)
#             if not container.env:
#                 container.env = []
#             container.env.append(hostname)



    # def get_node_internal_ip(node):
    #     for address in node.status.addresses:
    #         if address.type == "InternalIP":
    #             ip = address.address
    #             return ip

    # def get_first_node(self):
    #     try:
    #         # List all nodes in the cluster
    #         nodes = self.api_instance.list_node()
    #     except ApiException as e:
    #         pytest.fail(f"Exception when calling CoreV1Api->list_node: {e}")
    #     return nodes.items[0]
    
    # def find_mnist_head_pod(self, namespace):
    #     try:
    #         # List all pods in the specified namespace
    #         pods = self.v1.list_namespaced_pod(namespace)
    #     except ApiException as e:
    #         print(f"Exception when calling CoreV1Api->list_namespaced_pod: {e}")
    #         return None
        
    #     for pod in pods.items:
    #         if pod.metadata.name.startswith("mnist-head"):
    #             return pod
    #     print("No 'mnist-head' pod found in the namespace")
    #     return None

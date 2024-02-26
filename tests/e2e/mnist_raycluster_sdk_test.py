from kubernetes import client, config
import kubernetes.client

import os

from time import sleep

import ray

from torchx.specs.api import AppState, is_terminal

from codeflare_sdk.cluster.cluster import Cluster, ClusterConfiguration
from codeflare_sdk.job.jobs import DDPJobDefinition

import pytest

from support import *

# Creates a Ray cluster, and trains the MNIST dataset using the CodeFlare SDK.
# Asserts creation of AppWrapper, RayCluster, and successful completion of the training job.
# Covers successfull installation of CodeFlare-SDK


@pytest.mark.kind
@pytest.mark.openshift
class TestMNISTRayClusterSDK:
    def setup_method(self):
        initialize_kubernetes_client(self)

    def teardown_method(self):
        delete_namespace(self)

    def test_mnist_ray_cluster_sdk(self):
        create_namespace(self)
        self.run_mnist_raycluster_sdk()

    def run_mnist_raycluster_sdk(self):
        ray_image = get_ray_image()

        cluster = Cluster(
            ClusterConfiguration(
                name="mnist",
                namespace=self.namespace,
                num_workers=1,
                head_cpus="500m",
                head_memory=2,
                min_cpus="500m",
                max_cpus=1,
                min_memory=1,
                max_memory=2,
                num_gpus=0,
                instascale=False,
                image=ray_image,
                write_to_file=True,
                mcad=True,
            )
        )

        cluster.up()
        self.assert_appwrapper_exists()

        cluster.status()

        cluster.wait_ready()
        self.assert_raycluster_exists()

        cluster.status()

        cluster.details()

        jobdef = DDPJobDefinition(
            name="mnist",
            script="./tests/e2e/mnist.py",
            scheduler_args={"requirements": "./tests/e2e/mnist_pip_requirements.txt"},
        )
        job = jobdef.submit(cluster)

        done = False
        time = 0
        timeout = 900
        while not done:
            status = job.status()
            if is_terminal(status.state):
                break
            if not done:
                print(status)
                if timeout and time >= timeout:
                    raise TimeoutError(f"job has timed out after waiting {timeout}s")
                sleep(5)
                time += 5

        print(job.status())
        self.assert_job_completion(status)

        print(job.logs())

        cluster.down()

    # Assertions
    def assert_appwrapper_exists(self):
        try:
            self.custom_api.get_namespaced_custom_object(
                "workload.codeflare.dev",
                "v1beta1",
                self.namespace,
                "appwrappers",
                "mnist",
            )
            print(
                f"AppWrapper 'mnist' has been created in the namespace: '{self.namespace}'"
            )
            assert True
        except Exception as e:
            print(f"AppWrapper 'mnist' has not been created. Error: {e}")
            assert False

    def assert_raycluster_exists(self):
        try:
            self.custom_api.get_namespaced_custom_object(
                "ray.io", "v1", self.namespace, "rayclusters", "mnist"
            )
            print(
                f"RayCluster 'mnist' created successfully in the namespace: '{self.namespace}'"
            )
            assert True
        except Exception as e:
            print(f"RayCluster 'mnist' has not been created. Error: {e}")
            assert False

    def assert_job_completion(self, status):
        if status.state == AppState.SUCCEEDED:
            print(f"Job has completed: '{status.state}'")
            assert True
        else:
            print(f"Job has completed: '{status.state}'")
            assert False

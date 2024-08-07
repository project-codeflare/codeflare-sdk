import requests

from time import sleep

from torchx.specs.api import AppState, is_terminal

from codeflare_sdk import Cluster, ClusterConfiguration, TokenAuthentication
from codeflare_sdk.job.jobs import DDPJobDefinition

import pytest

from support import *

# This test Creates a Ray cluster with openshift_oauth enable and covers the Ray Job submission with authentication and without authentication functionality


@pytest.mark.openshift
class TestRayClusterSDKOauth:
    def setup_method(self):
        initialize_kubernetes_client(self)

    def teardown_method(self):
        delete_namespace(self)

    def test_mnist_ray_cluster_sdk_auth(self):
        self.setup_method()
        create_namespace(self)
        self.run_mnist_raycluster_sdk_oauth()

    def run_mnist_raycluster_sdk_oauth(self):
        ray_image = get_ray_image()

        auth = TokenAuthentication(
            token=run_oc_command(["whoami", "--show-token=true"]),
            server=run_oc_command(["whoami", "--show-server=true"]),
            skip_tls=True,
        )
        auth.login()

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
                openshift_oauth=True,
            )
        )

        cluster.up()
        self.assert_appwrapper_exists()

        cluster.status()

        cluster.wait_ready()

        cluster.status()

        cluster.details()

        self.assert_jobsubmit_withoutLogin(cluster)

        self.assert_jobsubmit_withlogin(cluster)

    # Assertions

    def assert_jobsubmit_withoutLogin(self, cluster):
        dashboard_url = cluster.cluster_dashboard_uri()
        jobdata = {
            "entrypoint": "python mnist.py",
            "runtime_env": {
                "working_dir": "./tests/e2e/",
                "pip": "mnist_pip_requirements.txt",
            },
        }
        try:
            response = requests.post(
                dashboard_url + "/api/jobs/", verify=False, json=jobdata
            )
            if response.status_code == 403:
                assert True
            else:
                response.raise_for_status()
                assert False

        except Exception as e:
            print(f"An unexpected error occurred. Error: {e}")
            assert False

    def assert_jobsubmit_withlogin(self, cluster):
        self.assert_appwrapper_exists()

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

        cluster.down()

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

    def assert_job_completion(self, status):
        if status.state == AppState.SUCCEEDED:
            print(f"Job has completed: '{status.state}'")
            assert True
        else:
            print(f"Job has completed: '{status.state}'")
            assert False

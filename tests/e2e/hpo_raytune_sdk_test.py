import requests

from time import sleep

from codeflare_sdk import Cluster, ClusterConfiguration, TokenAuthentication
from codeflare_sdk.job import RayJobClient

import pytest

from support import *

# This test creates a Ray Cluster and submit the Ray Job of Hyperparameter Tuning with Ray Tune functionality is successfully tuning


@pytest.mark.openshift
class TestRayTuneHPOTuning:
    def setup_method(self):
        initialize_kubernetes_client(self)

    def teardown_method(self):
        delete_namespace(self)
        delete_kueue_resources(self)

    def test_ray_tune_hpo_tuning(self):
        self.setup_method()
        create_namespace(self)
        create_kueue_resources(self)
        self.run_ray_tune_hpo_tuning()

    def run_ray_tune_hpo_tuning(self):
        auth = TokenAuthentication(
            token=run_oc_command(["whoami", "--show-token=true"]),
            server=run_oc_command(["whoami", "--show-server=true"]),
            skip_tls=True,
        )
        auth.login()

        cluster = Cluster(
            ClusterConfiguration(
                name="hpo-raytune",
                namespace=self.namespace,
                num_workers=1,
                min_cpus=1,
                max_cpus=1,
                min_memory=4,
                max_memory=4,
                num_gpus=0,
                write_to_file=True,
                verify_tls=False,
            )
        )

        cluster.up()

        cluster.status()

        cluster.wait_ready()

        cluster.status()

        cluster.details()

        self.assert_jobsubmit(cluster)

    # Assertions
    def assert_jobsubmit(self, cluster):
        auth_token = run_oc_command(["whoami", "--show-token=true"])
        ray_dashboard = cluster.cluster_dashboard_uri()
        header = {"Authorization": f"Bearer {auth_token}"}
        client = RayJobClient(address=ray_dashboard, headers=header, verify=False)

        submission_id = client.submit_job(
            entrypoint="python mnist_raytune_hpo_pytorch.py",
            runtime_env={
                "working_dir": "./tests/e2e/",
                "pip": "./tests/e2e/hpo_raytune_pip_requirements.txt",
            },
        )
        print(f"Submitted job with ID: {submission_id}")
        done = False
        time = 0
        timeout = 900
        while not done:
            status = client.get_job_status(submission_id)
            if status.is_terminal():
                break
            if not done:
                print(status)
                if timeout and time >= timeout:
                    raise TimeoutError(f"job has timed out after waiting {timeout}s")
                sleep(5)
                time += 5

        logs = client.get_job_logs(submission_id)
        print(logs)

        self.assert_job_completion(status)

        client.delete_job(submission_id)

        cluster.down()

    def assert_job_completion(self, status):
        if status == "SUCCEEDED":
            print(f"Job has completed: '{status}'")
            assert True
        else:
            print(f"Job has completed: '{status}'")
            assert False

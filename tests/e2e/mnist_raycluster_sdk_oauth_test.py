import requests

from time import sleep

from codeflare_sdk import (
    Cluster,
    ClusterConfiguration,
    TokenAuthentication,
)
from codeflare_sdk.ray.client import RayJobClient

import pytest

from support import *

# This test creates a Ray Cluster and covers the Ray Job submission with authentication and without authentication functionality on Openshift Cluster


@pytest.mark.openshift
class TestRayClusterSDKOauth:
    def setup_method(self):
        initialize_kubernetes_client(self)

    def teardown_method(self):
        delete_namespace(self)
        delete_kueue_resources(self)

    def test_mnist_ray_cluster_sdk_auth(self):
        self.setup_method()
        create_namespace(self)
        create_kueue_resources(self)
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
                head_memory_requests=6,
                head_memory_limits=8,
                worker_cpu_requests=1,
                worker_cpu_limits=1,
                worker_memory_requests=6,
                worker_memory_limits=8,
                image=ray_image,
                write_to_file=True,
                verify_tls=False,
            )
        )

        cluster.apply()

        cluster.status()

        cluster.wait_ready()

        cluster.status()

        cluster.details()

        self.assert_jobsubmit_withoutLogin(cluster)
        self.assert_jobsubmit_withlogin(cluster)
        assert_get_cluster_and_jobsubmit(self, "mnist")

    # Assertions

    def assert_jobsubmit_withoutLogin(self, cluster):
        dashboard_url = cluster.cluster_dashboard_uri()

        # Verify that job submission is actually blocked by attempting to submit without auth
        # The endpoint path depends on whether we're using HTTPRoute (with path prefix) or not
        if "/ray/" in dashboard_url:
            # HTTPRoute format: https://hostname/ray/namespace/cluster-name
            # API endpoint is at the same base path
            api_url = dashboard_url + "/api/jobs/"
        else:
            # OpenShift Route format: https://hostname
            # API endpoint is directly under the hostname
            api_url = dashboard_url + "/api/jobs/"

        jobdata = {
            "entrypoint": "python mnist.py",
            "runtime_env": {
                "working_dir": "./tests/e2e/",
                "pip": "./tests/e2e/mnist_pip_requirements.txt",
                "env_vars": get_setup_env_variables(),
            },
        }

        # Try to submit a job without authentication
        # Follow redirects to see the final response - if it redirects to login, that's still a failure
        response = requests.post(
            api_url, verify=False, json=jobdata, allow_redirects=True
        )

        # Check if the submission was actually blocked
        # Success indicators that submission was blocked:
        # 1. Status code 403 (Forbidden)
        # 2. Status code 302 (Redirect to login) - but we need to verify the final response after redirect
        # 3. Status code 200 but with HTML content (login page) instead of JSON (job submission response)
        # 4. Status code 401 (Unauthorized)

        submission_blocked = False

        if response.status_code == 403:
            submission_blocked = True
        elif response.status_code == 401:
            submission_blocked = True
        elif response.status_code == 302:
            # Redirect happened - check if final response after redirect is also a failure
            # If we followed redirects, check the final status
            submission_blocked = True  # Redirect to login means submission failed
        elif response.status_code == 200:
            # Check if response is HTML (login page) instead of JSON (job submission response)
            content_type = response.headers.get("Content-Type", "")
            if "text/html" in content_type or "application/json" not in content_type:
                # Got HTML (likely login page) instead of JSON - submission was blocked
                submission_blocked = True
            else:
                # Got JSON response - check if it's an error or actually a successful submission
                try:
                    json_response = response.json()
                    # If it's a successful job submission, it should have a 'job_id' or 'submission_id'
                    # If it's an error, it might have 'error' or 'message'
                    if "job_id" in json_response or "submission_id" in json_response:
                        # Job was actually submitted - this is a failure!
                        submission_blocked = False
                    else:
                        # Error response - submission was blocked
                        submission_blocked = True
                except ValueError:
                    # Not JSON - likely HTML login page
                    submission_blocked = True

        if not submission_blocked:
            assert (
                False
            ), f"Job submission succeeded without authentication! Status: {response.status_code}, Response: {response.text[:200]}"

        # Also verify that RayJobClient cannot be used without authentication
        try:
            client = RayJobClient(address=dashboard_url, verify=False)
            # Try to call a method to trigger the connection and authentication check
            client.list_jobs()
            assert (
                False
            ), "RayJobClient succeeded without authentication - this should not be possible"
        except (
            requests.exceptions.JSONDecodeError,
            requests.exceptions.HTTPError,
            Exception,
        ):
            # Any exception is expected when trying to use the client without auth
            pass

        assert True, "Job submission without authentication was correctly blocked"

    def assert_jobsubmit_withlogin(self, cluster):
        auth_token = run_oc_command(["whoami", "--show-token=true"])
        ray_dashboard = cluster.cluster_dashboard_uri()
        header = {"Authorization": f"Bearer {auth_token}"}
        client = RayJobClient(address=ray_dashboard, headers=header, verify=False)

        # Verify that no jobs were submitted during the previous unauthenticated test
        # This ensures that the authentication check in assert_jobsubmit_withoutLogin actually worked
        existing_jobs = client.list_jobs()
        if existing_jobs:
            job_ids = [
                job.job_id if hasattr(job, "job_id") else str(job)
                for job in existing_jobs
            ]
            assert False, (
                f"Found {len(existing_jobs)} existing job(s) before authenticated submission: {job_ids}. "
                "This indicates that the unauthenticated job submission test failed to properly block submission."
            )
        else:
            print(
                "Verified: No jobs exist from the previous unauthenticated submission attempt."
            )

        submission_id = client.submit_job(
            entrypoint="python mnist.py",
            runtime_env={
                "working_dir": "./tests/e2e/",
                "pip": "./tests/e2e/mnist_pip_requirements.txt",
                "env_vars": get_setup_env_variables(),
            },
            entrypoint_num_cpus=1,
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

    def assert_job_completion(self, status):
        if status == "SUCCEEDED":
            print(f"Job has completed: '{status}'")
            assert True
        else:
            print(f"Job has completed: '{status}'")
            assert False

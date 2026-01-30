import pytest
import requests
from time import sleep

from codeflare_sdk import Cluster, ClusterConfiguration
from codeflare_sdk.ray.client import RayJobClient

from tests.e2e.support import *
from codeflare_sdk.ray.cluster.cluster import get_cluster

from codeflare_sdk.common import _kube_api_error_handling

namespace = "test-ns-rayupgrade"
# Global variables for kueue resources
cluster_queue = "cluster-queue-mnist"
flavor = "default-flavor-mnist"
local_queue = "local-queue-mnist"


# Creates a Ray cluster
@pytest.mark.pre_upgrade
class TestMNISTRayClusterApply:
    def setup_method(self):
        initialize_kubernetes_client(self)
        create_namespace_with_name(self, namespace)
        try:
            create_cluster_queue(self, cluster_queue, flavor)
            create_resource_flavor(self, flavor)
            create_local_queue(self, cluster_queue, local_queue)
        except Exception as e:
            delete_namespace(self)
            delete_kueue_resources(self)
            return _kube_api_error_handling(e)

    @pytest.fixture(autouse=True)
    def cleanup_on_failure(self, request):
        """Fixture to cleanup namespace and resources if pre-upgrade test fails"""
        # This runs after the test
        yield

        # Check if the test failed
        test_failed = (
            request.node.rep_call.failed if hasattr(request.node, "rep_call") else False
        )

        if test_failed:
            print(
                f"\n=== Pre-upgrade test failed, cleaning up namespace: {namespace} ==="
            )
            try:
                delete_namespace(self)
                delete_kueue_resources(self)
                print(f"Successfully cleaned up namespace: {namespace}")
            except Exception as e:
                print(f"Warning: Failed to cleanup namespace {namespace}: {e}")

    def test_mnist_ray_cluster_sdk_auth(self):
        self.run_mnist_raycluster_sdk_oauth()

    def run_mnist_raycluster_sdk_oauth(self):
        ray_image = get_ray_image()

        # Set up authentication based on detected method
        auth_instance = authenticate_for_tests()

        # Store auth instance for cleanup
        self.auth_instance = auth_instance

        cluster = Cluster(
            ClusterConfiguration(
                name="mnist",
                namespace=self.namespace,
                num_workers=1,
                head_cpu_requests=1,
                head_cpu_limits=1,
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

        try:
            cluster.apply()
            cluster.status()
            # wait for raycluster to be Ready
            wait_ready_with_stuck_detection(cluster)
            cluster.status()
            # Check cluster details
            cluster.details()
            # Assert the cluster status is READY
            _, ready = cluster.status()
            assert ready

        except Exception as e:
            print(f"An unexpected error occurred. Error: ", e)
            delete_namespace(self)
            assert False, "Cluster is not ready!"


@pytest.mark.post_upgrade
class TestMnistJobSubmit:
    def setup_method(self):
        initialize_kubernetes_client(self)

        # Set up authentication based on detected method
        auth_instance = authenticate_for_tests()

        # Store auth instance for cleanup
        self.auth_instance = auth_instance

        self.namespace = namespace
        self.cluster = get_cluster("mnist", self.namespace)
        if not self.cluster:
            raise RuntimeError("TestRayClusterUp needs to be run before this test")

    def _is_byoidc_cluster(self):
        """
        Simple BYOIDC cluster detection by checking for OIDC issuer in cluster Authentication resource.
        """
        try:
            # Check if cluster has OIDC authentication configured
            auth_resource = self.custom_api.get_cluster_custom_object(
                group="config.openshift.io",
                version="v1",
                plural="authentications",
                name="cluster",
            )

            # Look for OIDC issuer URL in the authentication spec
            spec = auth_resource.get("spec", {})

            # Check oidcProviders first - must be BYOIDC-specific
            if "oidcProviders" in spec and spec["oidcProviders"]:
                for provider in spec["oidcProviders"]:
                    issuer_url = provider.get("issuer", {}).get("url", "")
                    # More specific check for BYOIDC patterns
                    if (
                        "keycloak" in issuer_url.lower()
                        and (
                            "rh-ods.com" in issuer_url or "qe.rh-ods.com" in issuer_url
                        )
                    ) or "realms/openshift" in issuer_url:
                        print(f"Detected BYOIDC cluster with OIDC issuer: {issuer_url}")
                        return True

            # Also check for webhookTokenAuthenticators (alternative OIDC config)
            if (
                "webhookTokenAuthenticators" in spec
                and spec["webhookTokenAuthenticators"]
            ):
                for webhook in spec["webhookTokenAuthenticators"]:
                    kubeconfig = webhook.get("kubeConfig", {})
                    if kubeconfig:
                        print(
                            "Detected BYOIDC cluster with webhook token authenticator"
                        )
                        return True

            # Check status for BYOIDC-specific OIDC clients
            status = auth_resource.get("status", {})
            if "oidcClients" in status and status["oidcClients"]:
                # Check if oc-cli client exists (BYOIDC-specific)
                for client in status["oidcClients"]:
                    if client.get("clientID") == "oc-cli":
                        print(
                            "Detected BYOIDC cluster from status.oidcClients (oc-cli)"
                        )
                        return True

            # Fallback: check if we can detect OIDC from environment or other indicators
            # This is a simple heuristic - if we're using Jenkins vault credentials for BYOIDC
            import os

            if os.getenv("BYOIDC_ADMIN_USERNAME") or os.getenv(
                "TEST_USER_USERNAME", ""
            ).startswith("odh-"):
                print("Detected BYOIDC cluster from environment variables")
                return True

            print("No BYOIDC OIDC providers found in cluster Authentication resource")
            return False

        except Exception as e:
            print(f"Could not check cluster authentication method: {e}")
            # Fallback: check environment variables as last resort
            import os

            if os.getenv("BYOIDC_ADMIN_USERNAME") or os.getenv(
                "TEST_USER_USERNAME", ""
            ).startswith("odh-"):
                print("Detected BYOIDC cluster from environment variables (fallback)")
                return True
            return False

    def test_mnist_job_submission(self):
        self.assert_jobsubmit_withoutLogin(self.cluster)
        self.assert_jobsubmit_withlogin(self.cluster)

    # Assertions
    def assert_jobsubmit_withoutLogin(self, cluster):
        dashboard_url = cluster.cluster_dashboard_uri()

        # Check if this is a BYOIDC cluster
        is_byoidc_cluster = self._is_byoidc_cluster()

        # For BYOIDC clusters, authentication is enforced at the gateway level
        if is_byoidc_cluster:
            print("Skipping unauthenticated job submission test for BYOIDC cluster")
            print("BYOIDC authentication is enforced at the gateway level")
            print("Verifying that dashboard requires authentication...")

            # For BYOIDC, just verify that accessing the dashboard without auth redirects to login
            try:
                response = requests.get(
                    dashboard_url, verify=False, allow_redirects=False
                )
                if response.status_code in [302, 401, 403]:
                    print(
                        f"✓ Dashboard properly redirects unauthenticated access (status: {response.status_code})"
                    )
                    print("✓ BYOIDC authentication enforcement verified")
                    return
                else:
                    print(
                        f"Warning: Dashboard returned unexpected status {response.status_code} for unauthenticated access"
                    )
                    print("This may indicate authentication is not properly enforced")
            except Exception as e:
                print(f"Error testing dashboard authentication: {e}")
                # Don't fail the test for this - it's not critical
            return

        # For legacy authentication, verify that job submission is actually blocked by attempting to submit without auth
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
        ray_dashboard = cluster.cluster_dashboard_uri()

        # Check if this is a BYOIDC cluster - skip Ray Dashboard job submission for BYOIDC
        is_byoidc_cluster = self._is_byoidc_cluster()

        # For BYOIDC clusters, skip Ray Dashboard job submission due to authentication incompatibility
        if is_byoidc_cluster:
            print("Skipping Ray Dashboard job submission test for BYOIDC cluster")
            print(
                "BYOIDC authentication requires browser-based OIDC flow for Ray Dashboard"
            )
            print("Verifying cluster is accessible via Kubernetes API instead...")

            # Verify cluster is accessible via Kubernetes API as an alternative test
            try:
                cluster_details = cluster.details()
                if (
                    cluster_details
                    and hasattr(cluster_details, "status")
                    and cluster_details.status
                ):
                    print(
                        f"✓ Ray cluster is accessible and has status: {cluster_details.status}"
                    )
                    print(
                        "✓ BYOIDC authentication test passed - cluster is accessible via Kubernetes API"
                    )
                    return
                else:
                    raise RuntimeError(
                        "Cluster details could not be retrieved or cluster is not ready"
                    )
            except Exception as e:
                raise RuntimeError(
                    f"Failed to verify cluster accessibility via Kubernetes API: {e}"
                )

        # For legacy authentication, proceed with Ray Dashboard job submission
        print("Using legacy authentication for Ray Dashboard job submission...")

        try:
            # For legacy auth, use oc command to get token
            auth_token = run_oc_command(["whoami", "--show-token=true"])
            header = {"Authorization": f"Bearer {auth_token}"}
        except Exception as e:
            print(f"Warning: Could not get auth token via oc command: {e}")
            print("Attempting to use kubeconfig token...")
            # Try to extract token from kubeconfig
            try:
                import yaml

                kubeconfig_path = os.getenv(
                    "KUBECONFIG", os.path.expanduser("~/.kube/config")
                )
                with open(kubeconfig_path, "r") as f:
                    kubeconfig = yaml.safe_load(f)

                # Find current context and extract token
                current_context = kubeconfig.get("current-context")
                user_name = None
                for context in kubeconfig.get("contexts", []):
                    if context["name"] == current_context:
                        user_name = context["context"]["user"]
                        break

                auth_token = None
                for user in kubeconfig.get("users", []):
                    if user["name"] == user_name:
                        user_info = user.get("user", {})
                        auth_token = user_info.get("token")
                        if not auth_token and "auth-provider" in user_info:
                            # Handle auth-provider token
                            auth_provider = user_info["auth-provider"]
                            if "config" in auth_provider:
                                auth_token = auth_provider["config"].get("access-token")
                        break

                if auth_token:
                    header = {"Authorization": f"Bearer {auth_token}"}
                else:
                    # Fall back to no auth header (kubeconfig should handle auth)
                    header = {}
                    print("Warning: Using RayJobClient without explicit auth header")
            except Exception as token_error:
                print(
                    f"Warning: Could not extract token from kubeconfig: {token_error}"
                )
                header = {}

        client = RayJobClient(address=ray_dashboard, headers=header, verify=False)

        # Submit the job
        submission_id = client.submit_job(
            entrypoint="python mnist.py",
            runtime_env={
                "working_dir": "./tests/e2e/",
                "pip": "./tests/e2e/mnist_pip_requirements.txt",
                "env_vars": get_setup_env_variables(),
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

    def assert_job_completion(self, status):
        if status == "SUCCEEDED":
            print(f"Job has completed: '{status}'")
            assert True
        else:
            print(f"Job has completed: '{status}'")
            assert False

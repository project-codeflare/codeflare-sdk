# Copyright 2024 IBM, Red Hat
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
Lifecycle and runtime operations for RayCluster.

This mixin groups operational methods (apply/down/status), TLS handling, and
job submission helpers, keeping the main class focused on configuration state.
"""

from time import sleep
from typing import TYPE_CHECKING, List, Optional, Tuple

import requests
from kubernetes import client
from kubernetes.dynamic import DynamicClient
from ray.job_submission import JobSubmissionClient

from ...common import _kube_api_error_handling
from ...common.kubernetes_cluster.auth import config_check, get_api_client
from ...common.utils import get_current_namespace
from ..cluster.status import CodeFlareClusterStatus, RayClusterStatus

if TYPE_CHECKING:
    from .raycluster import RayCluster


class RayClusterLifecycleMixin:
    """
    Mixin containing lifecycle, TLS, and job client helpers.

    This keeps runtime behavior in one place while the dataclass stays small.
    """

    # -------------------------------------------------------------------------
    # Runtime Properties
    # -------------------------------------------------------------------------

    def _get_current_status(self) -> RayClusterStatus:
        """
        Get the current status of the RayCluster from Kubernetes.

        This method queries the Kubernetes API to get the live cluster state.
        For standalone clusters, this requires name to be set.

        Returns:
            RayClusterStatus enum value representing the current cluster state.
        """
        if not self.name:
            return RayClusterStatus.UNKNOWN

        self._ensure_namespace()
        cluster_status = self._ray_cluster_status(self.name, self.namespace)
        return cluster_status if cluster_status else RayClusterStatus.UNKNOWN

    @property
    def dashboard(self) -> str:
        """
        Get the dashboard URL for the cluster.

        Returns:
            The dashboard URL, or an error message if not available.
        """
        if not self.name:
            return "Dashboard not available - cluster name not set"
        return self.cluster_dashboard_uri()

    # -------------------------------------------------------------------------
    # Helper Methods (from Cluster class for compatibility)
    # -------------------------------------------------------------------------

    def get_dynamic_client(self):  # pragma: no cover
        """
        Returns a DynamicClient instance for Kubernetes API interactions.

        This method is provided for compatibility with the old Cluster class.

        Returns:
            DynamicClient: A dynamic Kubernetes client instance.
        """
        return DynamicClient(get_api_client())

    def config_check(self):
        """
        Wrapper for config_check() function.

        This method is provided for compatibility with the old Cluster class.
        It ensures that the Kubernetes configuration is properly loaded.
        """
        return config_check()

    def create_resource(self):
        """
        Creates the RayCluster yaml based on the current configuration.

        This method is called during initialization in the old Cluster class.
        It ensures namespace is set and builds the resource yaml.

        Returns:
            The resource yaml (dict or filename if write_to_file is True).
        """
        if not self.name:
            raise ValueError("name is required to create resource")

        self._ensure_namespace()
        self._resource_yaml = self._build_standalone_ray_cluster()
        return self._resource_yaml

    # -------------------------------------------------------------------------
    # Standalone Cluster Lifecycle Methods
    # -------------------------------------------------------------------------

    def apply(self, force: bool = False, timeout: int = 300):
        """
        Apply the RayCluster to Kubernetes using server-side apply.

        This creates or updates the RayCluster in the Kubernetes cluster.
        For standalone cluster management, this is the primary method to
        deploy the cluster.

        After applying the cluster resources, this method waits for the CA secret
        to be created by KubeRay and generates TLS certificates for mTLS connections.

        Args:
            force: If True, force conflicts during server-side apply.
            timeout: Maximum time in seconds to wait for post-apply operations such as
                TLS certificate generation. Default is 300 seconds (5 minutes).

        Raises:
            ValueError: If name is not set for standalone cluster.
            RuntimeError: If RayCluster CRD is not available.
        """
        if not self.name:
            raise ValueError("name is required for standalone cluster apply()")

        # Ensure namespace is set.
        self._ensure_namespace()

        # Build the resource yaml.
        self._resource_yaml = self._build_standalone_ray_cluster()

        # Check if RayCluster CRD exists.
        self._throw_for_no_raycluster()

        try:
            config_check()
            dynamic_client = DynamicClient(get_api_client())
            crds = dynamic_client.resources
            api_version = "ray.io/v1"
            api_instance = crds.get(api_version=api_version, kind="RayCluster")

            self._apply_ray_cluster(
                self._resource_yaml, self.namespace, api_instance, force=force
            )
            print(
                f"Ray Cluster: '{self.name}' has successfully been applied. "
                "For optimal resource management, you should delete this Ray Cluster when no longer in use."
            )
        except AttributeError as e:
            raise RuntimeError(f"Failed to initialize DynamicClient: {e}")
        except Exception as e:  # pragma: no cover
            if hasattr(e, "status") and e.status == 422:
                print(
                    "WARNING: RayCluster creation rejected due to invalid Kueue configuration. "
                    "Please contact your administrator."
                )
            else:
                print(
                    "WARNING: Failed to create RayCluster due to unexpected error. "
                    "Please contact your administrator."
                )
            return _kube_api_error_handling(e)

        # Generate TLS certificates for mTLS connections.
        tls_success = self._generate_tls_certs_with_wait(timeout=timeout)

        # Final completion message.
        if tls_success:
            print(
                f"Cluster '{self.name}' is ready. Use cluster.details() to see the status."
            )
        else:
            print(
                f"Cluster '{self.name}' resources applied but TLS setup incomplete. "
                "Run cluster.wait_ready() to complete setup."
            )

    def down(self):
        """
        Delete the RayCluster from Kubernetes.

        This scales down and deletes all resources associated with the cluster.
        Also removes the TLS certificates generated for this cluster to prevent
        accumulation of sensitive key material.

        Raises:
            ValueError: If name is not set.
            RuntimeError: If RayCluster CRD is not available.
        """
        if not self.name:
            raise ValueError("name is required for standalone cluster down()")

        self._ensure_namespace()
        self._throw_for_no_raycluster()

        try:
            config_check()
            api_instance = client.CustomObjectsApi(get_api_client())
            self._delete_resources(self.name, self.namespace, api_instance)
            print(f"Ray Cluster: '{self.name}' has successfully been deleted")

            # Automatically clean up TLS certificates (silently).
            from ...common.utils import generate_cert

            generate_cert.cleanup_tls_cert(self.name, self.namespace)

        except Exception as e:  # pragma: no cover
            return _kube_api_error_handling(e)

    def status(self, print_to_console: bool = True) -> Tuple[str, bool]:
        """
        Get the current status of the RayCluster.

        Args:
            print_to_console: Whether to print status to console.

        Returns:
            Tuple of (status, ready) where status is a CodeFlareClusterStatus
            and ready is True if the cluster is ready for use.
        """
        if not self.name:
            raise ValueError("name is required to check cluster status")

        self._ensure_namespace()
        ready = False
        status = CodeFlareClusterStatus.UNKNOWN

        # Query the cluster status from Kubernetes.
        # _ray_cluster_status returns RayClusterStatus enum or None if not found.
        ray_status = self._ray_cluster_status(self.name, self.namespace)

        if ray_status is not None:
            # Cluster exists - map RayClusterStatus to CodeFlareClusterStatus.
            if ray_status == RayClusterStatus.SUSPENDED:
                ready = False
                status = CodeFlareClusterStatus.SUSPENDED
            elif ray_status == RayClusterStatus.UNKNOWN:
                ready = False
                status = CodeFlareClusterStatus.STARTING
            elif ray_status == RayClusterStatus.READY:
                ready = True
                status = CodeFlareClusterStatus.READY
            elif ray_status in [RayClusterStatus.UNHEALTHY, RayClusterStatus.FAILED]:
                ready = False
                status = CodeFlareClusterStatus.FAILED

            # Print status using self directly.
            if print_to_console:
                from ..cluster import pretty_print

                pretty_print.print_cluster_status(self)
        elif print_to_console:
            # No cluster found in Kubernetes.
            from ..cluster import pretty_print

            pretty_print.print_no_resources_found()

        return status, ready

    def wait_ready(self, timeout: Optional[int] = None, dashboard_check: bool = True):
        """
        Wait for the cluster to be ready.

        This method checks the status of the cluster every five seconds until it is
        ready or the timeout is reached. If dashboard_check is enabled, it will also
        check for the readiness of the dashboard.

        Args:
            timeout: Maximum time to wait in seconds. If None, waits indefinitely.
            dashboard_check: Whether to also wait for the dashboard to be ready.

        Raises:
            ValueError: If name is not set.
            TimeoutError: If timeout is reached before the cluster is ready.
        """
        if not self.name:
            raise ValueError("name is required for wait_ready()")

        print("Waiting for requested resources to be set up...")
        time_elapsed = 0

        while True:
            if timeout and time_elapsed >= timeout:
                raise TimeoutError(
                    f"wait() timed out after waiting {timeout}s for cluster to be ready"
                )
            status, ready = self.status(print_to_console=False)
            if status == CodeFlareClusterStatus.UNKNOWN:
                print(
                    "WARNING: Current cluster status is unknown, have you run cluster.apply() yet? "
                    "Run cluster.details() to check if it's ready."
                )
            if ready:
                break
            sleep(5)
            time_elapsed += 5

        print("Requested cluster is up and running!")

        # Ensure TLS certificates exist (required for mTLS).
        # If apply() already generated them, this will be a no-op.
        try:
            from ...common.utils import generate_cert

            generate_cert.generate_tls_cert(self.name, self.namespace)
            generate_cert.export_env(self.name, self.namespace)
        except Exception as e:
            # Don't fail cluster setup if certificate generation fails.
            print(f"Warning: Could not generate TLS certificates: {e}")
            print(
                "You can manually generate certificates using generate_cert.generate_tls_cert()"
            )

        dashboard_wait_logged = False
        while dashboard_check:
            if timeout and time_elapsed >= timeout:
                raise TimeoutError(
                    f"wait() timed out after waiting {timeout}s for dashboard to be ready"
                )
            if self.is_dashboard_ready():
                print("Dashboard is ready!")
                break
            if not dashboard_wait_logged:
                dashboard_uri = self.cluster_dashboard_uri()
                if not dashboard_uri.startswith(("http://", "https://")):
                    print("Waiting for dashboard route/HTTPRoute to be created...")
                else:
                    print(
                        f"Waiting for dashboard to become accessible: {dashboard_uri}"
                    )
                dashboard_wait_logged = True
            sleep(5)
            time_elapsed += 5

    def is_dashboard_ready(self) -> bool:
        """
        Check if the cluster's dashboard is ready and accessible.

        Returns:
            True if the dashboard is ready, False otherwise.
        """
        dashboard_uri = self.cluster_dashboard_uri()
        if dashboard_uri is None:
            return False

        # Check if dashboard_uri is an error message rather than a valid URL.
        if not dashboard_uri.startswith(("http://", "https://")):
            return False

        try:
            # Don't follow redirects - we want to see the redirect response.
            # A 302 redirect from OAuth proxy indicates the dashboard is ready.
            response = requests.get(
                dashboard_uri,
                headers=self._client_headers,
                timeout=5,
                verify=self._client_verify_tls,
                allow_redirects=False,
            )
        except requests.exceptions.SSLError:  # pragma no cover
            # SSL exception occurs when oauth ingress has been created but cluster is not up.
            return False
        except Exception:  # pragma no cover
            # Any other exception (connection errors, timeouts, etc.).
            return False

        # Dashboard is ready if:
        # - 200: Dashboard is accessible (no auth required or already authenticated)
        # - 302: OAuth redirect - dashboard and OAuth proxy are ready, just needs authentication
        # - 401/403: OAuth is working and blocking unauthenticated requests - dashboard is ready
        return response.status_code in (200, 302, 401, 403)

    def cluster_uri(self) -> str:
        """
        Get the Ray client URI for the cluster.

        Note: If connecting to a cluster with mTLS enabled, ensure you have called
        cluster.wait_ready() first to automatically generate TLS certificates.

        Returns:
            The Ray client URI (ray://<cluster-name>-head-svc.<namespace>.svc:10001)
        """
        if not self.name:
            raise ValueError("name is required to get cluster URI")
        self._ensure_namespace()

        # Check if TLS certs exist and print warning if not.
        self._check_tls_certs_exist()

        return f"ray://{self.name}-head-svc.{self.namespace}.svc:10001"

    def cluster_dashboard_uri(self) -> str:
        """
        Get the dashboard URI for the cluster.

        Tries HTTPRoute first (RHOAI v3.0+), then falls back to OpenShift Routes or Ingresses.

        Returns:
            The dashboard URL, or an error message if not available.
        """
        if not self.name:
            raise ValueError("name is required to get dashboard URI")

        self._ensure_namespace()
        config_check()

        # Try HTTPRoute first (RHOAI v3.0+).
        httproute_url = self._get_dashboard_url_from_httproute(
            self.name, self.namespace
        )
        if httproute_url:
            return httproute_url

        # Fall back to OpenShift Routes (pre-v3.0) or Ingresses (Kind).
        if self._is_openshift_cluster():
            try:
                api_instance = client.CustomObjectsApi(get_api_client())
                routes = api_instance.list_namespaced_custom_object(
                    group="route.openshift.io",
                    version="v1",
                    namespace=self.namespace,
                    plural="routes",
                )
            except Exception as e:  # pragma: no cover
                return _kube_api_error_handling(e)

            for route in routes["items"]:
                if route["metadata"]["name"] == f"ray-dashboard-{self.name}" or route[
                    "metadata"
                ]["name"].startswith(f"{self.name}-ingress"):
                    protocol = "https" if route["spec"].get("tls") else "http"
                    return f"{protocol}://{route['spec']['host']}"

            return "Dashboard not available yet, have you run cluster.apply()?"
        try:
            api_instance = client.NetworkingV1Api(get_api_client())
            ingresses = api_instance.list_namespaced_ingress(self.namespace)
        except Exception as e:  # pragma: no cover
            return _kube_api_error_handling(e)

        for ingress in ingresses.items:
            annotations = ingress.metadata.annotations
            protocol = "http"
            if (
                ingress.metadata.name == f"ray-dashboard-{self.name}"
                or ingress.metadata.name.startswith(f"{self.name}-ingress")
            ):
                if annotations is None:
                    protocol = "http"
                elif "route.openshift.io/termination" in annotations:
                    protocol = "https"
                return f"{protocol}://{ingress.spec.rules[0].host}"

        return (
            "Dashboard not available yet, have you run cluster.apply()? "
            "Run cluster.details() to check if it's ready."
        )

    def get_dashboard_url(self) -> Optional[str]:
        """
        Get the dashboard URL if available.

        This method provides a cleaner programmatic API than cluster_dashboard_uri(),
        returning None instead of an error message string when the dashboard is
        not available.

        Returns:
            The dashboard URL string if available, or None if not available.

        Example:
            >>> url = cluster.get_dashboard_url()
            >>> if url:
            ...     print(f"Dashboard at: {url}")
            ... else:
            ...     print("Dashboard not ready yet")
        """
        url = self.cluster_dashboard_uri()
        if url and url.startswith(("http://", "https://")):
            return url
        return None

    def details(self, print_to_console: bool = True) -> "RayCluster":
        """
        Get details about the Ray Cluster.

        Returns `self` directly, allowing access to all cluster configuration
        and runtime properties.

        Args:
            print_to_console: Whether to print details to console.

        Returns:
            This RayCluster instance with all configuration and runtime info.
        """
        if not self.name:
            raise ValueError("name is required to get cluster details")

        if print_to_console:
            from ..cluster import pretty_print

            pretty_print.print_clusters([self])
        return self

    # -------------------------------------------------------------------------
    # Job Client Methods
    # -------------------------------------------------------------------------

    @property
    def _client_headers(self):
        """Get authorization headers for HTTP requests."""
        k8_client = get_api_client()
        return {
            "Authorization": k8_client.configuration.get_api_key_with_prefix(
                "authorization"
            )
        }

    @property
    def _client_verify_tls(self):
        """Get TLS verification setting."""
        return self._is_openshift_cluster() and self.verify_tls

    @property
    def job_client(self) -> JobSubmissionClient:
        """
        Get a Ray JobSubmissionClient for the cluster.

        Note: If connecting to a cluster with mTLS enabled, ensure you have called
        cluster.wait_ready() first to automatically generate TLS certificates.

        Returns:
            JobSubmissionClient connected to the cluster's dashboard.
        """
        # Check if TLS certs exist and print warning if not.
        self._check_tls_certs_exist()

        if self._job_submission_client:
            return self._job_submission_client

        if self._is_openshift_cluster():
            self._job_submission_client = JobSubmissionClient(
                self.cluster_dashboard_uri(),
                headers=self._client_headers,
                verify=self._client_verify_tls,
            )
        else:
            self._job_submission_client = JobSubmissionClient(
                self.cluster_dashboard_uri()
            )
        return self._job_submission_client

    def list_jobs(self) -> List:
        """
        List all jobs on the cluster.

        Returns:
            List of jobs from the Ray job client.
        """
        return self.job_client.list_jobs()

    def job_status(self, job_id: str) -> str:
        """
        Get the status of a specific job.

        Args:
            job_id: The job ID to check.

        Returns:
            The job status.
        """
        return self.job_client.get_job_status(job_id)

    def job_logs(self, job_id: str) -> str:
        """
        Get the logs for a specific job.

        Args:
            job_id: The job ID to get logs for.

        Returns:
            The job logs.
        """
        return self.job_client.get_job_logs(job_id)

    def local_client_url(self) -> str:
        """
        Constructs the URL for the local Ray client.

        This method is useful when you need to connect to the cluster
        from outside the Kubernetes cluster using an ingress domain.

        Note: If connecting to a cluster with mTLS enabled, ensure you have called
        cluster.wait_ready() first to automatically generate TLS certificates.

        Returns:
            str: The Ray client URL based on the ingress domain.
        """
        # Check if TLS certs exist and print warning if not.
        self._check_tls_certs_exist()

        ingress_domain = self._get_ingress_domain()
        return f"ray://{ingress_domain}"

    def _get_ingress_domain(self) -> Optional[str]:  # pragma: no cover
        """
        Get the ingress domain for the cluster's Ray client endpoint.

        This method looks for OpenShift Routes or Kubernetes Ingresses
        that expose the Ray client port (10001).

        Returns:
            str: The ingress domain hostname, or None if not found.
        """
        config_check()

        namespace = self.namespace if self.namespace else get_current_namespace()
        domain = None

        if self._is_openshift_cluster():
            try:
                api_instance = client.CustomObjectsApi(get_api_client())
                routes = api_instance.list_namespaced_custom_object(
                    group="route.openshift.io",
                    version="v1",
                    namespace=namespace,
                    plural="routes",
                )
            except Exception as e:  # pragma: no cover
                return _kube_api_error_handling(e)

            for route in routes["items"]:
                if (
                    route["spec"]["port"]["targetPort"] == "client"
                    or route["spec"]["port"]["targetPort"] == 10001
                ):
                    domain = route["spec"]["host"]
        else:
            try:
                api_client = client.NetworkingV1Api(get_api_client())
                ingresses = api_client.list_namespaced_ingress(namespace)
            except Exception as e:  # pragma: no cover
                return _kube_api_error_handling(e)

            for ingress in ingresses.items:
                if (
                    ingress.spec.rules[0].http.paths[0].backend.service.port.number
                    == 10001
                ):
                    domain = ingress.spec.rules[0].host

        return domain

    # -------------------------------------------------------------------------
    # TLS Certificate Methods (from Cluster class for mTLS support)
    # -------------------------------------------------------------------------

    def _ca_secret_exists(self) -> bool:
        """
        Checks if the CA secret for this cluster exists.

        The CA secret is created by KubeRay when the head pod starts.
        It is used for mTLS connections to the cluster.

        Returns:
            bool: True if the CA secret exists, False otherwise.
        """
        try:
            api_instance = client.CoreV1Api(get_api_client())
            label_selector = f"ray.openshift.ai/cluster-name={self.name}"
            secrets = api_instance.list_namespaced_secret(
                self.namespace, label_selector=label_selector
            )
            for secret in secrets.items:
                if f"{self.name}-ca-secret-" in secret.metadata.name:
                    return True
            return False
        except Exception:
            return False

    def _check_tls_certs_exist(self):
        """
        Check if TLS certificates exist and print helpful warning if not.

        This is called by connection methods (cluster_uri, local_client_url, job_client)
        to help users debug mTLS connection issues.
        """
        from ...common.utils.generate_cert import _get_tls_base_dir

        cert_dir = _get_tls_base_dir() / f"{self.name}-{self.namespace}"

        if not cert_dir.exists() or not (cert_dir / "tls.crt").exists():
            print("\n" + "=" * 70)
            print("WARNING: TLS Certificates Not Found!")
            print("=" * 70)
            print(f"Expected location: {cert_dir}")
            print()
            print("TLS certificates are required for mTLS connections to Ray clusters.")
            print(
                "Without certificates, your connection will likely fail with a timeout"
            )
            print("or TLS handshake error.")
            print()
            print("To fix this issue:")
            print("  1. Call cluster.wait_ready() after cluster.apply()")
            print(
                "     -> This automatically generates certificates when cluster is ready"
            )
            print()
            print("  2. Or manually generate certificates:")
            print("     from codeflare_sdk.common.utils import generate_cert")
            print(
                f"     generate_cert.generate_tls_cert('{self.name}', '{self.namespace}')"
            )
            print(f"     generate_cert.export_env('{self.name}', '{self.namespace}')")
            print("=" * 70 + "\n")

    def _generate_tls_certs_with_wait(self, timeout: int = 300) -> bool:
        """
        Waits for the CA secret to be created and generates TLS certificates.

        This is called by apply() to generate client TLS certificates after the
        cluster resources have been applied. The CA secret is created by KubeRay
        when the head pod starts, so we need to poll until it's available.

        Args:
            timeout: Maximum time in seconds to wait for the CA secret. Default is 300.

        Returns:
            bool: True if TLS certificates were generated successfully, False otherwise.
        """
        from ...common.utils import generate_cert

        print("Waiting for client TLS configuration to be available...")
        elapsed = 0
        poll_interval = 5

        # First, poll until the CA secret exists (without triggering error messages).
        while elapsed < timeout:
            if self._ca_secret_exists():
                break
            sleep(poll_interval)
            elapsed += poll_interval
        else:
            # Timeout reached.
            print(
                f"Warning: Timed out after {timeout}s waiting for TLS configuration. "
                "Client certificates were not generated. You can generate them later by calling "
                "cluster.wait_ready() or generate_cert.generate_tls_cert()."
            )
            return False

        # CA secret exists, now generate the certificates.
        try:
            generate_cert.generate_tls_cert(self.name, self.namespace)
            generate_cert.export_env(self.name, self.namespace)
            print(f"TLS certificates generated for '{self.name}'")
            return True
        except Exception as e:
            print(
                f"Warning: Failed to generate TLS certificates: {e}. "
                "You can generate them later by calling cluster.wait_ready() "
                "or generate_cert.generate_tls_cert()."
            )
            return False

    def refresh_certificates(self):
        """
        Refreshes TLS certificates by removing old ones and generating new ones.

        This is useful when:
        - The server CA secret has been rotated
        - Certificates have expired
        - You encounter TLS handshake failures
        - You need to regenerate certificates for any reason

        The method will:
        1. Remove existing client certificates
        2. Fetch the latest CA from Kubernetes
        3. Generate new client certificates
        4. Update environment variables for Ray

        Example:
            >>> # If you get TLS errors after CA rotation
            >>> cluster.refresh_certificates()
            >>> # Now you can reconnect
            >>> ray.init(address=cluster.cluster_uri())
        """
        from ...common.utils import generate_cert

        if not self.name:
            raise ValueError("name is required to refresh certificates")

        self._ensure_namespace()

        print(f"Refreshing TLS certificates for '{self.name}'...")

        # Use the refresh function which handles cleanup and regeneration.
        generate_cert.refresh_tls_cert(self.name, self.namespace)
        generate_cert.export_env(self.name, self.namespace)

        print(f"TLS certificates refreshed for '{self.name}'")

    # -------------------------------------------------------------------------
    # Namespace and UI Helpers
    # -------------------------------------------------------------------------

    def _ensure_namespace(self):
        """Ensure namespace is set, defaulting to current namespace."""
        if self.namespace is None:
            self.namespace = get_current_namespace()
            if self.namespace is None:
                print("Please specify with namespace=<your_current_namespace>")
            elif not isinstance(self.namespace, str):
                raise TypeError(
                    f"Namespace {self.namespace} is of type {type(self.namespace)}. "
                    "Check your Kubernetes Authentication."
                )

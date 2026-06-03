import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "ui"))

from pages.distributed_workloads_page import DistributedWorkloadsPage

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "e2e"))
from support import (
    delete_namespace,
    delete_kueue_resources,
    initialize_kubernetes_client,
)

from ui.conftest import (
    selenium_driver,
    dashboard_url,
    test_credentials,
    login_to_dashboard,
)

NAMESPACE = "test-ns-rayupgrade"
CLUSTER_NAME = "mnist"


@pytest.mark.pre_upgrade
@pytest.mark.ui
class TestDistributedWorkloadsUIPreUpgrade:
    """
    Verify Ray cluster visibility in Workload Metrics UI before upgrade.
    Mirrors ods-ci 0201__pre_upgrade.robot (Distributed Workloads section).
    """

    @pytest.fixture(autouse=True)
    def cleanup_on_failure(self, request):
        initialize_kubernetes_client(self)
        self.namespace = NAMESPACE
        yield
        test_failed = (
            request.node.rep_call.failed if hasattr(request.node, "rep_call") else False
        )
        if test_failed:
            print(
                f"\n=== Pre-upgrade UI test failed, cleaning up namespace: {NAMESPACE} ==="
            )
            try:
                delete_namespace(self)
                try:
                    delete_kueue_resources(self)
                except Exception:
                    pass
            except Exception as e:
                print(f"Warning: Failed to cleanup namespace {NAMESPACE}: {e}")

    def test_verify_cluster_in_distributed_workloads_ui(
        self, selenium_driver, login_to_dashboard
    ):
        driver = selenium_driver
        dw_page = DistributedWorkloadsPage(driver)

        print(
            f"\n=== Verifying cluster '{CLUSTER_NAME}' exists in namespace '{NAMESPACE}' ==="
        )
        from kubernetes import client
        from kubernetes.client.rest import ApiException

        api_instance = client.CustomObjectsApi()
        try:
            ray_cluster = api_instance.get_namespaced_custom_object(
                group="ray.io",
                version="v1",
                namespace=NAMESPACE,
                plural="rayclusters",
                name=CLUSTER_NAME,
            )
            cluster_state = ray_cluster.get("status", {}).get("state", "Unknown")
            print(f"Found RayCluster '{CLUSTER_NAME}' with state: {cluster_state}")
            if cluster_state not in ["ready", "Ready"]:
                raise AssertionError(
                    f"RayCluster '{CLUSTER_NAME}' is not ready (state={cluster_state})"
                )
        except ApiException as e:
            if e.status == 404:
                raise AssertionError(
                    f"RayCluster '{CLUSTER_NAME}' does not exist in '{NAMESPACE}'. "
                    "Run SDK pre_upgrade test first."
                )
            raise

        print("\n=== Navigating to Workload Metrics page ===")
        dw_page.navigate()

        print(f"\n=== Selecting project: {NAMESPACE} ===")
        dw_page.select_project(NAMESPACE)

        print("\n=== Verifying cluster is Running or Admitted ===")
        assert dw_page.verify_cluster_running(), (
            f"Cluster in {NAMESPACE} should be Running or Admitted before upgrade"
        )

        print("\n=== Checking Project Metrics tab ===")
        dw_page.click_project_metrics_tab()
        assert dw_page.verify_metrics_visible(), (
            "Distributed workload resource metrics should be visible"
        )

        print("\n=== Checking Workload Status tab ===")
        dw_page.click_workload_status_tab()
        assert dw_page.verify_cluster_in_workload_list(CLUSTER_NAME), (
            f"Cluster '{CLUSTER_NAME}' should appear in workload list with Running status"
        )

        print("\n=== Pre-upgrade UI verification completed successfully ===")


@pytest.mark.post_upgrade
@pytest.mark.ui
class TestDistributedWorkloadsUIPostUpgrade:
    def test_verify_cluster_persists_after_upgrade(
        self, selenium_driver, login_to_dashboard
    ):
        driver = selenium_driver
        dw_page = DistributedWorkloadsPage(driver)

        dw_page.navigate()
        dw_page.select_project(NAMESPACE)
        assert dw_page.verify_cluster_running()
        dw_page.click_project_metrics_tab()
        assert dw_page.verify_metrics_visible()
        dw_page.click_workload_status_tab()
        assert dw_page.verify_cluster_in_workload_list(CLUSTER_NAME)

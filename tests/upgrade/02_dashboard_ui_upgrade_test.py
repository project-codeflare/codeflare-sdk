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

import pytest
import sys
import os

# Add tests/ui to path to import page objects
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "ui"))

from pages.distributed_workloads_page import DistributedWorkloadsPage

# Import cleanup functions
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "e2e"))
from support import (
    delete_namespace,
    delete_kueue_resources,
    initialize_kubernetes_client,
)

# Fixtures are imported via conftest.py in this directory

# Test configuration - should match the cluster created in raycluster_sdk_upgrade_test.py
NAMESPACE = "test-ns-rayupgrade"
CLUSTER_NAME = "mnist"


@pytest.mark.pre_upgrade
@pytest.mark.ui
class TestDistributedWorkloadsUIPreUpgrade:
    """
    UI tests to verify Ray cluster appears in RHOAI Dashboard before upgrade.
    These tests validate that the cluster created by TestMNISTRayClusterApply
    is visible and properly displayed in the Workload Metrics UI (under Observe & monitor).
    """

    @pytest.fixture(autouse=True)
    def cleanup_on_failure(self, request):
        """Fixture to cleanup namespace and resources if pre-upgrade UI test fails"""
        # Initialize kubernetes client for cleanup
        initialize_kubernetes_client(self)
        self.namespace = NAMESPACE

        # This runs after the test
        yield

        # Check if the test failed
        test_failed = (
            request.node.rep_call.failed if hasattr(request.node, "rep_call") else False
        )

        if test_failed:
            print(
                f"\n=== Pre-upgrade UI test failed, cleaning up namespace: {NAMESPACE} ==="
            )
            try:
                delete_namespace(self)
                # Note: Kueue resources might have been already cleaned by TestMNISTRayClusterApply
                # but we try to clean them again just in case
                try:
                    delete_kueue_resources(self)
                except:
                    pass  # May have already been deleted
                print(f"Successfully cleaned up namespace: {NAMESPACE}")
            except Exception as e:
                print(f"Warning: Failed to cleanup namespace {NAMESPACE}: {e}")

    def test_verify_cluster_in_distributed_workloads_ui(
        self, selenium_driver, login_to_dashboard
    ):
        """
        Verify that the Ray cluster is visible in the Workload Metrics UI
        and shows correct status and metrics before upgrade.
        """
        driver = selenium_driver
        dw_page = DistributedWorkloadsPage(driver)

        # Navigate to Workload Metrics page (under Observe & monitor)
        print("\n=== Navigating to Workload Metrics page ===")
        dw_page.navigate()

        # Select the project
        print(f"\n=== Selecting project: {NAMESPACE} ===")
        dw_page.select_project(NAMESPACE)

        # Verify cluster is Running or Admitted
        # (needs to be clarified with dw team - in the past the status was "Running")
        print("\n=== Verifying cluster is in Running or Admitted state ===")
        assert (
            dw_page.verify_cluster_running()
        ), f"Cluster in {NAMESPACE} should be in Running or Admitted state before upgrade"

        # Click Project Metrics tab and verify metrics are visible
        print("\n=== Checking Project Metrics tab ===")
        dw_page.click_project_metrics_tab()
        assert (
            dw_page.verify_metrics_visible()
        ), "Resource metrics should be visible on Project Metrics tab"

        # Click Workload Status tab and verify cluster appears in the list
        print("\n=== Checking Workload Status tab ===")
        dw_page.click_workload_status_tab()
        assert dw_page.verify_cluster_in_workload_list(
            CLUSTER_NAME
        ), f"Cluster '{CLUSTER_NAME}' should appear in workload list with Running or Admitted status"

        print("\n=== Pre-upgrade UI verification completed successfully ===")


@pytest.mark.post_upgrade
@pytest.mark.ui
class TestDistributedWorkloadsUIPostUpgrade:
    """
    UI tests to verify Ray cluster persists in RHOAI Dashboard after upgrade.
    These tests validate that the cluster created before the upgrade is still
    visible and functional in the Workload Metrics UI (under Observe & monitor) after the upgrade completes.
    """

    def test_verify_cluster_persists_after_upgrade(
        self, selenium_driver, login_to_dashboard
    ):
        """
        Verify that the Ray cluster is still visible in the Workload Metrics UI
        and shows correct status and metrics after upgrade.

        This test performs the same verifications as the pre-upgrade test to ensure
        the cluster survived the upgrade process.
        """
        driver = selenium_driver
        dw_page = DistributedWorkloadsPage(driver)

        # Navigate to Workload Metrics page (under Observe & monitor)
        print("\n=== Navigating to Workload Metrics page ===")
        dw_page.navigate()

        # Select the project
        print(f"\n=== Selecting project: {NAMESPACE} ===")
        dw_page.select_project(NAMESPACE)

        # Verify cluster is still Running or Admitted after upgrade
        # (needs to be clarified with dw team - in the past the status was "Running")
        print(
            "\n=== Verifying cluster is still in Running or Admitted state after upgrade ==="
        )
        assert (
            dw_page.verify_cluster_running()
        ), f"Cluster in {NAMESPACE} should still be in Running or Admitted state after upgrade"

        # Click Project Metrics tab and verify metrics are still accessible
        print("\n=== Checking Project Metrics tab ===")
        dw_page.click_project_metrics_tab()
        assert (
            dw_page.verify_metrics_visible()
        ), "Resource metrics should still be visible on Project Metrics tab after upgrade"

        # Click Workload Status tab and verify cluster still appears in the list
        print("\n=== Checking Workload Status tab ===")
        dw_page.click_workload_status_tab()
        assert dw_page.verify_cluster_in_workload_list(
            CLUSTER_NAME
        ), f"Cluster '{CLUSTER_NAME}' should still appear in workload list with Running or Admitted status after upgrade"

        print("\n=== Post-upgrade UI verification completed successfully ===")
        print(
            "The cluster has successfully persisted through the upgrade and remains functional."
        )

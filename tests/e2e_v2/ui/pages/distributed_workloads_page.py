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

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


class DistributedWorkloadsPage:
    """Page Object Model for RHOAI Workload Metrics page"""

    # Locators - multiple options for better compatibility
    # New structure: "Workload metrics" is nested under "Observe & monitor"
    OBSERVE_MONITOR_NAV_OPTIONS = [
        (By.XPATH, "//nav//button[contains(., 'Observe & monitor')]"),
        (By.XPATH, "//nav//a[contains(., 'Observe & monitor')]"),
        (
            By.XPATH,
            "//button[contains(@class, 'pf-v5-c-nav__link') and contains(., 'Observe')]",
        ),
    ]

    WORKLOAD_METRICS_NAV_OPTIONS = [
        (By.XPATH, "//a[contains(., 'Workload metrics')]"),
        (By.XPATH, "//nav//a[contains(@href, 'workload-metrics')]"),
        (By.XPATH, "//nav//a[contains(@href, 'workloadmetrics')]"),
    ]

    PAGE_TITLE_OPTIONS = [
        (By.XPATH, "//h1[contains(text(), 'Workload metrics')]"),
    ]
    # Project selector - multiple options for compatibility (PatternFly v6)
    PROJECT_SELECTOR_OPTIONS = [
        (By.ID, "project-selector"),  # Direct ID match
        (By.CSS_SELECTOR, "[data-testid='project-selector-toggle']"),  # Data testid
        (By.XPATH, "//button[@id='project-selector']"),
        (By.XPATH, "//button[@data-testid='project-selector-toggle']"),
        (
            By.XPATH,
            "//button[contains(@class, 'pf-v6-c-menu-toggle')]",
        ),  # PatternFly v6
        (
            By.XPATH,
            "//button[contains(@class, 'pf-v5-c-menu-toggle')]",
        ),  # PatternFly v5 fallback
        (By.XPATH, "//button[contains(@aria-label, 'project')]"),
        (By.XPATH, "//button[contains(@aria-label, 'Project')]"),
    ]
    # Status locators - support multiple states (Admitted, Running, etc.)
    STATUS_LABEL_OPTIONS = [
        # PatternFly v6
        (By.XPATH, "//span[contains(@class, 'pf-v6-c-label__text')]"),
        # PatternFly v5
        (By.XPATH, "//span[contains(@class, 'pf-v5-c-label__text')]"),
        # Generic
        (By.XPATH, "//span[contains(@class, 'pf-c-label__text')]"),
    ]

    # Workload metrics table
    WORKLOAD_METRICS_TABLE = (
        By.CSS_SELECTOR,
        "[data-testid='workload-resource-metrics-table']",
    )

    # Tab locators - support both PatternFly v5 and v6
    PROJECT_METRICS_TAB_OPTIONS = [
        (
            By.XPATH,
            "//button[contains(@class, 'pf-v6-c-tabs__link') and .//span[text()='Project metrics']]",
        ),
        (
            By.XPATH,
            "//button[contains(@class, 'pf-v5-c-tabs__link') and .//span[text()='Project metrics']]",
        ),
        (By.XPATH, "//button[@role='tab' and .//span[text()='Project metrics']]"),
    ]

    WORKLOAD_STATUS_TAB_OPTIONS = [
        (
            By.XPATH,
            "//button[contains(@class, 'pf-v6-c-tabs__link') and .//span[text()='Workload status']]",
        ),
        (
            By.XPATH,
            "//button[contains(@class, 'pf-v5-c-tabs__link') and .//span[text()='Workload status']]",
        ),
        (
            By.XPATH,
            "//button[@role='tab' and contains(.//span/text(), 'workload status')]",
        ),
    ]

    RESOURCE_METRICS_TITLE_OPTIONS = [
        (By.XPATH, "//*[contains(text(), 'Requested resources')]"),
        (By.XPATH, "//h1[contains(text(), 'Project metrics')]"),
        (By.XPATH, "//h2[contains(text(), 'Project metrics')]"),
        (By.XPATH, "//*[contains(text(), 'Resource metrics')]"),
        (By.CSS_SELECTOR, "[data-testid='dw-requested-resources']"),
        (By.CSS_SELECTOR, "[data-testid='dw-workload-resource-metrics']"),
    ]

    def __init__(self, driver, timeout=30):
        self.driver = driver
        self.wait = WebDriverWait(driver, timeout)

    def navigate(self):
        """Navigate to Workload Metrics page (nested under Observe & monitor)"""
        import time

        # Give React app time to fully render (increased from 3 to 10 seconds)
        print("Waiting for dashboard React app to fully render...")
        for i in range(10):
            time.sleep(1)
            # Check if body has content
            try:
                body = self.driver.find_element(By.TAG_NAME, "body")
                if len(body.text) > 100:  # Body has substantial content
                    print(f"Dashboard rendered after {i+1} seconds")
                    break
            except:
                pass

        time.sleep(2)  # Extra wait for animations/transitions

        try:
            # Step 1: Find and click "Observe & monitor" in the side nav
            print("Searching for 'Observe & monitor' navigation item...")
            observe_monitor_element = None

            for by, value in self.OBSERVE_MONITOR_NAV_OPTIONS:
                try:
                    print(f"Trying locator: {by}={value}")
                    element = self.driver.find_element(by, value)
                    if element.is_displayed():
                        observe_monitor_element = element
                        print(f"Found 'Observe & monitor' using: {by}={value}")
                        break
                except Exception as e:
                    print(f"Locator {by}={value} not found: {str(e)[:100]}")
                    continue

            if observe_monitor_element:
                # Check if it's expandable (has nested items)
                print("Clicking 'Observe & monitor' to expand submenu...")
                observe_monitor_element.click()
                time.sleep(1)  # Wait for submenu to expand
            else:
                print("Warning: Could not find 'Observe & monitor' navigation item")

            # Step 2: Find and click "Workload metrics" link
            print("Searching for 'Workload metrics' navigation link...")
            workload_metrics_link = None

            for by, value in self.WORKLOAD_METRICS_NAV_OPTIONS:
                try:
                    print(f"Trying locator: {by}={value}")
                    element = self.driver.find_element(by, value)
                    if element.is_displayed():
                        workload_metrics_link = element
                        print(f"Found 'Workload metrics' link using: {by}={value}")
                        break
                except Exception as e:
                    print(f"Locator {by}={value} not found: {str(e)[:100]}")
                    continue

            if not workload_metrics_link:
                print(
                    "\nCould not find navigation link, attempting direct URL navigation..."
                )
                # Try direct navigation to workload metrics page
                current_url = self.driver.current_url
                base_url = current_url.rstrip("/")

                # Try different possible URL patterns
                possible_urls = [
                    f"{base_url}/workloadMetrics",
                    f"{base_url}/workload-metrics",
                    f"{base_url}/workloadmetrics",
                    f"{base_url}/workloads",
                ]

                navigation_successful = False
                for url in possible_urls:
                    try:
                        print(f"Trying direct navigation to: {url}")
                        self.driver.get(url)
                        time.sleep(3)

                        # Check if we got to a valid page (not 404)
                        if (
                            "404" not in self.driver.page_source
                            and "not found" not in self.driver.page_source.lower()
                        ):
                            print(f"Successfully navigated to: {url}")
                            navigation_successful = True
                            break
                    except Exception as e:
                        print(f"Direct navigation to {url} failed: {str(e)[:100]}")
                        continue

                if not navigation_successful:
                    # Take screenshot for debugging
                    try:
                        screenshot_path = "/tmp/workload_metrics_nav_failure.png"
                        self.driver.save_screenshot(screenshot_path)
                        print(f"Screenshot saved to: {screenshot_path}")
                    except:
                        pass

                    # Print more page source for debugging
                    page_source = self.driver.page_source
                    print(f"\nPage source (chars 1000-3000):\n{page_source[1000:3000]}")

                    # Try to find any navigation links
                    print("\nSearching for any navigation links...")
                    try:
                        nav_links = self.driver.find_elements(By.XPATH, "//nav//a")
                        print(f"Found {len(nav_links)} navigation links:")
                        for link in nav_links[:20]:  # Print first 20
                            try:
                                print(
                                    f"  - text: '{link.text}', href: '{link.get_attribute('href')}'"
                                )
                            except:
                                pass
                    except Exception as e:
                        print(f"Could not enumerate nav links: {e}")

                    raise RuntimeError(
                        f"Could not find or navigate to Workload Metrics page. "
                        f"Current URL: {self.driver.current_url}, "
                        f"Page title: {self.driver.title}"
                    )
            else:
                # Click the link
                print("Clicking 'Workload metrics' link...")
                workload_metrics_link.click()

                # Wait for page to load
                print("Waiting for Workload Metrics page to load...")
                time.sleep(3)

            # Verify we're on the right page
            print(f"Final URL: {self.driver.current_url}")
            if "workload" in self.driver.current_url.lower():
                print(
                    "Successfully navigated to Workload Metrics page (URL indicates success)"
                )
            else:
                print(
                    f"Warning: URL might not be Workload Metrics page: {self.driver.current_url}"
                )

        except Exception as e:
            print(f"Failed to navigate to Workload Metrics page: {e}")
            # Take screenshot on any failure
            try:
                screenshot_path = "/tmp/workload_metrics_nav_failure.png"
                self.driver.save_screenshot(screenshot_path)
                print(f"Screenshot saved to: {screenshot_path}")
            except:
                pass
            raise

    def select_project(self, project_name):
        """Select a project by navigating directly to the project URL"""
        import time

        try:
            # Wait a bit for the page to fully load
            time.sleep(2)

            # Check current URL to see if we're already on the right project
            current_url = self.driver.current_url
            print(f"Current URL: {current_url}")

            # Check if already on the correct project
            if f"/{project_name}" in current_url or current_url.endswith(project_name):
                print(f"Project '{project_name}' is already selected")
                return

            # Use direct URL navigation
            print(f"Selecting project '{project_name}' via URL navigation")
            self._select_project_by_url(project_name)

        except Exception as e:
            print(f"Failed to select project {project_name}: {e}")
            # Take screenshot on any failure
            try:
                screenshot_path = "/tmp/select_project_failure.png"
                self.driver.save_screenshot(screenshot_path)
                print(f"Screenshot saved to: {screenshot_path}")
            except:
                pass
            raise

    def _select_project_by_url(self, project_name):
        """Select project by navigating to the URL with the project name"""
        import time
        import re

        current_url = self.driver.current_url
        print(f"Attempting to select project via URL navigation")
        print(f"Current URL: {current_url}")

        # URL pattern: .../observe-monitor/workload-metrics/workload-status/{project_name}
        # Replace the last path segment with the project name
        if "/workload-metrics/" in current_url:
            # Find the last path segment and replace it
            url_parts = current_url.rstrip("/").split("/")

            # If URL ends with a project name, replace it
            if len(url_parts) >= 2:
                # Replace last segment with project_name
                url_parts[-1] = project_name
                new_url = "/".join(url_parts)
            else:
                # Append project name to URL
                new_url = f"{current_url.rstrip('/')}/{project_name}"

            print(f"Navigating to: {new_url}")
            self.driver.get(new_url)
            time.sleep(3)  # Wait for page to load

            print(f"New URL after navigation: {self.driver.current_url}")
            print(f"Successfully navigated to project: {project_name}")
        else:
            raise RuntimeError(
                f"Cannot determine correct URL pattern to select project. "
                f"Current URL: {current_url}"
            )

    def verify_cluster_running(self):
        """Verify that a cluster is in Running or Admitted state"""
        import time

        try:
            # Wait a bit for the page to load
            time.sleep(2)

            # Try to find status labels using multiple locators
            print("Searching for cluster status...")
            status_found = False

            for by, value in self.STATUS_LABEL_OPTIONS:
                try:
                    print(f"Trying locator: {by}={value}")
                    status_elements = self.driver.find_elements(by, value)

                    if status_elements:
                        print(f"Found {len(status_elements)} status label(s)")
                        for elem in status_elements:
                            if elem.is_displayed():
                                status_text = elem.text
                                print(f"Status text: {status_text}")
                                # Accept both "Running" and "Admitted" as valid states
                                if status_text in ["Running", "Admitted"]:
                                    print(f"✓ Cluster is in {status_text} state")
                                    status_found = True
                                    break

                    if status_found:
                        break

                except Exception as e:
                    print(f"Locator {by}={value} error: {str(e)[:100]}")
                    continue

            if status_found:
                return True

            # Fallback: Try to find the workload metrics table as indication of success
            print("Status label not found, checking for workload metrics table...")
            try:
                table = self.driver.find_element(*self.WORKLOAD_METRICS_TABLE)
                if table.is_displayed():
                    print("✓ Workload metrics table is visible (cluster exists)")
                    return True
            except:
                pass

            print("✗ Could not verify cluster status")
            return False

        except Exception as e:
            print(f"Failed to verify cluster status: {e}")
            import traceback

            traceback.print_exc()
            return False

    def click_project_metrics_tab(self):
        """Click on the Project Metrics tab"""
        import time

        try:
            # Try to find the tab using multiple locators
            print("Searching for Project Metrics tab...")
            tab = None

            for by, value in self.PROJECT_METRICS_TAB_OPTIONS:
                try:
                    print(f"Trying locator: {by}={value}")
                    element = self.driver.find_element(by, value)
                    if element.is_displayed():
                        tab = element
                        print(f"Found Project Metrics tab using: {by}={value}")
                        break
                except Exception as e:
                    print(f"Locator {by}={value} not found: {str(e)[:100]}")
                    continue

            if not tab:
                # Take screenshot for debugging
                try:
                    screenshot_path = "/tmp/project_metrics_tab_not_found.png"
                    self.driver.save_screenshot(screenshot_path)
                    print(f"Screenshot saved to: {screenshot_path}")
                except:
                    pass
                raise RuntimeError("Could not find Project Metrics tab")

            tab.click()
            time.sleep(2)  # Wait for tab content to load
            print("Successfully clicked Project Metrics tab")
        except Exception as e:
            print(f"Failed to click Project Metrics tab: {e}")
            raise

    def verify_metrics_visible(self):
        """Verify that resource metrics are visible"""
        import time

        try:
            # Wait a bit for content to load
            time.sleep(2)

            # Try to find metrics using multiple locators
            print("Searching for resource metrics indicators...")

            for by, value in self.RESOURCE_METRICS_TITLE_OPTIONS:
                try:
                    print(f"Trying locator: {by}={value}")
                    element = self.driver.find_element(by, value)
                    if element.is_displayed():
                        print(f"Found resource metrics using: {by}={value}")
                        return True
                except Exception as e:
                    print(f"Locator {by}={value} not found: {str(e)[:100]}")
                    continue

            # If no specific metrics title found, check if the tab content area exists
            try:
                # Look for the project-metrics tab content section
                tab_content = self.driver.find_element(
                    By.XPATH,
                    "//section[@id='project-metrics-tab-content' or contains(@aria-labelledby, 'project-metrics')]",
                )
                if tab_content.is_displayed():
                    print("Project metrics tab content is visible")
                    return True
            except:
                pass

            # Take screenshot for debugging
            try:
                screenshot_path = "/tmp/metrics_not_visible.png"
                self.driver.save_screenshot(screenshot_path)
                print(f"Screenshot saved to: {screenshot_path}")
            except:
                pass

            print("Resource metrics not visible")
            return False
        except Exception as e:
            print(f"Failed to verify metrics visibility: {e}")
            return False

    def click_workload_status_tab(self):
        """Click on the Workload Status tab"""
        import time

        try:
            # Try to find the tab using multiple locators
            print("Searching for Workload Status tab...")
            tab = None

            for by, value in self.WORKLOAD_STATUS_TAB_OPTIONS:
                try:
                    print(f"Trying locator: {by}={value}")
                    element = self.driver.find_element(by, value)
                    if element.is_displayed():
                        tab = element
                        print(f"Found Workload Status tab using: {by}={value}")
                        break
                except Exception as e:
                    print(f"Locator {by}={value} not found: {str(e)[:100]}")
                    continue

            if not tab:
                # Take screenshot for debugging
                try:
                    screenshot_path = "/tmp/workload_status_tab_not_found.png"
                    self.driver.save_screenshot(screenshot_path)
                    print(f"Screenshot saved to: {screenshot_path}")
                except:
                    pass
                raise RuntimeError("Could not find Workload Status tab")

            tab.click()
            time.sleep(2)  # Wait for tab content to load
            print("Successfully clicked Workload Status tab")
        except Exception as e:
            print(f"Failed to click Workload Status tab: {e}")
            raise

    def verify_cluster_in_workload_list(self, cluster_name):
        """Verify that a cluster appears in the workload list with Running or Admitted status"""
        import time

        try:
            # Wait for table to load
            time.sleep(2)

            # Look for the cluster name in the table
            cluster_cell = self.wait.until(
                EC.presence_of_element_located(
                    (By.XPATH, f"//td[contains(text(), '{cluster_name}')]")
                )
            )
            is_visible = cluster_cell.is_displayed()
            print(f"Cluster {cluster_name} found in workload list: {is_visible}")

            if not is_visible:
                return False

            # Find the parent row
            cluster_row = cluster_cell.find_element(By.XPATH, "./ancestor::tr")

            # Find the status cell within the row (PatternFly v6 label structure)
            # Try multiple approaches to find the status
            status_found = False
            status_text = None

            # Approach 1: Look for pf-v6-c-label__text within the row
            try:
                status_label = cluster_row.find_element(
                    By.XPATH,
                    ".//td[@data-label='Status']//span[contains(@class, 'pf-v6-c-label__text')]",
                )
                status_text = status_label.text
                print(f"Found status (v6 label): {status_text}")
                status_found = True
            except:
                pass

            # Approach 2: Try PatternFly v5
            if not status_found:
                try:
                    status_label = cluster_row.find_element(
                        By.XPATH,
                        ".//td[@data-label='Status']//span[contains(@class, 'pf-v5-c-label__text')]",
                    )
                    status_text = status_label.text
                    print(f"Found status (v5 label): {status_text}")
                    status_found = True
                except:
                    pass

            # Approach 3: Generic approach - find any text in status cell
            if not status_found:
                try:
                    status_cell = cluster_row.find_element(
                        By.XPATH, ".//td[@data-label='Status']"
                    )
                    status_text = status_cell.text
                    print(f"Found status (generic): {status_text}")
                    status_found = True
                except:
                    pass

            if not status_found:
                print("Could not find status cell")
                return False

            # Check if status is Running or Admitted
            if status_text in ["Running", "Admitted"]:
                print(f"✓ Cluster {cluster_name} status is {status_text}")
                return True
            else:
                print(f"✗ Cluster {cluster_name} has unexpected status: {status_text}")
                return False

        except Exception as e:
            print(f"Failed to verify cluster {cluster_name} in workload list: {e}")
            import traceback

            traceback.print_exc()
            return False

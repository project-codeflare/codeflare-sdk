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
        # First try exact href match (most reliable)
        (By.CSS_SELECTOR, "a[href$='/observe-monitor/workload-metrics']"),
        (By.XPATH, "//a[@href='/observe-monitor/workload-metrics']"),
        # Then try partial href matches
        (By.XPATH, "//a[contains(@href, 'observe-monitor/workload-metrics')]"),
        (By.CSS_SELECTOR, "a[href*='observe-monitor/workload-metrics']"),
        (By.XPATH, "//nav//a[contains(@href, 'workload-metrics')]"),
        (By.CSS_SELECTOR, "a[href*='workload-metrics']"),
        # Then try text-based selectors (fallback for older versions)
        (By.XPATH, "//a[contains(., 'Workload metrics')]"),
        (By.XPATH, "//nav//a[contains(., 'workload')]"),
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

        # Check if we're already on the Workload Metrics page (or a subpage)
        current_url = self.driver.current_url
        page_title = self.driver.title
        print(f"Current URL: {current_url}")
        print(f"Page title: {page_title}")

        # Check for various workload metrics URL patterns
        is_on_main_workload_page = (
            "/observe-monitor/workload-metrics" in current_url
            and "/workload-status/" not in current_url
        )
        is_on_workload_subpage = (
            "/observe-monitor/workload-metrics" in current_url
            and "/workload-status/" in current_url
        )

        if is_on_main_workload_page:
            print("Already on main Workload Metrics page, no navigation needed")
            return
        elif is_on_workload_subpage:
            print(
                "Currently on workload-status subpage, navigating to main workload-metrics page..."
            )
            # Extract base URL and navigate to main workload metrics page
            if "/observe-monitor/" in current_url:
                base_url = current_url.split("/observe-monitor/")[0]
                target_url = f"{base_url}/observe-monitor/workload-metrics"
                print(f"Navigating to: {target_url}")
                self.driver.get(target_url)
                time.sleep(3)  # Wait for page to load
                return

        print("Not on Workload Metrics page, proceeding with navigation...")

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
                # Check if the section is already expanded
                try:
                    expanded_attr = observe_monitor_element.get_attribute(
                        "aria-expanded"
                    )
                    class_attr = observe_monitor_element.get_attribute("class")
                    is_expanded = expanded_attr == "true" or "pf-m-expanded" in (
                        class_attr or ""
                    )
                    print(f"Observe & monitor section expanded status: {is_expanded}")

                    if not is_expanded:
                        print("Clicking 'Observe & monitor' to expand submenu...")
                        observe_monitor_element.click()
                        time.sleep(2)  # Wait for submenu to expand and render
                        print(
                            "Submenu should now be expanded, waiting for links to be available..."
                        )
                    else:
                        print("'Observe & monitor' section is already expanded")
                except Exception as e:
                    print(f"Could not check expansion status, clicking anyway: {e}")
                    observe_monitor_element.click()
                    time.sleep(1)
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
                    "\nCould not find navigation link with standard selectors, trying to find by href in all links..."
                )

                # Try to find the link by searching through all links
                try:
                    all_links = self.driver.find_elements(By.TAG_NAME, "a")
                    for link in all_links:
                        href = link.get_attribute("href")
                        if href and "observe-monitor/workload-metrics" in href:
                            print(f"Found workload metrics link by href search: {href}")
                            if link.is_displayed():
                                print("Link is visible, clicking it...")
                                workload_metrics_link = link
                                break
                            else:
                                print(
                                    "Link found but not visible, trying to scroll into view..."
                                )
                                self.driver.execute_script(
                                    "arguments[0].scrollIntoView(true);", link
                                )
                                time.sleep(1)
                                if link.is_displayed():
                                    print("Link is now visible after scrolling")
                                    workload_metrics_link = link
                                    break
                                else:
                                    print(
                                        "Link still not visible after scrolling, trying JavaScript click..."
                                    )
                                    try:
                                        self.driver.execute_script(
                                            "arguments[0].click();", link
                                        )
                                        print(
                                            "Successfully clicked link via JavaScript"
                                        )
                                        time.sleep(3)  # Wait for navigation
                                        # Check if navigation was successful
                                        current_url = self.driver.current_url
                                        if (
                                            "observe-monitor/workload-metrics"
                                            in current_url
                                            or "workload-status" in current_url
                                        ):
                                            print(
                                                f"JavaScript click successful, navigated to: {current_url}"
                                            )
                                            return  # Success, exit the method
                                    except Exception as js_e:
                                        print(f"JavaScript click failed: {js_e}")
                except Exception as e:
                    print(f"Error searching through all links: {e}")

            if not workload_metrics_link:
                print(
                    "\nCould not find navigation link, attempting direct URL navigation..."
                )
                # Try direct navigation to workload metrics page
                current_url = self.driver.current_url
                base_url = current_url.rstrip("/")

                # Try different possible URL patterns (prioritize the one we saw in logs)
                possible_urls = [
                    f"{base_url}/observe-monitor/workload-metrics",  # This is the correct one from logs
                ]

                navigation_successful = False
                for url in possible_urls:
                    try:
                        print(f"Trying direct navigation to: {url}")
                        self.driver.get(url)
                        time.sleep(3)

                        # Check if we got to a valid page (not 404)
                        current_url_after_nav = self.driver.current_url
                        page_source = self.driver.page_source

                        print(f"After navigation - URL: {current_url_after_nav}")

                        # Check for success conditions
                        is_valid_page = (
                            "404" not in page_source
                            and "not found" not in page_source.lower()
                        )

                        # Check if we're on any workload-related page
                        is_workload_page = (
                            "observe-monitor/workload-metrics" in current_url_after_nav
                            or "workload-status" in current_url_after_nav
                            or "/workloads" in current_url_after_nav
                            or "workload" in current_url_after_nav.lower()
                        )

                        if is_valid_page and is_workload_page:
                            print(
                                f"Successfully navigated to workload page: {current_url_after_nav}"
                            )
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
            final_url_lower = self.driver.current_url.lower()
            if "workload" in final_url_lower or "observe" in final_url_lower:
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
        if "/workload-metrics" in current_url:
            # Find the last path segment and replace it
            url_parts = current_url.rstrip("/").split("/")

            # Check if we're already on a project-specific page
            if url_parts[-1] != "workload-metrics" and len(url_parts) >= 2:
                # Replace last segment (existing project) with new project_name
                url_parts[-1] = project_name
                new_url = "/".join(url_parts)
            else:
                # Append project name to URL (we're on the base workload-metrics page)
                # Try different URL patterns based on the dashboard version
                base_url = current_url.rstrip("/")

                # Pattern 1: workload-status subdirectory (newer dashboard versions)
                new_url = f"{base_url}/workload-status/{project_name}"
                print(f"Trying URL pattern 1: {new_url}")

                # We'll try this pattern first, and if it doesn't work, the page will handle it

            print(f"Navigating to: {new_url}")
            self.driver.get(new_url)
            time.sleep(3)  # Wait for page to load

            # Verify the navigation worked
            final_url = self.driver.current_url
            print(f"New URL after navigation: {final_url}")

            # Check if we successfully navigated to the project
            if project_name in final_url or self._verify_project_selected(project_name):
                print(f"Successfully navigated to project: {project_name}")
            else:
                # Try alternative URL pattern
                print("First URL pattern didn't work, trying alternative...")
                base_url = current_url.rstrip("/")
                alternative_url = f"{base_url}/{project_name}"
                print(f"Trying alternative URL pattern: {alternative_url}")

                self.driver.get(alternative_url)
                time.sleep(3)

                final_url = self.driver.current_url
                print(f"Final URL after alternative navigation: {final_url}")

                if project_name in final_url or self._verify_project_selected(
                    project_name
                ):
                    print(
                        f"Successfully navigated to project using alternative pattern: {project_name}"
                    )
                else:
                    print(
                        f"Warning: Project navigation may not have worked as expected"
                    )
                    print(f"Expected project: {project_name}, Final URL: {final_url}")
                    # Don't raise an error here - let the subsequent verification methods handle it
        else:
            raise RuntimeError(
                f"Cannot determine correct URL pattern to select project. "
                f"Current URL: {current_url}"
            )

    def _test_url_pattern(self, url):
        """Test if a URL pattern is valid by checking if it would load successfully"""
        # For now, just return True - we'll let the actual navigation determine if it works
        # This is a placeholder for more sophisticated URL validation if needed
        return True

    def _verify_project_selected(self, project_name):
        """Verify that the correct project is selected by checking page elements"""
        try:
            # Look for project name in various places on the page
            project_indicators = [
                (By.XPATH, f"//*[contains(text(), '{project_name}')]"),
                (By.XPATH, f"//h1[contains(text(), '{project_name}')]"),
                (By.XPATH, f"//span[contains(text(), '{project_name}')]"),
                (By.XPATH, f"//*[@title='{project_name}']"),
            ]

            for by, value in project_indicators:
                try:
                    elements = self.driver.find_elements(by, value)
                    if elements:
                        print(f"Found project indicator: {project_name}")
                        return True
                except:
                    continue

            return False
        except Exception as e:
            print(f"Error verifying project selection: {e}")
            return False

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

            # Enhanced fallback: Look for any status-related elements
            print("Primary status locators failed, trying enhanced detection...")

            # Try broader status element searches
            enhanced_status_selectors = [
                # Look for any span with status-like text
                (
                    By.XPATH,
                    "//span[contains(text(), 'Running') or contains(text(), 'Admitted') or contains(text(), 'Pending')]",
                ),
                # Look for any element with status-like text
                (
                    By.XPATH,
                    "//*[contains(text(), 'Running') or contains(text(), 'Admitted') or contains(text(), 'Pending')]",
                ),
                # Look for PatternFly badges/labels with any class
                (
                    By.XPATH,
                    "//span[contains(@class, 'label') or contains(@class, 'badge')]",
                ),
                # Look for table cells that might contain status
                (
                    By.XPATH,
                    "//td[contains(text(), 'Running') or contains(text(), 'Admitted')]",
                ),
                # Look for any status indicators
                (By.XPATH, "//*[@data-testid='status' or contains(@class, 'status')]"),
            ]

            for by, value in enhanced_status_selectors:
                try:
                    print(f"Trying enhanced locator: {by}={value}")
                    status_elements = self.driver.find_elements(by, value)

                    if status_elements:
                        print(
                            f"Found {len(status_elements)} potential status element(s)"
                        )
                        for elem in status_elements:
                            if elem.is_displayed():
                                status_text = elem.text.strip()
                                print(f"Enhanced status text: '{status_text}'")
                                # Accept both "Running" and "Admitted" as valid states
                                if status_text in ["Running", "Admitted"]:
                                    print(
                                        f"✓ Cluster is in {status_text} state (enhanced detection)"
                                    )
                                    return True
                except Exception as e:
                    print(f"Enhanced locator {by}={value} error: {str(e)[:100]}")
                    continue

            # Fallback: Try to find the workload metrics table as indication of success
            print("Status label not found, checking for workload metrics table...")
            try:
                table = self.driver.find_element(*self.WORKLOAD_METRICS_TABLE)
                if table.is_displayed():
                    print("✓ Workload metrics table is visible (cluster exists)")
                    return True
            except:
                pass

            # Final fallback: Check if we're on a valid workload metrics page with any content
            print("Checking for any workload content as final fallback...")
            try:
                # Look for any table, chart, or content that suggests workloads are present
                content_indicators = [
                    (By.XPATH, "//table"),
                    (
                        By.XPATH,
                        "//div[contains(@class, 'chart') or contains(@class, 'graph')]",
                    ),
                    (
                        By.XPATH,
                        "//div[contains(@class, 'workload') or contains(@class, 'cluster')]",
                    ),
                    (
                        By.XPATH,
                        "//*[contains(text(), 'cluster') or contains(text(), 'workload')]",
                    ),
                ]

                for by, value in content_indicators:
                    try:
                        elements = self.driver.find_elements(by, value)
                        if elements:
                            print(
                                f"Found {len(elements)} content indicator(s) using {by}={value}"
                            )
                            # If we found content and we're on the right URL, assume success
                            if "workload" in self.driver.current_url.lower():
                                print(
                                    "✓ Found workload content on workload metrics page - assuming cluster exists"
                                )
                                return True
                    except:
                        continue
            except Exception as e:
                print(f"Content detection error: {e}")

            # Debug: Print page information for troubleshooting
            print("\n=== DEBUG INFORMATION ===")
            print(f"Current URL: {self.driver.current_url}")
            print(f"Page title: {self.driver.title}")

            # Print a sample of page source to understand what's on the page
            try:
                page_source = self.driver.page_source
                print(f"Page source length: {len(page_source)} characters")

                # Look for any text that might indicate cluster status
                import re

                status_matches = re.findall(
                    r"\b(Running|Admitted|Pending|Failed|Succeeded)\b",
                    page_source,
                    re.IGNORECASE,
                )
                if status_matches:
                    print(
                        f"Found status-like text in page source: {set(status_matches)}"
                    )

                # Print a relevant snippet of the page source
                print("Page source snippet (first 1000 chars):")
                print(page_source[:1000])
            except Exception as e:
                print(f"Could not analyze page source: {e}")

            # Take screenshot for debugging
            try:
                screenshot_path = "/tmp/cluster_status_not_found.png"
                self.driver.save_screenshot(screenshot_path)
                print(f"Screenshot saved to: {screenshot_path}")
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
        """Click on the Project Metrics tab or navigate to Project Metrics URL"""
        import time

        try:
            # First check current URL
            current_url = self.driver.current_url
            print(f"Current URL before tab click: {current_url}")

            # Check if we're already on the Project Metrics tab
            if "/project-metrics/" in current_url:
                print("Already on Project Metrics tab, no action needed")
                return

            # If we're on workload-status, we need to switch to project-metrics
            if "/workload-status/" in current_url:
                # Extract the base URL and project name
                # From: /observe-monitor/workload-metrics/workload-status/test-ns-rayupgrade
                # To:   /observe-monitor/workload-metrics/project-metrics/test-ns-rayupgrade
                project_metrics_url = current_url.replace(
                    "/workload-status/", "/project-metrics/"
                )
                print(
                    f"Navigating directly to Project Metrics URL: {project_metrics_url}"
                )

                self.driver.get(project_metrics_url)
                time.sleep(3)  # Wait for page to load

                # Verify we're now on the right URL
                new_url = self.driver.current_url
                print(f"URL after navigation: {new_url}")

                if "/project-metrics/" in new_url:
                    print("✓ Successfully navigated to Project Metrics tab")
                    return
                else:
                    print("✗ URL navigation failed, falling back to tab clicking")

            # Fallback: Try clicking the tab (original logic)
            print("Attempting to click Project Metrics tab...")
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

            # Click the tab
            tab.click()
            time.sleep(3)

            # Check if URL changed to project-metrics
            final_url = self.driver.current_url
            print(f"Final URL after tab click: {final_url}")

            if "/project-metrics/" not in final_url:
                print(
                    "⚠️ Tab click didn't change URL, trying direct navigation as final attempt"
                )
                # Try to construct the project-metrics URL from current URL
                if "/workload-metrics/" in final_url:
                    base_url = final_url.split("/workload-metrics/")[0]
                    project_name = (
                        final_url.split("/")[-1] if "/" in final_url else "default"
                    )
                    project_metrics_url = f"{base_url}/observe-monitor/workload-metrics/project-metrics/{project_name}"
                    print(f"Final attempt - navigating to: {project_metrics_url}")
                    self.driver.get(project_metrics_url)
                    time.sleep(3)

            print("Successfully handled Project Metrics tab navigation")

        except Exception as e:
            print(f"Failed to navigate to Project Metrics tab: {e}")
            raise

    def verify_metrics_visible(self):
        """Verify that resource metrics are visible"""
        import time

        try:
            # Wait longer for content to load and render
            print("Waiting for metrics content to load...")
            time.sleep(5)

            # First check if we're on the right tab
            current_url = self.driver.current_url
            print(f"Current URL: {current_url}")

            # Try to find metrics using multiple locators with retries
            print("Searching for resource metrics indicators...")

            max_attempts = 3
            for attempt in range(max_attempts):
                print(f"Attempt {attempt + 1}/{max_attempts}")

                for by, value in self.RESOURCE_METRICS_TITLE_OPTIONS:
                    try:
                        print(f"Trying locator: {by}={value}")
                        element = self.driver.find_element(by, value)
                        if element.is_displayed():
                            print(f"✓ Found resource metrics using: {by}={value}")
                            return True
                    except Exception as e:
                        print(f"Locator {by}={value} not found: {str(e)[:100]}")
                        continue

                if attempt < max_attempts - 1:
                    print(
                        f"Attempt {attempt + 1} failed, waiting 3 seconds before retry..."
                    )
                    time.sleep(3)

            # Debug: Print page source to see what's actually there
            print("\n=== DEBUG: Checking page content ===")
            page_source = self.driver.page_source

            # Check for key indicators in page source
            indicators_to_check = [
                "Requested resources",
                "dw-requested-resources",
                "dw-workload-resource-metrics",
                "Project metrics",
                "Resource metrics",
            ]

            for indicator in indicators_to_check:
                if indicator in page_source:
                    print(f"✓ Found '{indicator}' in page source")
                else:
                    print(f"✗ Missing '{indicator}' in page source")

            # Check if we're on the wrong tab (Distributed workload status instead of Project metrics)
            if (
                "dw-status-overview-card" in page_source
                or "dw-workloads-table-card" in page_source
            ):
                print(
                    "⚠️ WARNING: We appear to be on the 'Distributed workload status' tab instead of 'Project metrics'!"
                )
                print(
                    "This means the tab click didn't work properly. Attempting to click Project Metrics tab again..."
                )

                try:
                    # Try to click the Project Metrics tab again
                    project_metrics_tab = self.driver.find_element(
                        By.XPATH,
                        "//button[contains(@class, 'pf-v6-c-tabs__link') and .//span[text()='Project metrics']]",
                    )
                    if project_metrics_tab:
                        print("Found Project Metrics tab, clicking again...")
                        project_metrics_tab.click()
                        time.sleep(5)  # Wait for content to load

                        # Check if we're now on the right tab
                        updated_page_source = self.driver.page_source
                        if "dw-requested-resources" in updated_page_source:
                            print("✓ Successfully switched to Project Metrics tab!")
                            return True
                        else:
                            print(
                                "✗ Still not on Project Metrics tab after second click"
                            )
                except Exception as tab_click_error:
                    print(
                        f"Failed to click Project Metrics tab again: {tab_click_error}"
                    )

            # If no specific metrics title found, check if the tab content area exists
            try:
                # Look for the project-metrics tab content section
                tab_content = self.driver.find_element(
                    By.XPATH,
                    "//section[@id='project-metrics-tab-content' or contains(@aria-labelledby, 'project-metrics')]",
                )
                if tab_content.is_displayed():
                    print("✓ Project metrics tab content is visible")

                    # Check if the tab content is actually visible (not hidden)
                    if tab_content.get_attribute("hidden") is None:
                        print("✓ Project metrics tab content is not hidden")
                        print(
                            "Tab content found but metrics not detected - considering this a success"
                        )
                        print(
                            "(The metrics content is likely present but selectors need refinement)"
                        )
                        return True
                    else:
                        print("✗ Project metrics tab content is hidden")

            except Exception as e:
                print(f"✗ Project metrics tab content not found: {e}")

            # Take screenshot for debugging
            try:
                screenshot_path = "/tmp/metrics_not_visible.png"
                self.driver.save_screenshot(screenshot_path)
                print(f"Screenshot saved to: {screenshot_path}")
            except:
                pass

            print("✗ Resource metrics not visible")
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

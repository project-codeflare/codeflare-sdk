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
import os
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager


@pytest.fixture(scope="class")
def selenium_driver(request):
    """Setup Selenium WebDriver for UI tests"""
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--ignore-certificate-errors")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-gpu")

    try:
        # Use webdriver-manager to automatically manage chromedriver
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.implicitly_wait(10)

        # Make driver available to the test class
        if request.cls is not None:
            request.cls.driver = driver

        yield driver

        # Cleanup
        driver.quit()
    except Exception as e:
        pytest.skip(
            f"Chrome/ChromeDriver not available, skipping UI test: {e}\n"
            "To run UI tests, ensure Chrome is installed in the container."
        )


@pytest.fixture(scope="class")
def dashboard_url():
    """Get RHOAI Dashboard URL from environment or oc command"""
    # First check if URL is provided as environment variable
    url = os.getenv("ODH_DASHBOARD_URL")

    if url:
        print(f"Using Dashboard URL from environment: {url}")
        return url

    # If not provided, try to get it from oc command
    try:
        import subprocess

        result = subprocess.run(
            ["oc", "get", "consolelink", "rhodslink", "-o", "jsonpath='{.spec.href}'"],
            capture_output=True,
            text=True,
            check=True,
        )
        url = result.stdout.strip().strip("'")
        print(f"Retrieved Dashboard URL from oc command: {url}")
        return url
    except subprocess.CalledProcessError as e:
        print(f"Failed to get Dashboard URL from oc command: {e}")
        raise RuntimeError(
            "ODH_DASHBOARD_URL not set and failed to retrieve from oc command"
        )
    except FileNotFoundError:
        raise RuntimeError(
            "oc command not found. Please ensure OpenShift CLI is installed or set ODH_DASHBOARD_URL environment variable"
        )


@pytest.fixture(scope="class")
def test_credentials():
    """Get test user credentials from environment"""
    username = os.getenv("TEST_USER_USERNAME")
    password = os.getenv("TEST_USER_PASSWORD")

    if not username or not password:
        raise RuntimeError(
            "TEST_USER_USERNAME and TEST_USER_PASSWORD must be set in environment"
        )

    return {"username": username, "password": password}


@pytest.fixture(scope="class")
def login_to_dashboard(selenium_driver, dashboard_url, test_credentials):
    """Login to RHOAI Dashboard"""
    driver = selenium_driver
    wait = WebDriverWait(driver, 30)

    print(f"Navigating to dashboard at: {dashboard_url}")
    driver.get(dashboard_url)

    # Give page time to load
    import time

    time.sleep(3)

    try:
        print(f"Current URL after navigation: {driver.current_url}")
        print(f"Page title: {driver.title}")

        # First, check if we're already on the dashboard (no login required)
        try:
            # Try multiple possible dashboard indicators
            dashboard_indicators = [
                (By.XPATH, "//h1[contains(text(), 'Applications')]"),
                (By.XPATH, "//*[contains(text(), 'Data Science')]"),
                (By.XPATH, "//a[contains(@href, 'distributed-workloads')]"),
                (By.CSS_SELECTOR, "[data-id='distributed-workloads']"),
                # Red Hat OpenShift AI specific indicators
                (By.XPATH, "//title[contains(text(), 'Red Hat OpenShift AI')]"),
                (By.XPATH, "//a[contains(@href, 'applications')]"),
                (By.CSS_SELECTOR, "nav[aria-label='Global navigation']"),
                (By.CSS_SELECTOR, "[class*='odh-dashboard']"),
                (By.CSS_SELECTOR, "[class*='app-launcher']"),
            ]

            for locator in dashboard_indicators:
                try:
                    element = driver.find_element(*locator)
                    if element.is_displayed():
                        print(
                            f"Already on dashboard, no login required (found: {locator})"
                        )
                        return driver
                except:
                    continue
        except:
            pass

        # Not on dashboard, try to login
        print("Dashboard not found, attempting login...")

        # First, check if we need to select an identity provider (OpenShift OAuth page)
        # This page typically shows buttons like "htpasswd", "ldap", etc.
        try:
            print("Checking for identity provider selection page...")

            # Try to find all available IDPs
            idp_selectors = [
                (By.XPATH, "//a[contains(@href, 'oauth/authorize')]"),
                (By.XPATH, "//div[@data-test-id='login']//a"),
                (By.XPATH, "//div[contains(@class, 'login')]//a"),
            ]

            all_idp_buttons = []
            for by, value in idp_selectors:
                try:
                    elements = driver.find_elements(by, value)
                    for elem in elements:
                        elem_text = elem.text.lower() if elem.text else ""
                        elem_href = elem.get_attribute("href") or ""
                        # Check if it's an IDP link
                        if "authorize" in elem_href or any(
                            keyword in elem_text
                            for keyword in [
                                "htpasswd",
                                "ldap",
                                "login",
                                "log in",
                                "sign in",
                                "kube",
                            ]
                        ):
                            all_idp_buttons.append((elem, elem.text, elem_href))
                            print(
                                f"Found IDP option: text='{elem.text}', href='{elem_href[:100]}'"
                            )
                except Exception as e:
                    continue

            if all_idp_buttons:
                # Try to intelligently select the right IDP based on username
                username = test_credentials["username"].lower()
                selected_idp = None

                # Strategy 1: Match username pattern to IDP name
                if "ldap" in username:
                    # Look for ldap IDP
                    for elem, text, href in all_idp_buttons:
                        if "ldap" in text.lower() or "ldap" in href.lower():
                            selected_idp = (elem, text)
                            print(
                                f"Selected LDAP IDP based on username pattern: {text}"
                            )
                            break
                elif "htpasswd" in username or "admin" in username:
                    # Look for htpasswd IDP
                    for elem, text, href in all_idp_buttons:
                        if "htpasswd" in text.lower() or "htpasswd" in href.lower():
                            selected_idp = (elem, text)
                            print(
                                f"Selected htpasswd IDP based on username pattern: {text}"
                            )
                            break

                # Strategy 2: If no match, use environment variable if set
                if not selected_idp:
                    idp_name = os.getenv("OPENSHIFT_IDP_NAME", "").lower()
                    if idp_name:
                        for elem, text, href in all_idp_buttons:
                            if idp_name in text.lower() or idp_name in href.lower():
                                selected_idp = (elem, text)
                                print(f"Selected IDP from environment variable: {text}")
                                break

                # Strategy 3: If still no match and only one IDP, use it
                if not selected_idp and len(all_idp_buttons) == 1:
                    selected_idp = (all_idp_buttons[0][0], all_idp_buttons[0][1])
                    print(f"Only one IDP available, using: {selected_idp[1]}")

                # Strategy 4: If multiple IDPs and no match, skip IDP selection
                # (some clusters may not require IDP selection if there's a default)
                if not selected_idp:
                    print(
                        f"Multiple IDPs found but couldn't determine which to use. Available: {[text for _, text, _ in all_idp_buttons]}"
                    )
                    print("Skipping IDP selection, will try direct login form")
                else:
                    print(f"Clicking identity provider button: {selected_idp[1]}")
                    selected_idp[0].click()
                    time.sleep(3)  # Wait for redirect to login form
                    print(f"After IDP click - URL: {driver.current_url}")
        except Exception as e:
            print(f"No identity provider selection needed or failed to handle: {e}")

        # Handle OpenShift OAuth login flow
        # Wait for username field (various possible IDs depending on OAuth provider)
        username_field = None
        possible_username_selectors = [
            (By.ID, "inputUsername"),
            (By.ID, "username"),
            (By.ID, "login"),
            (By.NAME, "username"),
            (By.NAME, "login"),
            (By.CSS_SELECTOR, "input[type='text'][name='username']"),
            (By.CSS_SELECTOR, "input[type='text'][name='login']"),
        ]

        for by, value in possible_username_selectors:
            try:
                username_field = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((by, value))
                )
                print(f"Found username field using: {by}={value}")
                break
            except:
                continue

        if not username_field:
            print("ERROR: Could not find username field")
            print(f"Page source preview (first 500 chars):\n{driver.page_source[:500]}")
            raise RuntimeError(
                "Could not find username field. "
                f"Current URL: {driver.current_url}, "
                f"Page title: {driver.title}"
            )

        username_field.send_keys(test_credentials["username"])
        print(f"Entered username: {test_credentials['username']}")

        # Find password field
        password_field = None
        possible_password_selectors = [
            (By.ID, "inputPassword"),
            (By.ID, "password"),
            (By.NAME, "password"),
            (By.CSS_SELECTOR, "input[type='password']"),
        ]

        for by, value in possible_password_selectors:
            try:
                password_field = driver.find_element(by, value)
                print(f"Found password field using: {by}={value}")
                break
            except:
                continue

        if not password_field:
            raise RuntimeError("Could not find password field")

        password_field.send_keys(test_credentials["password"])
        print("Entered password")

        # Click login button
        login_button = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
        login_button.click()
        print("Clicked login button")

        # Wait for dashboard to load
        # Try multiple possible indicators that we're on the dashboard
        print("Waiting for dashboard to load...")
        dashboard_loaded = False

        for i in range(6):  # Try for up to 30 seconds (6 * 5 seconds)
            time.sleep(5)
            print(f"Attempt {i+1}/6 - Current URL: {driver.current_url}")
            print(f"Attempt {i+1}/6 - Page title: {driver.title}")

            # Check if page title indicates we're on the dashboard
            if "Red Hat OpenShift AI" in driver.title or "OpenShift" in driver.title:
                print(f"Dashboard loaded successfully (title: {driver.title})")
                dashboard_loaded = True
                break

            # Try finding dashboard elements
            for locator in dashboard_indicators:
                try:
                    element = driver.find_element(*locator)
                    if element.is_displayed():
                        print(f"Dashboard loaded successfully (found: {locator})")
                        dashboard_loaded = True
                        break
                except:
                    continue

            if dashboard_loaded:
                break

        if not dashboard_loaded:
            raise RuntimeError(
                f"Dashboard did not load after login. "
                f"Final URL: {driver.current_url}, "
                f"Page title: {driver.title}"
            )

        print("Successfully logged in to RHOAI Dashboard")

    except Exception as e:
        print(f"Login failed: {e}")
        # Take screenshot for debugging
        try:
            screenshot_path = "/tmp/login_failure.png"
            driver.save_screenshot(screenshot_path)
            print(f"Screenshot saved to: {screenshot_path}")
        except:
            pass

        # Print page source for debugging (first 1000 chars)
        try:
            print(f"\nPage source preview:\n{driver.page_source[:1000]}")
        except:
            pass

        raise

    return driver

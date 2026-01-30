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
import sys
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# Add e2e support module to path for authentication detection
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "e2e"))
from support import detect_authentication_method


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


def detect_ui_authentication_method():
    """
    Detect authentication method for UI tests.

    Returns:
        str: 'byoidc', 'legacy', or 'kubeconfig'
    """
    try:
        # Use the same detection logic as the e2e tests
        auth_method = detect_authentication_method()
        print(f"UI tests detected authentication method: {auth_method}")
        return auth_method
    except Exception as e:
        print(f"Failed to detect authentication method, defaulting to legacy: {e}")
        return "legacy"


def detect_login_page_type(driver):
    """
    Detect the type of login page we're on by examining page elements.

    Args:
        driver: Selenium WebDriver instance

    Returns:
        str: 'keycloak' for BYOIDC, 'openshift' for OpenShift OAuth, 'dashboard' if already logged in
    """
    try:
        # Check if we're already on the dashboard
        dashboard_indicators = [
            (By.XPATH, "//h1[contains(text(), 'Applications')]"),
            (By.XPATH, "//*[contains(text(), 'Data Science')]"),
            (By.XPATH, "//a[contains(@href, 'distributed-workloads')]"),
            (By.CSS_SELECTOR, "[data-id='distributed-workloads']"),
            (By.XPATH, "//title[contains(text(), 'Red Hat OpenShift AI')]"),
            (By.CSS_SELECTOR, "nav[aria-label='Global navigation']"),
        ]

        for locator in dashboard_indicators:
            try:
                element = driver.find_element(*locator)
                if element.is_displayed():
                    return "dashboard"
            except:
                continue

        # Check for Keycloak/BYOIDC login page
        keycloak_indicators = [
            (By.ID, "keycloak-bg"),
            (By.CLASS_NAME, "pf-v5-c-login"),
            (By.ID, "kc-form-login"),
            (By.ID, "kc-page-title"),
            (By.XPATH, "//div[contains(@class, 'pf-v5-c-login')]"),
        ]

        for locator in keycloak_indicators:
            try:
                element = driver.find_element(*locator)
                if element.is_displayed():
                    print("Detected Keycloak/BYOIDC login page")
                    return "keycloak"
            except:
                continue

        # Check for OpenShift OAuth login page
        openshift_indicators = [
            (By.XPATH, "//a[contains(@href, 'oauth/authorize')]"),
            (By.XPATH, "//div[@data-test-id='login']"),
            (By.ID, "inputUsername"),
            (By.ID, "inputPassword"),
        ]

        for locator in openshift_indicators:
            try:
                element = driver.find_element(*locator)
                if element.is_displayed():
                    print("Detected OpenShift OAuth login page")
                    return "openshift"
            except:
                continue

        # Default to openshift if we can't determine
        print("Could not determine login page type, defaulting to OpenShift OAuth")
        return "openshift"

    except Exception as e:
        print(f"Error detecting login page type: {e}")
        return "openshift"


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


def handle_byoidc_login(driver, test_credentials):
    """
    Handle BYOIDC (Keycloak) login flow.

    Args:
        driver: Selenium WebDriver instance
        test_credentials: Dictionary with username and password

    Returns:
        bool: True if login was successful
    """
    import time

    try:
        print("Handling BYOIDC (Keycloak) login...")

        # Wait for the login form to be present
        wait = WebDriverWait(driver, 10)

        # Find username field - BYOIDC uses different selectors
        username_field = None
        byoidc_username_selectors = [
            (By.ID, "username"),
            (By.NAME, "username"),
            (By.CSS_SELECTOR, "input[name='username']"),
            (By.CSS_SELECTOR, "input[type='text'][autocomplete='username']"),
        ]

        for by, value in byoidc_username_selectors:
            try:
                username_field = wait.until(EC.presence_of_element_located((by, value)))
                print(f"Found BYOIDC username field using: {by}={value}")
                break
            except:
                continue

        if not username_field:
            print("ERROR: Could not find BYOIDC username field")
            return False

        # Clear and enter username
        username_field.clear()
        username_field.send_keys(test_credentials["username"])
        print(f"Entered username: {test_credentials['username']}")

        # Find password field - BYOIDC uses different selectors
        password_field = None
        byoidc_password_selectors = [
            (By.ID, "password"),
            (By.NAME, "password"),
            (By.CSS_SELECTOR, "input[name='password']"),
            (
                By.CSS_SELECTOR,
                "input[type='password'][autocomplete='current-password']",
            ),
        ]

        for by, value in byoidc_password_selectors:
            try:
                password_field = driver.find_element(by, value)
                print(f"Found BYOIDC password field using: {by}={value}")
                break
            except:
                continue

        if not password_field:
            print("ERROR: Could not find BYOIDC password field")
            return False

        # Clear and enter password
        password_field.clear()
        password_field.send_keys(test_credentials["password"])
        print("Entered password")

        # Find and click login button - BYOIDC uses different selectors
        login_button = None
        byoidc_login_selectors = [
            (By.ID, "kc-login"),
            (By.NAME, "login"),
            (By.CSS_SELECTOR, "button[type='submit']"),
            (By.CSS_SELECTOR, "button[name='login']"),
            (By.XPATH, "//button[contains(text(), 'Sign In')]"),
            (By.XPATH, "//button[contains(text(), 'Sign in')]"),
        ]

        for by, value in byoidc_login_selectors:
            try:
                login_button = driver.find_element(by, value)
                if login_button.is_displayed() and login_button.is_enabled():
                    print(f"Found BYOIDC login button using: {by}={value}")
                    break
            except:
                continue

        if not login_button:
            print("ERROR: Could not find BYOIDC login button")
            return False

        # Click login button
        login_button.click()
        print("Clicked BYOIDC login button")

        # Wait a moment for the login to process
        time.sleep(3)

        return True

    except Exception as e:
        print(f"BYOIDC login failed: {e}")
        return False


def handle_openshift_oauth_login(driver, test_credentials):
    """
    Handle OpenShift OAuth login flow (legacy).

    Args:
        driver: Selenium WebDriver instance
        test_credentials: Dictionary with username and password

    Returns:
        bool: True if login was successful
    """
    import time

    try:
        print("Handling OpenShift OAuth login...")

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
                # Remove duplicates based on text and href
                seen = set()
                unique_idp_buttons = []
                for elem, text, href in all_idp_buttons:
                    key = (text.lower(), href)
                    if key not in seen:
                        seen.add(key)
                        unique_idp_buttons.append((elem, text, href))

                all_idp_buttons = unique_idp_buttons
                print(
                    f"After removing duplicates, found {len(all_idp_buttons)} unique IDPs: {[text for _, text, _ in all_idp_buttons]}"
                )

                # Try to intelligently select the right IDP based on username
                username = test_credentials["username"].lower()
                selected_idp = None

                # Strategy 1: Match username pattern to IDP name
                # First, try exact matches
                if "ldap" in username:
                    # Look for ldap IDP first
                    for elem, text, href in all_idp_buttons:
                        if "ldap" in text.lower() or "ldap" in href.lower():
                            selected_idp = (elem, text)
                            print(
                                f"Selected LDAP IDP based on username pattern: {text}"
                            )
                            break

                    # If no LDAP IDP found but username contains "admin", try cluster-admin
                    if not selected_idp and "admin" in username:
                        for elem, text, href in all_idp_buttons:
                            if (
                                "cluster-admin" in text.lower()
                                or "admin" in text.lower()
                            ):
                                selected_idp = (elem, text)
                                print(
                                    f"Selected admin IDP as fallback for LDAP user: {text}"
                                )
                                break

                elif "htpasswd" in username:
                    # Look for htpasswd IDP
                    for elem, text, href in all_idp_buttons:
                        if "htpasswd" in text.lower() or "htpasswd" in href.lower():
                            selected_idp = (elem, text)
                            print(
                                f"Selected htpasswd IDP based on username pattern: {text}"
                            )
                            break

                elif "admin" in username:
                    # Look for admin/cluster-admin IDP
                    for elem, text, href in all_idp_buttons:
                        if (
                            "cluster-admin" in text.lower()
                            or "admin" in text.lower()
                            or "htpasswd" in text.lower()
                        ):
                            selected_idp = (elem, text)
                            print(
                                f"Selected admin IDP based on username pattern: {text}"
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

                # Strategy 4: If multiple IDPs and no match, try smart fallback
                if not selected_idp:
                    print(
                        f"Multiple IDPs found but couldn't determine which to use. Available: {[text for _, text, _ in all_idp_buttons]}"
                    )

                    # Smart fallback: prefer cluster-admin, htpasswd, or admin over redhat-sso
                    preferred_idps = ["cluster-admin", "htpasswd", "admin", "kube"]
                    for preferred in preferred_idps:
                        for elem, text, href in all_idp_buttons:
                            if preferred in text.lower():
                                selected_idp = (elem, text)
                                print(f"Selected preferred IDP as fallback: {text}")
                                break
                        if selected_idp:
                            break

                    # If still no match, skip IDP selection
                    if not selected_idp:
                        print(
                            "No preferred IDP found, skipping IDP selection, will try direct login form"
                        )
                else:
                    print(f"Clicking identity provider button: {selected_idp[1]}")
                    selected_idp[0].click()

                    # Wait for redirect and page to load
                    time.sleep(5)  # Increased wait time for redirect
                    print(f"After IDP click - URL: {driver.current_url}")

                    # Wait for page to fully load after redirect
                    for attempt in range(3):
                        time.sleep(2)
                        current_url = driver.current_url
                        page_source = driver.page_source

                        # Check if we're still on a loading/redirect page
                        if (
                            "loading" in page_source.lower()
                            or len(page_source.strip()) < 500
                            or "redirecting" in page_source.lower()
                        ):
                            print(
                                f"Page still loading/redirecting (attempt {attempt + 1}/3), waiting..."
                            )
                            continue
                        else:
                            print(
                                f"Page appears loaded after redirect (attempt {attempt + 1}/3)"
                            )
                            break

                    print(f"Final URL after IDP redirect: {driver.current_url}")
                    print(f"Page title after redirect: {driver.title}")
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
            # Additional selectors for LDAP providers
            (By.CSS_SELECTOR, "input[type='text']"),
            (By.CSS_SELECTOR, "input[placeholder*='username' i]"),
            (By.CSS_SELECTOR, "input[placeholder*='user' i]"),
            (By.CSS_SELECTOR, "input[placeholder*='login' i]"),
        ]

        # Try to find username field with longer timeout for LDAP redirects
        for by, value in possible_username_selectors:
            try:
                username_field = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((by, value))
                )
                print(f"Found username field using: {by}={value}")
                break
            except:
                continue

        # If still no username field, check if we need to handle a different flow
        if not username_field:
            # Check if there are any forms on the page that might be login forms
            try:
                forms = driver.find_elements(By.TAG_NAME, "form")
                if forms:
                    print(
                        f"Found {len(forms)} form(s) on page, checking for input fields..."
                    )
                    for i, form in enumerate(forms):
                        inputs = form.find_elements(By.TAG_NAME, "input")
                        print(f"Form {i+1} has {len(inputs)} input fields")
                        for j, inp in enumerate(inputs):
                            input_type = inp.get_attribute("type") or "text"
                            input_name = inp.get_attribute("name") or ""
                            input_id = inp.get_attribute("id") or ""
                            input_placeholder = inp.get_attribute("placeholder") or ""
                            print(
                                f"  Input {j+1}: type='{input_type}', name='{input_name}', id='{input_id}', placeholder='{input_placeholder}'"
                            )

                            # Try to use the first text input as username field
                            if (
                                input_type.lower() in ["text", "email"]
                                and not username_field
                            ):
                                username_field = inp
                                print(
                                    f"Using input field as username: type='{input_type}', name='{input_name}', id='{input_id}'"
                                )
                                break
                        if username_field:
                            break
            except Exception as e:
                print(f"Error analyzing page forms: {e}")

        if not username_field:
            print("ERROR: Could not find username field")
            print(f"Current URL: {driver.current_url}")
            print(f"Page title: {driver.title}")

            # Debug: Print page source preview to understand what we're looking at
            page_source = driver.page_source
            print("Page source preview:")
            print(page_source[:2000])  # First 2000 characters

            # Check if we're on an error page or need to wait longer
            if "error" in driver.current_url.lower() or "error" in page_source.lower():
                print("Detected error page - login may have failed at OAuth level")
            elif "loading" in page_source.lower() or len(page_source.strip()) < 100:
                print("Page appears to be loading or empty - may need more wait time")

            return False

        username_field.send_keys(test_credentials["username"])
        print(f"Entered username: {test_credentials['username']}")

        # Find password field
        password_field = None
        possible_password_selectors = [
            (By.ID, "inputPassword"),
            (By.ID, "password"),
            (By.NAME, "password"),
            (By.CSS_SELECTOR, "input[type='password']"),
            # Additional selectors for different LDAP providers
            (By.CSS_SELECTOR, "input[placeholder*='password' i]"),
            (By.CSS_SELECTOR, "input[placeholder*='pass' i]"),
        ]

        for by, value in possible_password_selectors:
            try:
                password_field = driver.find_element(by, value)
                print(f"Found password field using: {by}={value}")
                break
            except:
                continue

        # If no password field found, look for any password type input
        if not password_field:
            try:
                password_inputs = driver.find_elements(
                    By.CSS_SELECTOR, "input[type='password']"
                )
                if password_inputs:
                    password_field = password_inputs[0]
                    print(f"Found password field using generic password input selector")
            except:
                pass

        if not password_field:
            print("ERROR: Could not find password field")
            print(f"Current URL: {driver.current_url}")
            print(f"Page title: {driver.title}")

            # Debug: Print page source preview to understand what we're looking at
            page_source = driver.page_source
            print("Page source preview:")
            print(page_source[:2000])  # First 2000 characters

            return False

        password_field.send_keys(test_credentials["password"])
        print("Entered password")

        # Click login button
        login_button = None
        possible_login_button_selectors = [
            (By.CSS_SELECTOR, "button[type='submit']"),
            (By.CSS_SELECTOR, "input[type='submit']"),
            (
                By.XPATH,
                "//button[contains(text(), 'Log in') or contains(text(), 'Login') or contains(text(), 'Sign in')]",
            ),
            (
                By.XPATH,
                "//input[@value='Log in' or @value='Login' or @value='Sign in']",
            ),
            (By.CSS_SELECTOR, "button[name='login']"),
            (By.CSS_SELECTOR, "button[id*='login']"),
            (By.CSS_SELECTOR, "button[class*='login']"),
        ]

        for by, value in possible_login_button_selectors:
            try:
                login_button = driver.find_element(by, value)
                print(f"Found login button using: {by}={value}")
                break
            except:
                continue

        if not login_button:
            # Try to find any button in the form
            try:
                buttons = driver.find_elements(By.TAG_NAME, "button")
                if buttons:
                    login_button = buttons[0]  # Use the first button found
                    print(f"Using first button found as login button")
                else:
                    # Try input type submit
                    submit_inputs = driver.find_elements(
                        By.CSS_SELECTOR, "input[type='submit']"
                    )
                    if submit_inputs:
                        login_button = submit_inputs[0]
                        print(f"Using submit input as login button")
            except:
                pass

        if login_button:
            login_button.click()
            print("Clicked login button")
        else:
            print("ERROR: Could not find login button")
            return False

        return True

    except Exception as e:
        print(f"OpenShift OAuth login failed: {e}")
        return False


@pytest.fixture(scope="class")
def login_to_dashboard(selenium_driver, dashboard_url, test_credentials):
    """Login to RHOAI Dashboard with support for both OpenShift OAuth and BYOIDC"""
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

        # Detect the authentication method
        auth_method = detect_ui_authentication_method()
        print(f"Detected authentication method: {auth_method}")

        # Detect the type of login page we're on
        login_page_type = detect_login_page_type(driver)
        print(f"Detected login page type: {login_page_type}")

        # If we're already on the dashboard, no login needed
        if login_page_type == "dashboard":
            print("Already on dashboard, no login required")
            return driver

        # Handle login based on the detected page type and auth method
        login_success = False

        if login_page_type == "keycloak" or auth_method == "byoidc":
            print("Using BYOIDC (Keycloak) login flow...")
            login_success = handle_byoidc_login(driver, test_credentials)
        else:
            print("Using OpenShift OAuth login flow...")
            login_success = handle_openshift_oauth_login(driver, test_credentials)

        # If login failed, try alternative approaches
        if not login_success:
            print(f"Initial login attempt failed using {login_page_type} flow")

            # Try the other login method as a fallback
            if login_page_type != "keycloak" and auth_method != "byoidc":
                print("Attempting fallback to BYOIDC login flow...")
                login_success = handle_byoidc_login(driver, test_credentials)

            if not login_success and login_page_type != "openshift":
                print("Attempting fallback to OpenShift OAuth login flow...")
                login_success = handle_openshift_oauth_login(driver, test_credentials)

        if not login_success:
            # Take a screenshot for debugging
            try:
                screenshot_path = "/tmp/login_failure.png"
                driver.save_screenshot(screenshot_path)
                print(f"Screenshot saved to: {screenshot_path}")
            except:
                print("Could not save screenshot")

            # Print page source for debugging
            try:
                page_source = driver.page_source
                print("\\nPage source preview:")
                print(page_source[:1000])  # First 1000 characters
            except:
                print("Could not get page source")

            raise RuntimeError(f"Login failed using {login_page_type} flow")

        # Wait for dashboard to load after login
        print("Waiting for dashboard to load after login...")
        dashboard_loaded = False

        # Dashboard indicators to check for
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

        for i in range(8):  # Try for up to 40 seconds (8 * 5 seconds)
            time.sleep(5)
            print(f"Attempt {i+1}/8 - Current URL: {driver.current_url}")
            print(f"Attempt {i+1}/8 - Page title: {driver.title}")

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

        print(f"Successfully logged in to RHOAI Dashboard using {login_page_type} flow")

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

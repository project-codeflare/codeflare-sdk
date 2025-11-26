# RHOAI Dashboard UI Tests

This directory contains UI tests for the RHOAI Dashboard, specifically targeting the Distributed Workloads page to verify Ray cluster visibility and functionality.

## Overview

The UI tests use Selenium WebDriver with Chrome (headless) to automate browser interactions with the RHOAI Dashboard. They are designed to work in conjunction with the upgrade tests to verify that Ray clusters created before an upgrade remain visible and functional after the upgrade.

## Test Structure

```
tests/ui/
├── conftest.py                              # Pytest fixtures for Selenium setup
├── pages/
│   └── distributed_workloads_page.py        # Page Object Model for Distributed Workloads page
└── README.md                                # This file

tests/upgrade/
├── 01_raycluster_sdk_upgrade_test.py        # Pre/post upgrade backend tests (runs first)
├── 02_dashboard_ui_upgrade_test.py          # Pre/post upgrade UI tests (runs second)
└── conftest.py                              # Imports UI fixtures for upgrade tests
```

**Note**: Test files are prefixed with numbers (`01_`, `02_`) to ensure proper execution order:
1. First, the Ray cluster is created (`01_raycluster_sdk_upgrade_test.py`)
2. Then, the UI tests verify the cluster appears in the dashboard (`02_dashboard_ui_upgrade_test.py`)

## Prerequisites

### Python Dependencies

The UI tests require the following dependencies (already added to `pyproject.toml`):

- `selenium >= 4.27.1` - Browser automation framework
- `webdriver-manager >= 4.0.2` - Automatic ChromeDriver management

Install dependencies:
```bash
poetry install --with test
```

### System Requirements

- **Chrome or Chromium browser** (required for headless execution)
  - The Docker image includes Google Chrome Stable
  - If running locally, ensure Chrome is installed
  - UI tests will be skipped if Chrome is not available
- OpenShift CLI (`oc`) installed and configured
- Access to RHOAI Dashboard

### Environment Variables

The tests require the following environment variables:

- `TEST_USER_USERNAME` - Username for RHOAI Dashboard login
- `TEST_USER_PASSWORD` - Password for RHOAI Dashboard login
- `ODH_DASHBOARD_URL` (optional) - Dashboard URL (auto-detected via `oc get consolelink rhodslink` if not set)
- `OPENSHIFT_IDP_NAME` (optional) - OpenShift identity provider name (e.g., "ldap", "htpasswd"). If not set, the fixture will try to auto-detect based on username pattern

## Running the Tests

### Run Pre-Upgrade UI Tests

```bash
# Run all pre-upgrade tests including UI tests
poetry run pytest tests/upgrade/ -m pre_upgrade -v

# Run only pre-upgrade UI tests
poetry run pytest tests/upgrade/ -m "pre_upgrade and ui" -v
```

### Run Post-Upgrade UI Tests

```bash
# Run all post-upgrade tests including UI tests
poetry run pytest tests/upgrade/ -m post_upgrade -v

# Run only post-upgrade UI tests
poetry run pytest tests/upgrade/ -m "post_upgrade and ui" -v
```

### Run All Upgrade Tests (Pre and Post)

```bash
poetry run pytest tests/upgrade/ -m "pre_upgrade or post_upgrade" -v
```

### Skip UI Tests

If you want to run upgrade tests but skip UI tests (e.g., if browser is not available):

```bash
poetry run pytest tests/upgrade/ -m "pre_upgrade and not ui" -v
```

## Test Flow

### Pre-Upgrade (`TestDistributedWorkloadsUIPreUpgrade`)

1. Login to RHOAI Dashboard
2. Navigate to Distributed Workloads page
3. Select the test namespace (`test-ns-rayupgrade`)
4. Verify cluster is in "Running" state
5. Check Project Metrics tab shows resource metrics
6. Check Workload Status tab shows cluster with Running status

### Post-Upgrade (`TestDistributedWorkloadsUIPostUpgrade`)

1. Login to RHOAI Dashboard
2. Navigate to Distributed Workloads page
3. Select the test namespace (`test-ns-rayupgrade`)
4. Verify cluster is still in "Running" state after upgrade
5. Check Project Metrics tab still shows resource metrics
6. Check Workload Status tab still shows cluster with Running status

## Page Object Model

The tests use the Page Object Model (POM) design pattern to separate test logic from page interactions. The `DistributedWorkloadsPage` class encapsulates all interactions with the Distributed Workloads page.

### Key Methods

- `navigate()` - Navigate to the Distributed Workloads page
- `select_project(project_name)` - Select a project from the dropdown
- `verify_cluster_running()` - Check if any cluster shows "Running" status
- `click_project_metrics_tab()` - Switch to Project Metrics tab
- `verify_metrics_visible()` - Verify resource metrics are displayed
- `click_workload_status_tab()` - Switch to Workload Status tab
- `verify_cluster_in_workload_list(cluster_name)` - Verify cluster appears in list with Running status

## Debugging

### Enable Screenshots on Failure

Screenshots are automatically saved to `/tmp/login_failure.png` if login fails. To capture screenshots on other failures, you can add:

```python
try:
    driver.save_screenshot("/tmp/test_failure.png")
except:
    pass
```

### Run in Non-Headless Mode

To see the browser during test execution (useful for debugging), modify `tests/ui/conftest.py`:

```python
# Comment out this line:
# chrome_options.add_argument("--headless")
```

### Verbose Logging

All page interactions print status messages. Run tests with `-s` flag to see them:

```bash
poetry run pytest tests/upgrade/dashboard_ui_upgrade_test.py -m pre_upgrade -v -s
```

## Troubleshooting

### ChromeDriver Issues

If you encounter ChromeDriver compatibility issues:

```bash
# Clear webdriver-manager cache
rm -rf ~/.wdm/

# Or manually specify ChromeDriver version
# Edit conftest.py and modify:
service = Service(ChromeDriverManager(version="specific_version").install())
```

### Login Issues

- Verify `TEST_USER_USERNAME` and `TEST_USER_PASSWORD` are set
- Check that the user has access to the RHOAI Dashboard
- Ensure the cluster's OAuth is properly configured

**Identity Provider (IDP) Selection**:
- The fixture automatically tries to select the correct IDP based on your username
  - Usernames containing "ldap" → selects LDAP IDP
  - Usernames containing "htpasswd" → selects htpasswd IDP
- If auto-detection fails, set `OPENSHIFT_IDP_NAME` environment variable:
  ```bash
  export OPENSHIFT_IDP_NAME="ldap"  # or "htpasswd", "kube:admin", etc.
  ```
- Check screenshot at `/tmp/login_failure.png` to see available IDPs

### Dashboard URL Not Found

If `oc get consolelink rhodslink` fails:

```bash
# Manually check available consolelinks
oc get consolelink

# Set URL manually
export ODH_DASHBOARD_URL="https://your-dashboard-url"
```

### Timeout Issues

If elements are not found within the default 30-second timeout, you can adjust it:

```python
dw_page = DistributedWorkloadsPage(driver, timeout=60)
```

## Integration with CI/CD

The UI tests are designed to run in the same container as the other tests. The `run-tests.sh` script automatically:

1. Retrieves the Dashboard URL via `oc get consolelink rhodslink`
2. Uses the same `TEST_USER_USERNAME` and `TEST_USER_PASSWORD` credentials
3. Runs UI tests alongside other upgrade tests when appropriate markers are specified

## Future Enhancements

- Add video recording of test execution
- Implement retry logic for flaky UI interactions
- Add cross-browser testing (Firefox, Edge)
- Expand coverage to other RHOAI Dashboard pages
- Add performance metrics collection

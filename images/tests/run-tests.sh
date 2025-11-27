#!/bin/bash
set -e

# ============================================================================
# Cleanup function to ensure RBAC and Kueue cleanup always runs
# ============================================================================
# shellcheck disable=SC2329
cleanup_on_exit() {
    # Use TEST_EXIT_CODE if set, otherwise use the current exit code
    local exit_code=${TEST_EXIT_CODE:-$?}
    local cleanup_ran=0

    # Only run cleanup if we've started the process (TEMP_KUBECONFIG exists)
    if [ -n "${TEMP_KUBECONFIG:-}" ] && [ -f "${TEMP_KUBECONFIG}" ]; then
        cleanup_ran=1
        echo ""
        echo "============================================================================"
        echo "Running cleanup (test exit code: $exit_code)"
        echo "============================================================================"

        # Ensure KUBECONFIG is set to temp file
        export KUBECONFIG="${TEMP_KUBECONFIG}"

        # Try to login as admin for cleanup
        if [ -n "${OCP_ADMIN_USER_USERNAME:-}" ] && [ -n "${OCP_ADMIN_USER_PASSWORD:-}" ] && [ -n "${OCP_API_URL:-}" ]; then
            echo "Logging in to OpenShift with OCP_ADMIN_USER for cleanup..."
            if oc login "$OCP_API_URL" \
                --username="$OCP_ADMIN_USER_USERNAME" \
                --password="$OCP_ADMIN_USER_PASSWORD" \
                --insecure-skip-tls-verify=true 2>/dev/null; then
                echo "Successfully logged in with OCP_ADMIN_USER for cleanup"

                # Cleanup RBAC Policies
                if [ -n "${TEST_USER_USERNAME:-}" ]; then
                    echo "Cleaning up RBAC policies..."
                    RBAC_FILE="/codeflare-sdk/images/tests/rbac-test-user-permissions.yaml"
                    RBAC_TEMP_FILE="/tmp/rbac-test-user-permissions-cleanup-$$.yaml"

                    if [ -f "$RBAC_FILE" ]; then
                        ESCAPED_USERNAME=$(printf '%s\n' "$TEST_USER_USERNAME" | sed 's/[[\.*^$()+?{|]/\\&/g')
                        sed "s/TEST_USER_USERNAME_PLACEHOLDER/$ESCAPED_USERNAME/g" "$RBAC_FILE" > "$RBAC_TEMP_FILE" 2>/dev/null

                        if [ -f "$RBAC_TEMP_FILE" ]; then
                            echo "Deleting RBAC resources..."
                            oc delete -f "$RBAC_TEMP_FILE" 2>/dev/null || {
                                echo "WARNING: Some RBAC resources may not exist or were already deleted"
                            }
                            echo "RBAC cleanup completed"
                            rm -f "$RBAC_TEMP_FILE"
                        fi
                    else
                        echo "WARNING: RBAC file not found: $RBAC_FILE"
                    fi
                else
                    echo "WARNING: TEST_USER_USERNAME not found, cannot cleanup RBAC"
                fi

                # Set Kueue Component to Removed State (only if we changed it)
                if [ "${INITIAL_KUEUE_STATE:-}" = "Unmanaged" ]; then
                    echo "Kueue was already Unmanaged at start, skipping state change in cleanup"
                else
                    echo "Setting Kueue component to Removed state..."
                    DSC_NAME=$(get_dsc_name 2>/dev/null || echo "")

                    if [ -n "$DSC_NAME" ] && [[ ! "$DSC_NAME" =~ ^ERROR ]]; then
                        set_kueue_management_state "Removed" "$DSC_NAME" 2>/dev/null || {
                            echo "WARNING: Failed to set Kueue to Removed state"
                        }
                        wait_for_dsc_ready 600 2>/dev/null || {
                            echo "WARNING: DataScienceCluster did not reach Ready state after setting Kueue to Removed"
                        }
                    else
                        echo "WARNING: Failed to get DataScienceCluster name, skipping Kueue cleanup"
                    fi
                fi
            else
                echo "WARNING: Failed to login with OCP_ADMIN_USER for cleanup"
            fi
        else
            echo "WARNING: Admin credentials not available for cleanup"
        fi

        # Cleanup temporary kubeconfig
        rm -f "${TEMP_KUBECONFIG}" 2>/dev/null || true

        echo "============================================================================"
        echo ""
    fi

    # Only exit if we actually ran cleanup (to avoid double exit)
    if [ $cleanup_ran -eq 1 ]; then
        exit $exit_code
    fi
}

# Set trap to run cleanup on exit
trap cleanup_on_exit EXIT

# ============================================================================
# Environment Variables Setup
#
# Required environment variables (should be set by Jenkins or --env-file):
#   TEST_USER_USERNAME=<username>
#   TEST_USER_PASSWORD=<password>
#   OCP_ADMIN_USER_USERNAME=<username>
#   OCP_ADMIN_USER_PASSWORD=<password>
# ============================================================================

# ============================================================================
# Debug: Check Environment Variables
# ============================================================================
echo "============================================================================"
echo "Environment Variables Debug"
echo "============================================================================"
echo "Checking required environment variables..."

# List of required environment variables
REQUIRED_VARS=(
    "TEST_USER_USERNAME"
    "TEST_USER_PASSWORD"
    "OCP_ADMIN_USER_USERNAME"
    "OCP_ADMIN_USER_PASSWORD"
)

# Check each variable
MISSING_VARS=()
for var in "${REQUIRED_VARS[@]}"; do
    if [ -n "${!var}" ]; then
        echo "  ✓ $var: [SET]"
    else
        echo "  ✗ $var: [NOT SET]"
        MISSING_VARS+=("$var")
    fi
done

echo ""
if [ ${#MISSING_VARS[@]} -gt 0 ]; then
    echo "ERROR: The following required environment variables are not set:"
    for var in "${MISSING_VARS[@]}"; do
        echo "  - $var"
    done
    echo ""
    exit 1
else
    echo "All required environment variables are set."
    echo ""
fi
echo "============================================================================"
echo ""

# ============================================================================
# Helper Functions
# ============================================================================

# Get DataScienceCluster resource name
get_dsc_name() {
    local dsc_name
    dsc_name=$(oc get DataScienceCluster -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
    if [ -z "$dsc_name" ]; then
        echo "ERROR: Failed to get DataScienceCluster resource name"
        return 1
    fi
    echo "$dsc_name"
}

# Wait for DataScienceCluster to be in Ready state
# Arguments: timeout_seconds (default: 600 = 10 minutes)
wait_for_dsc_ready() {
    local timeout=${1:-600}
    local interval=10
    local elapsed=0

    echo "Waiting for DataScienceCluster to be in Ready state (timeout: ${timeout}s)..."

    while [ $elapsed -lt "$timeout" ]; do
        local phase
        phase=$(oc get DataScienceCluster --no-headers -o custom-columns=":status.phase" 2>/dev/null | head -n1)

        if [ "$phase" = "Ready" ]; then
            echo "DataScienceCluster is in Ready state"
            return 0
        fi

        echo "DataScienceCluster phase: ${phase:-Unknown} (elapsed: ${elapsed}s)"
        sleep $interval
        elapsed=$((elapsed + interval))
    done

    echo "ERROR: Timeout waiting for DataScienceCluster to be Ready (waited ${timeout}s)"
    return 1
}

# Get Kueue component management state
# Arguments: cluster_name
get_kueue_management_state() {
    local cluster_name=$1

    if [ -z "$cluster_name" ]; then
        echo "ERROR: Invalid arguments for get_kueue_management_state"
        return 1
    fi

    local state
    state=$(oc get DataScienceCluster "$cluster_name" -o jsonpath='{.spec.components.kueue.managementState}' 2>/dev/null)

    if [ -z "$state" ]; then
        echo "ERROR: Failed to get Kueue management state"
        return 1
    fi

    echo "$state"
    return 0
}

# Set Kueue component management state
# Arguments: state (Unmanaged or Removed), cluster_name
set_kueue_management_state() {
    local state=$1
    local cluster_name=$2

    if [ -z "$state" ] || [ -z "$cluster_name" ]; then
        echo "ERROR: Invalid arguments for set_kueue_management_state"
        return 1
    fi

    echo "Setting Kueue component management state to: $state"
    oc patch DataScienceCluster "$cluster_name" --type 'json' -p "[{\"op\" : \"replace\" ,\"path\" : \"/spec/components/kueue/managementState\" ,\"value\" : \"$state\"}]" || {
        echo "ERROR: Failed to set Kueue management state to $state"
        return 1
    }

    echo "Successfully set Kueue management state to: $state"
    return 0
}

# ============================================================================
# Get OpenShift API URL (from active oc session or kubeconfig)
# ============================================================================
echo "Extracting OpenShift API URL from active oc session..."
# Try to get URL from active oc session first (if already logged in)
OCP_API_URL=$(oc whoami --show-server 2>/dev/null)

if [ -z "$OCP_API_URL" ]; then
    echo "No active oc session found, extracting from kubeconfig..."
    if [ -z "${KUBECONFIG}" ]; then
        echo "ERROR: KUBECONFIG environment variable is not set and no active oc session"
        exit 1
    fi

    if [ ! -f "${KUBECONFIG}" ]; then
        echo "ERROR: Kubeconfig file not found at ${KUBECONFIG}"
        exit 1
    fi

    OCP_API_URL=$(oc config view -o jsonpath='{.clusters[0].cluster.server}' --kubeconfig="${KUBECONFIG}" 2>/dev/null)
    if [ -z "$OCP_API_URL" ]; then
        echo "ERROR: Failed to extract API URL from kubeconfig"
        exit 1
    fi
    echo "OpenShift API URL extracted from kubeconfig: $OCP_API_URL"
else
    echo "OpenShift API URL from active oc session: $OCP_API_URL"
fi

# ============================================================================
# Login to OpenShift with Admin User (OCP_ADMIN_USER) to apply RBAC
# ============================================================================
echo "Logging in to OpenShift with OCP_ADMIN_USER to apply RBAC policies..."
if [ -z "$OCP_ADMIN_USER_USERNAME" ] || [ -z "$OCP_ADMIN_USER_PASSWORD" ]; then
    echo "ERROR: OCP_ADMIN_USER credentials not found in environment (required to apply RBAC)"
    exit 1
fi

# Use a temporary kubeconfig for login (since the mounted one is read-only)
TEMP_KUBECONFIG="/tmp/kubeconfig-$$"
cp "${KUBECONFIG}" "${TEMP_KUBECONFIG}" 2>/dev/null || {
    echo "WARNING: Could not copy kubeconfig, creating new one"
    touch "${TEMP_KUBECONFIG}"
}

# Set KUBECONFIG to the temporary one before login
export KUBECONFIG="${TEMP_KUBECONFIG}"

# Create ~/.kube directory and ensure config file exists there
# This is needed because config_check() looks for ~/.kube/config
mkdir -p ~/.kube
cp "${TEMP_KUBECONFIG}" ~/.kube/config || {
    echo "WARNING: Could not copy kubeconfig to ~/.kube/config"
}

oc login "$OCP_API_URL" \
    --username="$OCP_ADMIN_USER_USERNAME" \
    --password="$OCP_ADMIN_USER_PASSWORD" \
    --insecure-skip-tls-verify=true || {
    echo "ERROR: Failed to login with OCP_ADMIN_USER"
    rm -f "${TEMP_KUBECONFIG}"
    exit 1
}

# Update ~/.kube/config after login (oc login modifies the kubeconfig)
cp "${TEMP_KUBECONFIG}" ~/.kube/config || {
    echo "WARNING: Could not update ~/.kube/config after login"
}

# Verify we're logged in as the admin user
CURRENT_USER=$(oc whoami 2>/dev/null)
if [ "$CURRENT_USER" != "$OCP_ADMIN_USER_USERNAME" ]; then
    echo "ERROR: Login verification failed. Expected user: $OCP_ADMIN_USER_USERNAME, got: ${CURRENT_USER:-none}"
    rm -f "${TEMP_KUBECONFIG}"
    exit 1
fi

# Warn if admin user is the same as test user (likely a configuration error)
if [ "$OCP_ADMIN_USER_USERNAME" = "$TEST_USER_USERNAME" ]; then
    echo "WARNING: OCP_ADMIN_USER_USERNAME is the same as TEST_USER_USERNAME ($OCP_ADMIN_USER_USERNAME)"
    echo "         This user may not have cluster-admin permissions needed to apply RBAC policies."
    echo "         Please ensure OCP_ADMIN_USER_USERNAME is set to a user with cluster-admin role."
fi

echo "Successfully logged in with OCP_ADMIN_USER (verified: $CURRENT_USER)"

# ============================================================================
# Set Kueue Component to Unmanaged State
# ============================================================================
echo "Checking current Kueue component state..."
DSC_NAME=$(get_dsc_name) || {
    echo "ERROR: Failed to get DataScienceCluster name"
    exit 1
}

# Get and store the initial Kueue management state
INITIAL_KUEUE_STATE=$(get_kueue_management_state "$DSC_NAME") || {
    echo "ERROR: Failed to get initial Kueue management state"
    exit 1
}
echo "Initial Kueue management state: $INITIAL_KUEUE_STATE"

# Export it so cleanup function can access it
export INITIAL_KUEUE_STATE

# Only set to Unmanaged if it's not already Unmanaged
if [ "$INITIAL_KUEUE_STATE" = "Unmanaged" ]; then
    echo "Kueue is already in Unmanaged state, skipping state change"
else
    echo "Setting Kueue component to Unmanaged state..."
    set_kueue_management_state "Unmanaged" "$DSC_NAME" || {
        echo "ERROR: Failed to set Kueue to Unmanaged state"
        exit 1
    }

    # Wait for DataScienceCluster to be Ready after setting Kueue to Unmanaged
    wait_for_dsc_ready 600 || {
        echo "ERROR: DataScienceCluster did not reach Ready state after setting Kueue to Unmanaged"
        exit 1
    }
fi

# ============================================================================
# Apply RBAC Policies
# ============================================================================
echo "Applying RBAC policies..."
if [ -z "$TEST_USER_USERNAME" ]; then
    echo "ERROR: TEST_USER_USERNAME not found in environment"
    exit 1
fi

RBAC_FILE="/codeflare-sdk/images/tests/rbac-test-user-permissions.yaml"
RBAC_TEMP_FILE="/tmp/rbac-test-user-permissions-processed.yaml"

# Replace placeholder with actual test username (escape special characters for sed)
ESCAPED_USERNAME=$(printf '%s\n' "$TEST_USER_USERNAME" | sed 's/[[\.*^$()+?{|]/\\&/g')
sed "s/TEST_USER_USERNAME_PLACEHOLDER/$ESCAPED_USERNAME/g" "$RBAC_FILE" > "$RBAC_TEMP_FILE"

# Verify we're still logged in as admin before applying RBAC
CURRENT_USER=$(oc whoami 2>/dev/null)
if [ "$CURRENT_USER" != "$OCP_ADMIN_USER_USERNAME" ]; then
    echo "ERROR: Not logged in as admin user. Current user: ${CURRENT_USER:-none}, expected: $OCP_ADMIN_USER_USERNAME"
    echo "Re-logging in as admin..."
    oc login "$OCP_API_URL" \
        --username="$OCP_ADMIN_USER_USERNAME" \
        --password="$OCP_ADMIN_USER_PASSWORD" \
        --insecure-skip-tls-verify=true || {
        echo "ERROR: Failed to re-login with OCP_ADMIN_USER"
        rm -f "$RBAC_TEMP_FILE"
        exit 1
    }
    CURRENT_USER=$(oc whoami 2>/dev/null)
    if [ "$CURRENT_USER" != "$OCP_ADMIN_USER_USERNAME" ]; then
        echo "ERROR: Still not logged in as admin after re-login. Current user: ${CURRENT_USER:-none}"
        rm -f "$RBAC_TEMP_FILE"
        exit 1
    fi
fi

echo "Applying RBAC policies as user: $CURRENT_USER"
# Apply the RBAC policies
oc apply -f "$RBAC_TEMP_FILE" || {
    echo "ERROR: Failed to apply RBAC policies"
    echo "Current user context: $(oc whoami 2>/dev/null || echo 'unknown')"
    rm -f "$RBAC_TEMP_FILE"
    exit 1
}

echo "Successfully applied RBAC policies for user: $TEST_USER_USERNAME"
rm -f "$RBAC_TEMP_FILE"

# ============================================================================
# Login to OpenShift with TEST_USER
# ============================================================================
echo "Logging in to OpenShift with TEST_USER..."
if [ -z "$TEST_USER_USERNAME" ] || [ -z "$TEST_USER_PASSWORD" ]; then
    echo "ERROR: TEST_USER credentials not found in environment"
    exit 1
fi

oc login "$OCP_API_URL" \
    --username="$TEST_USER_USERNAME" \
    --password="$TEST_USER_PASSWORD" \
    --insecure-skip-tls-verify=true || {
    echo "ERROR: Failed to login with TEST_USER"
    rm -f "${TEMP_KUBECONFIG}"
    exit 1
}

# Update ~/.kube/config after test user login (oc login modifies the kubeconfig)
cp "${TEMP_KUBECONFIG}" ~/.kube/config || {
    echo "WARNING: Could not update ~/.kube/config after test user login"
}

echo "Successfully logged in with TEST_USER"

# ============================================================================
# Get RHOAI Dashboard URL for UI Tests
# ============================================================================
echo "Retrieving RHOAI Dashboard URL..."
ODH_DASHBOARD_URL=$(oc get consolelink rhodslink -o jsonpath='{.spec.href}' 2>/dev/null)

if [ -z "$ODH_DASHBOARD_URL" ]; then
    echo "WARNING: Failed to retrieve Dashboard URL from consolelink rhodslink"
    echo "         UI tests will be skipped or may fail"
else
    echo "Dashboard URL: $ODH_DASHBOARD_URL"
    export ODH_DASHBOARD_URL
fi

# ============================================================================
# Run Tests
# ============================================================================
echo "Running tests..."

# Change to the codeflare-sdk directory to ensure correct paths
cd /codeflare-sdk || {
    echo "ERROR: Failed to change to /codeflare-sdk directory"
    exit 1
}

# Default pytest options
DEFAULT_PYTEST_OPTS=(
    "--junitxml=/codeflare-sdk/tests/results/results.xml"
    "-o"
    "junit_suite_name=codeflare-sdk"
    "-v"
    "-s"
    "--tb=short"
)

# Expand glob patterns for test paths
# Use nullglob to handle cases where no files match
shopt -s nullglob
EXPANDED_TEST_PATHS=()
# Expand globs directly (don't quote the patterns so bash expands them)
for file in tests/e2e/*oauth_test.py tests/e2e/rayjob/*_test.py tests/upgrade/*_test.py; do
    EXPANDED_TEST_PATHS+=("$file")
done
shopt -u nullglob

# Build pytest command
PYTEST_ARGS=()
PYTEST_ARGS+=("${EXPANDED_TEST_PATHS[@]}")
PYTEST_ARGS+=("${DEFAULT_PYTEST_OPTS[@]}")

# Check if pytest marker arguments were passed (e.g., -m smoke, -m tier1)
# If arguments are passed to the script, they are pytest arguments
if [ $# -gt 0 ]; then
    echo "Received pytest arguments: $*"
    # Add passed arguments to pytest args
    PYTEST_ARGS+=("$@")
else
    echo "No pytest arguments provided, running all oauth tests"
fi

if [ ${#EXPANDED_TEST_PATHS[@]} -eq 0 ]; then
    echo "ERROR: No test files found matching patterns: tests/e2e/*oauth_test.py tests/e2e/rayjob/*_test.py tests/upgrade/*_test.py"
    exit 1
fi

echo "Executing: poetry run pytest ${PYTEST_ARGS[*]}"
poetry run pytest "${PYTEST_ARGS[@]}"

TEST_EXIT_CODE=$?

# ============================================================================
# Cleanup will be handled by the trap function (cleanup_on_exit)
# The trap ensures cleanup always runs, even if tests fail or script exits early
# ============================================================================
echo ""
echo "Tests completed with exit code: $TEST_EXIT_CODE"
echo ""

# Exit - the trap will handle cleanup automatically
exit $TEST_EXIT_CODE

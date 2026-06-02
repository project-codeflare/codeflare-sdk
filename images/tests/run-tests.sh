#!/bin/bash
set -e

# Preserve args for pytest parsing later (entrypoint forwards "$@").
SCRIPT_ARGS=("$@")

# v0.31-pre-upgrade: reject post_upgrade before trap/setup/cleanup.
reject_post_upgrade_marker() {
    while [ $# -gt 0 ]; do
        case "$1" in
            -m|--markers)
                if [ "${2:-}" = "post_upgrade" ]; then
                    echo "ERROR: post_upgrade tests are disabled in this branch's container image."
                    echo "       Use the 3.0+ test image tag for post_upgrade tests, or the 3.5+ test image tag for 2.x -> 3.x post_upgrade."
                    exit 1
                fi
                shift 2
                ;;
            -mpost_upgrade)
                echo "ERROR: post_upgrade tests are disabled in this branch's container image."
                echo "       Use the 3.0+ test image tag for post_upgrade tests, or the 3.5+ test image tag for 2.x -> 3.x post_upgrade."
                exit 1
                ;;
            *)
                shift
                ;;
        esac
    done
}

reject_post_upgrade_marker "${SCRIPT_ARGS[@]}"

# ============================================================================
# Cleanup function to ensure RBAC and Kueue cleanup always runs
# ============================================================================
# shellcheck disable=SC2329
cleanup_on_exit() {
    # Use TEST_EXIT_CODE if set, otherwise use the current exit code
    local exit_code=${TEST_EXIT_CODE:-$?}
    local cleanup_ran=0

    # Skip cleanup for early configuration errors (e.g. disallowed post_upgrade on this branch).
    if [ "${SKIP_CONTAINER_CLEANUP:-}" = "1" ]; then
        exit "$exit_code"
    fi

    # Only run cleanup if we've started the process (TEMP_KUBECONFIG exists)
    if [ -n "${TEMP_KUBECONFIG:-}" ] && [ -f "${TEMP_KUBECONFIG}" ]; then
        cleanup_ran=1
        echo ""
        echo "============================================================================"
        echo "Running cleanup (test exit code: $exit_code)"
        echo "============================================================================"

        # Ensure KUBECONFIG is set to temp file
        export KUBECONFIG="${TEMP_KUBECONFIG}"

        # Authenticate for cleanup based on auth method
        CLEANUP_AUTHENTICATED=false

        if [ "$AUTH_METHOD" = "legacy" ] && [ -n "${OCP_ADMIN_USER_USERNAME:-}" ] && [ -n "${OCP_ADMIN_USER_PASSWORD:-}" ] && [ -n "${OCP_API_URL:-}" ]; then
            echo "Logging in to OpenShift with OCP_ADMIN_USER for cleanup..."
            if oc login "$OCP_API_URL" \
                --username="$OCP_ADMIN_USER_USERNAME" \
                --password="$OCP_ADMIN_USER_PASSWORD" \
                --insecure-skip-tls-verify=true 2>/dev/null; then
                echo "Successfully logged in with OCP_ADMIN_USER for cleanup"
                CLEANUP_AUTHENTICATED=true
            else
                echo "WARNING: Failed to login with OCP_ADMIN_USER for cleanup"
            fi
        elif [ "$AUTH_METHOD" = "byoidc" ]; then
            echo "Using BYOIDC kubeconfig-based authentication for cleanup..."
            # Try oc whoami first, fall back to alternative verification for external OIDC clusters
            if oc whoami >/dev/null 2>&1; then
                echo "Successfully verified BYOIDC kubeconfig authentication for cleanup"
                CLEANUP_AUTHENTICATED=true
            elif oc auth can-i get namespaces 2>/dev/null | grep -q "yes"; then
                echo "Successfully verified BYOIDC authentication for cleanup (external OIDC mode)"
                CLEANUP_AUTHENTICATED=true
            else
                echo "WARNING: Cannot access cluster with BYOIDC kubeconfig for cleanup"
            fi
        else
            echo "WARNING: No valid authentication method for cleanup"
        fi

        # Perform cleanup if authenticated
        if [ "$CLEANUP_AUTHENTICATED" = "true" ]; then
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
#
# For Legacy Authentication:
#   TEST_USER_USERNAME=<username>
#   TEST_USER_PASSWORD=<password>
#   OCP_ADMIN_USER_USERNAME=<username>
#   OCP_ADMIN_USER_PASSWORD=<password>
#
# For BYOIDC Authentication:
#   CLUSTER_AUTH=oidc
#   TEST_USER_USERNAME=<odh-user*>
#   OCP_ADMIN_USER_USERNAME=byoidc-admin
#   (passwords not needed - kubeconfig-based auth)
#
# For Kubeconfig Authentication:
#   (no specific env vars needed - auto-detected)
# ============================================================================

# ============================================================================
# Debug: Check Environment Variables
# ============================================================================
echo "============================================================================"
echo "Environment Variables Debug"
echo "============================================================================"
echo "Checking required environment variables..."

# Cluster-based authentication detection (does not rely on credentials/env vars)
echo "Detecting cluster authentication type from cluster configuration..."

# Detect BYOIDC from cluster configuration alone
CLUSTER_IS_BYOIDC=false

# Method 0: Check kubeconfig exec plugin format (no API call — safe before auth setup)
# Handles clusters where the kubeconfig uses oc get-token with OIDC (e.g., PSI BYOIDC with exec plugin)
EXEC_ARGS=$(oc config view --minify -o jsonpath='{.users[0].user.exec.args}' 2>/dev/null) || true
if echo "$EXEC_ARGS" | grep -qi "oc-cli\|realms/openshift"; then
    echo "Detected BYOIDC cluster: kubeconfig uses OIDC exec plugin (oc-cli / realms/openshift)"
    CLUSTER_IS_BYOIDC=true
fi

# Method 1: Check Authentication resource type (most reliable for OIDC clusters)
# Uses timeout to avoid hanging when kubeconfig requires interactive token refresh
if [ "$CLUSTER_IS_BYOIDC" = "false" ]; then
    AUTH_TYPE=$(timeout 10 oc get authentication cluster -o jsonpath='{.spec.type}' 2>/dev/null) || true
    if [ "$AUTH_TYPE" = "OIDC" ]; then
        echo "Detected BYOIDC cluster: Authentication spec.type = OIDC"
        CLUSTER_IS_BYOIDC=true
    fi
fi

# Method 2: Check for OIDC providers in Authentication resource (fallback)
if [ "$CLUSTER_IS_BYOIDC" = "false" ]; then
    OIDC_ISSUER=$(timeout 10 oc get authentication cluster -o jsonpath='{.spec.oidcProviders[*].issuer.issuerURL}' 2>/dev/null) || true
    if [ -n "$OIDC_ISSUER" ]; then
        echo "Detected BYOIDC cluster: Authentication has oidcProviders with issuerURL: $OIDC_ISSUER"
        CLUSTER_IS_BYOIDC=true
    fi
fi

# Method 3: Check for oidcClients in Authentication status (another fallback)
if [ "$CLUSTER_IS_BYOIDC" = "false" ]; then
    if timeout 10 oc get authentication cluster -o jsonpath='{.status.oidcClients}' 2>/dev/null | grep -q "oc-cli"; then
        echo "Detected BYOIDC cluster: Authentication status has oidcClients with oc-cli"
        CLUSTER_IS_BYOIDC=true
    fi
fi

# Method 4: Check OAuth resource for openID identity provider (legacy OIDC setup)
if [ "$CLUSTER_IS_BYOIDC" = "false" ]; then
    if timeout 10 oc get oauth cluster -o jsonpath='{.spec.identityProviders[*].type}' 2>/dev/null | grep -qi "OpenID"; then
        echo "Detected BYOIDC cluster: OAuth has OpenID identity provider"
        CLUSTER_IS_BYOIDC=true
    fi
fi

# Set authentication method based purely on cluster type
if [ "$CLUSTER_IS_BYOIDC" = "true" ]; then
    AUTH_METHOD="byoidc"
    echo "Final authentication method: byoidc (cluster-based detection)"

    # For BYOIDC, use BYOIDC-specific env vars if available
    # This allows the env file to have both legacy and BYOIDC credentials
    if [ -n "${BYOIDC_TEST_USERNAME:-}" ]; then
        echo "Using BYOIDC_TEST_USERNAME instead of TEST_USER_USERNAME"
        export TEST_USER_USERNAME="$BYOIDC_TEST_USERNAME"
    fi
    if [ -n "${BYOIDC_TEST_PASSWORD:-}" ]; then
        export TEST_USER_PASSWORD="$BYOIDC_TEST_PASSWORD"
    fi
    if [ -n "${BYOIDC_ADMIN_USERNAME:-}" ]; then
        echo "Using BYOIDC_ADMIN_USERNAME instead of OCP_ADMIN_USER_USERNAME"
        export OCP_ADMIN_USER_USERNAME="$BYOIDC_ADMIN_USERNAME"
    fi
    if [ -n "${BYOIDC_ADMIN_PASSWORD:-}" ]; then
        export OCP_ADMIN_USER_PASSWORD="$BYOIDC_ADMIN_PASSWORD"
    fi
else
    AUTH_METHOD="legacy"
    echo "Final authentication method: legacy (standard OAuth/HTPasswd/LDAP)"
fi

# Debug: Print relevant environment variables
echo ""
echo "Environment variables (after BYOIDC override if applicable):"
echo "  OCP_ADMIN_USER_USERNAME: ${OCP_ADMIN_USER_USERNAME:-[NOT SET]}"
echo "  TEST_USER_USERNAME: ${TEST_USER_USERNAME:-[NOT SET]}"
if [ "$AUTH_METHOD" = "byoidc" ]; then
    echo "  (Original BYOIDC_TEST_USERNAME: ${BYOIDC_TEST_USERNAME:-[NOT SET]})"
    echo "  (Original BYOIDC_ADMIN_USERNAME: ${BYOIDC_ADMIN_USERNAME:-[NOT SET]})"
fi

# Check required variables based on authentication method
MISSING_VARS=()
if [ "$AUTH_METHOD" = "legacy" ]; then
    echo ""
    echo "Checking required variables for legacy authentication..."
    REQUIRED_VARS=(
        "TEST_USER_USERNAME"
        "TEST_USER_PASSWORD"
        "OCP_ADMIN_USER_USERNAME"
        "OCP_ADMIN_USER_PASSWORD"
    )

    for var in "${REQUIRED_VARS[@]}"; do
        if [ -n "${!var}" ]; then
            echo "  ✓ $var: [SET]"
        else
            echo "  ✗ $var: [NOT SET]"
            MISSING_VARS+=("$var")
        fi
    done

elif [ "$AUTH_METHOD" = "byoidc" ]; then
    echo ""
    echo "Checking configuration for BYOIDC authentication..."
    echo "  ✓ Authentication will use the mounted kubeconfig (no oc login needed)"

    # For BYOIDC, we need TEST_USER_USERNAME for RBAC policies
    if [ -n "${TEST_USER_USERNAME}" ]; then
        echo "  ✓ TEST_USER_USERNAME: ${TEST_USER_USERNAME} (for RBAC policies)"
    else
        echo "  ✗ TEST_USER_USERNAME: Not set (required for RBAC policies)"
        MISSING_VARS+=("TEST_USER_USERNAME")
    fi

    # Detect kubeconfig format (conversion will happen later on writable kubeconfig)
    AUTH_PROVIDER_TOKEN=$(oc config view --minify -o jsonpath='{.users[0].user.auth-provider.config.id-token}' 2>/dev/null)
    DIRECT_TOKEN=$(oc config view --minify -o jsonpath='{.users[0].user.token}' 2>/dev/null)
    HAS_EXEC_PLUGIN=$(oc config view --minify -o jsonpath='{.users[0].user.exec.command}' 2>/dev/null)

    if [ -n "$DIRECT_TOKEN" ]; then
        echo "  ✓ Kubeconfig has a direct token"
    elif [ -n "$AUTH_PROVIDER_TOKEN" ]; then
        echo "  ℹ️  Kubeconfig uses auth-provider (OIDC) format - will convert to token"
    elif [ -n "$HAS_EXEC_PLUGIN" ]; then
        echo "  ⚠️  Kubeconfig uses exec plugin ($HAS_EXEC_PLUGIN) - will attempt conversion"
    else
        echo "  ⚠️  Unknown kubeconfig authentication format"
    fi

    echo "  ℹ️  Kubeconfig authentication will be verified after temp kubeconfig is created"
fi

echo ""
if [ ${#MISSING_VARS[@]} -gt 0 ]; then
    echo "ERROR: The following required environment variables are not set or invalid for $AUTH_METHOD authentication:"
    for var in "${MISSING_VARS[@]}"; do
        echo "  - $var"
    done
    echo ""
    exit 1
else
    echo "All required environment variables are set for $AUTH_METHOD authentication."
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
# Use timeout to avoid hanging when kubeconfig uses an exec plugin (e.g., BYOIDC with oc get-token)
OCP_API_URL=$(timeout 10 oc whoami --show-server 2>/dev/null) || true

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
# Authentication Setup for RBAC Application
# ============================================================================
echo "Setting up authentication for RBAC policies..."

# Save original kubeconfig directory for token cache lookup later
ORIGINAL_KUBE_DIR=$(dirname "${KUBECONFIG:-/codeflare-sdk/tests/.kube/config}")

# Create a temporary kubeconfig (since the mounted one is read-only)
TEMP_KUBECONFIG="/tmp/kubeconfig-$$"
cp "${KUBECONFIG}" "${TEMP_KUBECONFIG}" 2>/dev/null || {
    echo "WARNING: Could not copy kubeconfig, creating new one"
    touch "${TEMP_KUBECONFIG}"
}
export KUBECONFIG="${TEMP_KUBECONFIG}"

# Create ~/.kube directory and copy config
mkdir -p ~/.kube
cp "${TEMP_KUBECONFIG}" ~/.kube/config || {
    echo "WARNING: Could not copy kubeconfig to ~/.kube/config"
}

if [ "$AUTH_METHOD" = "legacy" ]; then
    echo "Using legacy authentication with username/password..."
    if [ -z "$OCP_ADMIN_USER_USERNAME" ] || [ -z "$OCP_ADMIN_USER_PASSWORD" ]; then
        echo "ERROR: OCP_ADMIN_USER credentials not found in environment (required for legacy auth)"
        exit 1
    fi

    echo "Logging in to OpenShift with OCP_ADMIN_USER..."
    oc login "$OCP_API_URL" \
        --username="$OCP_ADMIN_USER_USERNAME" \
        --password="$OCP_ADMIN_USER_PASSWORD" \
        --insecure-skip-tls-verify=true || {
        echo "ERROR: Failed to login with OCP_ADMIN_USER"
        rm -f "${TEMP_KUBECONFIG}"
        exit 1
    }

    # Update ~/.kube/config after login
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

    echo "✅ Successfully logged in with legacy authentication (user: $CURRENT_USER)"

elif [ "$AUTH_METHOD" = "byoidc" ]; then
    echo "Using BYOIDC authentication (kubeconfig-based, no oc login needed)..."

    # Extract and convert token if needed (now working on writable temp kubeconfig)
    KUBECONFIG_TOKEN=""
    NEEDS_CONVERSION=false

    # Check for auth-provider format (Jenkins uses kubectl config set-credentials --auth-provider=oidc)
    AUTH_PROVIDER_TOKEN=$(oc config view --minify -o jsonpath='{.users[0].user.auth-provider.config.id-token}' 2>/dev/null)
    if [ -n "$AUTH_PROVIDER_TOKEN" ]; then
        echo "Detected auth-provider (OIDC) format, extracting id-token..."
        KUBECONFIG_TOKEN="$AUTH_PROVIDER_TOKEN"
        NEEDS_CONVERSION=true
    fi

    # Allow a pre-extracted token to be injected via BYOIDC_ADMIN_TOKEN env var.
    # Useful for local runs on BYOIDC clusters where the exec plugin can't run
    # inside the container (no token cache, no browser).
    # Obtain it on the host: python3 -c "import json,glob,os; [print(json.load(open(f))['id_token']) for f in glob.glob(os.path.expanduser('~/.kube/cache/oc/*')) if 'id_token' in json.load(open(f))]" | head -1
    if [ -z "$KUBECONFIG_TOKEN" ] && [ -n "${BYOIDC_ADMIN_TOKEN:-}" ]; then
        echo "Using pre-extracted token from BYOIDC_ADMIN_TOKEN"
        KUBECONFIG_TOKEN="$BYOIDC_ADMIN_TOKEN"
        NEEDS_CONVERSION=true
    fi

    # Check for exec plugin format (oc-oidc plugin)
    if [ -z "$KUBECONFIG_TOKEN" ]; then
        HAS_EXEC_PLUGIN=$(oc config view --minify -o jsonpath='{.users[0].user.exec.command}' 2>/dev/null)
        if [ -n "$HAS_EXEC_PLUGIN" ]; then
            echo "Detected exec-plugin format ($HAS_EXEC_PLUGIN), searching for cached token..."

            # Check oc's built-in token cache (~/.kube/cache/oc/<hash> JSON files).
            # oc stores tokens at <kube-dir>/cache/oc/<hash> where <kube-dir> is the
            # directory containing the kubeconfig. This is populated when ~/.kube/ is
            # mounted into the container (not just ~/.kube/config).
            OC_CACHE_DIR="${ORIGINAL_KUBE_DIR}/cache/oc"
            if [ -z "$KUBECONFIG_TOKEN" ] && [ -d "$OC_CACHE_DIR" ]; then
                for cache_file in "$OC_CACHE_DIR"/*; do
                    if [ -f "$cache_file" ]; then
                        TOKEN=$(grep -o '"id_token":"[^"]*"' "$cache_file" 2>/dev/null | head -1 | cut -d'"' -f4)
                        if [ -n "$TOKEN" ]; then
                            KUBECONFIG_TOKEN="$TOKEN"
                            echo "Found cached OIDC token in oc cache: $(basename "$cache_file")"
                            break
                        fi
                    fi
                done
            fi

            # Also check legacy oidc-login cache location
            if [ -z "$KUBECONFIG_TOKEN" ] && [ -f ~/.kube/oidc-login.cache ]; then
                KUBECONFIG_TOKEN=$(cat ~/.kube/oidc-login.cache 2>/dev/null | grep -o '"id_token":"[^"]*"' | cut -d'"' -f4)
            fi

            # Last resort: try running the exec plugin directly to get a fresh token.
            # Works when oc can refresh the token non-interactively (e.g. valid refresh_token
            # is in the cache AND the cache directory is mounted into the container).
            if [ -z "$KUBECONFIG_TOKEN" ]; then
                echo "No cached token found, attempting to run exec plugin directly..."
                mapfile -t EXEC_PLUGIN_ARGS < <(oc config view --minify -o jsonpath='{range .users[0].user.exec.args[*]}{@}{"\n"}{end}' 2>/dev/null)
                if [ ${#EXEC_PLUGIN_ARGS[@]} -gt 0 ]; then
                    EXEC_OUTPUT=$(timeout 30 "$HAS_EXEC_PLUGIN" "${EXEC_PLUGIN_ARGS[@]}" 2>/dev/null) || true
                    if [ -n "$EXEC_OUTPUT" ]; then
                        KUBECONFIG_TOKEN=$(echo "$EXEC_OUTPUT" | grep -o '"token":"[^"]*"' | head -1 | cut -d'"' -f4)
                        [ -n "$KUBECONFIG_TOKEN" ] && echo "Obtained token from exec plugin"
                    fi
                fi
            fi

            if [ -n "$KUBECONFIG_TOKEN" ]; then
                NEEDS_CONVERSION=true
            else
                # No cached token found. Use the same approach as Jenkins loginByoidcUser:
                # call Keycloak's token endpoint directly with grant_type=password, then
                # inject id-token + refresh-token into the kubeconfig via auth-provider.
                # The OIDC issuer URL and client ID are already in the exec plugin args.
                if [ -n "${OCP_ADMIN_USER_USERNAME:-}" ] && [ -n "${OCP_ADMIN_USER_PASSWORD:-}" ]; then
                    echo "Attempting Keycloak password grant (same method as Jenkins loginByoidcUser)..."

                    # Extract issuer URL and client ID directly from exec plugin args in kubeconfig
                    OIDC_ISSUER=$(oc config view --minify \
                        -o jsonpath='{range .users[0].user.exec.args[*]}{@}{"\n"}{end}' 2>/dev/null \
                        | grep -- '--issuer-url=' | sed 's/--issuer-url=//' | tr -d '[:space:]')
                    OIDC_CLIENT_ID=$(oc config view --minify \
                        -o jsonpath='{range .users[0].user.exec.args[*]}{@}{"\n"}{end}' 2>/dev/null \
                        | grep -- '--client-id=' | sed 's/--client-id=//' | tr -d '[:space:]')

                    # Allow env overrides (consistent with Jenkins configData fields)
                    OIDC_ISSUER="${CLUSTER_OIDC_ISSUER:-$OIDC_ISSUER}"
                    OIDC_CLIENT_ID="${CLIENT_ID_OC_CLI:-${OIDC_CLIENT_ID:-oc-cli}}"
                    OIDC_TOKEN_ENDPOINT="${CLUSTER_OIDC_TOKEN_ENDPOINT:-${OIDC_ISSUER}/protocol/openid-connect/token}"

                    if [ -n "$OIDC_ISSUER" ]; then
                        echo "  OIDC issuer: $OIDC_ISSUER"
                        echo "  Admin user:  $OCP_ADMIN_USER_USERNAME"

                        # Use OIDC well-known discovery to find the correct token endpoint
                        # (mirrors opendatahub-tests get_oidc_token_endpoint())
                        if [ -z "${CLUSTER_OIDC_TOKEN_ENDPOINT:-}" ]; then
                            WELL_KNOWN=$(curl -sk --max-time 10 "${OIDC_ISSUER}/.well-known/openid-configuration" 2>/dev/null) || true
                            if [ -n "$WELL_KNOWN" ]; then
                                DISCOVERED_ENDPOINT=$(echo "$WELL_KNOWN" | python3 -c \
                                    "import json,sys; print(json.load(sys.stdin).get('token_endpoint',''))" \
                                    2>/dev/null || true)
                                [ -n "$DISCOVERED_ENDPOINT" ] && OIDC_TOKEN_ENDPOINT="$DISCOVERED_ENDPOINT"
                            fi
                        fi
                        echo "  Token endpoint: $OIDC_TOKEN_ENDPOINT"

                        # mirrors Jenkins loginByoidcUser / opendatahub-tests get_oidc_tokens():
                        # --data-urlencode safely handles special characters in credentials.
                        # scope matches Jenkins OIDC_LOGIN_SCOPE (default "openid").
                        OIDC_SCOPE="${OIDC_LOGIN_SCOPE:-openid}"
                        TOKENS=$(curl -sk -L -X POST "$OIDC_TOKEN_ENDPOINT" \
                            -H "Content-Type: application/x-www-form-urlencoded" \
                            -H "User-Agent: python-requests" \
                            --data-urlencode "username=${OCP_ADMIN_USER_USERNAME}" \
                            --data-urlencode "password=${OCP_ADMIN_USER_PASSWORD}" \
                            -d "grant_type=password" \
                            -d "client_id=${OIDC_CLIENT_ID}" \
                            -d "scope=${OIDC_SCOPE}" 2>/dev/null) || true

                        if [ -n "$TOKENS" ]; then
                            ID_TOKEN=$(echo "$TOKENS" | python3 -c \
                                "import json,sys; print(json.load(sys.stdin).get('id_token',''))" \
                                2>/dev/null || echo "$TOKENS" | grep -o '"id_token":"[^"]*"' | cut -d'"' -f4)
                            REFRESH_TOKEN_VAL=$(echo "$TOKENS" | python3 -c \
                                "import json,sys; print(json.load(sys.stdin).get('refresh_token',''))" \
                                2>/dev/null || echo "$TOKENS" | grep -o '"refresh_token":"[^"]*"' | cut -d'"' -f4)

                            if [ -n "$ID_TOKEN" ] && [ "$ID_TOKEN" != "None" ] && [ "$ID_TOKEN" != "" ]; then
                                # Inject tokens into kubeconfig using auth-provider format
                                # (identical to Jenkins loginByoidcUser kubectl config set-credentials call)
                                oc config set-credentials "${OCP_ADMIN_USER_USERNAME}" \
                                    --auth-provider=oidc \
                                    --auth-provider-arg=idp-issuer-url="${OIDC_ISSUER}" \
                                    --auth-provider-arg=client-id="${OIDC_CLIENT_ID}" \
                                    --auth-provider-arg=client-secret="" \
                                    --auth-provider-arg=refresh-token="${REFRESH_TOKEN_VAL}" \
                                    --auth-provider-arg=id-token="${ID_TOKEN}" 2>/dev/null
                                oc config set-context --current --user="${OCP_ADMIN_USER_USERNAME}" 2>/dev/null
                                cp "${TEMP_KUBECONFIG}" ~/.kube/config 2>/dev/null || true
                                echo "  ✓ Kubeconfig updated with Keycloak id-token + refresh-token"
                                KUBECONFIG_TOKEN="$ID_TOKEN"
                                NEEDS_CONVERSION=false
                            else
                                ERR=$(echo "$TOKENS" | python3 -c \
                                    "import json,sys; d=json.load(sys.stdin); print(d.get('error','?') + ': ' + d.get('error_description',''))" \
                                    2>/dev/null || echo "$TOKENS" | head -c 200)
                                echo "  WARNING: Keycloak token request failed: $ERR"
                                echo "  Falling back to kubeconfig exec plugin as-is"
                            fi
                        else
                            echo "  WARNING: No response from Keycloak token endpoint"
                        fi
                    else
                        echo "  WARNING: Could not determine OIDC issuer from exec plugin args"
                    fi
                fi

                if [ -z "$KUBECONFIG_TOKEN" ]; then
                    # Last resort: use kubeconfig with exec plugin as-is.
                    # When running interactively (-it), oc get-token may prompt for device/browser auth.
                    echo "Using kubeconfig with exec plugin as-is (no static token conversion)"
                    echo "oc commands will invoke the exec plugin to authenticate when needed"
                fi
            fi
        fi
    fi

    # Check if we already have a direct token
    if [ -z "$KUBECONFIG_TOKEN" ]; then
        DIRECT_TOKEN=$(oc config view --minify -o jsonpath='{.users[0].user.token}' 2>/dev/null)
        if [ -n "$DIRECT_TOKEN" ]; then
            echo "Kubeconfig already has a direct token"
            KUBECONFIG_TOKEN="$DIRECT_TOKEN"
            NEEDS_CONVERSION=false
        fi
    fi

    # Convert to simple token-based authentication if needed
    if [ "$NEEDS_CONVERSION" = true ]; then
        if [ -n "$KUBECONFIG_TOKEN" ]; then
            echo "Converting to token-based authentication..."
            # Debug: show token length (not the token itself)
            echo "  Token length: ${#KUBECONFIG_TOKEN} characters"

            # Try to decode JWT and check expiration (if base64 and jq available)
            if command -v base64 >/dev/null 2>&1; then
                # JWT has 3 parts separated by dots, payload is the 2nd part
                JWT_PAYLOAD=$(echo "$KUBECONFIG_TOKEN" | cut -d. -f2 2>/dev/null)
                if [ -n "$JWT_PAYLOAD" ]; then
                    # Add padding if needed
                    PADDING=$((4 - ${#JWT_PAYLOAD} % 4))
                    if [ $PADDING -ne 4 ]; then
                        JWT_PAYLOAD="${JWT_PAYLOAD}$(printf '=%.0s' $(seq 1 $PADDING))"
                    fi
                    # Try to decode and extract exp
                    DECODED=$(echo "$JWT_PAYLOAD" | base64 -d 2>/dev/null || true)
                    if [ -n "$DECODED" ]; then
                        EXP=$(echo "$DECODED" | grep -o '"exp":[0-9]*' | cut -d: -f2 2>/dev/null || true)
                        if [ -n "$EXP" ]; then
                            NOW=$(date +%s)
                            if [ "$EXP" -lt "$NOW" ]; then
                                echo "  ⚠️  WARNING: Token appears to be EXPIRED (exp: $EXP, now: $NOW)"
                                EXPIRES_AGO=$((NOW - EXP))
                                echo "  Token expired $EXPIRES_AGO seconds ago"
                            else
                                EXPIRES_IN=$((EXP - NOW))
                                echo "  ✓ Token expires in $EXPIRES_IN seconds"
                            fi
                        fi
                    fi
                fi
            fi

            oc config set-credentials byoidc-user --token="$KUBECONFIG_TOKEN" 2>/dev/null
            oc config set-context --current --user=byoidc-user 2>/dev/null
            # Update ~/.kube/config after conversion
            cp "${TEMP_KUBECONFIG}" ~/.kube/config 2>/dev/null || true
            echo "✓ Converted to token-based authentication"
        fi
    fi

    # Verify we can access the cluster with the kubeconfig
    # Note: On some BYOIDC clusters (external OIDC mode), oc whoami doesn't work
    # because users.user.openshift.io resource doesn't exist.
    # We use alternative methods to verify authentication.
    echo "Verifying cluster access..."

    CURRENT_USER=""
    WHOAMI_OUTPUT=$(oc whoami 2>&1) || true

    # Check if oc whoami worked
    if ! echo "$WHOAMI_OUTPUT" | grep -qi "error\|unauthorized\|forbidden\|notfound"; then
        CURRENT_USER="$WHOAMI_OUTPUT"
        echo "User identified via oc whoami: $CURRENT_USER"
    else
        # oc whoami failed - this can happen on external OIDC clusters
        # Try alternative verification methods
        echo "Note: oc whoami not available on this cluster (external OIDC mode)"
        echo "Using alternative authentication verification..."

        # Method 1: Raw connectivity check — /version is unauthenticated, avoids exec plugin
        if [ -n "${OCP_API_URL:-}" ] && \
           curl -sk --max-time 10 "${OCP_API_URL}/version" 2>/dev/null | grep -q '"major"'; then
            echo "  ✓ API server connectivity verified (unauthenticated /version endpoint)"
        elif [ -z "$KUBECONFIG_TOKEN" ]; then
            # No static token — exec plugin as-is; connectivity may still work through Python client.
            # Don't abort: the Python kubernetes client handles exec plugins in-process and may succeed.
            echo "  WARNING: Could not verify API connectivity via /version (exec plugin as-is mode)"
            echo "  Tests will attempt to run; Python's kubernetes client invokes the exec plugin natively."
            echo "  If tests fail with 401, ensure BYOIDC_ADMIN_PASSWORD is correct in your env file,"
            echo "  or extract the id_token from the oc cache on your host and set BYOIDC_ADMIN_TOKEN:"
            echo "    python3 -c \"import json,glob,os; [print(json.load(open(f))['id_token']) for f in glob.glob(os.path.expanduser('~/.kube/cache/oc/*')) if 'id_token' in json.load(open(f))]\" | head -1"
        else
            echo "ERROR: Cannot connect to API server at ${OCP_API_URL:-[not set]}"
            rm -f "${TEMP_KUBECONFIG}"
            exit 1
        fi

        # Method 2: Check if we can perform basic API calls (requires valid token)
        if oc auth can-i get namespaces 2>/dev/null | grep -q "yes"; then
            echo "  ✓ Authentication verified (can get namespaces)"
        else
            echo "  WARNING: Cannot verify API authentication via oc auth can-i"
            echo "  This is expected when the exec plugin is used without a cached token."
        fi

        # Method 3: Try to extract username from token (JWT sub claim)
        if [ -n "$KUBECONFIG_TOKEN" ]; then
            JWT_PAYLOAD=$(echo "$KUBECONFIG_TOKEN" | cut -d. -f2 2>/dev/null)
            if [ -n "$JWT_PAYLOAD" ]; then
                PADDING=$((4 - ${#JWT_PAYLOAD} % 4))
                if [ $PADDING -ne 4 ]; then
                    JWT_PAYLOAD="${JWT_PAYLOAD}$(printf '=%.0s' $(seq 1 $PADDING))"
                fi
                DECODED=$(echo "$JWT_PAYLOAD" | base64 -d 2>/dev/null || true)
                if [ -n "$DECODED" ]; then
                    # Try to extract preferred_username or sub
                    CURRENT_USER=$(echo "$DECODED" | grep -o '"preferred_username":"[^"]*"' | cut -d'"' -f4 2>/dev/null || true)
                    if [ -z "$CURRENT_USER" ]; then
                        CURRENT_USER=$(echo "$DECODED" | grep -o '"sub":"[^"]*"' | cut -d'"' -f4 2>/dev/null || true)
                    fi
                fi
            fi
        fi

        if [ -z "$CURRENT_USER" ]; then
            CURRENT_USER="byoidc-authenticated-user"
            echo "  ℹ️  Could not extract username from token, using placeholder"
        else
            echo "  ✓ User identified from token: $CURRENT_USER"
        fi
    fi

    echo "Current authenticated user: $CURRENT_USER"

    # Verify admin permissions by trying to list cluster roles
    if ! oc get clusterroles >/dev/null 2>&1; then
        echo "ERROR: Current user ($CURRENT_USER) does not have cluster admin permissions required for RBAC setup"
        echo "Please ensure the kubeconfig is configured with a user that has cluster-admin role"
        rm -f "${TEMP_KUBECONFIG}"
        exit 1
    fi

    echo "✅ Verified BYOIDC authentication and cluster admin permissions (user: $CURRENT_USER)"
fi

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
CURRENT_USER=$(oc whoami 2>/dev/null) || true
if [ "$AUTH_METHOD" = "legacy" ]; then
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
elif [ "$AUTH_METHOD" = "byoidc" ] || [ "$AUTH_METHOD" = "kubeconfig" ]; then
    # For BYOIDC/external OIDC, oc whoami might not work - use alternative verification
    if [ -z "$CURRENT_USER" ]; then
        # Try alternative: check if we can access the API
        if oc auth can-i get namespaces 2>/dev/null | grep -q "yes"; then
            CURRENT_USER="byoidc-authenticated-user"
            echo "Verified kubeconfig authentication (external OIDC mode)"
        else
            echo "ERROR: Not authenticated with kubeconfig"
            rm -f "$RBAC_TEMP_FILE"
            exit 1
        fi
    else
        echo "Verified kubeconfig authentication (current user: $CURRENT_USER)"
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
# Setup Test User Authentication
# ============================================================================
if [ "$AUTH_METHOD" = "legacy" ]; then
    echo "Setting up legacy test user authentication..."
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

    # Update ~/.kube/config after test user login
    cp "${TEMP_KUBECONFIG}" ~/.kube/config || {
        echo "WARNING: Could not update ~/.kube/config after test user login"
    }

    echo "✅ Successfully logged in with legacy test user"

elif [ "$AUTH_METHOD" = "byoidc" ]; then
    echo "Using BYOIDC authentication for tests..."

    # For BYOIDC, we continue using the kubeconfig authentication
    # The tests will use the already-authenticated user from kubeconfig
    # On external OIDC clusters, oc whoami might not work
    CURRENT_USER=$(oc whoami 2>/dev/null) || true
    if [ -z "$CURRENT_USER" ]; then
        # Try alternative verification for external OIDC clusters
        if oc auth can-i get namespaces 2>/dev/null | grep -q "yes"; then
            CURRENT_USER="byoidc-authenticated-user"
        else
            echo "ERROR: Lost cluster access during test setup"
            rm -f "${TEMP_KUBECONFIG}"
            exit 1
        fi
    fi

    echo "✅ Using BYOIDC authenticated user for tests (current user: $CURRENT_USER)"
    echo "   RBAC policies have been applied for TEST_USER_USERNAME: $TEST_USER_USERNAME"
fi

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
    "--junitxml=/codeflare-sdk/tests/results/results_xunit.xml"
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

# v0.31-pre-upgrade branch: post_upgrade runs on the 3.x image only.
# Pytest 7.x uses the last -m when multiple are passed, so use one combined expression.
PYTEST_MARKER="pre_upgrade and not post_upgrade"
FORWARD_ARGS=()

set -- "${SCRIPT_ARGS[@]}"
while [ $# -gt 0 ]; do
    case "$1" in
        -m|--markers)
            if [ -z "${2:-}" ]; then
                echo "ERROR: -m requires a marker expression"
                export SKIP_CONTAINER_CLEANUP=1
                exit 1
            fi
            PYTEST_MARKER="$2 and not post_upgrade"
            shift 2
            ;;
        *)
            FORWARD_ARGS+=("$1")
            shift
            ;;
    esac
done

if [ ${#FORWARD_ARGS[@]} -gt 0 ]; then
    echo "Received pytest arguments: ${FORWARD_ARGS[*]} -m ${PYTEST_MARKER}"
    PYTEST_ARGS+=("${FORWARD_ARGS[@]}")
else
    echo "No pytest arguments provided, using marker expression: ${PYTEST_MARKER}"
fi
PYTEST_ARGS+=("-m" "${PYTEST_MARKER}")

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

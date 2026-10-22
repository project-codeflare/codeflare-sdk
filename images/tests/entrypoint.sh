#!/bin/sh
# Entrypoint script that handles -- separator in podman commands
# Passes all arguments to run-tests.sh which will forward them to pytest

# Shift-left Jenkins runs this image as the agent uid (--userns=keep-id --user <uid>).
# The tree under /codeflare-sdk is root-owned; SDK writes ~/.codeflare and pytest uses a cache dir.
export HOME="${CODEFLARE_TEST_HOME:-/tmp/codeflare-test-home}"
export PYTEST_CACHE_DIR="${PYTEST_CACHE_DIR:-/tmp/pytest-cache}"
export TMPDIR="${TMPDIR:-${HOME}/tmp}"
mkdir -p \
    "${HOME}/.codeflare/resources" \
    "${PYTEST_CACHE_DIR}" \
    "${TMPDIR}" \
    "${HOME}/.kube"

exec /codeflare-sdk/run-tests.sh "$@"

# Multi-stage build for Python tests with oc CLI
FROM python:3.12-slim AS builder

# Install system dependencies needed for building
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
ENV POETRY_VERSION=1.8.3 \
    POETRY_HOME="/opt/poetry" \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    POETRY_NO_INTERACTION=1 \
    POETRY_CACHE_DIR=/tmp/poetry_cache

ENV PATH="$POETRY_HOME/bin:$PATH"

RUN pip install --no-cache-dir "poetry==$POETRY_VERSION"

# ============================================================================
# Base Directory: /codeflare-sdk
# This is the root directory where all project files will be located.
# Similar to kuberay structure, all source code and tests are under /codeflare-sdk
# ============================================================================
WORKDIR /codeflare-sdk

# Copy dependency files
COPY pyproject.toml poetry.lock* ./

# Install dependencies (including test dependencies)
RUN poetry install --no-root --with test && rm -rf $POETRY_CACHE_DIR

# Runtime stage
FROM python:3.12-slim

# Install system dependencies for runtime including Chrome for Selenium tests
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    wget \
    gnupg \
    && wget -q -O /tmp/google-chrome-key.pub https://dl-ssl.google.com/linux/linux_signing_key.pub \
    && gpg --dearmor -o /usr/share/keyrings/google-chrome-keyring.gpg /tmp/google-chrome-key.pub \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome-keyring.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
    google-chrome-stable \
    && rm -rf /var/lib/apt/lists/* /tmp/google-chrome-key.pub

# Install OpenShift CLI (oc)
RUN curl -L https://mirror.openshift.com/pub/openshift-v4/clients/oc/latest/linux/oc.tar.gz | \
    tar -xz -C /usr/local/bin && \
    chmod +x /usr/local/bin/oc && \
    oc version --client

# Install Poetry for runtime (needed for poetry run command)
ENV POETRY_VERSION=1.8.3 \
    POETRY_HOME="/opt/poetry" \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    POETRY_NO_INTERACTION=1

ENV PATH="$POETRY_HOME/bin:/codeflare-sdk/.venv/bin:$PATH"

RUN pip install --no-cache-dir "poetry==$POETRY_VERSION"

# ============================================================================
# Base Directory: /codeflare-sdk
# This is the root directory where all project files will be located.
# Similar to kuberay structure, all source code and tests are under /codeflare-sdk
# ============================================================================
WORKDIR /codeflare-sdk

# Copy virtual environment from builder
COPY --from=builder /codeflare-sdk/.venv /codeflare-sdk/.venv

# Copy project files
COPY pyproject.toml poetry.lock* ./
COPY README.md ./
COPY src/ ./src/
COPY tests/ ./tests/

# Copy test runner script, entrypoint, and RBAC file
COPY images/tests/run-tests.sh /codeflare-sdk/run-tests.sh
COPY images/tests/entrypoint.sh /codeflare-sdk/entrypoint.sh
COPY images/tests/rbac-test-user-permissions.yaml /codeflare-sdk/images/tests/rbac-test-user-permissions.yaml
RUN chmod +x /codeflare-sdk/run-tests.sh /codeflare-sdk/entrypoint.sh

# Install the codeflare_sdk package in editable mode so it can be imported
# This is needed because we used --no-root in the builder stage
WORKDIR /codeflare-sdk
RUN /codeflare-sdk/.venv/bin/pip install -e .

# ============================================================================
# Working Directory: /codeflare-sdk
# Tests expect to run from the project root so relative paths like ./tests/e2e/ work correctly
# ============================================================================
WORKDIR /codeflare-sdk

ENV KUBECONFIG=/codeflare-sdk/tests/.kube/config

# ============================================================================
# Test Results Directory: /codeflare-sdk/tests/results
# This directory will contain pytest output files (JUnit XML, coverage, etc.)
# Mount this as a volume when running the container to access test results
# ============================================================================
RUN mkdir -p /codeflare-sdk/tests/results

# ============================================================================
# Environment File Setup
# The containerEnvFile should be passed via --env-file parameter when running
# the container. Expected environment variables:
#   TEST_USER_USERNAME, TEST_USER_PASSWORD
#   OCP_ADMIN_USER_USERNAME, OCP_ADMIN_USER_PASSWORD
# Example: podman run --env-file containerEnvFile codeflare-sdk-tests
# ============================================================================

# ============================================================================
# Default Command (can be overridden when running the container)
# This CMD runs the test wrapper script which handles:
# - Extracting OpenShift API URL from kubeconfig
# - Applying RBAC policies
# - Logging in with TEST_USER
# - Running tests
# - Logging in with OCP_ADMIN_USER after tests
# - Cleaning up RBAC
# To override it, just provide your command after the image name:
#   podman run --env-file containerEnvFile codeflare-sdk-tests poetry run pytest tests/e2e/specific_test.py
# ============================================================================
# Set entrypoint to handle -- separator arguments
ENTRYPOINT ["/codeflare-sdk/entrypoint.sh"]
# Default command (can be overridden, but entrypoint will handle it)
CMD []

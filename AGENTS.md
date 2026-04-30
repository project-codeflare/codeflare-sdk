# AGENTS.md - CodeFlare SDK

Instructions for AI coding agents working on this codebase.

## Quick Reference

```bash
# Setup
poetry install --with test,dev        # Install all dependencies
pre-commit install                     # Enable pre-commit hooks

# Development
black <file>                           # Format a file
black --check .                        # Check formatting

# Testing
pytest -v src/codeflare_sdk           # Run all unit tests
pytest -v src/codeflare_sdk/path/to/test_file.py  # Run specific test
coverage run --omit="src/**/test_*.py,src/codeflare_sdk/common/utils/unit_test_support.py,src/codeflare_sdk/vendored/**" -m pytest
coverage report -m                     # View coverage report (must be >= 90%)
```

## General Rules

- **Python ^3.11** is required. Do not use features removed in 3.11+ or syntax unavailable before 3.11.
- **Poetry** is the package manager. Never use `pip install` for dependency management -- use `poetry add` or edit `pyproject.toml`.
- **Do not modify** anything under `src/codeflare_sdk/vendored/`. This is a vendored copy of the KubeRay Python client.
- Always run `black` on changed files before committing. The project enforces formatting via pre-commit hooks.
- Maintain **>= 90% test coverage**. All new code must have unit tests.
- Do not commit secrets, credentials, or `.env` files.

## Project Structure

```
src/codeflare_sdk/
  __init__.py              # Public API exports -- update when adding public classes/functions
  conftest.py              # Global test fixtures (auto-mocks K8s API clients)
  common/
    kubernetes_cluster/    # Auth, API client management, error handling
    kueue/                 # Kueue local queue listing and default queue resolution
    utils/                 # Constants, helpers, validation, cert generation
    widgets/               # Jupyter/IPython widgets for cluster management
  ray/
    cluster/               # Cluster creation, config, status, deletion (main entry point)
    rayjobs/               # RayJob submission, tracking, runtime env management
    client/                # Thin wrapper around Ray's JobSubmissionClient
  vendored/                # DO NOT MODIFY -- vendored KubeRay Python client
tests/
  e2e/                     # End-to-end tests (require KinD + Kueue + KubeRay)
  e2e_v2/                  # Newer e2e test suite
```

## Code Conventions

### Style
- Use **type hints** on all function signatures and return types.
- Use **dataclasses** (not plain dicts) for configuration and structured data.
- Use **Enums** for state/status values.
- Use **relative imports** within the `codeflare_sdk` package (e.g., `from ...common.utils import ...`).
- Follow existing patterns -- check neighboring files before introducing new patterns.

### Deprecation
- Use the `@deprecated` decorator from `typing_extensions` for deprecated classes/functions.
- Also emit `warnings.warn(..., DeprecationWarning, stacklevel=2)` in `__init__` for deprecated classes.

### Error Handling
- Use `_kube_api_error_handling()` in `common/kubernetes_cluster/kube_api_helpers.py` for Kubernetes API errors.
- Provide user-friendly error messages -- the SDK targets data scientists who may not know Kubernetes internals.

### Naming
- Cluster names must follow RFC 1123 subdomain format (lowercase, alphanumeric, hyphens).
- Test files: `test_<module>.py`, colocated with source files under `src/`.
- Constants go in `common/utils/constants.py`.

## Testing

### Running Tests
```bash
poetry install --with test
pytest -v src/codeflare_sdk
```

### Writing Tests
- Place unit tests alongside source: `src/codeflare_sdk/<module>/test_<name>.py`
- The global `conftest.py` at `src/codeflare_sdk/conftest.py` auto-mocks Kubernetes API clients. Your tests inherit these mocks automatically.
- To test specific Kubernetes config behavior, override mocks locally with `monkeypatch`.
- Use `pytest-mock` (`mocker` fixture) for mocking.
- Mark tests with appropriate markers: `@pytest.mark.kind`, `@pytest.mark.openshift`, `@pytest.mark.smoke`, `@pytest.mark.tier1`, `@pytest.mark.ui`.
- E2E tests go in `tests/e2e/` or `tests/e2e_v2/`, not in `src/`.
- Never make real Kubernetes API calls in unit tests.

### Coverage
- CI enforces >= 90% coverage on the `src/codeflare_sdk` directory.
- Use `# pragma: no cover` sparingly and only for cleanup/teardown code that can't be reliably tested.
- Vendored code is excluded from coverage.

## Architecture

### Public API
All public exports are defined in `src/codeflare_sdk/__init__.py`. When adding new public classes or functions, export them there.

### Key Modules
- **`ray/cluster/`** -- Cluster creation, configuration, status, and deletion. `Cluster` is the main entry point.
- **`ray/rayjobs/`** -- RayJob submission, tracking, and runtime environment management.
- **`ray/client/`** -- Thin wrapper around Ray's `JobSubmissionClient`.
- **`common/kubernetes_cluster/`** -- Authentication (`kube-authkit` integration), API client management, error handling.
- **`common/kueue/`** -- Kueue local queue listing and default queue resolution.
- **`common/widgets/`** -- Jupyter/IPython widgets for interactive cluster management.

### Authentication
- **Preferred:** `kube-authkit` (`AuthConfig`, `get_k8s_client`) -- re-exported at the SDK top level.
- **Legacy (deprecated):** `TokenAuthentication`, `KubeConfigFileAuthentication`.
- `config_check()` handles auto-detection of kubeconfig vs in-cluster config.
- `set_api_client()` registers a custom Kubernetes API client globally.

## CI/CD Notes

- Unit tests run on **Python 3.12** in CI (GitHub Actions).
- CI workflow: `.github/workflows/unit-tests.yml` -- runs on PRs and pushes to `main`.
- E2E tests require a GPU runner with KinD, Kueue, and KubeRay installed.
- Pre-commit hooks run `black` and basic file checks (trailing whitespace, YAML validation).
- The `release.yaml` workflow publishes to PyPI -- it is triggered manually.

## Common Pitfalls

- **Don't import from vendored directly** -- use the SDK's own wrappers.
- **Don't hardcode Ray image tags** -- use `common/utils/constants.py` which maps Python versions to default images.
- **Don't skip `config_check()`** -- it ensures the Kubernetes client is properly initialized before API calls.
- **Don't add dependencies with `pip`** -- always use Poetry (`poetry add <package>`).
- **Test timeout is 900s** -- if a test hangs, it will be killed after 15 minutes.

# CodeFlare SDK

Python SDK for simplifying the management of distributed computing resources
on Kubernetes. Provides interfaces for Ray cluster lifecycle, job submission,
and Kueue integration. Apache-2.0 licensed, Python ^3.11.

## Repository Structure

| Directory | Description |
| --- | --- |
| `src/codeflare_sdk/` | Main package |
| `src/codeflare_sdk/common/` | Shared utilities (auth, Kueue, widgets) |
| `src/codeflare_sdk/ray/` | Ray cluster and job management |
| `src/codeflare_sdk/vendored/` | Vendored KubeRay client — DO NOT MODIFY |
| `tests/` | E2E and upgrade test suites |
| `demo-notebooks/` | Jupyter demo notebooks |
| `docs/` | Sphinx documentation |
| `images/` | Docker build files |

### Key Packages

```
src/codeflare_sdk/
  common/
    kubernetes_cluster/    # Auth, API client, error handling
    kueue/                 # Local queue listing, default queue resolution
    utils/                 # Constants, helpers, validation
    widgets/               # Jupyter/IPython widgets
  ray/
    cluster/               # Cluster create/config/status/delete
    rayjobs/               # RayJob submit, tracking, runtime env
    client/                # Ray JobSubmissionClient wrapper
```

## Setup

```sh
# Install (development)
poetry install

# Install with test dependencies
poetry install --with test

# Install with test + docs dependencies
poetry install --with test,docs

# Install pre-commit hooks
pre-commit install
```

## Build and Test Commands

```sh
# Pre-commit (formatting + checks)
pre-commit run --show-diff-on-failure --color=always --all-files

# Unit tests with coverage (excludes E2E, notebooks, vendored)
coverage run \
  --omit="src/**/test_*.py,src/codeflare_sdk/common/utils/unit_test_support.py,src/codeflare_sdk/vendored/**" \
  -m pytest \
  --ignore=tests/e2e --ignore=tests/e2e_v2 --ignore=tests/upgrade \
  --ignore=demo-notebooks --ignore=tests/ui

# Coverage report
coverage report -m

# Check patch coverage for specific files
coverage report -m --include="path/to/changed1.py,path/to/changed2.py"
```

### Single-File Commands

```sh
# Format a single file
black path/to/file.py

# Check formatting without modifying
black --check path/to/file.py
```

### Coverage Requirements

- **Project**: >= 90% (enforced in CI)
- **Patch**: >= 85% for new/changed files
- CI uses codecov with patch threshold 85%, overall threshold 2.5%

## Coding Conventions

### Python Style

- **Formatter**: black (via pre-commit)
- **Naming**: snake_case for functions/variables/modules, PascalCase for classes
- **Type hints**: required for function parameters and return types
- **Docstrings**: Google-style (Args, Returns, Raises sections)
- **License header**: Apache-2.0 at top of every new file
- **Import order**: standard library, third-party, local (blank line between groups)
- **Local imports**: use relative imports within the same package, absolute
  `from codeflare_sdk...` when crossing package boundaries or in tests

### Public API

Export new public classes and functions in `src/codeflare_sdk/__init__.py`.
Do not add public API without listing it there.

### Vendored Code

The `src/codeflare_sdk/vendored/` directory contains a vendored KubeRay Python
client. Do not modify files in this directory. Do not import directly from
vendored modules — use the SDK's own wrappers.

### Kubernetes API Patterns

- Call `config_check()` before Kubernetes API calls
- Use `get_api_client()` to obtain the client — do not instantiate directly
- Handle `ApiException` with `_kube_api_error_handling(e)` — do not add new
  ad-hoc exception handling patterns
- Use safe access (`.get()`, `try/except`) when parsing Custom Resource dicts
- Reuse existing enums (e.g., `RayClusterStatus`) — do not introduce new
  string-based status fields for concepts already modeled

## Testing

- **Framework**: pytest with pytest-mock and pytest-timeout (900s default)
- **Unit tests**: colocated with source in `src/codeflare_sdk/**/test_*.py`
- **E2E tests**: in `tests/e2e/`, require a Kubernetes cluster (not run locally)
- **Global fixtures**: `src/codeflare_sdk/conftest.py` auto-mocks K8s API clients
- **Mocking**: use `mocker` (pytest-mock) for K8s/API calls
- **Test helpers**: use functions from `common/utils/unit_test_support.py`
  (e.g., `get_ray_obj_with_status`, `create_cluster_config`) — never hardcode
  raw Kubernetes JSON payloads in test files
- **Edge cases**: when parsing K8s CRs, add tests with malformed/partial
  payloads (empty items, missing spec/status)

### Pre-Commit Hooks

Pre-commit hooks enforce:

- trailing-whitespace removal
- end-of-file newline
- YAML validation
- Large file checks
- black formatting

## Cursor Rules (extended guidance)

This repository has more detailed AI coding rules in `.cursor/rules/`:

- `.cursor/rules/01-project-context.mdc` — Grounding, personas, hallucination avoidance
- `.cursor/rules/02-python-standards.mdc` — Python style, canonical examples, common pitfalls
- `.cursor/rules/03-testing-and-ci.mdc` — CI workflows, demo notebooks, KinD adaptations

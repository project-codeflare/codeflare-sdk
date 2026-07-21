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

### Where to Make Changes

| Task | Location |
| --- | --- |
| Cluster config / creation | `src/codeflare_sdk/ray/cluster/` |
| RayJob lifecycle | `src/codeflare_sdk/ray/rayjobs/` |
| Ray job client (submission API) | `src/codeflare_sdk/ray/client/` |
| K8s auth / client setup | `src/codeflare_sdk/common/kubernetes_cluster/` |
| Kueue integration | `src/codeflare_sdk/common/kueue/` |
| Widgets (Jupyter) | `src/codeflare_sdk/common/widgets/` |
| Constants (Ray version, images) | `src/codeflare_sdk/common/utils/constants.py` |
| Unit tests | Colocated `test_*.py` next to source, or `test/` subdirectory |
| Unit test helpers | `src/codeflare_sdk/common/utils/unit_test_support.py` |
| E2e tests | `tests/e2e/` (KinD), `tests/e2e_v2/` |
| Example notebooks | `demo-notebooks/guided-demos/` |
| Vendored KubeRay client | `src/codeflare_sdk/vendored/` (DO NOT MODIFY) |
| CI workflows | `.github/workflows/` |
| Pre-commit config | `.pre-commit-config.yaml` |
| Linter / formatter config | `pyproject.toml` (`[tool.ruff]`, `[tool.mypy]`) |

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
ruff format path/to/file.py

# Check formatting without modifying
ruff format --check path/to/file.py

# Lint a single file (with auto-fix)
ruff check --fix path/to/file.py

# Lint a single file (check only, no changes)
ruff check path/to/file.py
```

### Coverage Requirements

- **Project**: >= 90% (enforced in CI)
- **Patch**: >= 85% for new/changed files
- CI uses codecov with patch threshold 85%, overall threshold 2.5%

## Coding Conventions

### Python Style

- **Formatter**: ruff-format (via pre-commit)
- **Linter**: ruff (pycodestyle, pyflakes)
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

### Public API Surface

The machine-readable registry of all public exports is at `docs/api/public-surface.json`.
It mirrors `src/codeflare_sdk/__init__.py` and subpackage `__init__.py` exports.
When adding or removing public symbols, update both the Python `__init__.py` and the JSON registry.

Design-level architecture: `docs/designs/CodeFlare-SDK-design-doc.md`.
User-facing Sphinx docs: `docs/sphinx/`.

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

### Import Boundaries

Layer boundaries are enforced in CI via import-linter (`.importlinter`), run in the
`lint` workflow and via pre-commit (`PYTHONPATH=src lint-imports`).

- `ray.client.ray_jobs` is isolated — no imports from `common`, other `ray` layers, or `vendored`
- Foundation utils (`common.utils.*` production modules) must not import `ray`
- `common.kueue` and `common.kubernetes_cluster` auth helpers must not import `ray`
- `vendored` may only be imported from `ray.rayjobs.rayjob` (all other listed production modules forbidden)

Additional boundaries are documented in path-scoped rules (`.cursor/rules/`, `.claude/rules/`):

- `cluster` ↔ `widgets` circular dependency (prose-only, pending refactor)
- Ray layers should prefer package-level `common.utils` imports over deep submodule imports (prose-only)

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
- ruff linting and formatting

## Pattern References

Real examples for the most common change types. Follow these patterns, not descriptions.

### Adding or modifying ClusterConfiguration / ManagedClusterConfig

- `ClusterConfiguration` dataclass: `src/codeflare_sdk/ray/cluster/config.py` (line 58)
- `ManagedClusterConfig` dataclass: `src/codeflare_sdk/ray/rayjobs/config.py` (line 65)
- Tests: `src/codeflare_sdk/ray/cluster/test_config.py` — see `test_config_creation_all_parameters`
  and `test_autoscaling_config_valid` for the pattern.

### Adding or modifying RayJob methods

- `RayJob` class: `src/codeflare_sdk/ray/rayjobs/rayjob.py` (line 58)
- Tests: `src/codeflare_sdk/ray/rayjobs/test/test_rayjob.py` — uses `auto_mock_setup`
  fixture from `src/codeflare_sdk/ray/rayjobs/test/conftest.py`.

### Adding unit and e2e tests

- **Unit tests**: colocated with source as `test_*.py`. The global
  `src/codeflare_sdk/conftest.py` auto-mocks K8s clients — tests inherit those
  fakes. See `src/codeflare_sdk/common/kueue/test_kueue.py` for a mocker-based
  pattern using helpers from `common/utils/unit_test_support.py`.
- **E2e tests**: `tests/e2e/` — see `tests/e2e/cluster_apply_kind_test.py` for
  a KinD-based lifecycle test (`@pytest.mark.kind`).

### Updating runtime images and Ray versions

- `RAY_VERSION` and runtime image constants: `src/codeflare_sdk/common/utils/constants.py`
- Image selection logic: `src/codeflare_sdk/common/utils/utils.py` (`update_image`,
  `get_ray_image_for_python_version`)
- Ray dependency version: `pyproject.toml` (search `ray =`)
- E2e image resolution: `tests/e2e/support.py` (`get_ray_image`)

### Updating example notebooks

- Guided demos: `demo-notebooks/guided-demos/` (8 notebooks: `0_basic_ray` through
  `7_rayjob_checkpointing_example`)
- CI workflow: `.github/workflows/guided_notebook_tests.yaml` — runs on KinD via
  papermill. See `.cursor/rules/03-testing-and-ci.mdc` for KinD adaptations
  (namespace, auth removal, dashboard_check=False).

## Context File Maintenance

Context files (`.cursor/rules/`, `.claude/rules/`, `AGENTS.md`) are living documents.
See the "Maintaining AI Context" section in CONTRIBUTING.md for the update process.

## Cursor Rules (extended guidance)

This repository has more detailed AI coding rules in `.cursor/rules/`:

- `.cursor/rules/01-project-context.mdc` — Grounding, personas, hallucination avoidance
- `.cursor/rules/02-python-standards.mdc` — Python style, canonical examples, common pitfalls
- `.cursor/rules/03-testing-and-ci.mdc` — CI workflows, demo notebooks, KinD adaptations
- `.cursor/rules/cluster.mdc` — Ray cluster layer (`src/codeflare_sdk/ray/cluster/`)
- `.cursor/rules/rayjobs.mdc` — RayJob layer (`src/codeflare_sdk/ray/rayjobs/`)
- `.cursor/rules/utils.mdc` — Shared utilities (`src/codeflare_sdk/common/utils/`)

Claude Code uses equivalent rules in `.claude/rules/` (same body content, different frontmatter).

# CodeFlare SDK

Python SDK for simplifying the management of distributed computing resources
on Kubernetes. Provides interfaces for Ray cluster lifecycle, job submission,
and Kueue integration. Apache-2.0 licensed, Python ^3.11.

`Codeflare` is the single entrypoint. It authenticates via kube-authkit and
owns the resulting Kubernetes client; `cf.clusters` and `cf.jobs` create
objects bound to that client. The lower-level `Cluster` / `RayJob` classes
remain public and usable directly.

```python
from codeflare_sdk import ClusterConfiguration, Codeflare, SDKConfig

cf = Codeflare(config=SDKConfig(namespace="my-project"))
cluster = cf.clusters.create(ClusterConfiguration(name="my-cluster", num_workers=2))
cluster.apply()
```

`ClusterConfiguration` is the one way to describe a cluster: `cf.clusters.create()`,
`cf.jobs.create(cluster_config=...)` and `Cluster()` all take it.

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
| Single entrypoint (`Codeflare`, `SDKConfig`, handlers) | `src/codeflare_sdk/codeflare.py` |
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
  codeflare.py             # Codeflare entrypoint, SDKConfig, cluster/job handlers
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

# Type check (CI job: type-check.yml)
mypy src/codeflare_sdk/ --config-file pyproject.toml

# Import boundaries (CI job: lint.yml, also a pre-commit hook)
PYTHONPATH=src lint-imports
```

Run `pre-commit run --all-files` before pushing. The CI `precommit` job fails
with "files were modified by this hook" when a locally installed ruff differs
from the version pinned in `.pre-commit-config.yaml`.

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

Nothing in CI checks the two against each other, so the registry can drift —
verify against the code rather than trusting it.

The `codeflare` entry covers the single entrypoint: `Codeflare`, `SDKConfig`,
and the `JobOptions` TypedDict shared by the `cf.jobs` overloads.

### Removing a public symbol (RHOAIENG-98947)

A public name may only be removed after it has shipped a `DeprecationWarning`
in a prior release, **and** not before any removal version we published for it.
Check both — they live in different places and have disagreed. For the last
tag, check `git show <tag>:<path>` for the warning, the tag's `README.md` and
`docs/` for the promised version, and `git show <tag>:demo-notebooks/...` for
whether a guided notebook uses it. Every removal in v0.40.0 failed at least
one of those:

| Name | What was missing |
| --- | --- |
| `set_api_client` | no warning at all; broke the v0.39.1 `2_basic_interactive` notebook on its first line. Re-exported and deprecated instead. |
| `TokenAuthentication` | warned, but `docs/auth_migration_guide.md` promised v1.0.0 *and* told token users to stay on it |
| `KubeConfigFileAuthentication` | same promise; also never carried `@deprecated`, only a `warnings.warn` inside `__init__` |
| `ManagedClusterConfig` | no warning; used by guided notebooks `5_submit_rayjob_cr` and `7_rayjob_checkpointing` |

Do not reach for "it was tech preview" as a rationale without checking: v0.39.1
labels nothing tech preview anywhere in `README.md`, `docs/` or `src/`.

When a name does go, add it to `REMOVED` in `src/codeflare_sdk/_compat.py` with
a message naming the replacement — the package `__getattr__` raises it. Raise
`ImportError`, not `AttributeError`: `from codeflare_sdk import X` discards an
`AttributeError`'s message and substitutes its own `cannot import name X`, and
`from ... import` is how users write every one of these. The cost is that
`hasattr()` on a removed name raises rather than returning `False`.

The deprecation wrapper lives on the package re-export only. `set_api_client`
is still imported unwrapped from `common.kubernetes_cluster.auth` by
`Codeflare.__init__`; pointing an internal caller at the wrapper would make
every `Codeflare()` warn about itself.

`src/codeflare_sdk/test_compat.py` replays the v0.39.1 notebook's cells, so a
future removal that breaks it fails the suite.

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

#### Client isolation (RHOAIENG-98754)

`Cluster` and `RayJob` are bound to the Kubernetes client they were created
with. `get_api_client()` resolves, in order: the client bound to the current
operation, the module-level client set by `set_api_client` (legacy fallback),
then a fresh default client. Binding is carried by a `ContextVar` in
`common/kubernetes_cluster/auth.py` rather than a parameter, so the helpers
that resolve a client themselves (`build_ray_cluster`, the Kueue helpers, cert
generation) pick it up without threading one through.

When adding a method to `Cluster` or `RayJob` that reaches a Kubernetes API —
directly or through any helper — decorate it:

```python
from ...common.kubernetes_cluster.auth import _bound_to_api_client

@_bound_to_api_client
def my_new_method(self): ...

@property
@_bound_to_api_client          # decorator goes *under* @property
def my_new_property(self): ...
```

Module-level helpers (`get_cluster`, `list_all_clusters`, `list_all_queued`)
take an additive `api_client: Optional[client.ApiClient] = None` and wrap their
body in `with _use_api_client(api_client):`.

Missing the decorator is a silent bug, not an error: the method works until a
second `Codeflare` is constructed, then quietly talks to the wrong cluster.
Transitive reach counts — audit what a helper calls, not just the method body.
Regression tests: `src/codeflare_sdk/test_client_isolation.py`.

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

### Adding or modifying ClusterConfiguration

- `ClusterConfiguration` dataclass: `src/codeflare_sdk/ray/cluster/config.py` (line 218)
- `WorkerGroup` dataclass (multi-worker-group support):
  `src/codeflare_sdk/ray/cluster/config.py` (line 111)
- Two builders consume the same dataclass and must stay in parity:
  - standalone RayCluster: `src/codeflare_sdk/ray/cluster/build_ray_cluster.py`
  - RayJob-embedded `rayClusterSpec`: `src/codeflare_sdk/ray/rayjobs/config.py`
    (`build_ray_cluster_spec`, line 96)

  A field added to only one builder is silently dropped by the other path.
- Nothing to add on the facade side: `cf.clusters.create()` takes a
  `ClusterConfiguration` rather than `**kwargs`, so a new field reaches it for
  free (RHOAIENG-98954).
- `__post_init__` is **not idempotent** — it merges the default accelerator
  mapping into `extended_resource_mapping` and then rejects the merged result.
  `dataclasses.replace()` on a configured instance therefore raises. Use
  `copy.copy()` and set the attribute, as `ClusterHandler.create` does when it
  injects the namespace.
- Tests: `src/codeflare_sdk/ray/cluster/test_config.py` — see `test_config_creation_all_parameters`
  and `test_autoscaling_config_valid` for the pattern.

### Adding or modifying RayJob methods

- `RayJob` class: `src/codeflare_sdk/ray/rayjobs/rayjob.py` (line 64)
- Tests: `src/codeflare_sdk/ray/rayjobs/test/test_rayjob.py` — uses `auto_mock_setup`
  fixture from `src/codeflare_sdk/ray/rayjobs/test/conftest.py`.
- Methods reaching the Kubernetes API need `@_bound_to_api_client` — see
  "Client isolation" above.
- `cf.jobs.create()` / `cf.jobs.submit()` are `@overload`ed so that passing
  neither or both of `cluster_name` / `cluster_config` is a type error, not just
  a runtime `ValueError`. A new keyword argument goes in three places: the
  implementation signature, the `JobOptions` TypedDict, and the docstring. Both
  methods delegate to `JobHandler._build()`; they cannot call each other,
  because an overloaded method cannot satisfy its own overloads without
  re-narrowing the target.

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

- Guided demos: `demo-notebooks/guided-demos/` (9 notebooks: `0_basic_ray` through
  `7_rayjob_checkpointing_example`, plus `6_single_entrypoint` for the `Codeflare`
  entrypoint — note two notebooks share the `6_` prefix)
- CI workflow: `.github/workflows/guided_notebook_tests.yaml` — runs `0_basic_ray`,
  `4_rayjob_existing_cluster`, `5_submit_rayjob_cr` and `6_autoscaling` on KinD via
  papermill. See `.cursor/rules/03-testing-and-ci.mdc` for KinD adaptations
  (namespace, auth removal, dashboard_check=False).
- **These jobs only run when the PR carries the `test-guided-notebooks` label**
  (`test-additional-notebooks` for `additional_demo_notebook_tests.yaml`). Without
  it they report as skipped, so a broken notebook looks green. Add the label when
  touching notebooks or the public API they use.
- The workflow deletes cells with `jq 'del(.cells[] | select(.source[] | ...))'`,
  which requires each cell's `source` to be a **list of lines**. Some notebook
  editors collapse it to a single string; `jq` then fails and, under
  `set -euo pipefail`, takes the whole step down.

## Context File Maintenance

Context files (`.cursor/rules/`, `.claude/rules/`, `AGENTS.md`) are living documents.
See the "Maintaining AI Context" section in CONTRIBUTING.md for the update process.

## Cursor Rules (extended guidance)

This repository has more detailed AI coding rules in `.cursor/rules/`:

- `01-project-context.mdc` — Grounding, personas, hallucination avoidance
- `02-python-standards.mdc` — Python style, canonical examples, common pitfalls
- `03-testing-and-ci.mdc` — CI workflows, demo notebooks, KinD adaptations
- `04-e2e-byoidc-detection.mdc` through `07-run-tests-sh-contract.mdc` — e2e
  BYOIDC detection, validation workflow, test-fix checklist, `run-tests.sh` contract
- `cluster.mdc`, `rayjobs.mdc`, `utils.mdc` — path-scoped layer rules

Claude Code mirrors the three path-scoped rules in `.claude/rules/`
(`cluster.md`, `rayjobs.md`, `utils.md`) — same body content, different
frontmatter. The numbered `01`–`07` rules exist only under `.cursor/rules/`;
read them from there.

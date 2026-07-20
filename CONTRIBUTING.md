# Contributing to the CodeFlare SDK

Thank you for your interest in contributing to the CodeFlare SDK!

## Getting Started

### Prerequisites

- Python 3.11
- [Poetry](https://python-poetry.org/)

### Setting Up Your Development Environment

1. **Clone the repository:**

   ```sh
   git clone https://github.com/project-codeflare/codeflare-sdk.git
   cd codeflare-sdk
   ```

2. Create a Poetry virtual environment:

   ```sh
   poetry shell
   ```

3. Install dependencies:

   ```sh
   poetry install
   ```

    - To include test dependencies, run:

      ```sh
      poetry install --with test
      ```

    - To include docs dependencies, run:

      ```sh
      poetry install --with docs
      ```

    - To include both test and docs dependencies, run:

      ```sh
      poetry install --with test,docs
      ```

## Development Workflow

### Pre-commit

We use pre-commit to ensure consistent code formatting. To enable pre-commit hooks, run:

```sh
pre-commit install
```

## Testing

To install CodeFlare SDK in editable mode, run:

```sh
pip install -e .
```

### Unit Testing

To run the unit tests, execute:

```sh
pytest -v src/codeflare_sdk
```

### Local e2e Testing

- Please follow the [e2e documentation](https://github.com/project-codeflare/codeflare-sdk/blob/main/docs/sphinx/user-docs/e2e.rst)

#### Code Coverage

- Run tests with the following command: `coverage run -m pytest`
- To then view a code coverage report w/ missing lines, run `coverage report -m`

### Design Docs

The canonical design document is `docs/designs/CodeFlare-SDK-design-doc.md`.

If a PR changes component boundaries, API contracts, or public SDK exports, the design doc or `AGENTS.md` must be updated in the same PR (or a linked follow-up). Examples of changes that require doc updates:

- Adding or removing a symbol in `src/codeflare_sdk/__init__.py`
- Changing how `ray/cluster`, `ray/rayjobs`, or `common/utils` layers interact
- Modifying import boundaries enforced in `.importlinter`
- Altering the relationship between SDK layers and vendored KubeRay client code

### Import Boundary Checks

Layer boundaries are enforced via [import-linter](https://import-linter.readthedocs.io/) (`.importlinter`).
Run locally via pre-commit (after `pre-commit install`) or directly:

```sh
PYTHONPATH=src lint-imports
```

If using Poetry: `poetry run lint-imports` also works when the package is installed in editable mode.

### Code Formatting

- Primary formatter/linter: **ruff** and **ruff-format** (via pre-commit)
- To check formatting: `ruff format --check .`
- To auto-format: `ruff format .`
- Legacy: `black` is still listed in dev dependencies but pre-commit uses ruff-format

## Maintaining AI Context

This repository includes context files that help AI coding agents work reliably in the codebase:
`AGENTS.md` (root conventions, symlinked as `CLAUDE.md`), `.cursor/rules/` and `.claude/rules/` (module-specific rules).

### When to update context files

- **Reviewer catches a pattern issue on an AI-generated PR:** add a rule to the relevant `.cursor/rules/` or `.claude/rules/` file, or `AGENTS.md`, to prevent the same mistake
- **New public API symbols added:** update `src/codeflare_sdk/__init__.py` and `docs/api/public-surface.json`
- **Module boundaries change:** update the corresponding `.cursor/rules/` and `.claude/rules/` files and `.importlinter` contracts

### Rule lifecycle

- New rules should be specific and actionable (e.g., "never import `codeflare_sdk.vendored` outside `ray/rayjobs/`")
- Prefer import-linter contracts over prose warnings — lint rules are deterministic and enforced in CI
- When updating module rules, change both `.cursor/rules/` and `.claude/rules/` in the same PR (body content must stay in sync; only frontmatter differs)
- Periodically audit context files: remove lines that no longer prevent real failures
- Treat context files as a living list of codebase conventions, not permanent configuration

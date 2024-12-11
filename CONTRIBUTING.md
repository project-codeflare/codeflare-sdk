# Contributing to the CodeFlare SDK

Thank you for your interest in contributing to the CodeFlare SDK!

## Getting Started

### Prerequisites

- Python 3.9
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

### Code Formatting

- To check file formatting, in top-level dir run `black --check .`
- To auto-reformat all files, remove the `--check` flag
- To reformat an individual file, run `black <filename>`

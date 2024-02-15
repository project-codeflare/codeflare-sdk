# Codeflare-SDK

[![Python application](https://github.com/project-codeflare/codeflare-sdk/actions/workflows/unit-tests.yml/badge.svg?branch=main)](https://github.com/project-codeflare/codeflare-sdk/actions/workflows/unit-tests.yml)
![coverage badge](./coverage.svg)

An intuitive, easy-to-use python interface for batch resource requesting, access, job submission, and observation. Simplifying the developer's life while enabling access to high-performance compute resources, either in the cloud or on-prem.

For guided demos and basics walkthroughs, check out the following links:

- Guided demo notebooks available [here](https://github.com/project-codeflare/codeflare-sdk/tree/main/demo-notebooks/guided-demos), and copies of the notebooks with [expected output](https://github.com/project-codeflare/codeflare-sdk/tree/main/demo-notebooks/guided-demos/notebook-ex-outputs) also available
- Note that these notebooks will work with the latest `codeflare-sdk` PyPI release. For testing and experimentation with `main` branch, please use the [preview notebooks](https://github.com/project-codeflare/codeflare-sdk/tree/main/demo-notebooks/guided-demos/preview_nbs)
- Additionally, we have a [video walkthrough](https://www.youtube.com/watch?v=U76iIfd9EmE) of these basic demos from June, 2023

Full documentation can be found [here](https://project-codeflare.github.io/codeflare-sdk/detailed-documentation)

## Installation

Can be installed via `pip`: `pip install codeflare-sdk`

## Development

### Prerequisites

We recommend using Python 3.9 for development, along with Poetry.
Create a Poetry virtual environment with the required Python version 3.9, and run all commands within this environment.

  - run: `poetry shell`

#### Install dependencies:

  - run: `poetry install`

This will install standard requirements as specified in the poetry.lock file. Test and docs dependencies are optional.

- To include test dependencies run: `poetry install --with test`

- To include docs dependencies run: `poetry install --with docs`

- To include test and docs dependencies run: `poetry install --with test,docs`

If you require a requirements.txt file you can run:

`poetry export -f requirements.txt --output requirements.txt --without-hashes`

### Pre-commit

We use pre-commit to make sure the code is consistently formatted. To make sure that pre-commit is run every time you commit changes, simply run `pre-commit install`

To build the codeflare-sdk pre-commit image run `podman build -f .github/build/Containerfile .` from the root directory.

### Testing

- To install codeflare-sdk in editable mode, run `pip install -e .` from the repo root.
- Any new test functions/scripts can be added into the `tests` folder
- NOTE: Functional tests coming soon, will live in `tests/func_test.py`

#### Unit Testing
- To run the unit tests, run `pytest -v tests/unit_test.py`

#### Local e2e Testing
- Please follow the [e2e documentation](https://github.com/project-codeflare/codeflare-sdk/blob/main/docs/e2e.md)

#### Code Coverage

- Run tests with the following command: `coverage run -m --source=src pytest tests/unit_test.py`
- To then view a code coverage report w/ missing lines, run `coverage report -m`

### Code Formatting

- To check file formatting, in top-level dir run `black --check .`
- To auto-reformat all files, remove the `--check` flag
- To reformat an individual file, run `black <filename>`

### Package Build

To build the python package: `$ poetry build`

## Release Instructions

### Automated Releases

It is possible to use the Release Github workflow to do the release. This is generally the process we follow for releases

### Manual Releases

The following instructions apply when doing release manually. This may be required in instances where the automation is failing.

- Check and update the version in "pyproject.toml" file.
- Generate new documentation.
`pdoc --html -o docs src/codeflare_sdk && pushd docs && rm -rf cluster job utils && mv codeflare_sdk/* . && rm -rf codeflare_sdk && popd && find docs -type f -name "*.html" -exec bash -c "echo '' >> {}" \;` (it is possible to install **pdoc** using the following command `poetry install --with docs`)
- Commit all the changes to the repository.
- Create Github release (<https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository#creating-a-release>).
- Build the Python package. `poetry build`
- If not present already, add the API token to Poetry.
`poetry config pypi-token.pypi API_TOKEN`
- Publish the Python package. `poetry publish`
- Change directory to custom-nb-image. `cd custom-nb-image`
- Set tag `export tag=TAG`
- Build the container image. `podman build --build-arg SDK_VERSION=<version> -t quay.io/project-codeflare/notebook:${tag} .`
- Login to quay.io. `podman login quay.io`
- Push the image. `podman push quay.io/project-codeflare/notebook:${tag}`
- Push the stable image tag `podman push quay.io/project-codeflare/notebook:${tag} quay.io/project-codeflare/notebook:stable`

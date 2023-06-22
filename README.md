# Codeflare-SDK

[![Python application](https://github.com/project-codeflare/codeflare-sdk/actions/workflows/python-app.yml/badge.svg?branch=main)](https://github.com/project-codeflare/codeflare-sdk/actions/workflows/python-app.yml)
![coverage badge](./coverage.svg)

An intuitive, easy-to-use python interface for batch resource requesting, access, job submission, and observation. Simplifying the developer's life while enabling access to high-performance compute resources, either in the cloud or on-prem.

Tutorial and basics walkthrough coming soon!

Full documentation can be found [here](https://project-codeflare.github.io/codeflare-sdk/)

## Installation

Can be installed via `pip`: `pip install codeflare-sdk`

## Development

### Prerequisites

We recommend using Python 3.9 for development.
Install development specific dependencies:
  `$ pip install -r requirements-dev.txt`

Additional dependencies can be found in `requirements.txt`: `$ pip install -r requirements.txt`

### Pre-commit

We use pre-commit to make sure the code is consistently formatted. To make sure that pre-commit is run every time you commit changes, simply run `pre-commit install`

### Testing

- To install codeflare-sdk in editable mode, run `pip install -e .` from the repo root.
- To run the unit tests, run `pytest -v tests/unit_test.py`
- Any new test functions/scripts can be added into the `tests` folder
- NOTE: Functional tests coming soon, will live in `tests/func_test.py`

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

* Check and update the version in "pyproject.toml" file.
* Generate new documentation.
`pdoc --html -o docs src/codeflare_sdk && pushd docs && rm -rf cluster job utils && mv codeflare_sdk/* . && rm -rf codeflare_sdk && popd` (it is possible to install **pdoc** using the following command `poetry install --with docs`)
* Commit all the changes to the repository.
* Create Github release (https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository#creating-a-release).
* Build the Python package. `poetry build`
* If not present already, add the API token to Poetry.
`poetry config pypi-token.pypi API_TOKEN`
* Publish the Python package. `poetry publish`
* Change directory to custom-nb-image. `cd custom-nb-image`
* Set tag `export tag=TAG`
* Build the Docker image. `docker build --build-arg SDK_VERSION=<version> -t quay.io/project-codeflare/notebook:${tag} .`
* Tag the image as latest. `docker tag quay.io/project-codeflare/notebook:${tag} quay.io/project-codeflare/notebook:latest`
* Login to quay.io. `docker login quay.io`
* Push the image. `docker push quay.io/project-codeflare/notebook:${tag}`
* Push the image. `docker push quay.io/project-codeflare/notebook:latest`

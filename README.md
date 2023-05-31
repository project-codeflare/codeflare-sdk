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

> Some tests, i.e. test_ray_details,test_cluster_status,and test_wait_ready require an Openshift cluster with [Codeflare Stack](https://github.com/opendatahub-io/distributed-workloads/blob/main/Quick-Start.md#quick-start-guide-for-distributed-workflows-with-the-codeflare-stack) installed.
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

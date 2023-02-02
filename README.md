# Codeflare-SDK

[![Python application](https://github.com/project-codeflare/codeflare-sdk/actions/workflows/python-app.yml/badge.svg?branch=main)](https://github.com/project-codeflare/codeflare-sdk/actions/workflows/python-app.yml)
![coverage badge](./coverage.svg)

An intuitive, easy-to-use python interface for batch resource requesting, access, job submission, and observation. Simplifying the developer's life while enabling access to high-performance compute resources, either in the cloud or on-prem.

Tutorial and basics walkthrough coming soon!

Full documentation can be found [here](https://project-codeflare.github.io/codeflare-sdk/)

## Installation

Can be installed via `pip`: `pip install codeflare-sdk`

## Development

For testing, make sure to have installed:
 - `pytest`, `pytest-mock` (can both be installed with `pip`)
 - The remaining dependencies located in `requirements.txt`
 - To run the unit tests, run `pytest -v tests/unit_test.py`)
 - Any new test functions/scripts can be added into the `tests` folder

NOTE: Functional tests coming soon, will live in `tests/func_test.py`

For checking code coverage while testing:
 - Start by installing `coverage` (can be done via `pip`)
 - Now instead when testing run `coverage run -m --source=src pytest tests/unit_test.py`
 - To then view a code coverage report w/ missing lines, run `coverage report -m`

For formatting:
 - Currently using black v22.3.0 for format checking
 - To install, run `pip install black==22.3.0`
 - To check file formatting, in top-level dir run `black --check .`
   - To auto-reformat all files, remove the `--check` flag
   - To reformat an individual file, run `black <filename>`

To build the python package:
 - If poetry is not installed: `pip install poetry`
 - `poetry build`

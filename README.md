# Codeflare-SDK

An intuitive, easy-to-use python interface for batch resource requesting, access, job submission, and observation. Simplifying the developer's life while enabling access to high-performance compute resources, either in the cloud or on-prem.

Documentation site coming soon, link will be provided here

## Installation

Can be installed via `pip`: `pip install codeflare-sdk`

## Development

For testing, make sure to have installed:
 - `pytest`
 - The remaining dependencies located in `requirements.txt`

NOTE: Self-contained unit/functional tests coming soon, will live in `tests` folder

For formatting:
 - Currently using black v22.3.0 for format checking
 - To install, run `pip install black==22.3.0`
 - To check file formatting, in top-level dir run `black --check .`
   - To auto-reformat all files, remove the `--check` flag
   - To reformat an individual file, run `black <filename>`

To build the python package:
 - If poetry is not installed: `pip install poetry`
 - `poetry build`

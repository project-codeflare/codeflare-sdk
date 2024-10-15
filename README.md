# CodeFlare SDK

[![Python application](https://github.com/project-codeflare/codeflare-sdk/actions/workflows/unit-tests.yml/badge.svg?branch=main)](https://github.com/project-codeflare/codeflare-sdk/actions/workflows/unit-tests.yml)
![coverage badge](./coverage.svg)

An intuitive, easy-to-use python interface for batch resource requesting, access, job submission, and observation. Simplifying the developer's life while enabling access to high-performance compute resources, either in the cloud or on-prem.

For guided demos and basics walkthroughs, check out the following links:

- Guided demo notebooks available [here](https://github.com/project-codeflare/codeflare-sdk/tree/main/demo-notebooks/guided-demos), and copies of the notebooks with [expected output](https://github.com/project-codeflare/codeflare-sdk/tree/main/demo-notebooks/guided-demos/notebook-ex-outputs) also available
- these demos can be copied into your current working directory when using the `codeflare-sdk` by using the `codeflare_sdk.copy_demo_nbs()` function
- Additionally, we have a [video walkthrough](https://www.youtube.com/watch?v=U76iIfd9EmE) of these basic demos from June, 2023

Full documentation can be found [here](https://project-codeflare.github.io/codeflare-sdk/index.html)

## Installation

Can be installed via `pip`: `pip install codeflare-sdk`

## Development

Please see our [CONTRIBUTING.md](./CONTRIBUTING.md) for detailed instructions.

## Release Instructions

### Automated Releases

It is possible to use the Release Github workflow to do the release. This is generally the process we follow for releases

### Manual Releases

The following instructions apply when doing release manually. This may be required in instances where the automation is failing.

- Check and update the version in "pyproject.toml" file.
- Commit all the changes to the repository.
- Create Github release (<https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository#creating-a-release>).
- Build the Python package. `poetry build`
- If not present already, add the API token to Poetry.
`poetry config pypi-token.pypi API_TOKEN`
- Publish the Python package. `poetry publish`
- Trigger the [Publish Documentation](https://github.com/project-codeflare/codeflare-sdk/actions/workflows/publish-documentation.yaml) workflow

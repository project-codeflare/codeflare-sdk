#!/bin/bash

# Install Poetry and configure virtualenvs
pip install poetry
poetry config virtualenvs.create false

# Clone the CodeFlare SDK repository
echo "first ls"
ls
pip uninstall codeflare-sdk
echo "install codeflare sdk"
pip install codeflare_sdk-0.0.0.dev0-py3-none-any.whl
echo "second ls"
ls
# git clone --branch main https://github.com/project-codeflare/codeflare-sdk.git
# cd codeflare-sdk

# # Lock dependencies and install them
# poetry lock --no-update
# poetry install --with test,docs

# Return to the previous directory
# cd ..

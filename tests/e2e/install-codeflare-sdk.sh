#!/bin/bash

cd ..

# Install Poetry and configure virtualenvs
pip install poetry
poetry config virtualenvs.create false

cd codeflare-sdk

# Lock dependencies and install them
poetry lock --no-update
poetry install --with test,docs

# Return to the workdir
cd ..
cd workdir

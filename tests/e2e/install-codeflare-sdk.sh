# !/bin/bash

# Install Poetry and configure virtualenvs
pip install poetry
poetry config virtualenvs.create false

# Lock dependencies and install them
poetry lock --no-update
poetry install --with test,docs

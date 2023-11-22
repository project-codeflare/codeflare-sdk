#!/bin/bash

# Generate zip file beforehand
# tar -czvf root-dir.tar.gz --exclude='.git' --exclude='.github' --exclude='.pytest_cache' ./

# Create temp-pod to contain the zip file
# kubectl apply -f temp-pod.yaml

# Copy the zip file to the temp-pod:/mnt
# kubectl cp root-dir.tar.gz temp-pod:/mnt

# Run a shell in the temp-pod
# kubectl exec -it temp-pod -- /bin/sh

# Unzip the zip file
# tar -xzvf /mnt/root-dir.tar.gz -C /mnt

# Not necessary as the PVC is mounted to /codeflare-sdk
# mv /mnt/* /codeflare-sdk/

## Copy files from temp-pod /mnt into the codeflare-sdk volume mount in this other pod.
# kubectl cp default/temp-pod:/mnt codeflare-sdk


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

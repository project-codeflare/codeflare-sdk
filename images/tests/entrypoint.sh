#!/bin/sh
# Entrypoint script that handles -- separator in podman commands
# Passes all arguments to run-tests.sh which will forward them to pytest

exec /codeflare-sdk/run-tests.sh "$@"


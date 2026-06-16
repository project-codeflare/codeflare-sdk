# Copyright 2024 IBM, Red Hat
#
# Minimal Ray job for upgrade qualification on disconnected clusters.
# Validates job submission and execution without pip installs or external datasets.

import sys


def main() -> int:
    print("upgrade-job-smoke: job started")
    print("upgrade-job-smoke: job finished successfully")
    return 0


if __name__ == "__main__":
    sys.exit(main())

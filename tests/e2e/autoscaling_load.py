"""
Workload used by E2E autoscaling tests.

This script is submitted via Ray Job submission to generate enough queued work
to trigger Ray in-tree autoscaling on a KinD cluster.
"""

import os
import time

import ray


def main():
    # Expect to run inside the Ray cluster environment (dashboard job submission)
    ray.init(address="auto")

    concurrency = int(os.getenv("AUTOSCALING_TASKS", "4"))
    sleep_s = int(os.getenv("AUTOSCALING_TASK_SLEEP_S", "120"))

    @ray.remote(num_cpus=1)
    def burn_cpu():
        time.sleep(sleep_s)
        return True

    futures = [burn_cpu.remote() for _ in range(concurrency)]
    ray.get(futures)


if __name__ == "__main__":
    main()

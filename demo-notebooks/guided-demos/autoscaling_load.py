"""
Workload used by the autoscaling guided demo notebook.

Submit via the Ray Job Submission Client to queue enough CPU tasks to trigger
Ray in-tree autoscaling (scale-up). Tasks sleep long enough to observe workers
before they complete and the cluster scales back down.
"""

import os
import time

import ray


def main():
    ray.init(address="auto")

    concurrency = int(os.getenv("AUTOSCALING_TASKS", "3"))
    sleep_s = int(os.getenv("AUTOSCALING_TASK_SLEEP_S", "120"))

    @ray.remote(num_cpus=1)
    def burn_cpu():
        time.sleep(sleep_s)
        return True

    futures = [burn_cpu.remote() for _ in range(concurrency)]
    ray.get(futures)


if __name__ == "__main__":
    main()

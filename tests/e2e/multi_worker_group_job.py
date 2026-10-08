# Copyright 2026 IBM, Red Hat
#
# Ray job used by heterogeneous-cluster e2e tests. Pins one task to each
# non-head Ray node so work is dispatched across worker groups.

import socket
import sys
import time

import ray
from ray.util.scheduling_strategies import NodeAffinitySchedulingStrategy


HEAD_RESOURCE = "node:__internal_head__"


def _alive_worker_nodes():
    return [
        node
        for node in ray.nodes()
        if node.get("Alive") and HEAD_RESOURCE not in node.get("Resources", {})
    ]


@ray.remote(num_cpus=1)
def ping():
    return socket.gethostname()


def main() -> int:
    ray.init()
    deadline = time.time() + 180
    workers = []
    while time.time() < deadline:
        workers = _alive_worker_nodes()
        if len(workers) >= 2:
            break
        time.sleep(2)
    if len(workers) < 2:
        print(f"expected at least 2 worker nodes, got {len(workers)}")
        return 1

    hostnames = ray.get(
        [
            ping.options(
                scheduling_strategy=NodeAffinitySchedulingStrategy(
                    worker["NodeID"], soft=False
                )
            ).remote()
            for worker in workers[:2]
        ]
    )
    print(f"worker_hosts: {hostnames}")
    if len(set(hostnames)) < 2:
        print("tasks did not land on distinct worker group nodes")
        return 1
    print("tasks dispatched across worker groups")
    return 0


if __name__ == "__main__":
    sys.exit(main())

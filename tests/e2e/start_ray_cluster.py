import sys
import os

from time import sleep

from codeflare_sdk.cluster.cluster import Cluster, ClusterConfiguration

namespace = sys.argv[1]
ray_image = os.getenv("RAY_IMAGE")

cluster = Cluster(
    ClusterConfiguration(
        name="mnist",
        namespace=namespace,
        num_workers=1,
        head_cpu_requests="500m",
        head_cpu_limits="500m",
        head_memory_requests=2,
        head_memory_limits=2,
        worker_cpu_requests="500m",
        worker_cpu_limits=1,
        worker_memory_requests=1,
        worker_memory_limits=2,
        image=ray_image,
        appwrapper=True,
    )
)

cluster.up()

cluster.status()

cluster.wait_ready()

cluster.status()

cluster.details()

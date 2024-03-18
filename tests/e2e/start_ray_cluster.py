import sys
import os

from time import sleep

from codeflare_sdk.cluster.cluster import Cluster, ClusterConfiguration

namespace = sys.argv[1]
ray_image = os.getenv("RAY_IMAGE")
host = os.getenv("CLUSTER_HOSTNAME")

ingress_options = {}
if host is not None:
    ingress_options = {
        "ingresses": [
            {
                "ingressName": "ray-dashboard",
                "port": 8265,
                "pathType": "Prefix",
                "path": "/",
                "host": host,
            },
        ]
    }

cluster = Cluster(
    ClusterConfiguration(
        name="mnist",
        namespace=namespace,
        num_workers=1,
        head_cpus="500m",
        head_memory=2,
        min_cpus="500m",
        max_cpus=1,
        min_memory=1,
        max_memory=2,
        num_gpus=0,
        image=ray_image,
        ingress_options=ingress_options,
    )
)

cluster.up()

cluster.status()

cluster.wait_ready()

cluster.status()

cluster.details()

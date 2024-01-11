import sys
import os

from time import sleep

import ray

from torchx.specs.api import AppState, is_terminal

from codeflare_sdk.cluster.cluster import Cluster, ClusterConfiguration
from codeflare_sdk.job.jobs import DDPJobDefinition

namespace = sys.argv[1]
ray_image = "quay.io/project-codeflare/ray:latest-py39-cu118"
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
        min_memory=0.5,
        max_memory=2,
        num_gpus=0,
        instascale=False,
        image=ray_image,
        ingress_options=ingress_options,
    )
)

cluster.up()

cluster.status()

cluster.wait_ready()

cluster.status()

cluster.details()

jobdef = DDPJobDefinition(
    name="mnist",
    script="mnist.py",
    scheduler_args={"requirements": "requirements.txt"},
)

# THIS DOESN'T WORK: (CURRENT STATUS: CONNECTION REFUSED)
host_alias = {
    "ip": "172.18.0.2",  # Replace with the actual node IP
    "hostnames": ["kind"],  # Replace with the actual hostname
}
jobdef["spec"]["template"]["spec"]["hostAliases"] = [host_alias]

job = jobdef.submit(cluster)

done = False
time = 0
timeout = 900
while not done:
    status = job.status()
    if is_terminal(status.state):
        break
    if not done:
        print(status)
        if timeout and time >= timeout:
            raise TimeoutError(f"job has timed out after waiting {timeout}s")
        sleep(5)
        time += 5

print(f"Job has completed: {status.state}")

print(job.logs())

cluster.down()

if not status.state == AppState.SUCCEEDED:
    exit(1)
else:
    exit(0)

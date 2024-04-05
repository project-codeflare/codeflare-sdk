import sys

from time import sleep

from support import *

from codeflare_sdk.cluster.cluster import get_cluster
from codeflare_sdk.job import RayJobClient

namespace = sys.argv[1]

cluster = get_cluster("mnist", namespace)

cluster.details()

auth_token = run_oc_command(["whoami", "--show-token=true"])
ray_dashboard = cluster.cluster_dashboard_uri()
header = {"Authorization": f"Bearer {auth_token}"}
client = RayJobClient(address=ray_dashboard, headers=header, verify=True)

# Submit the job
submission_id = client.submit_job(
    entrypoint="python mnist.py",
    runtime_env={"working_dir": "/", "pip": "requirements.txt"},
)
print(f"Submitted job with ID: {submission_id}")
done = False
time = 0
timeout = 900
while not done:
    status = client.get_job_status(submission_id)
    if status.is_terminal():
        break
    if not done:
        print(status)
        if timeout and time >= timeout:
            raise TimeoutError(f"job has timed out after waiting {timeout}s")
        sleep(5)
        time += 5

logs = client.get_job_logs(submission_id)
print(logs)

client.delete_job(submission_id)
cluster.down()


if not status == "SUCCEEDED":
    exit(1)
else:
    exit(0)

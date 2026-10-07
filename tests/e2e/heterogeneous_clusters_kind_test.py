import subprocess
import time

from codeflare_sdk import Cluster, ClusterConfiguration, WorkerGroup
from codeflare_sdk.ray.client import RayJobClient

import pytest

from support import *


@pytest.mark.kind
@pytest.mark.timeout(1800)
class TestHeterogeneousClustersKind:
    def setup_method(self):
        initialize_kubernetes_client(self)
        self.port_forward_process = None

    def cleanup_port_forward(self):
        if self.port_forward_process:
            self.port_forward_process.terminate()
            self.port_forward_process.wait(timeout=10)
            self.port_forward_process = None

    def teardown_method(self):
        self.cleanup_port_forward()
        delete_namespace(self)
        delete_kueue_resources(self)

    # nvidia_gpu is required for PR CI (`pytest -m 'kind and nvidia_gpu'`).
    # The cluster itself is CPU-only; GPU is not requested.
    @pytest.mark.nvidia_gpu
    def test_heterogeneous_clusters(self):
        create_namespace(self)
        create_kueue_resources(self)
        self.run_heterogeneous_clusters()

    def run_heterogeneous_clusters(self):
        cluster_name = "test-mwg"
        extra_group_name = "cpu-extra"
        expected_groups = [
            f"small-group-{cluster_name}",
            extra_group_name,
        ]

        cluster = Cluster(
            ClusterConfiguration(
                name=cluster_name,
                namespace=self.namespace,
                num_workers=1,
                head_cpu_requests="500m",
                head_cpu_limits="500m",
                head_memory_requests=2,
                head_memory_limits=2,
                worker_cpu_requests="500m",
                worker_cpu_limits=1,
                worker_memory_requests=1,
                worker_memory_limits=4,
                image=get_ray_image(),
                verify_tls=False,
                local_queue=self.local_queue,
                additional_worker_groups=[
                    WorkerGroup(
                        group_name=extra_group_name,
                        replicas=1,
                        cpu_requests="500m",
                        cpu_limits=1,
                        memory_requests=1,
                        memory_limits=4,
                    ),
                ],
            )
        )

        spec_groups = [
            group["groupName"]
            for group in cluster.resource_yaml["spec"]["workerGroupSpecs"]
        ]
        assert spec_groups == expected_groups, (
            f"expected workerGroupSpecs {expected_groups}, got {spec_groups}"
        )

        cluster.apply()
        # KinD has no HTTPRoute/Route; do not wait on the dashboard URI.
        self.wait_worker_groups_running(cluster_name, expected_groups)

        ray_cluster = get_ray_cluster(cluster_name, self.namespace)
        live_groups = [
            group["groupName"] for group in ray_cluster["spec"]["workerGroupSpecs"]
        ]
        assert live_groups == expected_groups, (
            f"live CR workerGroupSpecs {live_groups} != {expected_groups}"
        )

        self.submit_and_wait_multi_group_job(cluster)

        cluster.down()
        self.wait_cluster_deleted(cluster_name)

    def wait_worker_groups_running(self, cluster_name, expected_groups, timeout=600):
        deadline = time.time() + timeout
        last = {}
        while time.time() < deadline:
            pods = self.api_instance.list_namespaced_pod(
                self.namespace,
                label_selector=(
                    f"ray.io/cluster={cluster_name},ray.io/node-type=worker"
                ),
            )
            last = {}
            for pod in pods.items:
                group = pod.metadata.labels.get("ray.io/group")
                last[group] = pod.status.phase == "Running"
            print(f"wait: worker_groups_running={last}")
            if all(last.get(group) for group in expected_groups):
                print(f"Worker groups running: {last}")
                return
            time.sleep(10)
        raise TimeoutError(
            f"Worker groups {expected_groups} not running after {timeout}s: {last}"
        )

    def wait_cluster_deleted(self, cluster_name, timeout=180):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if get_ray_cluster(cluster_name, self.namespace) is None:
                print(f"Cluster {cluster_name} removed")
                return
            time.sleep(5)
        raise TimeoutError(
            f"RayCluster {cluster_name} still present after cluster.down()"
        )

    def submit_and_wait_multi_group_job(self, cluster, timeout=600):
        local_port = "8265"
        cluster_name = cluster.config.name
        port_forward_cmd = [
            "kubectl",
            "port-forward",
            "-n",
            self.namespace,
            f"svc/{cluster_name}-head-svc",
            f"{local_port}:8265",
        ]
        self.port_forward_process = subprocess.Popen(
            port_forward_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        time.sleep(5)

        client = RayJobClient(address=f"http://localhost:{local_port}", verify=False)
        try:
            submission_id = client.submit_job(
                entrypoint="python multi_worker_group_job.py",
                runtime_env={"working_dir": "./tests/e2e/"},
                entrypoint_num_cpus=1,
            )
            print(f"Submitted multi-worker-group job {submission_id}")
            elapsed = 0
            status = None
            while elapsed < timeout:
                status = client.get_job_status(submission_id)
                if status.is_terminal():
                    break
                print(status)
                time.sleep(5)
                elapsed += 5
            logs = client.get_job_logs(submission_id)
            print(logs)
            status_value = getattr(status, "value", status)
            assert status_value == "SUCCEEDED", (
                f"Job completed with status {status_value}, logs:\n{logs}"
            )
            assert "tasks dispatched across worker groups" in logs
            client.delete_job(submission_id)
        finally:
            self.cleanup_port_forward()

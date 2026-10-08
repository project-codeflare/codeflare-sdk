import os
import time

from codeflare_sdk import Cluster, ClusterConfiguration, WorkerGroup
from codeflare_sdk.ray.client import RayJobClient

import pytest

from support import *


@pytest.mark.openshift
@pytest.mark.tier1
@pytest.mark.timeout(1800)
class TestHeterogeneousClustersOauth:
    def setup_method(self):
        initialize_kubernetes_client(self)

    def teardown_method(self):
        if hasattr(self, "auth_instance"):
            cleanup_authentication(self.auth_instance)
        delete_namespace(self)
        delete_kueue_resources(self)

    def test_heterogeneous_clusters(self):
        create_namespace(self)
        create_kueue_resources(self)
        self.auth_instance = authenticate_for_tests()
        self.assert_worker_group_validation()
        self.run_heterogeneous_clusters()

    def assert_worker_group_validation(self):
        with pytest.raises(ValueError, match="Duplicate worker group name"):
            ClusterConfiguration(
                name="validation-cluster",
                namespace=self.namespace,
                additional_worker_groups=[
                    WorkerGroup(group_name="cpu-extra"),
                    WorkerGroup(group_name="cpu-extra"),
                ],
            )

        with pytest.raises(ValueError, match="conflicts with the default worker group"):
            ClusterConfiguration(
                name="validation-cluster",
                namespace=self.namespace,
                additional_worker_groups=[
                    WorkerGroup(group_name="small-group-validation-cluster"),
                ],
            )

        with pytest.raises(ValueError, match="gpu_type"):
            WorkerGroup(group_name="bad-gpu", gpu_count=1)

        with pytest.raises(ValueError, match="min_replicas"):
            WorkerGroup(
                group_name="bad-range",
                replicas=1,
                min_replicas=5,
                max_replicas=2,
            )

    def run_heterogeneous_clusters(self):
        ray_image = get_ray_image()
        resources = get_platform_appropriate_resources()
        cluster_name = "test-mwg"
        extra_group_name = "cpu-extra"
        expected_groups = [
            f"small-group-{cluster_name}",
            extra_group_name,
        ]

        cluster = Cluster(
            ClusterConfiguration(
                namespace=self.namespace,
                name=cluster_name,
                num_workers=1,
                head_cpu_requests=resources["head_cpu_requests"],
                head_cpu_limits=resources["head_cpu_limits"],
                head_memory_requests=resources["head_memory_requests"],
                head_memory_limits=resources["head_memory_limits"],
                worker_cpu_requests=resources["worker_cpu_requests"],
                worker_cpu_limits=resources["worker_cpu_limits"],
                worker_memory_requests=resources["worker_memory_requests"],
                worker_memory_limits=resources["worker_memory_limits"],
                image=ray_image,
                verify_tls=False,
                local_queue=self.local_queue,
                additional_worker_groups=[
                    WorkerGroup(
                        group_name=extra_group_name,
                        replicas=1,
                        cpu_requests=resources["worker_cpu_requests"],
                        cpu_limits=resources["worker_cpu_limits"],
                        memory_requests=resources["worker_memory_requests"],
                        memory_limits=resources["worker_memory_limits"],
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
        # Kueue unsuspends the RayCluster after admission, but this operator
        # can leave status.state=suspended while pods are already running.
        # Wait on pod readiness + dashboard instead of cluster.wait_ready().
        self.wait_cluster_and_groups_ready(cluster, expected_groups)

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

    def dump_cluster_debug(self, cluster_name):
        print(f"\n===== debug dump for {cluster_name} in {self.namespace} =====")
        rc = get_ray_cluster(cluster_name, self.namespace)
        if rc is None:
            print("RayCluster CR not found")
        else:
            print(f"RayCluster spec.suspend: {rc.get('spec', {}).get('suspend')}")
            print(
                f"RayCluster annotations: {rc.get('metadata', {}).get('annotations')}"
            )
            print(f"RayCluster labels: {rc.get('metadata', {}).get('labels')}")
            print(f"RayCluster status: {rc.get('status', {})}")
            print(
                "workerGroupSpecs: "
                f"{[g.get('groupName') for g in rc.get('spec', {}).get('workerGroupSpecs', [])]}"
            )
        pods = self.api_instance.list_namespaced_pod(
            self.namespace, label_selector=f"ray.io/cluster={cluster_name}"
        )
        for pod in pods.items:
            print(
                f"pod {pod.metadata.name} phase={pod.status.phase} "
                f"group={pod.metadata.labels.get('ray.io/group')} "
                f"node={pod.spec.node_name} "
                f"reason={pod.status.reason}"
            )
            for cs in pod.status.container_statuses or []:
                waiting = cs.state.waiting
                terminated = cs.state.terminated
                print(
                    f"  container {cs.name} ready={cs.ready} "
                    f"waiting={waiting.reason if waiting else None} "
                    f"terminated={terminated.reason if terminated else None} "
                    f"restarts={cs.restart_count}"
                )
                try:
                    log = self.api_instance.read_namespaced_pod_log(
                        name=pod.metadata.name,
                        namespace=self.namespace,
                        container=cs.name,
                        tail_lines=40,
                    )
                    print(f"  --- logs {pod.metadata.name}/{cs.name} ---\n{log}")
                except Exception as e:
                    print(f"  could not read logs for {cs.name}: {e}")
        try:
            workloads = self.custom_api.list_namespaced_custom_object(
                group="kueue.x-k8s.io",
                version="v1beta1",
                namespace=self.namespace,
                plural="workloads",
            )
            for wl in workloads.get("items", []):
                print(
                    f"workload {wl['metadata']['name']} status={wl.get('status', {})}"
                )
        except Exception as e:
            print(f"Could not list Kueue workloads: {e}")
        events = self.api_instance.list_namespaced_event(self.namespace)
        for event in events.items[-20:]:
            print(
                f"event {event.last_timestamp} {event.reason} "
                f"{event.involved_object.kind}/{event.involved_object.name}: {event.message}"
            )
        print("===== end debug dump =====\n")

    def wait_cluster_and_groups_ready(self, cluster, expected_groups, timeout=600):
        cluster_name = cluster.config.name
        deadline = time.time() + timeout
        last_groups = {}
        dashboard_ready = False
        while time.time() < deadline:
            last_groups = self._pods_running_by_group(cluster_name)
            try:
                dashboard_ready = bool(cluster.is_dashboard_ready())
            except Exception as e:
                dashboard_ready = False
                print(f"dashboard check error: {e}")
            print(
                f"wait: worker_groups_running={last_groups} "
                f"dashboard_ready={dashboard_ready}"
            )
            groups_ok = all(last_groups.get(group) for group in expected_groups)
            if groups_ok and dashboard_ready:
                print(
                    f"Cluster {cluster_name} worker groups are up and dashboard is ready"
                )
                return
            time.sleep(10)
        self.dump_cluster_debug(cluster_name)
        raise TimeoutError(
            f"Cluster {cluster_name} not ready after {timeout}s: "
            f"worker_groups_running={last_groups} dashboard_ready={dashboard_ready}"
        )

    def _pods_running_by_group(self, cluster_name):
        pods = self.api_instance.list_namespaced_pod(
            self.namespace,
            label_selector=(f"ray.io/cluster={cluster_name},ray.io/node-type=worker"),
        )
        running = {}
        for pod in pods.items:
            group = pod.metadata.labels.get("ray.io/group")
            running[group] = pod.status.phase == "Running"
        return running

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
        client = self._ray_job_client(cluster)
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

    def _ray_job_client(self, cluster):
        if is_byoidc_cluster_detected():
            username = os.environ.get("OCP_ADMIN_USER_USERNAME", "")
            password = os.environ.get("OCP_ADMIN_USER_PASSWORD", "")
            if not username or not password:
                raise RuntimeError(
                    "OCP_ADMIN_USER_USERNAME and OCP_ADMIN_USER_PASSWORD must be set "
                    "for BYOIDC job submission"
                )
            issuer_url = get_byoidc_issuer_url()
            id_token, _ = get_oidc_tokens(username, password, issuer_url)
            if not id_token:
                raise RuntimeError(
                    "Failed to obtain OIDC token for Ray Dashboard authentication"
                )
            return RayJobClient(
                address=cluster.cluster_dashboard_uri(),
                headers={"Authorization": f"Bearer {id_token}"},
                verify=False,
            )

        auth_token = run_oc_command(["whoami", "--show-token=true"])
        header = {"Authorization": f"Bearer {auth_token}"} if auth_token else {}
        return RayJobClient(
            address=cluster.cluster_dashboard_uri(),
            headers=header,
            verify=False,
        )

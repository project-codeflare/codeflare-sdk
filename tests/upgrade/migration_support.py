# Copyright 2024 IBM, Red Hat
#
# Invoke scripts/migration/ray_cluster_migration.py from upgrade tests (no duplicated logic).

import os
import subprocess
import sys
from pathlib import Path
from typing import List

from kubernetes import client, config
from kubernetes.client.rest import ApiException

from tests.upgrade.constants import (
    CLUSTER_NAME,
    NAMESPACE,
    SECURE_NETWORK_ANNOTATION,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MIGRATION_SCRIPT = PROJECT_ROOT / "scripts" / "migration" / "ray_cluster_migration.py"
DEFAULT_BACKUP_BASE = os.environ.get(
    "RHOAI_UPGRADE_BACKUP_DIR", "/tmp/rhoai-upgrade-backup"
)

SUPPRESS_TLS_WARNINGS_ENV = "RAY_CLUSTER_MIGRATION_SUPPRESS_TLS_WARNINGS"
_PYTHONWARNINGS_TLS_FILTER = "ignore::urllib3.exceptions.InsecureRequestWarning"

_post_upgrade_invoked = False


def _suppress_migration_tls_warnings() -> bool:
    value = os.environ.get(SUPPRESS_TLS_WARNINGS_ENV, "1").strip().lower()
    return value not in ("0", "false", "no", "off")


def _migration_subprocess_env(backup_base_dir: str) -> dict:
    env = os.environ.copy()
    env["RHOAI_UPGRADE_BACKUP_DIR"] = backup_base_dir
    if _suppress_migration_tls_warnings():
        existing = env.get("PYTHONWARNINGS", "").strip()
        env["PYTHONWARNINGS"] = (
            f"{existing},{_PYTHONWARNINGS_TLS_FILTER}"
            if existing
            else _PYTHONWARNINGS_TLS_FILTER
        )
    return env


def mark_migration_post_upgrade_invoked() -> None:
    global _post_upgrade_invoked
    _post_upgrade_invoked = True


def migration_post_upgrade_was_invoked() -> bool:
    return _post_upgrade_invoked


def run_migration_post_upgrade(
    namespace: str = NAMESPACE,
    cluster_name: str = CLUSTER_NAME,
    backup_base_dir: str = DEFAULT_BACKUP_BASE,
    dry_run: bool = False,
) -> subprocess.CompletedProcess:
    """
    Run ray_cluster_migration.py post-upgrade for the qualification RayCluster.

    Uses --yes for non-interactive CI/container runs. Idempotent when already migrated.
    """
    if not MIGRATION_SCRIPT.is_file():
        raise FileNotFoundError(
            f"Migration script not found at {MIGRATION_SCRIPT}. "
            "Ensure scripts/migration/ray_cluster_migration.py is present."
        )

    cmd: List[str] = [
        sys.executable,
        str(MIGRATION_SCRIPT),
        "post-upgrade",
        "--namespace",
        namespace,
        "--cluster",
        cluster_name,
        "--yes",
    ]
    if dry_run:
        cmd.append("--dry-run")

    env = _migration_subprocess_env(backup_base_dir)

    print(f"\n=== Running migration post-upgrade: {' '.join(cmd)} ===\n")
    result = subprocess.run(
        cmd,
        cwd=str(PROJECT_ROOT),
        env=env,
        capture_output=False,
        text=True,
        check=False,
    )
    mark_migration_post_upgrade_invoked()
    return result


def _load_kube_config() -> None:
    try:
        config.load_kube_config(
            config_file=os.environ.get(
                "KUBECONFIG", os.path.expanduser("~/.kube/config")
            )
        )
    except config.ConfigException:
        config.load_incluster_config()


def raycluster_exists(
    namespace: str = NAMESPACE, cluster_name: str = CLUSTER_NAME
) -> bool:
    _load_kube_config()
    api = client.CustomObjectsApi()
    try:
        api.get_namespaced_custom_object(
            group="ray.io",
            version="v1",
            namespace=namespace,
            plural="rayclusters",
            name=cluster_name,
        )
        return True
    except ApiException as e:
        if e.status == 404:
            return False
        raise


def assert_raycluster_migrated_if_present(
    namespace: str = NAMESPACE,
    cluster_name: str = CLUSTER_NAME,
) -> None:
    """Assert 2→3 migration markers on the qualification RayCluster when it exists."""
    if not raycluster_exists(namespace, cluster_name):
        raise AssertionError(
            f"RayCluster '{cluster_name}' not found in '{namespace}' after post-upgrade. "
            "Run pre_upgrade seed tests before the RHOAI upgrade."
        )

    _load_kube_config()
    api = client.CustomObjectsApi()
    rc = api.get_namespaced_custom_object(
        group="ray.io",
        version="v1",
        namespace=namespace,
        plural="rayclusters",
        name=cluster_name,
    )
    annotations = (rc.get("metadata") or {}).get("annotations") or {}
    if annotations.get(SECURE_NETWORK_ANNOTATION) != "true":
        raise AssertionError(
            f"RayCluster '{cluster_name}' missing {SECURE_NETWORK_ANNOTATION}=true "
            "after post-upgrade migration."
        )
    print(
        f"Confirmed RayCluster '{cluster_name}' has {SECURE_NETWORK_ANNOTATION}=true."
    )


def assert_raycluster_ready_after_post_upgrade(
    namespace: str = NAMESPACE,
    cluster_name: str = CLUSTER_NAME,
    timeout: int = 600,
) -> None:
    from codeflare_sdk.ray.cluster.cluster import get_cluster

    from tests.e2e.support import wait_ready_with_stuck_detection

    # Match pre_upgrade seed tests: rh-ai gateway uses cluster ingress CA (verify fails locally).
    cluster = get_cluster(cluster_name, namespace, verify_tls=False)
    if not cluster:
        raise AssertionError(
            f"RayCluster '{cluster_name}' not found in '{namespace}' for readiness check."
        )

    wait_ready_with_stuck_detection(cluster, timeout=timeout)
    _, ready = cluster.status()
    if not ready:
        raise AssertionError(
            f"RayCluster '{cluster_name}' is not Ready after post-upgrade migration."
        )
    print(f"RayCluster '{cluster_name}' is Ready after post-upgrade migration.")

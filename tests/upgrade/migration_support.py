# Copyright 2024 IBM, Red Hat
#
# Helpers to invoke rhoai-upgrade-helpers ray_cluster_migration.py without duplicating logic.

import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Tuple

from kubernetes import client, config
from kubernetes.client.rest import ApiException

from tests.upgrade.constants import (
    CLUSTER_NAME,
    NAMESPACE,
    PRE_UPGRADE_BACKUP_ANNOTATION,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MIGRATION_SCRIPT = PROJECT_ROOT / "scripts" / "migration" / "ray_cluster_migration.py"
DEFAULT_BACKUP_BASE = os.environ.get(
    "RHOAI_UPGRADE_BACKUP_DIR", "/tmp/rhoai-upgrade-backup"
)

# Set to 0/false/no/off to allow urllib3 InsecureRequestWarning when invoking the script.
SUPPRESS_TLS_WARNINGS_ENV = "RAY_CLUSTER_MIGRATION_SUPPRESS_TLS_WARNINGS"
_PYTHONWARNINGS_TLS_FILTER = "ignore::urllib3.exceptions.InsecureRequestWarning"

_finalize_invoked = False


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


def mark_migration_pre_upgrade_invoked() -> None:
    global _finalize_invoked
    _finalize_invoked = True


def migration_pre_upgrade_was_invoked() -> bool:
    return _finalize_invoked


def run_migration_pre_upgrade(
    namespace: str = NAMESPACE,
    cluster_name: str = CLUSTER_NAME,
    backup_base_dir: str = DEFAULT_BACKUP_BASE,
) -> subprocess.CompletedProcess:
    """
    Run ray_cluster_migration.py pre-upgrade (upstream rhoai-upgrade-helpers).

    Backups go to $RHOAI_UPGRADE_BACKUP_DIR/ray/ (script default: /tmp/rhoai-upgrade-backup/ray/).
    """
    if not MIGRATION_SCRIPT.is_file():
        raise FileNotFoundError(
            f"Migration script not found at {MIGRATION_SCRIPT}. "
            "Ensure scripts/migration/ray_cluster_migration.py is present."
        )

    cmd: List[str] = [
        sys.executable,
        str(MIGRATION_SCRIPT),
        "pre-upgrade",
        "--namespace",
        namespace,
        "--cluster",
        cluster_name,
    ]

    env = _migration_subprocess_env(backup_base_dir)

    print(f"\n=== Running migration pre-upgrade: {' '.join(cmd)} ===\n")
    print(f"RHOAI_UPGRADE_BACKUP_DIR={backup_base_dir} (backups under .../ray/)\n")
    result = subprocess.run(
        cmd,
        cwd=str(PROJECT_ROOT),
        env=env,
        capture_output=False,
        text=True,
        check=False,
    )
    mark_migration_pre_upgrade_invoked()
    return result


def get_codeflare_management_state() -> Tuple[Optional[str], str]:
    """
    Return (managementState, dsc_name) for the codeflare DSC component.
    managementState is None if DSC or codeflare component is missing.
    """
    try:
        config.load_kube_config(
            config_file=os.environ.get(
                "KUBECONFIG", os.path.expanduser("~/.kube/config")
            )
        )
    except config.ConfigException:
        config.load_incluster_config()

    custom_api = client.CustomObjectsApi()
    dscs = custom_api.list_cluster_custom_object(
        group="datasciencecluster.opendatahub.io",
        version="v1",
        plural="datascienceclusters",
    )
    items = dscs.get("items") or []
    if not items:
        return None, ""

    dsc = items[0]
    name = dsc.get("metadata", {}).get("name", "unknown")
    components = dsc.get("spec", {}).get("components") or {}
    codeflare = components.get("codeflare") or {}
    return (codeflare.get("managementState"), name)


def assert_codeflare_removed() -> None:
    state, dsc_name = get_codeflare_management_state()
    if state is None:
        raise AssertionError(
            "DataScienceCluster has no codeflare component; "
            "cannot confirm codeflare Removed before RHOAI upgrade."
        )
    if (state or "").lower() != "removed":
        raise AssertionError(
            f"DataScienceCluster '{dsc_name}' codeflare managementState is '{state}', "
            "expected 'Removed' before RHOAI upgrade. "
            "RHOAI upgrade will fail if this is not set."
        )
    print(f"Confirmed codeflare is Removed on DataScienceCluster '{dsc_name}'.")


def assert_raycluster_pre_upgrade_artifacts_if_present(
    namespace: str = NAMESPACE,
    cluster_name: str = CLUSTER_NAME,
) -> None:
    """
    Optional checks when the qualification RayCluster exists after migration pre-upgrade.
    """
    try:
        config.load_kube_config(
            config_file=os.environ.get(
                "KUBECONFIG", os.path.expanduser("~/.kube/config")
            )
        )
    except config.ConfigException:
        config.load_incluster_config()

    api = client.CustomObjectsApi()
    try:
        rc = api.get_namespaced_custom_object(
            group="ray.io",
            version="v1",
            namespace=namespace,
            plural="rayclusters",
            name=cluster_name,
        )
    except ApiException as e:
        if e.status == 404:
            print(
                f"No RayCluster '{cluster_name}' in '{namespace}' after pre-upgrade "
                "(seed may have failed); DSC codeflare Removed is still required."
            )
            return
        raise

    head_spec = (rc.get("spec") or {}).get("headGroupSpec") or {}
    enable_ingress = head_spec.get("enableIngress")
    if enable_ingress is not False:
        raise AssertionError(
            f"RayCluster '{cluster_name}' enableIngress should be false after "
            f"migration pre-upgrade, got: {enable_ingress}"
        )

    annotations = (rc.get("metadata") or {}).get("annotations") or {}
    if PRE_UPGRADE_BACKUP_ANNOTATION not in annotations:
        print(
            f"Note: RayCluster missing {PRE_UPGRADE_BACKUP_ANNOTATION} annotation "
            "(non-fatal if backup step was skipped for this cluster)."
        )

    _assert_no_ray_owned_routes(namespace)


def _assert_no_ray_owned_routes(namespace: str) -> None:
    dynamic = client.ApiClient()
    try:
        route_api = client.CustomObjectsApi(dynamic)
        routes = route_api.list_namespaced_custom_object(
            group="route.openshift.io",
            version="v1",
            namespace=namespace,
            plural="routes",
        )
    except ApiException:
        print(f"Could not list routes in {namespace}; skipping route assertion.")
        return

    for item in routes.get("items") or []:
        name = item.get("metadata", {}).get("name", "")
        for owner in (item.get("metadata") or {}).get("ownerReferences") or []:
            if owner.get("kind") == "RayCluster" and owner.get("apiVersion", "").startswith(
                "ray.io/"
            ):
                raise AssertionError(
                    f"OpenShift Route '{namespace}/{name}' still owned by a RayCluster; "
                    "migration pre-upgrade should have removed it."
                )

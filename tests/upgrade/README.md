# Ray upgrade tests (codeflare-sdk)

Qualification tests for RHOAI **2.25 → 3.x** upgrade. Post-upgrade migration logic is developed on the `v0.36` branch; this branch (`v0.31-pre-upgrade`) covers **pre_upgrade** only.

## Pre-upgrade flow

Run in a **single** pytest session, then stop. Do not run OLM upgrade in the same session.

```text
pytest -m pre_upgrade
  01_raycluster_sdk_upgrade_test.py   # seed RayCluster mnist + Kueue objects
  02_dashboard_ui_upgrade_test.py     # Workload Metrics UI (optional if seed failed)
  03_ray_migration_pre_upgrade_finalize_test.py  # migration script + DSC assert
→ RHOAI OLM upgrade (outside this repo)
→ pytest -m post_upgrade   # later, on v0.36 branch
```

The final step invokes `scripts/migration/ray_cluster_migration.py` from **rhoai-upgrade-helpers** (vendored, no logic duplication). It sets **`codeflare: Removed`** on the DataScienceCluster and applies other Ray pre-upgrade steps when clusters exist.

**After finalize:** nothing else on that cluster until OLM upgrade (or lab revert below).

## Container

The test image `run-tests.sh` on this branch uses a single marker expression, default **`pre_upgrade and not post_upgrade`**. Passing **`-m post_upgrade` fails immediately** (before RBAC/login/cleanup). Oauth e2e and unmarked upgrade helpers are not run unless you pass a different `-m` (still combined with `and not post_upgrade`).

```bash
E2E_TEST_IMAGE_VERSION=test make build-test-image

podman run --rm --platform linux/amd64 --pull=never \
  -v "${KUBECONFIG:-$HOME/.kube/config}:/codeflare-sdk/tests/.kube/config:ro \
  -v ./tests/results:/codeflare-sdk/tests/results:Z \
  --env-file /path/to/cluster-env-file \
  quay.io/opendatahub/codeflare-sdk-tests:test
```

`-m pre_upgrade` is accepted and becomes `pre_upgrade and not post_upgrade`.

Backups are written under `$RHOAI_UPGRADE_BACKUP_DIR/ray` (default `/tmp/rhoai-upgrade-backup/ray`). Not required for the in-place post-upgrade path.

### Migration script

Vendored from [rhoai-upgrade-helpers](https://github.com/red-hat-data-services/rhoai-upgrade-helpers) — keep `scripts/migration/ray_cluster_migration.py` in sync.

| Variable | Default | Effect |
|----------|---------|--------|
| `RHOAI_UPGRADE_BACKUP_DIR` | `/tmp/rhoai-upgrade-backup` | Backup root for pre-upgrade (`.../ray/rhoai-2.x`, `.../rhoai-3.x`) |
| `RAY_CLUSTER_MIGRATION_SUPPRESS_TLS_WARNINGS` | `1` | Script calls `urllib3.disable_warnings` for `InsecureRequestWarning`; set `0` to show warnings |

Manual pre-upgrade (same cluster as tests):

```bash
python scripts/migration/ray_cluster_migration.py pre-upgrade \
  --namespace test-ns-rayupgrade --cluster mnist
```

**Known flake (fresh cluster):** first pre-upgrade may briefly leave Ray-owned Routes if KubeRay reconciles slowly; reruns usually pass. Script sets `enableIngress: false` before route delete and polls — see `upgrades/script_fix_suggestion.md` in qualification notes.

## Retry after failure

| Situation | Action |
|-----------|--------|
| Seed/UI failed **before** finalize | Delete `test-ns-rayupgrade`, rerun `-m pre_upgrade` (DSC can stay Managed). |
| Finalize ran (`codeflare: Removed`) | Do **not** OLM-upgrade. Delete namespace, patch DSC `codeflare` → `Managed`, rerun `-m pre_upgrade`. |

## Constants

See `constants.py`: namespace `test-ns-rayupgrade`, cluster `mnist`.

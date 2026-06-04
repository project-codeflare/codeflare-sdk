# Vendored from rhoai-upgrade-helpers

Ray cluster migration for RHOAI 2.x → 3.x. Invoked by upgrade tests; do not duplicate logic in pytest.

**Source of truth:** [red-hat-data-services/rhoai-upgrade-helpers](https://github.com/red-hat-data-services/rhoai-upgrade-helpers) (`ray/ray_cluster_migration.py` on `main`).

**Pinned commit when last refreshed:** `a9aa2e6` (file last changed in `743f063`).

Refresh (no drift) from a **separate** [rhoai-upgrade-helpers](https://github.com/red-hat-data-services/rhoai-upgrade-helpers) clone on `main` (run from the root of your codeflare-sdk clone):

```bash
HELPERS_REPO=/path/to/rhoai-upgrade-helpers
git -C "$HELPERS_REPO" fetch origin main && git -C "$HELPERS_REPO" pull --ff-only origin main
cp "$HELPERS_REPO/ray/ray_cluster_migration.py" scripts/migration/ray_cluster_migration.py
git -C "$HELPERS_REPO" rev-parse HEAD   # update pinned commit below
```

Do **not** copy from an old codeflare-sdk revision or another stale checkout.

```bash
python scripts/migration/ray_cluster_migration.py pre-upgrade \
  --namespace test-ns-rayupgrade --cluster mnist
# Backups: $RHOAI_UPGRADE_BACKUP_DIR/ray/ (default /tmp/rhoai-upgrade-backup/ray/)
```

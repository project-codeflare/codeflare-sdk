# Ray upgrade tests (`tests/upgrade/`)

Qualification flow for RHOAI Ray upgrades ([RHOAIENG-63109](https://issues.redhat.com/browse/RHOAIENG-63109)). Parent program: [RHAISTRAT-1519](https://redhat.atlassian.net/browse/RHAISTRAT-1519).

Upgrade qualification uses **two codeflare-sdk branches** and **two container runs** on the **same cluster** (same kubeconfig): pre on **2.25**, then OLM upgrade, then post on **3.x**.

---

## Branches and PRs

| Phase | When | RHOAI | codeflare-sdk branch | Base | Tests in image |
|-------|------|-------|----------------------|------|----------------|
| **Pre-upgrade** | Before OLM upgrade | **2.25.x** | **`v0.31-pre-upgrade-clean`** | `v0.31` (`origin/v0.31`, ~0.31.5) | `pre_upgrade` only (see that branch’s README for image guard) |
| **Post-upgrade** | After OLM upgrade | **3.x** (e.g. 3.3, 3.5 EA) | **`2.x-3.x-upgrade-tests-post-upgrade`** | **`main`** | `post_upgrade` (this branch) |

- **Pre-upgrade branch** (`v0.31-pre-upgrade-clean`): seeds RayCluster, optional UI check, runs migration **pre-upgrade** (`codeflare: Removed`, route cleanup, backup). Does **not** include post-upgrade finalize tests (`00_*`, post migration helpers on this tree).
- **Post-upgrade branch** (`2.x-3.x-upgrade-tests-post-upgrade`, merged to `main`): migration **post-upgrade**, MNIST job submit, UI after upgrade. Assumes pre phase already ran on the cluster (or equivalent lab state).
- Branch-specific notes may also exist on **`v0.31-pre-upgrade-clean`** (`tests/upgrade/README.md` there focuses on pre only). **This file** is the consolidated guide on the post-upgrade line.

**Jenkins / CI:** runs the published test image twice with `-m pre_upgrade` then `-m post_upgrade`; implementation lives in codeflare-sdk, not in Jenkins.

---

## End-to-end flow (2.25 → 3.x)

```text
[Cluster: RHOAI 2.25.x, ray Managed, kueue Unmanaged, …]

1. Build image from v0.31-pre-upgrade-clean
2. pytest -m pre_upgrade   (single session, then stop)
     01  Seed RayCluster mnist + Kueue (test-ns-rayupgrade)
     02  Dashboard UI (Workload Metrics) — optional if seed failed
     03  Migration pre-upgrade finalize (script + DSC codeflare Removed)
3. RHOAI OLM upgrade (outside this repo; channel per target, e.g. support-required-upgrade → 3.3, beta → 3.5 EA)

4. Build image from 2.x-3.x-upgrade-tests-post-upgrade (main)
5. pytest -m post_upgrade
     00  Migration post-upgrade finalize
     02  Dashboard UI
     01  MNIST job submission
```

Use the **same** namespace (`test-ns-rayupgrade`) and cluster name (`mnist`) across pre and post. See `constants.py`.

---

## Markers

| Marker | Phase | Typical branch / image |
|--------|-------|-------------------------|
| `pre_upgrade` | Before RHOAI OLM upgrade | **`v0.31-pre-upgrade-clean`** on 2.25 |
| `post_upgrade` | After RHOAI OLM upgrade | **`2.x-3.x-upgrade-tests-post-upgrade`** (`main`) on 3.x |
| `ui` | With pre or post UI tests | Combine: `-m "pre_upgrade and ui"` or `-m "post_upgrade and ui"` |

---

## Pre-upgrade (branch `v0.31-pre-upgrade-clean`)

Run in **one** pytest session on **RHOAI 2.25**, then stop. Do **not** run OLM upgrade in the same session.

### Test order

1. `01_raycluster_sdk_upgrade_test.py` — seed `RayCluster` + Kueue objects
2. `02_dashboard_ui_upgrade_test.py` — Workload Metrics UI (skipped meaningfully if seed failed)
3. `03_ray_migration_pre_upgrade_finalize_test.py` — `ray_cluster_migration.py pre-upgrade`

The finalize step (vendored from [rhoai-upgrade-helpers](https://github.com/red-hat-data-services/rhoai-upgrade-helpers)) sets **`codeflare: Removed`** on `DataScienceCluster` and other Ray pre-upgrade steps when clusters exist.

**After finalize:** do not re-seed on 2.25 without reverting DSC (see [Retry after failure](#retry-after-failure)).

### Build and run (pre)

On **`v0.31-pre-upgrade-clean`**:

```bash
E2E_TEST_IMAGE_VERSION=test make build-test-image

podman run --rm --platform linux/amd64 --pull=never \
  -v "${KUBECONFIG:-$HOME/.kube/config}:/codeflare-sdk/tests/.kube/config:ro" \
  -v "$(pwd)/tests/results:/codeflare-sdk/tests/results:Z" \
  --env-file /path/to/cluster-env-file \
  quay.io/opendatahub/codeflare-sdk-tests:test
```

That branch’s `run-tests.sh` defaults to **`pre_upgrade and not post_upgrade`** and **rejects** `-m post_upgrade` early. Passing `-m pre_upgrade` is normalized to that expression.

```bash
pytest tests/upgrade/ -m pre_upgrade -v
```

Pre-upgrade backups: `$RHOAI_UPGRADE_BACKUP_DIR/ray` (default `/tmp/rhoai-upgrade-backup/ray`). Used for rollback / `post-upgrade --from-backup`; not required for the default in-place post-upgrade path on 3.x.

### Manual pre-upgrade script

```bash
export PYTHONWARNINGS='ignore::urllib3.exceptions.InsecureRequestWarning'
python scripts/migration/ray_cluster_migration.py pre-upgrade \
  --namespace test-ns-rayupgrade --cluster mnist
```

---

## Post-upgrade (branch `2.x-3.x-upgrade-tests-post-upgrade` / `main`)

Run on **RHOAI 3.x** after OLM upgrade, **same cluster** as pre.

### Test order

Collection order is enforced in `conftest.py`:

1. `00_ray_migration_post_upgrade_finalize_test.py` — `ray_cluster_migration.py post-upgrade`
2. `02_dashboard_ui_upgrade_test.py` — Workload Metrics UI
3. `01_raycluster_sdk_upgrade_test.py` — MNIST job submission

### Build and run (post)

On **`2.x-3.x-upgrade-tests-post-upgrade`** (or `main` after merge):

```bash
E2E_TEST_IMAGE_VERSION=test make build-test-image

podman run --rm --platform linux/amd64 --pull=never \
  -v "${KUBECONFIG:-$HOME/.kube/config}:/codeflare-sdk/tests/.kube/config:ro" \
  -v "$(pwd)/tests/results:/codeflare-sdk/tests/results:Z" \
  --env-file /path/to/cluster-env-file \
  quay.io/opendatahub/codeflare-sdk-tests:test \
  -m post_upgrade -v
```

```bash
pytest tests/upgrade/ -m post_upgrade -v
pytest tests/upgrade/ -m "post_upgrade and ui" -v
```

This branch’s `run-tests.sh` includes `tests/upgrade/*_test.py` in the default oauth/upgrade set; pass **`-m post_upgrade`** explicitly for the post phase so e2e oauth tests are not run unless intended.

### Manual post-upgrade script

```bash
python scripts/migration/ray_cluster_migration.py post-upgrade \
  --namespace test-ns-rayupgrade --cluster mnist --yes
```

---

## Cluster prerequisites (Testops / lab)

Installed **before** `pre_upgrade`; not created by these tests:

| Prerequisite | Notes |
|--------------|--------|
| RHOAI **2.25.x** for pre | e.g. `stable-2.25` → `rhods-operator.2.25.7` |
| **`ray: Managed`** | KubeRay via RHOAI |
| **`kueue: Unmanaged`** + RHBoK | Baseline for 3.x qualification path |
| **cert-manager** | General 3.x prerequisite (Testops) |
| **2→3:** `codeflare: Removed` before product upgrade | Pre finalize sets this; or manual per upgrade guide |
| Same kubeconfig | Pre and post jobs must target the same cluster |

For **2.25 → 3.5 EA**, use FBC channel **`beta`** from 2.25 (not `stable-2.25` → `stable-3.x` without a 2.25 bridge). For **2.25 → 3.3**, use **`support-required-upgrade`**. See program upgrade notes / `revised_todo.md` in the qualification repo.

---

## TLS / gateway dashboard (QE clusters)

On many QE clusters, `rh-ai.apps.*` uses an ingress certificate that fails TLS verification from the test runner.

- **Pre-upgrade** seed: `verify_tls=False` on `ClusterConfiguration`.
- **Post-upgrade:** `get_cluster(name, namespace, verify_tls=False)` when loading the existing cluster.

Without this, `cluster.wait_ready()` can hang on dashboard URL checks (`SSLError` treated as not ready even when **302** to OAuth is healthy). Bearer-token job tests are unaffected.

---

## BYOIDC detection (job submission)

Post-upgrade job tests use `is_byoidc_cluster_detected()` from `tests/e2e/support.py` (aligned with `images/tests/run-tests.sh` on the pre branch).

- **Not BYOIDC:** `status.oidcClients` with `componentName: cli` alone (normal on standard OpenShift).
- **BYOIDC indicators:** `Authentication.spec.type == OIDC`, Keycloak issuer on `spec.oidcProviders` (rh-ods.com / qe.rh-ods.com), webhook token authenticators, or **`oc-cli`** in `status.oidcClients`.

On **htpasswd/LDAP** QE clusters, job tests use `oc whoami --show-token=true` with `OCP_ADMIN_USER_*` — not Keycloak password grant.

---

## Migration script

`scripts/migration/ray_cluster_migration.py` — keep in sync with [rhoai-upgrade-helpers](https://github.com/red-hat-data-services/rhoai-upgrade-helpers) `main`.

| Variable | Default | Effect |
|----------|---------|--------|
| `RHOAI_UPGRADE_BACKUP_DIR` | `/tmp/rhoai-upgrade-backup` | Backup root for pre-upgrade |
| `RAY_CLUSTER_MIGRATION_SUPPRESS_TLS_WARNINGS` | `1` | Suppress urllib3 `InsecureRequestWarning` during script (pytest sets `PYTHONWARNINGS` when `1`) |

Annotations (see `constants.py`): `odh.ray.io/pre-upgrade-backup-taken`, `odh.ray.io/secure-trusted-network` (post-migration).

**Known flake (pre, fresh cluster):** first `pre-upgrade` run may fail route assertion if KubeRay recreates Routes before `enableIngress: false` is applied; reruns usually pass. See qualification notes `script_fix_suggestion.md`.

---

## Retry after failure

| Situation | Action |
|-----------|--------|
| Pre: seed/UI failed **before** finalize | Delete `test-ns-rayupgrade`, rerun `-m pre_upgrade` (DSC `codeflare` can stay Managed). |
| Pre: finalize ran (`codeflare: Removed`) | Do **not** OLM-upgrade yet. Delete namespace, patch DSC `codeflare` → `Managed`, rerun `-m pre_upgrade` on **`v0.31-pre-upgrade-clean`**. |
| Post: migration or job/UI failed | Fix cluster/3.x state; rerun `-m post_upgrade` on **`2.x-3.x-upgrade-tests-post-upgrade`**. Idempotent post-upgrade skips already-migrated CRs. |

---

## Constants

`constants.py`:

- Namespace: `test-ns-rayupgrade`
- RayCluster: `mnist`
- Kueue: `cluster-queue-mnist`, `local-queue-mnist`, `default-flavor-mnist`

---

## Out of scope

- KFTO, kuberay lake gate, operator-chaos, opendatahub-tests as primary implementation
- Jenkins pipeline development (invoke image + markers only)
- Installing RHOAI or operators beyond what the migration script adjusts during finalize

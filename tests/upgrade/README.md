# Ray upgrade tests (`tests/upgrade/`)

Qualification flow for RHOAI Ray upgrades ([RHOAIENG-63109](https://issues.redhat.com/browse/RHOAIENG-63109)).

## Markers

| Marker | When | Image / branch (typical) |
|--------|------|---------------------------|
| `pre_upgrade` | Before RHOAI OLM upgrade | 2.25 / `v0.31*` — seed RayCluster, UI check, migration pre-upgrade |
| `post_upgrade` | After RHOAI OLM upgrade | 3.x / `v0.36*` — migration post-upgrade, then job + UI tests |

## Post-upgrade order (2.25 → 3.5)

1. `00_ray_migration_post_upgrade_finalize_test.py` — `ray_cluster_migration.py post-upgrade`
2. `02_dashboard_ui_upgrade_test.py` — Workload Metrics UI
3. `01_raycluster_sdk_upgrade_test.py` — MNIST job submission

## Run

```bash
pytest tests/upgrade/ -m post_upgrade -v
pytest tests/upgrade/ -m "post_upgrade and ui" -v
```

## TLS / gateway dashboard (QE clusters)

On many OpenShift QE clusters, the `rh-ai.apps.*` Gateway uses an ingress certificate that fails standard TLS verification from the test runner (self-signed or cluster CA not trusted locally).

- **Pre-upgrade** seed tests set `verify_tls=False` on `ClusterConfiguration`.
- **Post-upgrade** tests must use the same when loading an existing cluster: `get_cluster(name, namespace, verify_tls=False)`.

Without this, `cluster.wait_ready()` can hang forever on:

```text
Waiting for dashboard to become accessible: https://rh-ai.apps.<cluster>/ray/...
```

because `is_dashboard_ready()` treats `SSLError` as “not ready”, even when the route returns **302** to OAuth (which is healthy).

This does not disable auth for job submission tests that use bearer tokens; it only affects HTTPS checks to the external dashboard URL.

## BYOIDC detection (job submission tests)

Post-upgrade job tests use `is_byoidc_cluster_detected()` from `tests/e2e/support.py` (aligned with `images/tests/run-tests.sh`).

**Not BYOIDC:** `status.oidcClients` with `componentName: cli` is normal on standard OpenShift (console/oc CLI) — do not use that alone.

**BYOIDC indicators:** `Authentication.spec.type == OIDC`, Keycloak issuer on `spec.oidcProviders`, webhook token authenticators, or `oc-cli` in `status.oidcClients`.

On **htpasswd/LDAP** QE clusters (e.g. ods-qe-psi-17), job tests use `oc whoami --show-token=true` with `OCP_ADMIN_USER_*` credentials — not Keycloak password grant.

## Disconnected clusters (post-upgrade and tier1 job submission)

Full MNIST installs torch via pip and may fetch datasets from the public internet. On disconnected clusters that fails unless mirrors are configured.

Post-upgrade and tier1 MNIST job tests use `get_mnist_job_submission_spec()` from `tests/e2e/support.py`:

| Job | When |
|-----|------|
| **`upgrade_job_smoke.py`** (no pip) | Disconnected / mirror-only cluster without PyPI + S3 env |
| **`mnist.py`** (full pip + training) | Connected cluster, or disconnected with `PIP_INDEX_URL` (non-pypi.org) **and** `AWS_DEFAULT_ENDPOINT` set |

**Detection order:** `USE_SMOKE_JOB` / `UPGRADE_USE_SMOKE_JOB` override → MNIST prerequisites → `DISCONNECTED_CLUSTER` / `IS_DISCONNECTED_CLUSTER` (Jenkins) → API URL `-dis-` heuristic (last resort).

Registry image mirrors (`ImageDigestMirrorSet` / `ICSP`) are **not** used for detection — connected OpenShift clusters often have them without blocking pip.

Set `USE_SMOKE_JOB=false` or `UPGRADE_USE_SMOKE_JOB=false` to force full MNIST when mirrors are configured. Set `DISCONNECTED_CLUSTER=true` in the test env file for explicit lab config (aligns with Jenkins `IS_DISCONNECTED_CLUSTER`).

## Migration script

`scripts/migration/ray_cluster_migration.py` (keep in sync with [rhoai-upgrade-helpers](https://github.com/red-hat-data-services/rhoai-upgrade-helpers) `main`).

Optional env: `RHOAI_UPGRADE_BACKUP_DIR`, `RAY_CLUSTER_MIGRATION_SUPPRESS_TLS_WARNINGS` (default `1`).

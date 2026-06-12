# Ray upgrade tests (`tests/upgrade/`)

Qualification flow for RHOAI Ray upgrades ([RHOAIENG-63109](https://issues.redhat.com/browse/RHOAIENG-63109)). Parent program: [RHAISTRAT-1519](https://redhat.atlassian.net/browse/RHAISTRAT-1519).

**Documentation handoff:** [RHOAIENG-63115](https://redhat.atlassian.net/browse/RHOAIENG-63115) — this file is the component test-directory guide for coverage, limitations, ownership, and follow-ups.

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
| `RAY_CLUSTER_MIGRATION_SUPPRESS_TLS_WARNINGS` | `1` | Suppress urllib3 `InsecureRequestWarning` in the script via `urllib3.disable_warnings` |

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

## Upgrade path coverage

Documented for [RHOAIENG-63115](https://redhat.atlassian.net/browse/RHOAIENG-63115) handoff. Primary qualification target: **RHOAI 2.25.7 → 3.5 EA** on the same cluster.

| Upgrade path | Status | Notes |
|--------------|--------|-------|
| **2.25 → 3.5 EA** (`stable-2.25` → `beta`) | **Covered** | Primary path exercised in manual qualification; FBC channel graph documented above |
| **2.25 → 3.3** (`stable-2.25` → `support-required-upgrade`) | **Supported, not routinely qualified** | Same pre/post test flow and migration script; OLM channel differs |
| **3.x → 3.x** (e.g. `stable-3.x` within channel) | **Light coverage** | Post-upgrade skips 2→3 normalize when CR has no 2.x legacy; no dedicated 3.x→3.x qualification runbook yet |
| **3.3 / 3.4** as explicit targets | **TBD** | Port/adapt after 2.25→3.5 path is green — see [Known gaps](#known-gaps-and-follow-ups) |
| **GPU allocation survival** | **Not asserted** | 63111 mentions GPU checks; current tests do not validate GPU state across upgrade |
| **Cross-component workflows** | **Out of scope** | Owned by feature / program teams under RHAISTRAT-1519 |
| **opendatahub-tests mirror suite** | **Out of scope** | Implementation lives in codeflare-sdk; not a parallel opendatahub-tests tree |

What these tests **do** validate on the covered 2→3 path:

- Pre: RayCluster + Kueue seed, optional Workload Metrics UI, migration pre-finalize (`codeflare: Removed`, route cleanup, backup)
- Post: migration post-finalize (2.x artefact strip / Gateway readiness), UI, MNIST RayJob submission on surviving cluster

What they **do not** validate:

- OLM upgrade orchestration itself (channel switch, bundle selection) — Testops / upgrade job
- Operator install or DSC changes beyond migration script finalize steps
- KubeRay operator behaviour in isolation — see [Shift-left validation](#shift-left-validation-operator-chaos) and kuberay lake gate

---

## Maintenance and ownership

| Area | Owner | When to update |
|------|-------|----------------|
| `tests/upgrade/*`, pytest markers, `conftest.py` ordering | **Ray / codeflare-sdk** (distributed-workloads team) | Test flow, SDK job API, UI selectors, or cluster auth detection changes |
| `images/tests/` (Dockerfile, `run-tests.sh`, RBAC manifest) | **Ray / codeflare-sdk** | Container entrypoint, marker guards, env-file contract |
| `scripts/migration/ray_cluster_migration.py` (vendored copy) | **Ray team** — keep in sync with [rhoai-upgrade-helpers](https://github.com/red-hat-data-services/rhoai-upgrade-helpers) `main` | Migration behaviour, CRD/annotation handling, or pre/post finalize steps change |
| `tests/upgrade/constants.py`, `migration_support.py` | **Ray / codeflare-sdk** | Qualification namespace/cluster IDs or wrapper behaviour |
| Cluster prerequisites (RHOAI install, DSC, RHBoK, cert-manager, FBC image/channels) | **Testops** | Qualification cluster profile changes |
| Same cluster + kubeconfig across pre/post Jenkins runs | **Testops / upgrade job** | Job wiring — not implemented in this repo |
| Jenkins shift-left registration (`components-tests.yaml`, `-m pre_upgrade` / `-m post_upgrade`) | **DevTestOps** — see [RHOAIENG-63114](https://redhat.atlassian.net/browse/RHOAIENG-63114) | Gate registry only; pipeline owned by DevTestOps |
| Pass/fail gating policy for release qualification | **Feature owner** ([RHAISTRAT-1519](https://redhat.atlassian.net/browse/RHAISTRAT-1519)) | Not owned by codeflare-sdk |
| Migration script source of truth (non-vendored) | **rhoai-upgrade-helpers** maintainers | Authoritative script changes land there first; vendored copy updated in both pre and post branches |

**Pre branch maintenance:** `v0.31-pre-upgrade-clean` (PR to `v0.31`) — pre_upgrade tests and vendored migration script for 2.25. Keep migration script aligned with this branch when helpers change.

**Post branch maintenance:** `2.x-3.x-upgrade-tests-post-upgrade` (PR to `main`) — post_upgrade tests and post-phase migration helpers. **This README** is the consolidated handoff doc after merge to `main`.

When Ray or KubeRay APIs change, expect coordinated updates in:

1. [opendatahub-io/kuberay](https://github.com/opendatahub-io/kuberay) (operator, CRDs, operator-chaos knowledge model)
2. [rhoai-upgrade-helpers](https://github.com/red-hat-data-services/rhoai-upgrade-helpers) (migration script)
3. codeflare-sdk `tests/upgrade/` and vendored `scripts/migration/` (this repo)

---

## Shift-left validation (operator-chaos)

Upgrade tests in this directory are **integration** validation on a live cluster (pre/post OLM upgrade). **PR-time** breaking-change detection for the KubeRay operator is separate — [RHOAIENG-63113](https://redhat.atlassian.net/browse/RHOAIENG-63113).

| Layer | Repo | Purpose |
|-------|------|---------|
| Integration (this doc) | codeflare-sdk `tests/upgrade/` | End-to-end Ray workload + migration script on qualification cluster |
| Shift-left | [opendatahub-io/kuberay](https://github.com/opendatahub-io/kuberay) | operator-chaos on PRs that touch APIs, CRDs, or controllers |

**Maturity adopted (63113):** **Level 1 + Level 2 (dry-run)** on the KubeRay operator repo.

- **Workflow:** [`.github/workflows/operator-chaos.yml`](https://github.com/opendatahub-io/kuberay/blob/dev/.github/workflows/operator-chaos.yml) on `dev` (runs on PRs touching `ray-operator/apis/**`, CRDs, controllers, or `chaos/knowledge/**`).
- **Level 1:** `operator-chaos diff` / `diff-crds` with `--breaking` — fails PR if breaking knowledge-model or CRD schema changes lack a documented migration path.
- **Level 2:** `operator-chaos simulate-upgrade --dry-run` against the knowledge model diff.
- **Knowledge model:** `chaos/knowledge/kuberay.yaml` in [opendatahub-io/kuberay](https://github.com/opendatahub-io/kuberay). **Maintain when** RayCluster / RayJob CRDs, webhook behaviour, or controller reconciliation logic changes — update the YAML in the same PR as the API/controller change.
- **Not adopted:** Level 3 (ChaosClient in controller integration tests) and Level 4 (OLM channel-hop playbook) — tracked as follow-ups under 63113 / Ray backlog.

These upgrade tests do **not** replace operator-chaos; they complement it (shift-left catches schema drift early; integration tests catch migration + workload behaviour on real clusters).

**KubeRay lake gate:** Jenkins `kuberay-lake-gate` runs Tier1 e2e against operator images built from `dev` — component verification, not part of this upgrade test suite. See [Known gaps](#known-gaps-and-follow-ups).

---

## Known limitations

| Limitation | Impact | Mitigation |
|------------|--------|------------|
| **Pre-upgrade route flake (fresh cluster)** | KubeRay may recreate OpenShift Routes before `enableIngress: false` is applied | Rerun `-m pre_upgrade`; see qualification notes `script_fix_suggestion.md` |
| **TLS on QE dashboard URLs** | `cluster.wait_ready()` may hang on `SSLError` | `verify_tls=False` on seed/load — documented in [TLS / gateway dashboard](#tls--gateway-dashboard-qe-clusters) |
| **Single qualification identity** | Tests assume `test-ns-rayupgrade` / `mnist` | Do not re-seed after pre finalize without DSC revert — see [Retry after failure](#retry-after-failure) |
| **Two-branch / two-image model** | Pre and post require different codeflare-sdk branches and images | Operational complexity; intentional for 2.25 SDK vs 3.x SDK lines |
| **BYOIDC vs htpasswd/LDAP** | Job submission auth path differs | Auto-detected; wrong env file causes post job failures |
| **FBC channel selection** | Wrong channel (e.g. `stable-2.25` → `stable-3.x`) blocks OLM 2→3 | Use `beta` (3.5 EA) or `support-required-upgrade` (3.3) — see [Cluster prerequisites](#cluster-prerequisites-testops--lab) |
| **Vendored migration script drift** | Pre/post branches can diverge from helpers `main` | Sync `scripts/migration/ray_cluster_migration.py` from rhoai-upgrade-helpers on every migration change |
| **No GPU assertion** | GPU-backed clusters not explicitly qualified | Follow-up — see below |

---

## Known gaps and follow-ups

Remaining gaps are **not** blockers for merging upgrade test implementation ([RHOAIENG-63111](https://redhat.atlassian.net/browse/RHOAIENG-63111)); track as separate Jira tickets under the [RHOAIENG-63109](https://redhat.atlassian.net/browse/RHOAIENG-63109) epic or Ray team backlog:

| Gap | Suggested owner | Notes |
|-----|-----------------|-------|
| Routine **3.3 / 3.4** upgrade qualification | Ray / Testops | Adapt channel + FBC pins after 2.25→3.5 path is green |
| Dedicated **3.x → 3.x** runbook and markers | Ray / codeflare-sdk | Light path exists; no formal qualification doc yet |
| **GPU allocation** survival across upgrade | Ray / codeflare-sdk | Called out in 63111; not implemented in current tests |
| **opendatahub-tests** parity (if program still requires) | Ray / opendatahub-tests | This repo is the primary implementation; mirror only if mandated |
| operator-chaos **Level 3 / 4** (ChaosClient, OLM playbook) | Ray / kuberay | Follow-on from [RHOAIENG-63113](https://redhat.atlassian.net/browse/RHOAIENG-63113) |
| **KFTO** / training-operator upgrade interactions | Feature team | Out of scope for Ray upgrade tests |
| Formal **data backup/restore** via OADP | Testops / program | 63111 mentions OCP backup procedures; tests use migration script backup dir only |

File follow-up Jira issues for items your team commits to address; link them from this table when created.

---

## Out of scope (this repository)

- **Jenkins pipeline development** — consumers invoke the published test image with `-m pre_upgrade` / `-m post_upgrade` only ([RHOAIENG-63114](https://redhat.atlassian.net/browse/RHOAIENG-63114))
- **Installing RHOAI or operators** beyond what the migration script adjusts during finalize
- **Cross-component upgrade scenarios** and **pass/fail release gating policy**
- **Primary implementation in opendatahub-tests** — see [Upgrade path coverage](#upgrade-path-coverage)

Related but owned elsewhere:

- **operator-chaos** — kuberay repo ([Shift-left validation](#shift-left-validation-operator-chaos))
- **KubeRay lake gate** — Jenkins shift-left on `dev` branch images
- **rhoai-upgrade-helpers** — migration script source of truth (vendored here)

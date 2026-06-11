# RayCluster Migration Tool for RHOAI 2.x to RHOAI 3.x

A standalone script for migrating RayClusters during RHOAI upgrades.

## Overview

This tool helps you safely migrate RayClusters when upgrading from RHOAI 2.x to RHOAI 3.x. It is designed to be run in stages, allowing you to test the migration on a single cluster before proceeding to an entire namespace or the whole Kubernetes cluster.

### Key Features

- **Staged Migration**: Test on a single cluster → proceed to namespace → then cluster-wide
- **Idempotent Operations**: Safe to run multiple times - already migrated clusters are skipped
- **Dry-Run Support**: Preview all changes before applying them
- **Clear Guidance**: Commands named for when to use them, not what they do

## Requirements

### Python Packages

Install the required Python packages:

```bash
pip install kubernetes>=28.1.0 PyYAML>=6.0
```

Or use the included requirements file:

```bash
pip install -r ray_cluster_migration_requirements.txt
```

### RBAC Permissions

The script requires different permissions depending on the command:

| Command | Permissions |
|---------|-------------|
| `list` | Read-only (RayClusters, Pods, Namespaces) |
| `pre-upgrade` | Read-only (creates local backup files only) |
| `post-upgrade` | Read + Write (RayClusters, ServiceAccounts) |
| `post-upgrade --from-backup` | Read + Write (RayClusters, ServiceAccounts) |

See [PERMISSIONS.md](PERMISSIONS.md) for detailed RBAC requirements and example Role/ClusterRole YAML.

## Authentication

The script uses standard Kubernetes authentication methods:
1. `KUBECONFIG` environment variable
2. `~/.kube/config` file
3. In-cluster config (when running inside a Kubernetes pod)

## Migration Workflow

The recommended migration workflow follows three stages:

### Stage 1: Pre-Upgrade (Before RHOAI Upgrade)

Backup your RayCluster configurations. This only creates backup files - it does NOT modify or delete any clusters.

```bash
# Backup all clusters (you'll be prompted for backup directory)
python ray_cluster_migration.py pre-upgrade

# Or specify the backup directory directly
python ray_cluster_migration.py pre-upgrade ./my-backup-dir

# Backup a specific namespace
python ray_cluster_migration.py pre-upgrade --namespace my-ns

# Backup a single cluster
python ray_cluster_migration.py pre-upgrade --cluster my-cluster --namespace my-ns
```

#### Backup Directory Structure

The pre-upgrade command creates two subdirectories in your backup location:

```
my-backup-dir/
  rhoai-2.x/   # RHOAI 2.x compatible (with CodeFlare components)
  rhoai-3.x/   # RHOAI 3.x compatible (ready for post-upgrade)
```

- **`rhoai-2.x/`**: Contains the original RayCluster YAMLs with all CodeFlare-operator components (TLS, OAuth proxy, etc.). Use these if you **did not proceed with the RHOAI 3.x upgrade** and need to restore your RayClusters.

- **`rhoai-3.x/`**: Contains cleaned RayCluster YAMLs with CodeFlare components removed. Use these with `post-upgrade --from-backup` to migrate to RHOAI 3.x.

**Important**: If you decide not to proceed with the upgrade and need to restore your clusters on RHOAI 2.x, use the files in `rhoai-2.x/`, not `rhoai-3.x/`.

### Stage 2: Perform the RHOAI Upgrade

Follow your standard RHOAI upgrade procedure.

### Stage 3: Post-Upgrade (After RHOAI Upgrade)

Migrate your RayClusters to be compatible with RHOAI 3.x.

```bash
# ALWAYS use --dry-run first to preview changes!

# Start with the same single cluster you tested backup with
python ray_cluster_migration.py post-upgrade --cluster my-cluster --namespace my-ns --dry-run
python ray_cluster_migration.py post-upgrade --cluster my-cluster --namespace my-ns

# Then migrate the entire namespace (you'll be prompted to confirm)
python ray_cluster_migration.py post-upgrade --namespace my-ns --dry-run
python ray_cluster_migration.py post-upgrade --namespace my-ns

# Finally, migrate all clusters (you'll be prompted to confirm)
python ray_cluster_migration.py post-upgrade --dry-run
python ray_cluster_migration.py post-upgrade
```

## Commands Reference

### `list` - Discover RayClusters and Migration Status

See all RayClusters and whether they need migration:

```bash
# List all clusters across all namespaces
python ray_cluster_migration.py list

# List clusters in a specific namespace
python ray_cluster_migration.py list --namespace my-ns

# Output as YAML for scripting
python ray_cluster_migration.py list --format yaml
```

Example output:
```
Found 3 RayCluster(s):

Name                      Namespace          Status       Workers  Migration Status
----------------------------------------------------------------------------------------------------
production-cluster        production         ready        5        [OK]
staging-cluster           staging            ready        3        [NEEDS MIGRATION]
dev-cluster               dev                ready        2        [NEEDS MIGRATION]

Migration Summary: 1 migrated, 2 need migration
```

### `pre-upgrade` - Backup Before RHOAI Upgrade

Runs pre-flight checks and creates backup YAML files of your RayCluster configurations. Run this BEFORE performing the RHOAI upgrade.

```bash
# Backup all clusters (you'll be prompted for backup directory)
python ray_cluster_migration.py pre-upgrade

# Or specify the backup directory directly
python ray_cluster_migration.py pre-upgrade ./my-backup-dir

# Backup all clusters in a namespace
python ray_cluster_migration.py pre-upgrade --namespace my-ns

# Backup a single cluster
python ray_cluster_migration.py pre-upgrade --cluster my-cluster --namespace my-ns
```

**What it does:**
- Runs pre-flight checks to verify the cluster is ready for upgrade
- Creates a backup directory if it doesn't exist
- Exports each RayCluster to a separate YAML file
- Does NOT delete or modify any clusters

**Pre-flight checks:**
- **cert-manager**: Verifies cert-manager is installed (required for RHOAI 3.x)

If a required check fails, you'll be warned and asked to confirm before proceeding:
```
Running pre-upgrade checks...
------------------------------------------------------------
  [FAIL] cert-manager: cert-manager not detected
       cert-manager is required for RHOAI 3.x. Install it via OperatorHub
       before proceeding with the upgrade.
------------------------------------------------------------

Pre-upgrade checks failed. Please resolve the issues above before
proceeding with the RHOAI upgrade.
```

**Idempotency:** Running this multiple times simply overwrites the backup files.

### `post-upgrade` - Migrate After RHOAI Upgrade

Migrates RayClusters to be compatible with RHOAI 3.x. Run this AFTER the RHOAI upgrade.

```bash
# Migrate a single cluster (always use --dry-run first!)
python ray_cluster_migration.py post-upgrade --cluster my-cluster --namespace my-ns --dry-run
python ray_cluster_migration.py post-upgrade --cluster my-cluster --namespace my-ns

# Migrate all clusters in a namespace (you'll be prompted to confirm)
python ray_cluster_migration.py post-upgrade --namespace my-ns --dry-run
python ray_cluster_migration.py post-upgrade --namespace my-ns

# Migrate all clusters across all namespaces (you'll be prompted to confirm)
python ray_cluster_migration.py post-upgrade --dry-run
python ray_cluster_migration.py post-upgrade

# Skip confirmation prompt (for automation)
python ray_cluster_migration.py post-upgrade --yes
```

**What it does:**
- Removes CodeFlare-operator TLS/OAuth components from the RayCluster spec
- The KubeRay operator handles pod recreation with the new configuration
- The `odh.ray.io/secure-trusted-network: "true"` annotation is added automatically by the KubeRay mutating webhook
- Displays the new Gateway API routes for accessing your clusters after migration

**Important:** Migration will cause temporary downtime for each RayCluster as pods are restarted with the updated configuration.

**Migration modes:**
- **Live migration** (default): Modifies existing RayClusters in-place
- **Restore from backup** (`--from-backup`): Deletes existing clusters and recreates from backup files

### Restore from Backup (`--from-backup`)

Use this mode if your clusters were deleted during the upgrade or you prefer a clean restore:

```bash
# Restore all clusters from the rhoai-3.x/ backup directory
python ray_cluster_migration.py post-upgrade --from-backup ./my-backup-dir/rhoai-3.x

# Restore clusters in a specific namespace
python ray_cluster_migration.py post-upgrade --from-backup ./my-backup-dir/rhoai-3.x --namespace my-ns

# Restore a single cluster
python ray_cluster_migration.py post-upgrade --from-backup ./my-backup-dir/rhoai-3.x --cluster my-cluster --namespace my-ns

# Restore from a single backup file
python ray_cluster_migration.py post-upgrade --from-backup ./my-backup-dir/rhoai-3.x/raycluster-my-cluster-my-ns.yaml
```

**Note**: Use the `rhoai-3.x/` subdirectory for 3.x migration. The `rhoai-2.x/` subdirectory contains 2.x-compatible backups for rollback scenarios.

**What `--from-backup` does:**
1. If a cluster with the same name exists, it is **deleted first**
2. Waits for the deletion to complete
3. Creates the cluster from the backup configuration
4. Waits for the cluster to become ready
5. Displays the dashboard URL

**Warning shown:**
```
WARNING: Restore from backup will DELETE and RECREATE each RayCluster.
  - If a cluster currently exists, it will be deleted first.
  - All running pods, jobs, and workloads will be terminated.
  - Existing job state and logs will be lost.
  - The cluster will be recreated from the backup configuration.
```

**Idempotency:** Already-migrated clusters are automatically detected and skipped.

**Example output (live migration):**
```
Analyzing 2 RayCluster(s) (all clusters in namespace 'my-ns')

  [MIGRATE] my-cluster (ns: my-ns) - needs migration
  [MIGRATE] test-cluster (ns: my-ns) - needs migration

Summary: 2 to migrate, 0 already migrated

  [my-cluster] Applying migration...
  [my-cluster] Waiting for cluster to become ready...
       Status: ready, workers: 2/2 (45s)
  [OK] Migrated: my-cluster (ns: my-ns)
       Dashboard: https://my-cluster-my-ns.apps.example.com

============================================================
Migration Summary:
  Migrated: 2
  Skipped (already migrated): 0
  Failed: 0
```

**Example output (restore from backup):**
```
Found 1 RayCluster(s) in backup to migrate (cluster 'my-cluster' in namespace 'my-ns'):

  - my-cluster (ns: my-ns) from raycluster-my-cluster-my-ns.yaml

  [my-cluster] Deleting existing cluster...
  [my-cluster] Waiting for cluster deletion to complete...
  [my-cluster] Cluster deleted successfully
  [my-cluster] Creating cluster from backup...
  [my-cluster] Waiting for cluster to become ready...
       Status: ready, workers: 2/2 (60s)
  [OK] Restored from backup: my-cluster (ns: my-ns)
       Dashboard: https://my-cluster-my-ns.apps.example.com

============================================================
Restore from Backup Summary:
  Restored: 1
  Failed: 0
```

### `delete` - [Advanced] Delete RayClusters

Permanently deletes RayClusters from the cluster. This is an advanced operation.

```bash
# Preview what would be deleted
python ray_cluster_migration.py delete --cluster my-cluster --namespace my-ns --dry-run
python ray_cluster_migration.py delete --namespace my-ns --all --dry-run

# Delete (with confirmation)
python ray_cluster_migration.py delete --cluster my-cluster --namespace my-ns
```

### `import` - [Advanced] Restore from Backup

Restores RayClusters from backup YAML files. This is an advanced operation.

```bash
# Preview what would be imported
python ray_cluster_migration.py import ./backup --dry-run

# Import from backup
python ray_cluster_migration.py import ./backup

# Force import (overwrite conflicts)
python ray_cluster_migration.py import ./backup --force
```

## Scoping Options

All commands support consistent scoping options:

| Scope | Options | Description |
|-------|---------|-------------|
| Single Cluster | `--cluster NAME --namespace NS` | Target one specific cluster |
| Namespace | `--namespace NS` | Target all clusters in a namespace |
| Cluster-wide | (no flags) | Target all clusters across all namespaces |

When targeting multiple clusters, you'll be prompted to confirm before proceeding.

## Safety Features

### Dry-Run Mode

Always preview changes before applying:

```bash
# See what post-upgrade would do
python ray_cluster_migration.py post-upgrade --dry-run
```

### Confirmation Prompts

Migration operations require confirmation:

**Live migration:**
```
IMPORTANT: Migration will cause temporary downtime for each RayCluster.
  - Pods will be restarted as the KubeRay operator recreates them with the new configuration.
  - Existing job state and logs will be lost.
  - Currently running workloads/jobs will be interrupted and progress lost.

Proceed with migration? (yes/no):
```

**Restore from backup:**
```
WARNING: Restore from backup will DELETE and RECREATE each RayCluster.
  - If a cluster currently exists, it will be deleted first.
  - All running pods, jobs, and workloads will be terminated.
  - Existing job state and logs will be lost.
  - The cluster will be recreated from the backup configuration.

Proceed with restore from backup? (yes/no):
```

### Skip Confirmation for Automation

Use `--yes` to skip confirmation in CI/CD:

```bash
python ray_cluster_migration.py post-upgrade --yes
python ray_cluster_migration.py post-upgrade --namespace my-ns --yes
```

## Idempotency Details

### Pre-Upgrade (Backup)

- Running multiple times overwrites existing backup files
- Safe to run repeatedly - no cluster modifications

### Post-Upgrade (Migrate)

The script automatically detects if a cluster has already been migrated and skips it. This means you can safely run the migration multiple times without causing issues.

## Example: Complete Migration

```bash
# 1. Check current state
python ray_cluster_migration.py list

# 2. Backup everything before upgrade
python ray_cluster_migration.py pre-upgrade ./backup-$(date +%Y%m%d)

# 3. [Perform RHOAI upgrade using your standard procedure]

# 4. Check what needs migration
python ray_cluster_migration.py list

# 5. Test migration on a single cluster
python ray_cluster_migration.py post-upgrade --cluster test-cluster --namespace dev --dry-run
python ray_cluster_migration.py post-upgrade --cluster test-cluster --namespace dev

# 6. Verify the test cluster works correctly

# 7. Migrate the rest of the dev namespace
python ray_cluster_migration.py post-upgrade --namespace dev --dry-run
python ray_cluster_migration.py post-upgrade --namespace dev

# 8. Continue with other namespaces
python ray_cluster_migration.py post-upgrade --namespace staging
python ray_cluster_migration.py post-upgrade --namespace production

# 9. Or migrate everything at once
python ray_cluster_migration.py post-upgrade

# 10. Verify final state
python ray_cluster_migration.py list
```

## Troubleshooting

### "No Kubernetes configuration found"

Ensure you have valid kubeconfig:
```bash
kubectl cluster-info
```

### "RayCluster CRD not found"

Verify the RayCluster CRD is installed:
```bash
kubectl get crd rayclusters.ray.io
```

### "Permission denied"

Check your RBAC permissions:
```bash
kubectl auth can-i list rayclusters.ray.io --all-namespaces
kubectl auth can-i update rayclusters.ray.io --all-namespaces
```

### Cluster shows as needing migration but was already migrated

The cluster may be missing the annotation. Run post-upgrade again - it will add the annotation:
```bash
python ray_cluster_migration.py post-upgrade --cluster my-cluster --namespace my-ns
```

### Migration seems stuck or fails repeatedly

Check cluster status:
```bash
kubectl get raycluster my-cluster -n my-ns -o yaml
```

Try with verbose output and investigate any error messages.

## Output File Format

Backup files are saved as `raycluster-{name}-{namespace}.yaml`:

```
backup/
├── raycluster-production-cluster-production.yaml
├── raycluster-staging-cluster-staging.yaml
└── raycluster-dev-cluster-dev.yaml
```

Each file contains the RayCluster configuration ready for restoration if needed.

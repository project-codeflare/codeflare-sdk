# RHOAI RayCluster Migration Guide

This guide walks you through migrating your RayClusters from RHOAI 2.x to RHOAI 3.x.

## Overview

The migration tool helps you:
1. **Back up** your RayCluster configurations before the upgrade
2. **Verify** your cluster is ready for the upgrade (automatic pre-flight checks)
3. **Migrate** your RayClusters after the upgrade is complete

The tool is designed to be safe and predictable:
- **Staged approach**: Test on a single cluster before migrating everything
- **Idempotent**: Safe to run multiple times
- **Non-destructive**: Backups are created, nothing is deleted automatically

---

## Prerequisites

### 1. Python Environment

Python 3.6 or later is required.

```bash
python3 --version
```

### 2. Install Required Packages

```bash
pip install -r ray_cluster_migration_requirements.txt
```

Or install directly:

```bash
pip install kubernetes>=28.1.0 PyYAML>=6.0
```

### 3. Cluster Access

Verify you can connect to your OpenShift cluster:

```bash
oc whoami
oc get rayclusters --all-namespaces
```

---

## Step 1: Pre-Upgrade (Before RHOAI Upgrade)

Run the pre-upgrade command to verify prerequisites and back up your RayClusters:

```bash
python ray_cluster_migration.py pre-upgrade
```

The script will:
1. Prompt for a backup directory (default: `./raycluster-backups`)
2. Run automatic pre-flight checks (permissions, cert-manager, codeflare-operator status)
3. Back up your RayCluster configurations

**If any required checks fail, the script will stop and tell you exactly what needs to be fixed before you can proceed.**

### Pre-Upgrade Options

```bash
# Back up a specific namespace only
python ray_cluster_migration.py pre-upgrade --namespace my-namespace

# Back up a single cluster (for testing)
python ray_cluster_migration.py pre-upgrade --cluster my-cluster --namespace my-namespace

# Specify backup directory directly
python ray_cluster_migration.py pre-upgrade ./my-backup-directory
```

---

## Step 2: Perform the RHOAI Upgrade

Follow your standard RHOAI upgrade procedure to upgrade from RHOAI 2.x to RHOAI 3.x.

---

## Step 3: Post-Upgrade (After RHOAI Upgrade)

After the RHOAI upgrade is complete, migrate your RayClusters.

### Recommended: Staged Migration

We recommend migrating in stages to verify everything works correctly:

**Stage 1: Test with a single cluster**
```bash
# Preview first
python ray_cluster_migration.py post-upgrade --cluster my-cluster --namespace my-namespace --dry-run

# Run the migration
python ray_cluster_migration.py post-upgrade --cluster my-cluster --namespace my-namespace
```

**Stage 2: Migrate a namespace**
```bash
python ray_cluster_migration.py post-upgrade --namespace my-namespace
```

**Stage 3: Migrate all remaining clusters**
```bash
python ray_cluster_migration.py post-upgrade
```

### Post-Upgrade Options

```bash
# Skip confirmation prompt (for automation)
python ray_cluster_migration.py post-upgrade --yes

# Preview changes without making them
python ray_cluster_migration.py post-upgrade --dry-run
```

### Restore from Backup

If your clusters were deleted during the upgrade or you prefer to restore from backup files:

```bash
# Restore all clusters from backup directory
python ray_cluster_migration.py post-upgrade --from-backup ./raycluster-backups

# Restore a single cluster from backup
python ray_cluster_migration.py post-upgrade --from-backup ./raycluster-backups --cluster my-cluster --namespace my-namespace

# Restore from a single backup file
python ray_cluster_migration.py post-upgrade --from-backup ./raycluster-backups/raycluster-my-cluster-my-namespace.yaml
```

**Important:** `--from-backup` will **delete** any existing cluster with the same name before creating it from the backup. This ensures a clean restore.

---

## Check Migration Status

Check which clusters need migration at any time:

```bash
python ray_cluster_migration.py list
```

---

## Troubleshooting

### Pre-flight check failed: cert-manager not detected

Install cert-manager via OperatorHub in your OpenShift cluster:

1. Go to OperatorHub in the OpenShift console
2. Search for "cert-manager"
3. Install the cert-manager operator
4. Wait for it to be ready
5. Run pre-upgrade again

### Pre-flight check failed: codeflare-operator not Removed

Update your DataScienceCluster:

```bash
oc patch datasciencecluster <dsc-name> --type merge -p '{"spec":{"components":{"codeflare":{"managementState":"Removed"}}}}'
```

### Migration failed for a cluster

1. Check the error message for details
2. Verify cluster health: `oc get raycluster <name> -n <namespace>`
3. Retry just that cluster: `python ray_cluster_migration.py post-upgrade --cluster <name> --namespace <namespace>`

### Route not available after migration

Routes may take 30-60 seconds to be created. Check directly:

```bash
oc get httproute -n <namespace>
```

---

## Quick Reference

```bash
# Before RHOAI upgrade
python ray_cluster_migration.py pre-upgrade

# After RHOAI upgrade (staged approach)
python ray_cluster_migration.py post-upgrade --cluster test-cluster --namespace dev --dry-run
python ray_cluster_migration.py post-upgrade --cluster test-cluster --namespace dev
python ray_cluster_migration.py post-upgrade --namespace dev
python ray_cluster_migration.py post-upgrade

# Check status anytime
python ray_cluster_migration.py list
```

## Command Reference

| Command | Description |
|---------|-------------|
| `pre-upgrade` | Run pre-flight checks and backup RayClusters |
| `post-upgrade` | Migrate RayClusters after RHOAI upgrade |
| `list` | Show all RayClusters and their migration status |
| `delete` | [Advanced] Delete RayClusters |
| `import` | [Advanced] Restore RayClusters from backup |

### Common Options

| Option | Description |
|--------|-------------|
| `--cluster NAME` | Target a specific cluster (requires `--namespace`) |
| `--namespace NS` | Target a specific namespace |
| `--dry-run` | Preview changes without applying them |
| `--yes` | Skip confirmation prompts |
| `--from-backup PATH` | (post-upgrade only) Restore from backup file or directory. Deletes existing clusters before recreating. |

# RayCluster Migration Tool

A standalone script for exporting and importing RayClusters across Kubernetes environments.

## Overview

The `ray_cluster_migration.py` script provides functionality to:
- **List** all RayClusters across all namespaces or in a specific namespace
- **Export** all RayClusters from all namespaces in a Kubernetes cluster to YAML files
- **Cleanup** RayClusters in-place by removing TLS/OAuth components (without export or delete)
- **Delete** RayClusters from the cluster (specific, by namespace, or all)
- **Export with cleanup** - backup RayClusters then delete them from the cluster
- **Import** RayClusters from YAML files back into a cluster with dry-run support
- Automatically clean TLS/OAuth components for portability across different environments

## Requirements

Install the required Python packages:

```bash
pip install kubernetes>=28.1.0 PyYAML>=6.0
```

Or if using the codeflare-sdk development environment, these dependencies are already included.

## Authentication

The script uses standard Kubernetes authentication methods in the following order:
1. `KUBECONFIG` environment variable
2. `~/.kube/config` file
3. In-cluster config (when running inside a Kubernetes pod)

Make sure you have valid Kubernetes credentials configured before running the script.

## Usage

### List RayClusters

List all RayClusters across all namespaces:

```bash
python ray_cluster_migration.py list
```

List RayClusters in a specific namespace:

```bash
python ray_cluster_migration.py list --namespace my-namespace
```

List with YAML output format:

```bash
python ray_cluster_migration.py list --format yaml
```

This will display:
- Cluster name, namespace, status, and number of workers (table view)
- Detailed resource information (CPU/memory requests and limits) for head and worker nodes
- YAML output option for scripting and automation

### Export RayClusters

Export all RayClusters from all namespaces to a directory:

```bash
python ray_cluster_migration.py export ./exported_clusters
```

Export and cleanup (backup then delete from cluster):

```bash
python ray_cluster_migration.py export ./backup --cleanup
```

This will:
- Create the output directory if it doesn't exist
- Export each RayCluster to a separate YAML file named `raycluster-{name}-{namespace}.yaml`
- Remove auto-generated Kubernetes metadata
- Strip TLS/OAuth components for portability
- If `--cleanup` flag is used: delete all exported RayClusters from the cluster after successful export

### Cleanup RayClusters (In-Place TLS/OAuth Removal)

The cleanup command removes TLS/OAuth components from RayClusters **without** exporting or deleting them. This modifies the clusters in-place on the Kubernetes cluster.

**Cleanup a specific RayCluster:**

```bash
# Preview first
python ray_cluster_migration.py cleanup my-cluster --namespace default --dry-run

# Then cleanup
python ray_cluster_migration.py cleanup my-cluster --namespace default
```

**Cleanup all RayClusters in a specific namespace:**

```bash
# Preview first
python ray_cluster_migration.py cleanup --all --namespace production --dry-run

# Then cleanup
python ray_cluster_migration.py cleanup --all --namespace production
```

**Cleanup all RayClusters across all namespaces:**

```bash
# Preview first (strongly recommended!)
python ray_cluster_migration.py cleanup --all --dry-run

# Then cleanup
python ray_cluster_migration.py cleanup --all
```

The cleanup command will:
- Retrieve RayCluster resources from the Kubernetes cluster
- Remove TLS/OAuth components (same processing as export):
  * TLS environment variables and volume mounts
  * OAuth proxy sidecar containers
  * Certificate generation init containers
  * Related volumes and service account configuration
- Remove finalizers (including codeflare-operator finalizer)
- Add `odh.ray.io/secure-trusted-network: "true"` annotation (marks cluster as secure)
- Apply the cleaned version back to the cluster using **replace operation**
  * Replace (not merge) ensures fields are actually removed from the cluster
  * This is different from import which uses server-side apply
- Support dry-run mode to preview changes
- Provide detailed feedback for each cleanup attempt
- Report success/failure counts

**When to use cleanup:**
- Remove TLS/OAuth components from running clusters without downtime
- Modify clusters to work in environments without TLS/OAuth requirements
- Prepare clusters for migration to non-RHOAI environments
- Clean up clusters that were created with TLS/OAuth but no longer need it

**Important notes:**
- Cleanup removes finalizers including the codeflare-operator finalizer
- The operator may re-add its finalizer during reconciliation if still managing the cluster
- Adds `odh.ray.io/secure-trusted-network: "true"` annotation to indicate cluster is in a secure network
- Uses replace (not merge) operation to ensure complete removal of TLS/OAuth fields
- This is a more aggressive operation than import (which uses merge)
- Keeps `resourceVersion` and `uid` metadata fields required by Kubernetes for replace operation

### Delete RayClusters

Delete a specific RayCluster:

```bash
python ray_cluster_migration.py delete my-cluster --namespace default
```

Preview deletion (dry-run):

```bash
python ray_cluster_migration.py delete my-cluster --namespace default --dry-run
```

Delete all RayClusters in a specific namespace:

```bash
# Preview first
python ray_cluster_migration.py delete --all --namespace production --dry-run

# Then delete
python ray_cluster_migration.py delete --all --namespace production
```

Delete all RayClusters across all namespaces:

```bash
# Preview first (strongly recommended!)
python ray_cluster_migration.py delete --all --dry-run

# Then delete
python ray_cluster_migration.py delete --all
```

The delete command will:
- Delete RayCluster resources from the Kubernetes cluster
- Support dry-run mode to preview deletions
- Provide detailed feedback for each deletion attempt
- Report success/failure counts

### Import RayClusters

Preview import without applying changes (dry-run mode):

```bash
python ray_cluster_migration.py import ./exported_clusters --dry-run
```

Import RayClusters from a directory:

```bash
python ray_cluster_migration.py import ./exported_clusters
```

Import a single YAML file:

```bash
python ray_cluster_migration.py import ./my_cluster.yaml
```

Import with force flag (to overwrite conflicts):

```bash
python ray_cluster_migration.py import ./exported_clusters --force
```

Combine dry-run with force flag to preview what would happen:

```bash
python ray_cluster_migration.py import ./exported_clusters --dry-run --force
```

The import command will:
- Add `odh.ray.io/secure-trusted-network: "true"` annotation to each cluster
- Apply RayClusters using server-side apply
- Preserve the original namespace from the YAML
- Report success/failure for each cluster
- In dry-run mode: validate YAMLs and show what would be applied without making changes

## Safety Features

### Confirmation Prompts

**All destructive operations require explicit confirmation when not in dry-run mode:**

- **Cleanup operations** (modifying clusters in-place) show what will be modified and require "yes" confirmation
- **Delete operations** show what will be deleted and require "yes" confirmation with strong warnings
- **Export with cleanup** shows what will be deleted after export and requires "yes" confirmation

### Skip Confirmation for Automation

Use the `--yes` (or `-y`) flag to skip confirmation prompts for automation/scripting:

```bash
# Skip confirmation for cleanup
python ray_cluster_migration.py cleanup --all --namespace production --yes

# Skip confirmation for delete
python ray_cluster_migration.py delete --all --namespace test --yes

# Skip confirmation for export with cleanup
python ray_cluster_migration.py export ./backup --cleanup --yes
```

**Important:** Only use `--yes` in automation scripts where you're certain about the operation. Always test with `--dry-run` first!

### Dry-Run Mode

Dry-run mode never modifies anything and never requires confirmation. Use it to safely preview:

```bash
# Safe preview - no confirmation needed
python ray_cluster_migration.py cleanup --all --dry-run
python ray_cluster_migration.py delete --all --dry-run
```

## Features

### List and Search

The `list` command provides comprehensive visibility into RayClusters:

- **Search all namespaces**: Query all RayClusters across the entire cluster
- **Namespace filtering**: Focus on a specific namespace
- **Multiple output formats**: Table view for human reading, YAML for scripting
- **Detailed resource information**: View CPU/memory requests and limits for head and worker nodes
- **Status monitoring**: Check cluster status and worker count

### Automatic Cleanup During Export

The script automatically removes the following components during export to ensure portability:

**Auto-generated Kubernetes fields:**
- `creationTimestamp`, `resourceVersion`, `uid`, `selfLink`
- `managedFields`, `finalizers`, `generation`, `status`

**TLS/OAuth components (RHOAI-specific):**
- TLS environment variables (`RAY_USE_TLS`, `RAY_TLS_*`)
- OAuth proxy sidecar containers
- Certificate generation init containers
- TLS-related volumes and volume mounts
- Service account configurations

### In-Place Cleanup

The `cleanup` command modifies RayClusters in-place without exporting or deleting:

- **In-place modification**: Removes TLS/OAuth components from running clusters
- **No downtime**: Clusters remain running during cleanup
- **Targeted cleanup**: Clean specific clusters, namespace, or all clusters
- **Secure network annotation**: Adds `odh.ray.io/secure-trusted-network: "true"` annotation
- **Dry-run support**: Preview what will be modified before committing
- **Replace operation**: Uses replace (not merge) to ensure complete field removal

**Use Cases:**
- Remove TLS/OAuth from clusters running in non-RHOAI environments
- Prepare clusters for migration without exporting/deleting
- Clean up clusters that were created with TLS but no longer need it
- Modify multiple clusters simultaneously across namespaces

### Delete and Cleanup

The `delete` command provides safe cluster deletion:

- **Targeted deletion**: Remove specific RayClusters by name
- **Namespace cleanup**: Delete all clusters in a namespace
- **Bulk deletion**: Remove all clusters across all namespaces
- **Dry-run support**: Preview what will be deleted before committing
- **Export with cleanup**: The `export --cleanup` flag backs up clusters before deleting them

**Use Cases:**
- Clean up test clusters after export
- Decommission clusters in a namespace
- Prepare clusters for migration (export + cleanup, then import to new cluster)
- Free up resources after backing up cluster configurations

### Dry-Run Mode

The `--dry-run` flag for import, cleanup, and delete allows you to:
- Validate YAML files before applying them (import)
- Preview what changes would be made (import, cleanup)
- Preview which clusters would be modified (cleanup)
- Preview which clusters would be deleted (delete)
- Test operations safely before executing
- Combine with `--force` to see what conflicts would be resolved (import)

### Server-Side Apply

The import function uses Kubernetes server-side apply, which:
- Safely handles conflicts with existing resources
- Allows partial updates without overwriting unmanaged fields
- Supports the `--force` flag to resolve conflicts

## Example Workflow

### Discovering RayClusters

```bash
# List all RayClusters in the cluster
python ray_cluster_migration.py list

# Check RayClusters in a specific namespace
python ray_cluster_migration.py list --namespace production

# Get YAML output for scripting
python ray_cluster_migration.py list --format yaml > clusters.yaml
```

### Migrating Between Clusters

1. **List and verify clusters in source:**
   ```bash
   # Configure kubectl for source cluster
   export KUBECONFIG=~/.kube/config-source

   # List all RayClusters
   python ray_cluster_migration.py list
   ```

2. **Export from source cluster:**
   ```bash
   # Export all RayClusters
   python ray_cluster_migration.py export ./backup
   ```

3. **Preview import to destination cluster:**
   ```bash
   # Configure kubectl for destination cluster
   export KUBECONFIG=~/.kube/config-dest

   # Dry-run to preview changes
   python ray_cluster_migration.py import ./backup --dry-run
   ```

4. **Import to destination cluster:**
   ```bash
   # Import RayClusters
   python ray_cluster_migration.py import ./backup

   # Verify import
   python ray_cluster_migration.py list
   ```

### Backup and Restore

```bash
# Create a backup
python ray_cluster_migration.py export ./backup-$(date +%Y%m%d)

# Later, restore from backup
python ray_cluster_migration.py import ./backup-20241219
```

### Backup and Cleanup (Decommission Clusters)

```bash
# List clusters before cleanup
python ray_cluster_migration.py list

# Export for backup and delete from cluster
python ray_cluster_migration.py export ./backup-before-cleanup --cleanup

# Verify clusters are deleted
python ray_cluster_migration.py list

# Later, restore if needed
python ray_cluster_migration.py import ./backup-before-cleanup
```

### In-Place Cleanup (Remove TLS/OAuth Without Export/Delete)

```bash
# List clusters to see what needs cleanup
python ray_cluster_migration.py list --namespace production

# Preview cleanup changes
python ray_cluster_migration.py cleanup --all --namespace production --dry-run

# Apply cleanup to remove TLS/OAuth components
python ray_cluster_migration.py cleanup --all --namespace production

# Verify clusters are still running (just cleaned up)
python ray_cluster_migration.py list --namespace production
```

### Namespace Cleanup

```bash
# Preview what would be deleted
python ray_cluster_migration.py delete --all --namespace test-env --dry-run

# Export test namespace clusters first (optional)
python ray_cluster_migration.py export ./test-env-backup

# Delete all clusters in namespace (with confirmation)
python ray_cluster_migration.py delete --all --namespace test-env

# Or skip confirmation for automation
python ray_cluster_migration.py delete --all --namespace test-env --yes
```

## Output Format

### List Output

**Table format (default):**
```
Found 2 RayCluster(s):

Name                           Namespace            Status          Workers
--------------------------------------------------------------------------------
my-cluster                     default              ready           3
test-cluster                   test-ns              ready           2

Detailed Resource Information:
================================================================================

my-cluster (namespace: default)
  Status: ready
  Workers: 3
  Head Resources:
    CPU: 1 (request) / 2 (limit)
    Memory: 4Gi (request) / 8Gi (limit)
  Worker Resources:
    CPU: 2 (request) / 4 (limit)
    Memory: 8Gi (request) / 16Gi (limit)

test-cluster (namespace: test-ns)
  Status: ready
  Workers: 2
  Head Resources:
    CPU: 1 (request) / 2 (limit)
    Memory: 2Gi (request) / 4Gi (limit)
  Worker Resources:
    CPU: 1 (request) / 2 (limit)
    Memory: 4Gi (request) / 8Gi (limit)
```

**YAML format:**
```yaml
- name: my-cluster
  namespace: default
  status: ready
  num_workers: 3
  head_resources:
    cpu_request: '1'
    cpu_limit: '2'
    memory_request: 4Gi
    memory_limit: 8Gi
  worker_resources:
    cpu_request: '2'
    cpu_limit: '4'
    memory_request: 8Gi
    memory_limit: 16Gi
```

### Export Output

**Normal export:**
```
Created output directory: ./exported_clusters
Exported RayCluster 'my-cluster' from namespace 'default' to ./exported_clusters/raycluster-my-cluster-default.yaml
Exported RayCluster 'test-cluster' from namespace 'test-ns' to ./exported_clusters/raycluster-test-cluster-test-ns.yaml

Successfully exported 2 RayCluster(s)
```

**Export with cleanup (includes confirmation):**
```
Created output directory: ./backup
Exported RayCluster 'my-cluster' from namespace 'default' to ./backup/raycluster-my-cluster-default.yaml
Exported RayCluster 'test-cluster' from namespace 'test-ns' to ./backup/raycluster-test-cluster-test-ns.yaml

Successfully exported 2 RayCluster(s)

================================================================================
Cleanup Mode: Deleting exported RayClusters from cluster...
================================================================================

WARNING: Cleanup mode will PERMANENTLY DELETE the following exported RayCluster(s):
  - my-cluster (namespace: default)
  - test-cluster (namespace: test-ns)

IMPORTANT: This operation is IRREVERSIBLE!
The clusters have been exported to files, but will be removed from the cluster.

Do you want to continue with cleanup (delete clusters)? (yes/no): yes

Deleted RayCluster 'my-cluster' from namespace 'default'
Deleted RayCluster 'test-cluster' from namespace 'test-ns'

Cleanup Summary: 2 deleted, 0 failed
```

### Cleanup Output (In-Place Modification)

**Normal cleanup with confirmation:**
```
Found 2 RayCluster(s) to cleanup

WARNING: This will modify the following RayCluster(s) by removing TLS/OAuth components:
  - my-cluster (namespace: default)
  - test-cluster (namespace: test-ns)

This operation will:
  - Remove TLS environment variables and volume mounts
  - Remove OAuth proxy sidecar containers
  - Remove certificate generation init containers
  - Remove related volumes and service account configuration

The clusters will remain running but will be modified in-place.

Do you want to continue? (yes/no): yes

Cleaned up RayCluster 'my-cluster' in namespace 'default'
Cleaned up RayCluster 'test-cluster' in namespace 'test-ns'

Cleanup Summary: 2 cleaned, 0 failed
```

**Cleanup without confirmation (--yes flag):**
```
Found 2 RayCluster(s) to cleanup

Cleaned up RayCluster 'my-cluster' in namespace 'default'
Cleaned up RayCluster 'test-cluster' in namespace 'test-ns'

Cleanup Summary: 2 cleaned, 0 failed
```

**Cleanup with dry-run:**
```
=== DRY RUN MODE - No clusters will be modified ===

Found 2 RayCluster(s) to cleanup

[DRY RUN] Would cleanup RayCluster 'my-cluster' in namespace 'default'
  - Would remove TLS/OAuth components and apply back to cluster
[DRY RUN] Would cleanup RayCluster 'test-cluster' in namespace 'test-ns'
  - Would remove TLS/OAuth components and apply back to cluster

[DRY RUN] Cleanup Summary: 2 would be cleaned, 0 would fail
```

### Delete Output

**Normal delete with confirmation:**
```
Found 2 RayCluster(s) to delete

WARNING: This will PERMANENTLY DELETE the following RayCluster(s):
  - my-cluster (namespace: default)
  - test-cluster (namespace: test-ns)

IMPORTANT: This operation is IRREVERSIBLE!
All cluster data, configurations, and running workloads will be lost.
Consider using 'export' to backup clusters before deleting.

Are you absolutely sure you want to delete these clusters? (yes/no): yes

Deleted RayCluster 'my-cluster' from namespace 'default'
Deleted RayCluster 'test-cluster' from namespace 'test-ns'

Delete Summary: 2 deleted, 0 failed
```

**Delete without confirmation (--yes flag):**
```
Found 1 RayCluster(s) to delete

Deleted RayCluster 'my-cluster' from namespace 'default'

Delete Summary: 1 deleted, 0 failed
```

**Delete with dry-run:**
```
=== DRY RUN MODE - No clusters will be deleted ===

Found 2 RayCluster(s) to delete

[DRY RUN] Would delete RayCluster 'my-cluster' from namespace 'default'
[DRY RUN] Would delete RayCluster 'test-cluster' from namespace 'test-ns'

[DRY RUN] Delete Summary: 2 would be deleted, 0 would fail
```

### Import Output

**Normal import:**
```
Successfully applied RayCluster 'my-cluster' to namespace 'default'
Successfully applied RayCluster 'test-cluster' to namespace 'test-ns'

Import Summary: 2 succeeded, 0 failed
```

**Dry-run mode:**
```
=== DRY RUN MODE - No changes will be applied ===

[DRY RUN] Would apply RayCluster 'my-cluster' to namespace 'default'
[DRY RUN] Would apply RayCluster 'test-cluster' to namespace 'test-ns'

[DRY RUN] Import Summary: 2 would succeed, 0 would fail
```

## Error Handling

The script provides detailed error messages for common issues:

- **No Kubernetes config found:** Ensure you have a valid `~/.kube/config` or set `KUBECONFIG`
- **Permission denied:** Check your Kubernetes RBAC permissions for RayCluster resources
- **Namespace doesn't exist:** Create the target namespace before importing
- **Conflicts during import:** Use the `--force` flag to overwrite existing resources

## Troubleshooting

### "No Kubernetes configuration found"

Make sure you have a valid kubeconfig file:
```bash
kubectl cluster-info
```

### "Failed to initialize DynamicClient for RayCluster"

Verify that the RayCluster CRD is installed:
```bash
kubectl get crd rayclusters.ray.io
```

### Import fails with conflicts

First, use dry-run to see what conflicts exist:
```bash
python ray_cluster_migration.py import ./exported_clusters --dry-run
```

Then use the `--force` flag to resolve conflicts:
```bash
python ray_cluster_migration.py import ./exported_clusters --force
```

### List command shows "No RayClusters found"

Verify RayClusters exist in the cluster:
```bash
kubectl get rayclusters --all-namespaces
```

Check if you have permissions to list resources:
```bash
kubectl auth can-i list rayclusters.ray.io --all-namespaces
```

### Delete fails with permission error

Check if you have delete permissions:
```bash
kubectl auth can-i delete rayclusters.ray.io --all-namespaces
```

### Accidentally deleted clusters

If you didn't export before deleting, you cannot recover them. **Always use `--dry-run` first and consider exporting before deletion.**

If you exported before deleting (or used `--cleanup`), restore from backup:
```bash
python ray_cluster_migration.py import ./backup
```

### Cleanup fails with permission error

Check if you have update permissions:
```bash
kubectl auth can-i update rayclusters.ray.io --all-namespaces
kubectl auth can-i patch rayclusters.ray.io --all-namespaces
```

### Cleanup modified cluster incorrectly

If cleanup removed something it shouldn't have, you may need to:
1. Delete the cluster: `python ray_cluster_migration.py delete <cluster> --namespace <ns>`
2. Re-create it with the correct configuration

**This is why dry-run is important!** Always preview with `--dry-run` first.

### Confirmation prompts in automation/CI-CD

If you're running the script in automation or CI/CD pipelines, use the `--yes` flag to skip interactive prompts:

```bash
# In CI/CD or automation scripts
python ray_cluster_migration.py cleanup --all --namespace test --yes
python ray_cluster_migration.py delete --all --namespace temp --yes
python ray_cluster_migration.py export ./backup --cleanup --yes
```

**Best practice for automation:**
1. Always run with `--dry-run` first to verify
2. Only use `--yes` in tested automation scripts
3. Consider logging output for audit trails

### User cancelled operation

If you see "Operation cancelled by user", you responded "no" to the confirmation prompt. This is intentional - the operation was not performed. To proceed:

- Run the command again and answer "yes" when prompted
- Or use the `--yes` flag to skip the prompt
- Or use `--dry-run` to just preview without any confirmation

## Integration with CodeFlare SDK

This script is extracted from the CodeFlare SDK's cluster management functionality. It can be used:
- As a standalone tool without installing the full SDK
- For discovering and auditing RayClusters across environments
- For batch operations across multiple clusters
- For cluster lifecycle management (backup, restore, in-place cleanup, deletion)
- For removing TLS/OAuth components from running clusters without downtime
- In CI/CD pipelines for cluster backup/restore/cleanup
- For migrating between RHOAI versions or different Kubernetes distributions
- For testing and validating cluster configurations with dry-run mode
- For decommissioning clusters after backing up configurations
- For namespace cleanup and resource management

## Source

This script is based on the export/import functionality from:
- `src/codeflare_sdk/ray/cluster/cluster.py`

Key functions extracted:
- `list_ray_clusters()` - List and search functionality (new)
- `export_ray_clusters()` - Export functionality with optional cleanup (enhanced)
- `cleanup_ray_clusters()` - In-place TLS/OAuth removal with dry-run support (new)
- `delete_ray_clusters()` - Delete functionality with dry-run support (new)
- `import_ray_clusters()` - Import functionality with dry-run support (enhanced)
- `_process_ray_cluster_yaml()` - TLS/OAuth cleanup processing
- `remove_autogenerated_fields()` - Metadata cleanup
- `_apply_ray_cluster()` - Server-side apply

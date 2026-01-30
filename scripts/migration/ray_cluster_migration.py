#!/usr/bin/env python3
# Copyright 2024 IBM, Red Hat
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
RayCluster Migration Tool - Standalone Script

This script provides functionality to export and import RayClusters across
Kubernetes environments. It automatically removes TLS/OAuth components during
export to ensure portability across different cluster configurations.

REQUIREMENTS:
    - kubernetes>=28.1.0
    - PyYAML>=6.0

USAGE EXAMPLES:

    # List all RayClusters across all namespaces
    python ray_cluster_migration.py list

    # List RayClusters in a specific namespace
    python ray_cluster_migration.py list --namespace my-namespace

    # List with YAML output format
    python ray_cluster_migration.py list --format yaml

    # Export all RayClusters from all namespaces to a directory
    python ray_cluster_migration.py export ./exported_clusters

    # Export and cleanup (delete from cluster after backup)
    python ray_cluster_migration.py export ./backup --cleanup

    # Cleanup (remove TLS/OAuth) from clusters in-place without export/delete
    python ray_cluster_migration.py cleanup my-cluster --namespace default --dry-run
    python ray_cluster_migration.py cleanup my-cluster --namespace default
    python ray_cluster_migration.py cleanup --all --namespace production
    python ray_cluster_migration.py cleanup --all --namespace production --yes  # Skip confirmation

    # Delete a specific RayCluster
    python ray_cluster_migration.py delete my-cluster --namespace default

    # Delete all RayClusters in a namespace (preview first with dry-run)
    python ray_cluster_migration.py delete --all --namespace production --dry-run
    python ray_cluster_migration.py delete --all --namespace production
    python ray_cluster_migration.py delete --all --namespace production --yes  # Skip confirmation

    # Preview import without applying changes (dry-run)
    python ray_cluster_migration.py import ./exported_clusters --dry-run

    # Import RayClusters from a directory
    python ray_cluster_migration.py import ./exported_clusters

    # Import a single RayCluster YAML file
    python ray_cluster_migration.py import ./my_cluster.yaml

    # Import with force flag (overwrite conflicts)
    python ray_cluster_migration.py import ./exported_clusters --force

FEATURES:
    - List all RayClusters across all namespaces with detailed resource information
    - Search RayClusters in specific namespaces
    - Exports all RayClusters from all namespaces in the cluster
    - Cleanup RayClusters in-place (remove TLS/OAuth without export/delete):
      * Clean specific clusters by name
      * Clean all clusters in a namespace
      * Clean all clusters across all namespaces
      * Modify running clusters to remove TLS/OAuth components
      * Add odh.ray.io/secure-trusted-network annotation
    - Delete RayClusters from cluster (with dry-run support):
      * Delete specific clusters by name
      * Delete all clusters in a namespace
      * Delete all clusters across all namespaces
    - Export with cleanup option (backup then delete from cluster)
    - Safety features for destructive operations:
      * Confirmation prompts for cleanup and delete operations
      * Clear warnings about what will be modified/deleted
      * --yes flag to skip confirmations for automation
      * Dry-run mode never requires confirmation
    - Removes auto-generated Kubernetes metadata fields
    - Strips TLS/OAuth components for portability:
      * TLS environment variables and volume mounts
      * OAuth proxy sidecar containers
      * Certificate generation init containers
      * Related volumes and service account configuration
    - Dry-run mode to preview imports, cleanups, and deletes without applying changes
    - Server-side apply for safe imports and cleanups
    - Automatically adds odh.ray.io/secure-trusted-network annotation during import and cleanup
    - Preserves original namespace during import

AUTHENTICATION:
    The script uses standard Kubernetes authentication methods:
    1. KUBECONFIG environment variable
    2. ~/.kube/config file
    3. In-cluster config (when running in a pod)
"""

import os
import sys
import yaml
import copy
import argparse
from typing import List, Dict, Optional
from kubernetes import client, config
from kubernetes.dynamic import DynamicClient
from kubernetes.client.rest import ApiException

# Field manager identifier for server-side apply
CF_SDK_FIELD_MANAGER = "codeflare-sdk"


def config_check():
    """
    Check and load the Kubernetes config from the default location.

    This function checks if a Kubernetes config file exists at the default path
    (~/.kube/config). If none is provided, it tries to load in-cluster config.

    Raises:
        RuntimeError: If no valid credentials or config file is found.
    """
    home_directory = os.path.expanduser("~")

    # Try to load kube config if not already loaded
    try:
        # First try to load from default location
        if os.path.isfile(f"{home_directory}/.kube/config"):
            config.load_kube_config()
        # Then try in-cluster config
        elif "KUBERNETES_PORT" in os.environ:
            config.load_incluster_config()
        else:
            raise RuntimeError(
                "No Kubernetes configuration found. Please ensure you have a valid "
                "~/.kube/config file or are running in a Kubernetes cluster."
            )
    except config.ConfigException as e:
        raise RuntimeError(f"Failed to load Kubernetes configuration: {e}")


def get_api_client() -> client.ApiClient:
    """
    Retrieve the Kubernetes API client with the default configuration.

    Returns:
        client.ApiClient: The Kubernetes API client object.
    """
    return client.ApiClient()


def remove_autogenerated_fields(resource):
    """
    Recursively remove autogenerated fields from a dictionary.

    This removes Kubernetes metadata fields that are auto-generated and should
    not be included when re-applying resources to a different cluster.

    Args:
        resource: Dictionary or list to process (modified in-place)
    """
    if isinstance(resource, dict):
        for key in list(resource.keys()):
            if key in [
                "creationTimestamp",
                "resourceVersion",
                "uid",
                "selfLink",
                "managedFields",
                "finalizers",
                "generation",
                "status",
                "suspend",
                "workload.codeflare.dev/user",  # AppWrapper field
                "workload.codeflare.dev/userid",  # AppWrapper field
                "podSetInfos",  # AppWrapper field
            ]:
                del resource[key]
            else:
                remove_autogenerated_fields(resource[key])

    elif isinstance(resource, list):
        for item in resource:
            remove_autogenerated_fields(item)


def _process_ray_cluster_yaml(ray_cluster_yaml: dict) -> dict:
    """
    Processes a RayCluster YAML to remove TLS/OAuth-related components.

    This function removes hardcoded components that are typically added by RHOAI
    for security and OAuth proxy support:
    - TLS-related environment variables (RAY_USE_TLS, RAY_TLS_*)
    - TLS-related volume mounts (ca-vol, server-cert workspace mounts)
    - OAuth proxy sidecar container
    - Certificate generation initContainers
    - TLS/OAuth related volumes
    - Service account configuration

    This processing is applied to both head and worker pod specs.

    Args:
        ray_cluster_yaml (dict): The RayCluster YAML dictionary from Kubernetes API

    Returns:
        dict: The processed YAML with TLS/OAuth components removed
    """
    # Environment variable names to remove (TLS/OAuth related)
    tls_env_vars = {
        "RAY_USE_TLS",
        "RAY_TLS_SERVER_CERT",
        "RAY_TLS_SERVER_KEY",
        "RAY_TLS_CA_CERT",
    }

    # Volume names to remove
    volumes_to_remove = {"ca-vol", "proxy-tls-secret"}

    # Volume mount names to remove from containers
    volume_mounts_to_remove = {"ca-vol", "server-cert"}

    # Container names to remove (sidecar containers)
    containers_to_remove = {"oauth-proxy"}

    def process_container_spec(container_spec):
        """Process a single container spec to remove TLS/OAuth env vars and mounts."""
        if "env" in container_spec:
            # Filter out TLS-related environment variables
            container_spec["env"] = [
                env_var
                for env_var in container_spec["env"]
                if env_var.get("name") not in tls_env_vars
            ]
            # Remove env key if empty
            if not container_spec["env"]:
                del container_spec["env"]

        if "volumeMounts" in container_spec:
            # Filter out TLS/OAuth related volume mounts
            container_spec["volumeMounts"] = [
                mount
                for mount in container_spec["volumeMounts"]
                if mount.get("name") not in volume_mounts_to_remove
            ]
            # Remove volumeMounts key if empty
            if not container_spec["volumeMounts"]:
                del container_spec["volumeMounts"]

    def process_pod_spec(pod_spec):
        """Process a pod spec (in template.spec) to clean up TLS/OAuth components."""
        # Process containers
        if "containers" in pod_spec:
            # Remove sidecar containers like oauth-proxy
            pod_spec["containers"] = [
                container
                for container in pod_spec["containers"]
                if container.get("name") not in containers_to_remove
            ]
            # Process remaining containers to remove TLS env/mounts
            for container in pod_spec["containers"]:
                process_container_spec(container)

        # Remove entire initContainers section
        if "initContainers" in pod_spec:
            del pod_spec["initContainers"]

        # Remove serviceAccountName field
        if "serviceAccountName" in pod_spec:
            del pod_spec["serviceAccountName"]

        # Process volumes
        if "volumes" in pod_spec:
            # Filter out TLS/OAuth related volumes
            pod_spec["volumes"] = [
                volume
                for volume in pod_spec["volumes"]
                if volume.get("name") not in volumes_to_remove
            ]

    # Process headGroupSpec
    if "spec" in ray_cluster_yaml and "headGroupSpec" in ray_cluster_yaml["spec"]:
        head_spec = ray_cluster_yaml["spec"]["headGroupSpec"]
        if "template" in head_spec and "spec" in head_spec["template"]:
            process_pod_spec(head_spec["template"]["spec"])
        # Disable enableIngress if it's set to true
        if head_spec.get("enableIngress") is True:
            head_spec["enableIngress"] = False

    # Process workerGroupSpecs
    if "spec" in ray_cluster_yaml and "workerGroupSpecs" in ray_cluster_yaml["spec"]:
        for worker_spec in ray_cluster_yaml["spec"]["workerGroupSpecs"]:
            if "template" in worker_spec and "spec" in worker_spec["template"]:
                process_pod_spec(worker_spec["template"]["spec"])

    return ray_cluster_yaml


def _apply_ray_cluster(yamls, namespace: str, api_instance, force=False):
    """
    Applies a RayCluster resource using server-side apply.

    Args:
        yamls: The RayCluster resource definition (dict or YAML string)
        namespace: The Kubernetes namespace to apply to
        api_instance: A DynamicClient resource object that has server_side_apply method
        force: Whether to force apply in case of conflicts
    """
    api_instance.server_side_apply(
        field_manager=CF_SDK_FIELD_MANAGER,
        group="ray.io",
        version="v1",
        namespace=namespace,
        plural="rayclusters",
        body=yamls,
        force_conflicts=force,
    )


def export_ray_clusters(
    output_dir: str, cleanup: bool = False, auto_confirm: bool = False
) -> List[str]:
    """
    Exports all RayClusters from all namespaces in the cluster to YAML files.

    This function:
    - Lists all namespaces in the Kubernetes cluster
    - Queries each namespace for RayClusters
    - Removes auto-generated Kubernetes fields from each YAML
    - Removes TLS/OAuth-related components (hardcoded processing):
      * TLS environment variables and volume mounts
      * OAuth proxy sidecar containers
      * Certificate generation init containers
      * Related volumes and service account configuration
    - Saves each RayCluster to a separate YAML file in the specified output directory
    - Optionally deletes the RayClusters from the cluster after export (if cleanup=True)

    Args:
        output_dir (str): Directory path where YAML files will be saved.
                         Directory will be created if it doesn't exist.
        cleanup (bool, optional): If True, deletes RayClusters from cluster after export. Default is False.
        auto_confirm (bool, optional): If True, skips confirmation prompt for cleanup (for automation). Default is False.

    Returns:
        List[str]: List of file paths where RayCluster YAMLs were saved.

    Raises:
        RuntimeError: If unable to connect to Kubernetes cluster or access its API.
    """
    try:
        config_check()
    except Exception as e:
        raise RuntimeError(f"Failed to connect to Kubernetes cluster: {e}")

    # Create output directory if it doesn't exist
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"Created output directory: {output_dir}")

    saved_files = []
    clusters_to_delete = []  # Track clusters for cleanup if requested
    api_instance = client.CustomObjectsApi(get_api_client())
    core_api = client.CoreV1Api(get_api_client())

    try:
        # Get list of all namespaces
        namespaces = core_api.list_namespace()
        namespace_names = [ns.metadata.name for ns in namespaces.items]
    except Exception as e:
        print(f"Error listing namespaces: {e}")
        return saved_files

    # Query each namespace for RayClusters
    for namespace in namespace_names:
        try:
            rcs = api_instance.list_namespaced_custom_object(
                group="ray.io",
                version="v1",
                namespace=namespace,
                plural="rayclusters",
            )
        except Exception as e:
            print(
                f"Warning: Could not list RayClusters in namespace '{namespace}': {e}"
            )
            continue

        # Process each RayCluster
        for rc in rcs.get("items", []):
            try:
                # Make a copy to avoid modifying the original
                rc_copy = copy.deepcopy(rc)

                # Remove auto-generated fields
                remove_autogenerated_fields(rc_copy)

                # Apply hardcoded processing to remove TLS/OAuth components
                rc_copy = _process_ray_cluster_yaml(rc_copy)

                # Generate output filename
                cluster_name = rc_copy["metadata"]["name"]
                ns = rc_copy["metadata"]["namespace"]
                output_filename = os.path.join(
                    output_dir, f"raycluster-{cluster_name}-{ns}.yaml"
                )

                # Write to file
                with open(output_filename, "w") as outfile:
                    yaml.dump(rc_copy, outfile, default_flow_style=False)

                saved_files.append(output_filename)
                print(
                    f"Exported RayCluster '{cluster_name}' from namespace '{ns}' to {output_filename}"
                )

                # Track for cleanup if requested
                if cleanup:
                    clusters_to_delete.append({"name": cluster_name, "namespace": ns})

            except Exception as e:
                cluster_name = rc.get("metadata", {}).get("name", "unknown")
                print(f"Error processing RayCluster '{cluster_name}': {e}")
                continue

    print(f"\nSuccessfully exported {len(saved_files)} RayCluster(s)")

    # Cleanup (delete) exported clusters if requested
    if cleanup and clusters_to_delete:
        print(f"\n{'='*80}")
        print("Cleanup Mode: Deleting exported RayClusters from cluster...")
        print(f"{'='*80}\n")

        # Show warning and get confirmation if not auto-confirmed
        if not auto_confirm:
            print(
                "WARNING: Cleanup mode will PERMANENTLY DELETE the following exported RayCluster(s):"
            )
            for cluster_info in clusters_to_delete:
                print(
                    f"  - {cluster_info['name']} (namespace: {cluster_info['namespace']})"
                )

            print("\nIMPORTANT: This operation is IRREVERSIBLE!")
            print(
                "The clusters have been exported to files, but will be removed from the cluster."
            )

            response = (
                input(
                    "\nDo you want to continue with cleanup (delete clusters)? (yes/no): "
                )
                .strip()
                .lower()
            )
            if response not in ["yes", "y"]:
                print(
                    "Cleanup cancelled by user. Clusters have been exported but not deleted."
                )
                return saved_files
            print()

        deleted_count = 0
        failed_count = 0

        for cluster_info in clusters_to_delete:
            try:
                api_instance.delete_namespaced_custom_object(
                    group="ray.io",
                    version="v1",
                    namespace=cluster_info["namespace"],
                    plural="rayclusters",
                    name=cluster_info["name"],
                )
                print(
                    f"Deleted RayCluster '{cluster_info['name']}' from namespace '{cluster_info['namespace']}'"
                )
                deleted_count += 1
            except Exception as e:
                print(
                    f"Failed to delete RayCluster '{cluster_info['name']}' from namespace '{cluster_info['namespace']}': {e}"
                )
                failed_count += 1

        print(f"\nCleanup Summary: {deleted_count} deleted, {failed_count} failed")

    return saved_files


def import_ray_clusters(
    source_path: str, force: bool = False, dry_run: bool = False
) -> List[Dict]:
    """
    Imports RayClusters from YAML files and applies them to the cluster.

    This function:
    - Accepts either a directory path or a single file path
    - If directory: loads all .yaml files from it
    - If file: loads the single YAML file
    - For each YAML file, loads RayCluster resource(s) and applies them
    - Adds odh.ray.io/secure-trusted-network: "true" annotation to each cluster
    - Preserves the original namespace specified in each YAML's metadata

    Args:
        source_path (str): Path to a YAML file or directory containing YAML files.
        force (bool, optional): Whether to force apply in case of conflicts. Default is False.
        dry_run (bool, optional): If True, only validate and show what would be applied without actually applying. Default is False.

    Returns:
        List[Dict]: List of result dictionaries for each import attempt.
                   Each dict contains: {
                       'cluster_name': str,
                       'namespace': str,
                       'file': str,
                       'status': 'success' or 'error',
                       'message': str
                   }

    Raises:
        ValueError: If source_path does not exist or is neither file nor directory.
    """
    if not os.path.exists(source_path):
        raise ValueError(f"Source path does not exist: {source_path}")

    try:
        config_check()
    except Exception as e:
        raise RuntimeError(f"Failed to connect to Kubernetes cluster: {e}")

    results = []
    files_to_process = []

    # Determine if source is file or directory
    if os.path.isfile(source_path):
        if source_path.endswith(".yaml") or source_path.endswith(".yml"):
            files_to_process.append(source_path)
        else:
            raise ValueError(f"File is not a YAML file: {source_path}")
    elif os.path.isdir(source_path):
        # Find all YAML files in directory
        for filename in os.listdir(source_path):
            if filename.endswith(".yaml") or filename.endswith(".yml"):
                files_to_process.append(os.path.join(source_path, filename))
    else:
        raise ValueError(f"Source path is neither file nor directory: {source_path}")

    if not files_to_process:
        print("No YAML files found to import")
        return results

    if dry_run:
        print("=== DRY RUN MODE - No changes will be applied ===\n")

    # Use DynamicClient to get RayCluster resource
    # DynamicClient resources have the server_side_apply method needed by _apply_ray_cluster
    try:
        crds = DynamicClient(get_api_client()).resources
        api_instance = crds.get(api_version="ray.io/v1", kind="RayCluster")
    except Exception as e:
        raise RuntimeError(f"Failed to initialize DynamicClient for RayCluster: {e}")

    # Process each YAML file
    for yaml_file in files_to_process:
        try:
            with open(yaml_file, "r") as f:
                yaml_documents = yaml.safe_load_all(f)

                for doc_idx, doc in enumerate(yaml_documents):
                    if doc is None:
                        continue

                    try:
                        # Extract cluster information
                        cluster_name = doc.get("metadata", {}).get("name", "unknown")
                        namespace = doc.get("metadata", {}).get("namespace", "default")

                        # Verify this is a RayCluster
                        kind = doc.get("kind", "")
                        if kind != "RayCluster":
                            print(
                                f"Skipping non-RayCluster resource '{cluster_name}' of kind '{kind}' in {yaml_file}"
                            )
                            continue

                        # Add ODH secure trusted network annotation
                        if "metadata" not in doc:
                            doc["metadata"] = {}
                        if "annotations" not in doc["metadata"]:
                            doc["metadata"]["annotations"] = {}
                        doc["metadata"]["annotations"][
                            "odh.ray.io/secure-trusted-network"
                        ] = "true"

                        # Apply the RayCluster (or just validate in dry-run mode)
                        if dry_run:
                            # In dry-run mode, just validate the YAML structure
                            message = f"[DRY RUN] Would apply RayCluster '{cluster_name}' to namespace '{namespace}'"
                            if force:
                                message += " (with force)"
                        else:
                            _apply_ray_cluster(
                                doc, namespace, api_instance, force=force
                            )
                            message = f"Successfully applied RayCluster '{cluster_name}' to namespace '{namespace}'"

                        result = {
                            "cluster_name": cluster_name,
                            "namespace": namespace,
                            "file": yaml_file,
                            "status": "success",
                            "message": message,
                        }
                        results.append(result)
                        print(result["message"])

                    except Exception as e:
                        cluster_name = doc.get("metadata", {}).get("name", "unknown")
                        namespace = doc.get("metadata", {}).get("namespace", "default")
                        result = {
                            "cluster_name": cluster_name,
                            "namespace": namespace,
                            "file": yaml_file,
                            "status": "error",
                            "message": f"Error applying RayCluster '{cluster_name}': {str(e)}",
                        }
                        results.append(result)
                        print(result["message"])

        except Exception as e:
            result = {
                "cluster_name": "unknown",
                "namespace": "unknown",
                "file": yaml_file,
                "status": "error",
                "message": f"Error reading YAML file '{yaml_file}': {str(e)}",
            }
            results.append(result)
            print(result["message"])

    # Print summary
    success_count = sum(1 for r in results if r["status"] == "success")
    error_count = sum(1 for r in results if r["status"] == "error")

    if dry_run:
        print(
            f"\n[DRY RUN] Import Summary: {success_count} would succeed, {error_count} would fail"
        )
    else:
        print(f"\nImport Summary: {success_count} succeeded, {error_count} failed")

    return results


def cleanup_ray_clusters(
    cluster_name: Optional[str] = None,
    namespace: Optional[str] = None,
    all_in_namespace: bool = False,
    dry_run: bool = False,
    auto_confirm: bool = False,
) -> Dict[str, int]:
    """
    Cleans up RayClusters by removing TLS/OAuth components in-place.

    This function modifies existing RayClusters on the cluster by removing:
    - TLS environment variables and volume mounts
    - OAuth proxy sidecar containers
    - Certificate generation init containers
    - Related volumes and service account configuration
    - Finalizers (including codeflare-operator finalizer)

    And adds:
    - odh.ray.io/secure-trusted-network: "true" annotation (marks cluster as being in secure network)

    The cleaned clusters are applied back to the cluster using replace operation
    (not merge) to ensure fields are actually removed from the cluster.

    Note: resourceVersion and uid are preserved as required by Kubernetes for replace operations.

    Args:
        cluster_name (Optional[str]): Name of specific cluster to cleanup
        namespace (Optional[str]): Namespace to cleanup. Required if cluster_name is specified.
        all_in_namespace (bool): If True, cleans all clusters in the namespace(s)
        dry_run (bool): If True, shows what would be cleaned without actually applying changes
        auto_confirm (bool): If True, skips confirmation prompt (for automation)

    Returns:
        Dict[str, int]: Dictionary with 'cleaned' and 'failed' counts

    Raises:
        ValueError: If invalid combination of arguments provided
        RuntimeError: If unable to connect to Kubernetes cluster
    """
    try:
        config_check()
    except Exception as e:
        raise RuntimeError(f"Failed to connect to Kubernetes cluster: {e}")

    # Validate arguments
    if cluster_name and not namespace:
        raise ValueError(
            "Namespace must be specified when cleaning a specific cluster by name"
        )

    if not cluster_name and not all_in_namespace:
        raise ValueError(
            "Either specify a cluster name or use --all flag to cleanup multiple clusters"
        )

    api_instance = client.CustomObjectsApi(get_api_client())
    core_api = client.CoreV1Api(get_api_client())

    cleaned_count = 0
    failed_count = 0
    clusters_to_cleanup = []

    if dry_run:
        print("=== DRY RUN MODE - No clusters will be modified ===\n")

    # Case 1: Cleanup specific cluster
    if cluster_name:
        try:
            rc = api_instance.get_namespaced_custom_object(
                group="ray.io",
                version="v1",
                namespace=namespace,
                plural="rayclusters",
                name=cluster_name,
            )
            clusters_to_cleanup.append(rc)
        except Exception as e:
            print(
                f"Error retrieving RayCluster '{cluster_name}' from namespace '{namespace}': {e}"
            )
            return {"cleaned": 0, "failed": 1}

    # Case 2: Cleanup all in namespace(s)
    elif all_in_namespace:
        # Get list of namespaces
        if namespace:
            namespace_names = [namespace]
        else:
            try:
                namespaces = core_api.list_namespace()
                namespace_names = [ns.metadata.name for ns in namespaces.items]
            except Exception as e:
                print(f"Error listing namespaces: {e}")
                return {"cleaned": 0, "failed": 0}

        # Collect all clusters from specified namespace(s)
        for ns in namespace_names:
            try:
                rcs = api_instance.list_namespaced_custom_object(
                    group="ray.io",
                    version="v1",
                    namespace=ns,
                    plural="rayclusters",
                )

                for rc in rcs.get("items", []):
                    clusters_to_cleanup.append(rc)

            except Exception as e:
                if namespace:  # Only print error if user specified a namespace
                    print(f"Error listing RayClusters in namespace '{ns}': {e}")
                continue

    if not clusters_to_cleanup:
        print("No RayClusters found to cleanup")
        return {"cleaned": 0, "failed": 0}

    print(f"Found {len(clusters_to_cleanup)} RayCluster(s) to cleanup\n")

    # Show warning and get confirmation if not dry-run and not auto-confirmed
    if not dry_run and not auto_confirm:
        print(
            "WARNING: This will modify the following RayCluster(s) by removing TLS/OAuth components:"
        )
        for rc in clusters_to_cleanup:
            cluster_name_display = rc.get("metadata", {}).get("name", "unknown")
            namespace_display = rc.get("metadata", {}).get("namespace", "unknown")
            print(f"  - {cluster_name_display} (namespace: {namespace_display})")

        print("\nThis operation will:")
        print("  - Remove TLS environment variables and volume mounts")
        print("  - Remove OAuth proxy sidecar containers")
        print("  - Remove certificate generation init containers")
        print("  - Remove related volumes and service account configuration")
        print("\nThe clusters will remain running but will be modified in-place.")

        response = input("\nDo you want to continue? (yes/no): ").strip().lower()
        if response not in ["yes", "y"]:
            print("Operation cancelled by user.")
            return {"cleaned": 0, "failed": 0}
        print()

    # No need to initialize DynamicClient - we'll use regular CustomObjectsApi for replace operation

    # Cleanup clusters
    for rc in clusters_to_cleanup:
        cluster_name_current = rc.get("metadata", {}).get("name", "unknown")
        namespace_current = rc.get("metadata", {}).get("namespace", "unknown")

        try:
            # Make a copy
            rc_copy = copy.deepcopy(rc)

            # For cleanup/replace, we need to keep certain fields that Kubernetes requires
            # Save them before processing
            resource_version = rc_copy.get("metadata", {}).get("resourceVersion")
            uid = rc_copy.get("metadata", {}).get("uid")

            # Remove auto-generated fields (but we'll restore some for replace)
            remove_autogenerated_fields(rc_copy)

            # Process to remove TLS/OAuth components
            rc_cleaned = _process_ray_cluster_yaml(rc_copy)

            # Restore fields needed for replace operation and add secure network annotation
            if "metadata" not in rc_cleaned:
                rc_cleaned["metadata"] = {}
            if resource_version:
                rc_cleaned["metadata"]["resourceVersion"] = resource_version
            if uid:
                rc_cleaned["metadata"]["uid"] = uid

            # Add ODH secure trusted network annotation
            if "annotations" not in rc_cleaned["metadata"]:
                rc_cleaned["metadata"]["annotations"] = {}
            rc_cleaned["metadata"]["annotations"][
                "odh.ray.io/secure-trusted-network"
            ] = "true"

            if dry_run:
                print(
                    f"[DRY RUN] Would cleanup RayCluster '{cluster_name_current}' in namespace '{namespace_current}'"
                )
                print(f"  - Would remove TLS/OAuth components and finalizers")
                print(f"  - Would apply back to cluster using replace operation")
                cleaned_count += 1
            else:
                # Use replace instead of server-side apply to actually remove fields
                # Server-side apply merges, which keeps existing fields; replace removes them
                try:
                    api_instance.replace_namespaced_custom_object(
                        group="ray.io",
                        version="v1",
                        namespace=namespace_current,
                        plural="rayclusters",
                        name=cluster_name_current,
                        body=rc_cleaned,
                    )
                    print(
                        f"Cleaned up RayCluster '{cluster_name_current}' in namespace '{namespace_current}'"
                    )
                    cleaned_count += 1
                except Exception as replace_error:
                    # If replace fails, provide helpful error message
                    raise Exception(f"Failed to replace cluster: {replace_error}")

        except Exception as e:
            print(
                f"Failed to cleanup RayCluster '{cluster_name_current}' in namespace '{namespace_current}': {e}"
            )
            failed_count += 1

    # Print summary
    if dry_run:
        print(
            f"\n[DRY RUN] Cleanup Summary: {cleaned_count} would be cleaned, {failed_count} would fail"
        )
    else:
        print(f"\nCleanup Summary: {cleaned_count} cleaned, {failed_count} failed")

    return {"cleaned": cleaned_count, "failed": failed_count}


def delete_ray_clusters(
    cluster_name: Optional[str] = None,
    namespace: Optional[str] = None,
    all_in_namespace: bool = False,
    dry_run: bool = False,
    auto_confirm: bool = False,
) -> Dict[str, int]:
    """
    Deletes RayClusters from the cluster.

    This function can delete:
    - A specific RayCluster by name and namespace
    - All RayClusters in a specific namespace (with --all flag)
    - All RayClusters across all namespaces (with --all and no namespace specified)

    Args:
        cluster_name (Optional[str]): Name of specific cluster to delete
        namespace (Optional[str]): Namespace to delete from. Required if cluster_name is specified.
        all_in_namespace (bool): If True, deletes all clusters in the namespace(s)
        dry_run (bool): If True, shows what would be deleted without actually deleting
        auto_confirm (bool): If True, skips confirmation prompt (for automation)

    Returns:
        Dict[str, int]: Dictionary with 'deleted' and 'failed' counts

    Raises:
        ValueError: If invalid combination of arguments provided
        RuntimeError: If unable to connect to Kubernetes cluster
    """
    try:
        config_check()
    except Exception as e:
        raise RuntimeError(f"Failed to connect to Kubernetes cluster: {e}")

    # Validate arguments
    if cluster_name and not namespace:
        raise ValueError(
            "Namespace must be specified when deleting a specific cluster by name"
        )

    if not cluster_name and not all_in_namespace:
        raise ValueError(
            "Either specify a cluster name or use --all flag to delete multiple clusters"
        )

    api_instance = client.CustomObjectsApi(get_api_client())
    core_api = client.CoreV1Api(get_api_client())

    deleted_count = 0
    failed_count = 0
    clusters_to_delete = []

    if dry_run:
        print("=== DRY RUN MODE - No clusters will be deleted ===\n")

    # Case 1: Delete specific cluster
    if cluster_name:
        clusters_to_delete.append({"name": cluster_name, "namespace": namespace})

    # Case 2: Delete all in namespace(s)
    elif all_in_namespace:
        # Get list of namespaces
        if namespace:
            namespace_names = [namespace]
        else:
            try:
                namespaces = core_api.list_namespace()
                namespace_names = [ns.metadata.name for ns in namespaces.items]
            except Exception as e:
                print(f"Error listing namespaces: {e}")
                return {"deleted": 0, "failed": 0}

        # Collect all clusters from specified namespace(s)
        for ns in namespace_names:
            try:
                rcs = api_instance.list_namespaced_custom_object(
                    group="ray.io",
                    version="v1",
                    namespace=ns,
                    plural="rayclusters",
                )

                for rc in rcs.get("items", []):
                    cluster_name_found = rc.get("metadata", {}).get("name")
                    if cluster_name_found:
                        clusters_to_delete.append(
                            {"name": cluster_name_found, "namespace": ns}
                        )

            except Exception as e:
                if namespace:  # Only print error if user specified a namespace
                    print(f"Error listing RayClusters in namespace '{ns}': {e}")
                continue

    if not clusters_to_delete:
        print("No RayClusters found to delete")
        return {"deleted": 0, "failed": 0}

    print(f"Found {len(clusters_to_delete)} RayCluster(s) to delete\n")

    # Show warning and get confirmation if not dry-run and not auto-confirmed
    if not dry_run and not auto_confirm:
        print("WARNING: This will PERMANENTLY DELETE the following RayCluster(s):")
        for cluster_info in clusters_to_delete:
            print(
                f"  - {cluster_info['name']} (namespace: {cluster_info['namespace']})"
            )

        print("\nIMPORTANT: This operation is IRREVERSIBLE!")
        print("All cluster data, configurations, and running workloads will be lost.")
        print("Consider using 'export' to backup clusters before deleting.")

        response = (
            input(
                "\nAre you absolutely sure you want to delete these clusters? (yes/no): "
            )
            .strip()
            .lower()
        )
        if response not in ["yes", "y"]:
            print("Operation cancelled by user.")
            return {"deleted": 0, "failed": 0}
        print()

    # Delete clusters
    for cluster_info in clusters_to_delete:
        try:
            if dry_run:
                print(
                    f"[DRY RUN] Would delete RayCluster '{cluster_info['name']}' from namespace '{cluster_info['namespace']}'"
                )
                deleted_count += 1
            else:
                api_instance.delete_namespaced_custom_object(
                    group="ray.io",
                    version="v1",
                    namespace=cluster_info["namespace"],
                    plural="rayclusters",
                    name=cluster_info["name"],
                )
                print(
                    f"Deleted RayCluster '{cluster_info['name']}' from namespace '{cluster_info['namespace']}'"
                )
                deleted_count += 1
        except Exception as e:
            print(
                f"Failed to delete RayCluster '{cluster_info['name']}' from namespace '{cluster_info['namespace']}': {e}"
            )
            failed_count += 1

    # Print summary
    if dry_run:
        print(
            f"\n[DRY RUN] Delete Summary: {deleted_count} would be deleted, {failed_count} would fail"
        )
    else:
        print(f"\nDelete Summary: {deleted_count} deleted, {failed_count} failed")

    return {"deleted": deleted_count, "failed": failed_count}


def list_ray_clusters(
    namespace: Optional[str] = None, output_format: str = "table"
) -> List[Dict]:
    """
    Lists all RayClusters across all namespaces or in a specific namespace.

    This function:
    - Queries all namespaces (or a specific namespace) for RayClusters
    - Displays cluster information including name, namespace, status, and resource details
    - Supports different output formats (table or yaml)

    Args:
        namespace (Optional[str]): Specific namespace to query. If None, queries all namespaces.
        output_format (str): Output format - "table" (default) or "yaml"

    Returns:
        List[Dict]: List of RayCluster information dictionaries
    """
    try:
        config_check()
    except Exception as e:
        raise RuntimeError(f"Failed to connect to Kubernetes cluster: {e}")

    api_instance = client.CustomObjectsApi(get_api_client())
    core_api = client.CoreV1Api(get_api_client())
    clusters_info = []

    # Get list of namespaces to query
    if namespace:
        namespace_names = [namespace]
    else:
        try:
            namespaces = core_api.list_namespace()
            namespace_names = [ns.metadata.name for ns in namespaces.items]
        except Exception as e:
            print(f"Error listing namespaces: {e}")
            return clusters_info

    # Query each namespace for RayClusters
    for ns in namespace_names:
        try:
            rcs = api_instance.list_namespaced_custom_object(
                group="ray.io",
                version="v1",
                namespace=ns,
                plural="rayclusters",
            )
        except Exception as e:
            if namespace:  # Only print error if user specified a namespace
                print(f"Error listing RayClusters in namespace '{ns}': {e}")
            continue

        # Process each RayCluster
        for rc in rcs.get("items", []):
            cluster_name = rc.get("metadata", {}).get("name", "unknown")
            cluster_ns = rc.get("metadata", {}).get("namespace", "unknown")

            # Extract status
            status = rc.get("status", {}).get("state", "unknown")

            # Extract resource information
            head_resources = {}
            worker_resources = {}
            num_workers = 0

            try:
                head_spec = rc["spec"]["headGroupSpec"]["template"]["spec"][
                    "containers"
                ][0]["resources"]
                head_resources = {
                    "cpu_request": head_spec.get("requests", {}).get("cpu", "N/A"),
                    "cpu_limit": head_spec.get("limits", {}).get("cpu", "N/A"),
                    "memory_request": head_spec.get("requests", {}).get(
                        "memory", "N/A"
                    ),
                    "memory_limit": head_spec.get("limits", {}).get("memory", "N/A"),
                }

                worker_spec = rc["spec"]["workerGroupSpecs"][0]
                num_workers = worker_spec.get("replicas", 0)
                worker_container_resources = worker_spec["template"]["spec"][
                    "containers"
                ][0]["resources"]
                worker_resources = {
                    "cpu_request": worker_container_resources.get("requests", {}).get(
                        "cpu", "N/A"
                    ),
                    "cpu_limit": worker_container_resources.get("limits", {}).get(
                        "cpu", "N/A"
                    ),
                    "memory_request": worker_container_resources.get(
                        "requests", {}
                    ).get("memory", "N/A"),
                    "memory_limit": worker_container_resources.get("limits", {}).get(
                        "memory", "N/A"
                    ),
                }
            except (KeyError, IndexError):
                pass  # Use default empty values

            cluster_info = {
                "name": cluster_name,
                "namespace": cluster_ns,
                "status": status,
                "num_workers": num_workers,
                "head_resources": head_resources,
                "worker_resources": worker_resources,
            }
            clusters_info.append(cluster_info)

    # Display results
    if output_format == "yaml":
        print(yaml.dump(clusters_info, default_flow_style=False))
    else:
        # Table format (default)
        if not clusters_info:
            print("No RayClusters found")
            return clusters_info

        print(f"\nFound {len(clusters_info)} RayCluster(s):\n")
        print(f"{'Name':<30} {'Namespace':<20} {'Status':<15} {'Workers':<10}")
        print("-" * 80)

        for cluster in clusters_info:
            print(
                f"{cluster['name']:<30} "
                f"{cluster['namespace']:<20} "
                f"{cluster['status']:<15} "
                f"{cluster['num_workers']:<10}"
            )

        # Print detailed resource information
        if clusters_info:
            print("\nDetailed Resource Information:")
            print("=" * 80)
            for cluster in clusters_info:
                print(f"\n{cluster['name']} (namespace: {cluster['namespace']})")
                print(f"  Status: {cluster['status']}")
                print(f"  Workers: {cluster['num_workers']}")

                if cluster["head_resources"]:
                    print("  Head Resources:")
                    print(
                        f"    CPU: {cluster['head_resources'].get('cpu_request', 'N/A')} (request) / {cluster['head_resources'].get('cpu_limit', 'N/A')} (limit)"
                    )
                    print(
                        f"    Memory: {cluster['head_resources'].get('memory_request', 'N/A')} (request) / {cluster['head_resources'].get('memory_limit', 'N/A')} (limit)"
                    )

                if cluster["worker_resources"]:
                    print("  Worker Resources:")
                    print(
                        f"    CPU: {cluster['worker_resources'].get('cpu_request', 'N/A')} (request) / {cluster['worker_resources'].get('cpu_limit', 'N/A')} (limit)"
                    )
                    print(
                        f"    Memory: {cluster['worker_resources'].get('memory_request', 'N/A')} (request) / {cluster['worker_resources'].get('memory_limit', 'N/A')} (limit)"
                    )

    return clusters_info


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="RayCluster Migration Tool - Export, import, list, cleanup, and delete RayClusters across Kubernetes environments",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List all RayClusters across all namespaces
  %(prog)s list

  # List RayClusters in a specific namespace
  %(prog)s list --namespace my-namespace

  # List with YAML output format
  %(prog)s list --format yaml

  # Export all RayClusters to a directory
  %(prog)s export ./exported_clusters

  # Export and cleanup (delete from cluster after export)
  %(prog)s export ./backup --cleanup

  # Cleanup (remove TLS/OAuth) from a specific cluster in-place
  %(prog)s cleanup my-cluster --namespace default --dry-run
  %(prog)s cleanup my-cluster --namespace default

  # Cleanup all clusters in a namespace
  %(prog)s cleanup --all --namespace production --dry-run
  %(prog)s cleanup --all --namespace production
  %(prog)s cleanup --all --namespace production --yes  # Skip confirmation

  # Cleanup all clusters across all namespaces
  %(prog)s cleanup --all --dry-run
  %(prog)s cleanup --all

  # Delete a specific RayCluster
  %(prog)s delete my-cluster --namespace default

  # Delete all RayClusters in a namespace (with confirmation via dry-run)
  %(prog)s delete --all --namespace production --dry-run
  %(prog)s delete --all --namespace production
  %(prog)s delete --all --namespace production --yes  # Skip confirmation for automation

  # Delete all RayClusters in all namespaces
  %(prog)s delete --all

  # Import RayClusters from a directory (dry-run first)
  %(prog)s import ./exported_clusters --dry-run

  # Import RayClusters from a directory
  %(prog)s import ./exported_clusters

  # Import a single RayCluster YAML file
  %(prog)s import ./my_cluster.yaml

  # Import with force flag to overwrite conflicts
  %(prog)s import ./exported_clusters --force
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # List command
    list_parser = subparsers.add_parser(
        "list", help="List all RayClusters in the cluster"
    )
    list_parser.add_argument(
        "--namespace",
        "-n",
        help="Specific namespace to query (default: all namespaces)",
    )
    list_parser.add_argument(
        "--format",
        "-f",
        choices=["table", "yaml"],
        default="table",
        help="Output format (default: table)",
    )

    # Export command
    export_parser = subparsers.add_parser(
        "export", help="Export all RayClusters from all namespaces to YAML files"
    )
    export_parser.add_argument(
        "output_dir", help="Directory path where YAML files will be saved"
    )
    export_parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Delete RayClusters from cluster after exporting (backup and cleanup)",
    )
    export_parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Skip confirmation prompt (for automation)",
    )

    # Cleanup command
    cleanup_parser = subparsers.add_parser(
        "cleanup",
        help="Remove TLS/OAuth components from RayClusters in-place (without export or delete)",
    )
    cleanup_parser.add_argument(
        "cluster_name",
        nargs="?",
        help="Name of specific cluster to cleanup (requires --namespace)",
    )
    cleanup_parser.add_argument(
        "--namespace",
        "-n",
        help="Namespace to cleanup (required for specific cluster, optional with --all)",
    )
    cleanup_parser.add_argument(
        "--all",
        action="store_true",
        help="Cleanup all RayClusters in namespace (or all namespaces if no namespace specified)",
    )
    cleanup_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be cleaned without actually modifying clusters",
    )
    cleanup_parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Skip confirmation prompt (for automation)",
    )

    # Delete command
    delete_parser = subparsers.add_parser(
        "delete", help="Delete RayClusters from the cluster"
    )
    delete_parser.add_argument(
        "cluster_name",
        nargs="?",
        help="Name of specific cluster to delete (requires --namespace)",
    )
    delete_parser.add_argument(
        "--namespace",
        "-n",
        help="Namespace to delete from (required for specific cluster, optional with --all)",
    )
    delete_parser.add_argument(
        "--all",
        action="store_true",
        help="Delete all RayClusters in namespace (or all namespaces if no namespace specified)",
    )
    delete_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be deleted without actually deleting",
    )
    delete_parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Skip confirmation prompt (for automation)",
    )

    # Import command
    import_parser = subparsers.add_parser(
        "import",
        help="Import RayClusters from YAML files and apply them to the cluster",
    )
    import_parser.add_argument(
        "source_path", help="Path to a YAML file or directory containing YAML files"
    )
    import_parser.add_argument(
        "--force", action="store_true", help="Force apply in case of conflicts"
    )
    import_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be applied without actually applying changes",
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    try:
        if args.command == "list":
            list_ray_clusters(namespace=args.namespace, output_format=args.format)
        elif args.command == "export":
            export_ray_clusters(
                args.output_dir, cleanup=args.cleanup, auto_confirm=args.yes
            )
        elif args.command == "cleanup":
            cleanup_ray_clusters(
                cluster_name=args.cluster_name,
                namespace=args.namespace,
                all_in_namespace=args.all,
                dry_run=args.dry_run,
                auto_confirm=args.yes,
            )
        elif args.command == "delete":
            delete_ray_clusters(
                cluster_name=args.cluster_name,
                namespace=args.namespace,
                all_in_namespace=args.all,
                dry_run=args.dry_run,
                auto_confirm=args.yes,
            )
        elif args.command == "import":
            import_ray_clusters(
                args.source_path, force=args.force, dry_run=args.dry_run
            )
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

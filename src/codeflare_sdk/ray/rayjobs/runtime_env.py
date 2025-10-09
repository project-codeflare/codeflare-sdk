from __future__ import annotations  # Postpone evaluation of annotations

import logging
import os
import re
import yaml
import zipfile
import base64
import io
from typing import Dict, Any, Optional, List, TYPE_CHECKING
from codeflare_sdk.common.utils.constants import MOUNT_PATH
from kubernetes import client
from ray.runtime_env import RuntimeEnv

from codeflare_sdk.ray.rayjobs.config import ManagedClusterConfig
from ...common.kubernetes_cluster.auth import get_api_client

# Use TYPE_CHECKING to avoid circular import at runtime
if TYPE_CHECKING:
    from codeflare_sdk.ray.rayjobs.rayjob import RayJob

logger = logging.getLogger(__name__)

# Regex pattern for finding Python files in entrypoint commands
# Matches paths like: test.py, ./test.py, dir/test.py, my-dir/test.py
PYTHON_FILE_PATTERN = r"(?:python\s+)?([./\w/-]+\.py)"

# Path where working_dir will be unzipped on submitter pod
UNZIP_PATH = "/tmp/rayjob-working-dir"


def _normalize_runtime_env(
    runtime_env: Optional[RuntimeEnv],
) -> Optional[Dict[str, Any]]:
    if runtime_env is None:
        return None
    return runtime_env.to_dict()


def extract_all_local_files(job: RayJob) -> Optional[Dict[str, str]]:
    """
    Prepare local files for ConfigMap upload.

    - If runtime_env has local working_dir: zip entire directory into single file
    - If single entrypoint file (no working_dir): extract that file
    - If remote working_dir URL: return None (pass through to Ray)

    Returns:
        Dict with either:
        - {"working_dir.zip": <base64_encoded_zip>} for zipped directories
        - {"script.py": <file_content>} for single files
        - None for remote working_dir or no files
    """
    # Convert RuntimeEnv to dict for processing
    runtime_env_dict = _normalize_runtime_env(job.runtime_env)

    # If there's a remote working_dir, don't extract local files
    if (
        runtime_env_dict
        and "working_dir" in runtime_env_dict
        and not os.path.isdir(runtime_env_dict["working_dir"])
    ):
        logger.info(
            f"Remote working_dir detected: {runtime_env_dict['working_dir']}. "
            "Skipping local file extraction - using remote source."
        )
        return None

    # If there's a local working_dir, zip it
    if (
        runtime_env_dict
        and "working_dir" in runtime_env_dict
        and os.path.isdir(runtime_env_dict["working_dir"])
    ):
        working_dir = runtime_env_dict["working_dir"]
        logger.info(f"Zipping local working_dir: {working_dir}")
        zip_data = _zip_directory(working_dir)
        if zip_data:
            # Encode zip as base64 for ConfigMap storage
            zip_base64 = base64.b64encode(zip_data).decode("utf-8")
            return {"working_dir.zip": zip_base64}

    # If no working_dir, check for single entrypoint file
    entrypoint_file = _extract_single_entrypoint_file(job)
    if entrypoint_file:
        return entrypoint_file

    return None


def _zip_directory(directory_path: str) -> Optional[bytes]:
    """
    Zip entire directory preserving structure.

    Args:
        directory_path: Path to directory to zip

    Returns:
        Bytes of zip file, or None on error
    """
    try:
        # Create in-memory zip file
        zip_buffer = io.BytesIO()

        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
            # Walk through directory and add all files
            for root, dirs, files in os.walk(directory_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    # Calculate relative path from directory_path
                    arcname = os.path.relpath(file_path, directory_path)
                    zipf.write(file_path, arcname)
                    logger.debug(f"Added to zip: {arcname}")

        zip_data = zip_buffer.getvalue()
        logger.info(
            f"Successfully zipped directory: {directory_path} ({len(zip_data)} bytes)"
        )
        return zip_data

    except (IOError, OSError) as e:
        logger.error(f"Failed to zip directory {directory_path}: {e}")
        return None


def _extract_single_entrypoint_file(job: RayJob) -> Optional[Dict[str, str]]:
    """
    Extract single Python file from entrypoint if no working_dir specified.

    Returns a dict with metadata about the file path structure so we can
    preserve it when mounting via ConfigMap.

    Args:
        job: RayJob instance

    Returns:
        Dict with special format: {"__entrypoint_path__": path, "filename": content}
        This allows us to preserve directory structure when mounting
    """
    if not job.entrypoint:
        return None

    # Look for Python file in entrypoint
    matches = re.findall(PYTHON_FILE_PATTERN, job.entrypoint)

    for file_path in matches:
        # Check if it's a local file
        if os.path.isfile(file_path):
            try:
                with open(file_path, "r") as f:
                    content = f.read()

                # Use basename as key (ConfigMap keys can't have slashes)
                # But store the full path for later use in ConfigMap item.path
                filename = os.path.basename(file_path)
                relative_path = file_path.lstrip("./")

                logger.info(f"Extracted single entrypoint file: {file_path}")

                # Return special format with metadata
                return {"__entrypoint_path__": relative_path, filename: content}

            except (IOError, OSError) as e:
                logger.warning(f"Could not read entrypoint file {file_path}: {e}")

    return None


def process_runtime_env(
    job: RayJob, files: Optional[Dict[str, str]] = None
) -> Optional[str]:
    """
    Process runtime_env field to handle env_vars, pip dependencies, and working_dir.

    Returns:
        Processed runtime environment as YAML string, or None if no processing needed
    """
    # Convert RuntimeEnv to dict for processing
    runtime_env_dict = _normalize_runtime_env(job.runtime_env)

    processed_env = {}

    # Handle env_vars
    if runtime_env_dict and "env_vars" in runtime_env_dict:
        processed_env["env_vars"] = runtime_env_dict["env_vars"]
        logger.info(
            f"Added {len(runtime_env_dict['env_vars'])} environment variables to runtime_env"
        )

    # Handle pip dependencies
    if runtime_env_dict and "pip" in runtime_env_dict:
        pip_deps = process_pip_dependencies(job, runtime_env_dict["pip"])
        if pip_deps:
            processed_env["pip"] = pip_deps

    # Handle working_dir
    if runtime_env_dict and "working_dir" in runtime_env_dict:
        working_dir = runtime_env_dict["working_dir"]
        if os.path.isdir(working_dir):
            # Local working directory - will be zipped and unzipped to UNZIP_PATH by submitter pod
            processed_env["working_dir"] = UNZIP_PATH
            logger.info(
                f"Local working_dir will be zipped, mounted, and unzipped to: {UNZIP_PATH}"
            )
        else:
            # Remote URI (e.g., GitHub, S3) - pass through as-is
            processed_env["working_dir"] = working_dir
            logger.info(f"Using remote working_dir: {working_dir}")

    # If no working_dir specified but we have files (single file case)
    elif not runtime_env_dict or "working_dir" not in runtime_env_dict:
        if files and "working_dir.zip" not in files:
            # Single file case - mount at MOUNT_PATH
            processed_env["working_dir"] = MOUNT_PATH
            logger.info(f"Single file will be mounted at: {MOUNT_PATH}")

    # Convert to YAML string if we have any processed environment
    if processed_env:
        return yaml.dump(processed_env, default_flow_style=False)

    return None


def process_pip_dependencies(job: RayJob, pip_spec) -> Optional[List[str]]:
    """
    Process pip dependencies from runtime_env.

    Args:
        pip_spec: Can be a list of packages, a string path to requirements.txt, or dict

    Returns:
        List of pip dependencies
    """
    if isinstance(pip_spec, list):
        # Already a list of dependencies
        logger.info(f"Using provided pip dependencies: {len(pip_spec)} packages")
        return pip_spec
    elif isinstance(pip_spec, str):
        # Assume it's a path to requirements.txt
        return parse_requirements_file(pip_spec)
    elif isinstance(pip_spec, dict):
        # Handle dict format (e.g., {"packages": [...], "pip_check": False})
        if "packages" in pip_spec:
            logger.info(
                f"Using pip dependencies from dict: {len(pip_spec['packages'])} packages"
            )
            return pip_spec["packages"]

    logger.warning(f"Unsupported pip specification format: {type(pip_spec)}")
    return None


def parse_requirements_file(requirements_path: str) -> Optional[List[str]]:
    """
    Parse a requirements.txt file and return list of dependencies.

    Args:
        requirements_path: Path to requirements.txt file

    Returns:
        List of pip dependencies
    """
    if not os.path.isfile(requirements_path):
        logger.warning(f"Requirements file not found: {requirements_path}")
        return None

    try:
        with open(requirements_path, "r") as f:
            lines = f.readlines()

        # Parse requirements, filtering out comments and empty lines
        requirements = []
        for line in lines:
            line = line.strip()
            if line and not line.startswith("#"):
                requirements.append(line)

        logger.info(f"Parsed {len(requirements)} dependencies from {requirements_path}")
        return requirements

    except (IOError, OSError) as e:
        logger.warning(f"Could not read requirements file {requirements_path}: {e}")
        return None


def create_configmap_from_spec(
    job: RayJob, configmap_spec: Dict[str, Any], rayjob_result: Dict[str, Any] = None
) -> str:
    """
    Create ConfigMap from specification via Kubernetes API.

    Args:
        configmap_spec: ConfigMap specification dictionary
        rayjob_result: The result from RayJob creation containing UID

    Returns:
        str: Name of the created ConfigMap
    """

    configmap_name = configmap_spec["metadata"]["name"]

    metadata = client.V1ObjectMeta(**configmap_spec["metadata"])

    # Add owner reference if we have the RayJob result
    if (
        rayjob_result
        and isinstance(rayjob_result, dict)
        and rayjob_result.get("metadata", {}).get("uid")
    ):
        logger.info(
            f"Adding owner reference to ConfigMap '{configmap_name}' with RayJob UID: {rayjob_result['metadata']['uid']}"
        )
        metadata.owner_references = [
            client.V1OwnerReference(
                api_version="ray.io/v1",
                kind="RayJob",
                name=job.name,
                uid=rayjob_result["metadata"]["uid"],
                controller=True,
                block_owner_deletion=True,
            )
        ]
    else:
        logger.warning(
            f"No valid RayJob result with UID found, ConfigMap '{configmap_name}' will not have owner reference. Result: {rayjob_result}"
        )

    # Convert dict spec to V1ConfigMap
    configmap = client.V1ConfigMap(
        metadata=metadata,
        data=configmap_spec["data"],
    )

    # Create ConfigMap via Kubernetes API
    k8s_api = client.CoreV1Api(get_api_client())
    try:
        k8s_api.create_namespaced_config_map(namespace=job.namespace, body=configmap)
        logger.info(
            f"Created ConfigMap '{configmap_name}' with {len(configmap_spec['data'])} files"
        )
    except client.ApiException as e:
        if e.status == 409:  # Already exists
            logger.info(f"ConfigMap '{configmap_name}' already exists, updating...")
            k8s_api.replace_namespaced_config_map(
                name=configmap_name, namespace=job.namespace, body=configmap
            )
        else:
            raise RuntimeError(f"Failed to create ConfigMap '{configmap_name}': {e}")

    return configmap_name


def create_file_configmap(
    job: RayJob, files: Dict[str, str], rayjob_result: Dict[str, Any]
):
    """
    Create ConfigMap with owner reference for local files.
    """
    # Use a basic config builder for ConfigMap creation
    config_builder = ManagedClusterConfig()

    # Filter out metadata keys (like __entrypoint_path__) from ConfigMap data
    configmap_files = {k: v for k, v in files.items() if not k.startswith("__")}

    # Validate and build ConfigMap spec
    config_builder.validate_configmap_size(configmap_files)
    configmap_spec = config_builder.build_file_configmap_spec(
        job_name=job.name, namespace=job.namespace, files=configmap_files
    )

    # Create ConfigMap with owner reference
    # TODO Error handling
    create_configmap_from_spec(job, configmap_spec, rayjob_result)

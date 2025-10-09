# Copyright 2025 IBM, Red Hat
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


import pytest
import os
from unittest.mock import MagicMock, patch
from codeflare_sdk.common.utils.constants import MOUNT_PATH, RAY_VERSION
from ray.runtime_env import RuntimeEnv

from codeflare_sdk.ray.rayjobs.rayjob import RayJob
from codeflare_sdk.ray.cluster.config import ClusterConfiguration
from codeflare_sdk.ray.rayjobs.config import ManagedClusterConfig
from kubernetes.client import (
    V1Volume,
    V1VolumeMount,
    V1Toleration,
    V1ConfigMapVolumeSource,
    ApiException,
)

from codeflare_sdk.ray.rayjobs.runtime_env import (
    create_configmap_from_spec,
    extract_all_local_files,
)


def test_rayjob_with_remote_working_dir(auto_mock_setup):
    """
    Test RayJob with remote working directory in runtime_env.
    Should not extract local files and should pass through remote URL.
    """
    runtime_env = RuntimeEnv(
        working_dir="https://github.com/org/repo/archive/refs/heads/main.zip",
        pip=["numpy", "pandas"],
        env_vars={"TEST_VAR": "test_value"},
    )

    rayjob = RayJob(
        job_name="test-job",
        entrypoint="python test.py",
        cluster_name="test-cluster",
        runtime_env=runtime_env,
        namespace="test-namespace",
    )

    assert rayjob.runtime_env == runtime_env

    # Should not extract any local files due to remote working_dir
    files = extract_all_local_files(rayjob)
    assert files is None

    rayjob_cr = rayjob._build_rayjob_cr()

    # Should have runtimeEnvYAML with all fields
    expected_runtime_env = (
        "env_vars:\n"
        "  TEST_VAR: test_value\n"
        "pip:\n"
        "- numpy\n"
        "- pandas\n"
        "working_dir: https://github.com/org/repo/archive/refs/heads/main.zip\n"
    )
    assert rayjob_cr["spec"]["runtimeEnvYAML"] == expected_runtime_env

    # Should not have submitterPodTemplate since no local files
    assert "submitterPodTemplate" not in rayjob_cr["spec"]

    # Entrypoint should be unchanged
    assert rayjob_cr["spec"]["entrypoint"] == "python test.py"


def test_build_file_configmap_spec():
    """
    Test building ConfigMap specification for files.
    """
    config = ManagedClusterConfig()
    files = {"main.py": "print('main')", "helper.py": "print('helper')"}

    spec = config.build_file_configmap_spec(
        job_name="test-job", namespace="test-namespace", files=files
    )

    assert spec["apiVersion"] == "v1"
    assert spec["kind"] == "ConfigMap"
    assert spec["metadata"]["name"] == "test-job-files"
    assert spec["metadata"]["namespace"] == "test-namespace"
    assert spec["data"] == files


def test_build_file_volume_specs():
    """
    Test building volume and mount specifications for files.
    """
    config = ManagedClusterConfig()

    volume_spec, mount_spec = config.build_file_volume_specs(
        configmap_name="test-files", mount_path="/custom/path"
    )

    assert volume_spec["name"] == "ray-job-files"
    assert volume_spec["configMap"]["name"] == "test-files"

    assert mount_spec["name"] == "ray-job-files"
    assert mount_spec["mountPath"] == "/custom/path"


def test_add_file_volumes():
    """
    Test adding file volumes to cluster configuration.
    """
    config = ManagedClusterConfig()

    # Initially no volumes
    assert len(config.volumes) == 0
    assert len(config.volume_mounts) == 0

    config.add_file_volumes(configmap_name="test-files")

    assert len(config.volumes) == 1
    assert len(config.volume_mounts) == 1

    volume = config.volumes[0]
    mount = config.volume_mounts[0]

    assert volume.name == "ray-job-files"
    assert volume.config_map.name == "test-files"

    assert mount.name == "ray-job-files"
    assert mount.mount_path == MOUNT_PATH


def test_add_file_volumes_duplicate_prevention():
    """
    Test that adding file volumes twice doesn't create duplicates.
    """
    config = ManagedClusterConfig()

    # Add volumes twice
    config.add_file_volumes(configmap_name="test-files")
    config.add_file_volumes(configmap_name="test-files")

    assert len(config.volumes) == 1
    assert len(config.volume_mounts) == 1


def test_create_configmap_from_spec(auto_mock_setup):
    """
    Test creating ConfigMap via Kubernetes API.
    """
    mock_api_instance = auto_mock_setup["k8s_api"]

    rayjob = RayJob(
        job_name="test-job",
        cluster_name="existing-cluster",
        entrypoint="python test.py",
        namespace="test-namespace",
    )

    configmap_spec = {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {"name": "test-files", "namespace": "test-namespace"},
        "data": {"test.py": "print('test')"},
    }

    result = create_configmap_from_spec(rayjob, configmap_spec)

    assert result == "test-files"
    mock_api_instance.create_namespaced_config_map.assert_called_once()


def test_create_configmap_already_exists(auto_mock_setup):
    """
    Test creating ConfigMap when it already exists (409 conflict).
    """
    mock_api_instance = auto_mock_setup["k8s_api"]

    mock_api_instance.create_namespaced_config_map.side_effect = ApiException(
        status=409
    )

    rayjob = RayJob(
        job_name="test-job",
        cluster_name="existing-cluster",
        entrypoint="python test.py",
        namespace="test-namespace",
    )

    configmap_spec = {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {"name": "test-files", "namespace": "test-namespace"},
        "data": {"test.py": "print('test')"},
    }

    result = create_configmap_from_spec(rayjob, configmap_spec)

    assert result == "test-files"
    mock_api_instance.create_namespaced_config_map.assert_called_once()
    mock_api_instance.replace_namespaced_config_map.assert_called_once()


def test_create_configmap_with_owner_reference_basic(mocker, auto_mock_setup, caplog):
    """
    Test creating ConfigMap with owner reference from valid RayJob result.
    """
    mock_api_instance = auto_mock_setup["k8s_api"]

    # Mock client.V1ObjectMeta and V1ConfigMap
    mock_v1_metadata = mocker.patch("kubernetes.client.V1ObjectMeta")
    mock_metadata_instance = MagicMock()
    mock_v1_metadata.return_value = mock_metadata_instance

    rayjob = RayJob(
        job_name="test-job",
        cluster_name="existing-cluster",
        entrypoint="python test.py",
        namespace="test-namespace",
    )

    configmap_spec = {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {
            "name": "test-files",
            "namespace": "test-namespace",
            "labels": {
                "ray.io/job-name": "test-job",
                "app.kubernetes.io/managed-by": "codeflare-sdk",
                "app.kubernetes.io/component": "rayjob-files",
            },
        },
        "data": {"test.py": "print('test')"},
    }

    # Valid RayJob result with UID
    rayjob_result = {
        "metadata": {
            "name": "test-job",
            "namespace": "test-namespace",
            "uid": "a4dd4c5a-ab61-411d-b4d1-4abb5177422a",
        }
    }

    with caplog.at_level("INFO"):
        result = create_configmap_from_spec(rayjob, configmap_spec, rayjob_result)

    assert result == "test-files"

    # Verify owner reference was set
    expected_owner_ref = mocker.ANY  # We'll check via the logs
    assert (
        "Adding owner reference to ConfigMap 'test-files' with RayJob UID: a4dd4c5a-ab61-411d-b4d1-4abb5177422a"
        in caplog.text
    )

    assert mock_metadata_instance.owner_references is not None
    mock_api_instance.create_namespaced_config_map.assert_called_once()


def test_create_configmap_without_owner_reference_no_uid(
    mocker, auto_mock_setup, caplog
):
    """
    Test creating ConfigMap without owner reference when RayJob has no UID.
    """
    mock_api_instance = auto_mock_setup["k8s_api"]

    mock_v1_metadata = mocker.patch("kubernetes.client.V1ObjectMeta")
    mock_metadata_instance = MagicMock()
    mock_v1_metadata.return_value = mock_metadata_instance

    rayjob = RayJob(
        job_name="test-job",
        cluster_name="existing-cluster",
        entrypoint="python test.py",
        namespace="test-namespace",
    )

    configmap_spec = {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {"name": "test-files", "namespace": "test-namespace"},
        "data": {"test.py": "print('test')"},
    }

    # RayJob result without UID
    rayjob_result = {
        "metadata": {
            "name": "test-job",
            "namespace": "test-namespace",
            # No UID field
        }
    }

    with caplog.at_level("WARNING"):
        result = create_configmap_from_spec(rayjob, configmap_spec, rayjob_result)

    assert result == "test-files"

    # Verify warning was logged and no owner reference was set
    assert (
        "No valid RayJob result with UID found, ConfigMap 'test-files' will not have owner reference"
        in caplog.text
    )

    # The important part is that the warning was logged, indicating no owner reference was set
    mock_api_instance.create_namespaced_config_map.assert_called_once()


def test_create_configmap_with_invalid_rayjob_result(auto_mock_setup, caplog):
    """
    Test creating ConfigMap with None or invalid rayjob_result.
    """
    mock_api_instance = auto_mock_setup["k8s_api"]

    rayjob = RayJob(
        job_name="test-job",
        cluster_name="existing-cluster",
        entrypoint="python test.py",
        namespace="test-namespace",
    )

    configmap_spec = {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {"name": "test-files", "namespace": "test-namespace"},
        "data": {"test.py": "print('test')"},
    }

    # Test with None
    with caplog.at_level("WARNING"):
        result = create_configmap_from_spec(rayjob, configmap_spec, None)

    assert result == "test-files"
    assert "No valid RayJob result with UID found" in caplog.text

    # Test with string instead of dict
    caplog.clear()
    with caplog.at_level("WARNING"):
        result = create_configmap_from_spec(rayjob, configmap_spec, "not-a-dict")

    assert result == "test-files"
    assert "No valid RayJob result with UID found" in caplog.text


def test_file_handling_kubernetes_best_practice_flow(mocker, tmp_path):
    """
    Test the Kubernetes best practice flow: pre-declare volume, submit, create ConfigMap.
    """
    mocker.patch("kubernetes.config.load_kube_config")

    mock_api_class = mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")
    mock_api_instance = MagicMock()
    mock_api_class.return_value = mock_api_instance

    submit_result = {
        "metadata": {
            "name": "test-job",
            "namespace": "test-namespace",
            "uid": "test-uid-12345",
        }
    }
    mock_api_instance.submit_job.return_value = submit_result

    # Mock create_file_configmap where it's used (imported into rayjob module)
    mock_create_cm = mocker.patch(
        "codeflare_sdk.ray.rayjobs.rayjob.create_file_configmap"
    )
    mock_add_volumes = mocker.patch.object(ManagedClusterConfig, "add_file_volumes")

    # RayClusterApi is already mocked by auto_mock_setup

    test_file = tmp_path / "test.py"
    test_file.write_text("print('test')")

    call_order = []

    def track_add_volumes(*args, **kwargs):
        call_order.append("add_volumes")
        # Should be called with ConfigMap name
        assert args[0] == "test-job-files"

    def track_submit(*args, **kwargs):
        call_order.append("submit_job")
        return submit_result

    def track_create_cm(*args, **kwargs):
        call_order.append("create_configmap")
        # Args should be: (job, files, rayjob_result)
        assert len(args) >= 3, f"Expected 3 args, got {len(args)}: {args}"
        assert args[2] == submit_result  # rayjob_result should be third arg

    mock_add_volumes.side_effect = track_add_volumes
    mock_api_instance.submit_job.side_effect = track_submit
    mock_create_cm.side_effect = track_create_cm

    original_cwd = os.getcwd()
    try:
        os.chdir(tmp_path)

        cluster_config = ManagedClusterConfig()

        rayjob = RayJob(
            job_name="test-job",
            cluster_config=cluster_config,
            entrypoint="python test.py",
            namespace="test-namespace",
        )

        rayjob.submit()
    finally:
        os.chdir(original_cwd)

    # Verify the order: submit → create ConfigMap
    assert call_order == ["submit_job", "create_configmap"]

    mock_api_instance.submit_job.assert_called_once()
    mock_create_cm.assert_called_once()

    # Verify create_file_configmap was called with: (job, files, rayjob_result)
    # Files dict includes metadata key __entrypoint_path__ for single file case
    call_args = mock_create_cm.call_args[0]
    assert call_args[0] == rayjob
    assert call_args[2] == submit_result
    # Check that the actual file content is present
    assert "test.py" in call_args[1]
    assert call_args[1]["test.py"] == "print('test')"


def test_rayjob_submit_with_files_new_cluster(auto_mock_setup, tmp_path):
    """
    Test RayJob submission with file detection for new cluster.
    """
    mock_api_instance = auto_mock_setup["rayjob_api"]
    mock_api_instance.submit_job.return_value = True

    mock_k8s_instance = auto_mock_setup["k8s_api"]

    # Create test file
    test_file = tmp_path / "test.py"
    test_file.write_text("print('Hello from the test file!')")

    cluster_config = ManagedClusterConfig()

    original_cwd = os.getcwd()
    os.chdir(tmp_path)

    try:
        rayjob = RayJob(
            job_name="test-job",
            cluster_config=cluster_config,
            entrypoint="python test.py",
            namespace="test-namespace",
        )

        # Submit should detect files and handle them
        result = rayjob.submit()

        assert result == "test-job"

        mock_k8s_instance.create_namespaced_config_map.assert_called_once()

        assert len(cluster_config.volumes) == 0
        assert len(cluster_config.volume_mounts) == 0
        # Entrypoint should be adjusted to use just the filename
        assert rayjob.entrypoint == "python test.py"

    finally:
        os.chdir(original_cwd)


def test_create_configmap_api_error_non_409(auto_mock_setup):
    """
    Test _create_configmap_from_spec handles non-409 API errors.
    """
    mock_api_instance = auto_mock_setup["k8s_api"]

    # Configure to raise 500 error
    mock_api_instance.create_namespaced_config_map.side_effect = ApiException(
        status=500
    )

    rayjob = RayJob(
        job_name="test-job",
        cluster_name="existing-cluster",
        entrypoint="python test.py",
        namespace="test-namespace",
    )

    configmap_spec = {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {"name": "test-files", "namespace": "test-namespace"},
        "data": {"test.py": "print('test')"},
    }

    with pytest.raises(RuntimeError, match="Failed to create ConfigMap"):
        create_configmap_from_spec(rayjob, configmap_spec)


def test_add_file_volumes_existing_volume_skip():
    """
    Test add_file_volumes skips when volume already exists (missing coverage).
    """
    config = ManagedClusterConfig()

    # Pre-add a volume with same name
    existing_volume = V1Volume(
        name="ray-job-files",
        config_map=V1ConfigMapVolumeSource(name="existing-files"),
    )
    config.volumes.append(existing_volume)

    config.add_file_volumes(configmap_name="new-files")
    assert len(config.volumes) == 1
    assert len(config.volume_mounts) == 0  # Mount not added due to volume skip


def test_add_file_volumes_existing_mount_skip():
    """
    Test add_file_volumes skips when mount already exists (missing coverage).
    """
    config = ManagedClusterConfig()

    # Pre-add a mount with same name
    existing_mount = V1VolumeMount(name="ray-job-files", mount_path="/existing/path")
    config.volume_mounts.append(existing_mount)

    config.add_file_volumes(configmap_name="new-files")
    assert len(config.volumes) == 0  # Volume not added due to mount skip
    assert len(config.volume_mounts) == 1


def test_zip_directory_functionality(tmp_path):
    """
    Test _zip_directory with real directories and files.
    """
    from codeflare_sdk.ray.rayjobs.runtime_env import _zip_directory

    # Create test directory structure
    test_dir = tmp_path / "working_dir"
    test_dir.mkdir()

    # Create some test files
    (test_dir / "main.py").write_text("print('main script')")
    (test_dir / "utils.py").write_text("def helper(): pass")

    # Create subdirectory with file
    sub_dir = test_dir / "subdir"
    sub_dir.mkdir()
    (sub_dir / "nested.py").write_text("print('nested file')")

    # Test zipping
    zip_data = _zip_directory(str(test_dir))

    assert zip_data is not None
    assert len(zip_data) > 0
    assert isinstance(zip_data, bytes)


def test_zip_directory_error_handling():
    """
    Test _zip_directory error handling for IO errors during zipping.
    """
    from codeflare_sdk.ray.rayjobs.runtime_env import _zip_directory

    # Mock os.walk to raise an OSError
    with patch("os.walk", side_effect=OSError("Permission denied")):
        zip_data = _zip_directory("/some/path")
        assert zip_data is None


def test_extract_all_local_files_with_working_dir(tmp_path):
    """
    Test extract_all_local_files with local working directory.
    """
    # Create test working directory
    working_dir = tmp_path / "working_dir"
    working_dir.mkdir()
    (working_dir / "script.py").write_text("print('working dir script')")

    runtime_env = RuntimeEnv(working_dir=str(working_dir))

    rayjob = RayJob(
        job_name="test-job",
        entrypoint="python script.py",
        runtime_env=runtime_env,
        namespace="test-namespace",
        cluster_name="test-cluster",
    )

    files = extract_all_local_files(rayjob)

    assert files is not None
    assert "working_dir.zip" in files
    assert isinstance(files["working_dir.zip"], str)  # base64 encoded

    # Verify it's valid base64
    import base64

    try:
        decoded = base64.b64decode(files["working_dir.zip"])
        assert len(decoded) > 0
    except Exception:
        pytest.fail("Invalid base64 encoding")


def test_extract_single_entrypoint_file_error_handling(tmp_path):
    """
    Test _extract_single_entrypoint_file with file read errors.
    """
    from codeflare_sdk.ray.rayjobs.runtime_env import _extract_single_entrypoint_file

    # Create a file that exists but make it unreadable
    test_file = tmp_path / "unreadable.py"
    test_file.write_text("print('test')")

    rayjob = RayJob(
        job_name="test-job",
        entrypoint=f"python {test_file}",
        namespace="test-namespace",
        cluster_name="test-cluster",
    )

    # Mock open to raise IOError
    with patch("builtins.open", side_effect=IOError("Permission denied")):
        result = _extract_single_entrypoint_file(rayjob)
        assert result is None


def test_extract_single_entrypoint_file_no_match():
    """
    Test _extract_single_entrypoint_file with no Python file matches.
    """
    from codeflare_sdk.ray.rayjobs.runtime_env import _extract_single_entrypoint_file

    rayjob = RayJob(
        job_name="test-job",
        entrypoint="echo 'no python files here'",
        namespace="test-namespace",
        cluster_name="test-cluster",
    )

    result = _extract_single_entrypoint_file(rayjob)
    assert result is None


def test_parse_requirements_file_valid(tmp_path):
    """
    Test parse_requirements_file with valid requirements.txt.
    """
    from codeflare_sdk.ray.rayjobs.runtime_env import parse_requirements_file

    # Create test requirements file
    req_file = tmp_path / "requirements.txt"
    req_file.write_text(
        """# This is a comment
numpy==1.21.0
pandas>=1.3.0

# Another comment
scikit-learn
"""
    )

    result = parse_requirements_file(str(req_file))

    assert result is not None
    assert len(result) == 3
    assert "numpy==1.21.0" in result
    assert "pandas>=1.3.0" in result
    assert "scikit-learn" in result
    # Comments and empty lines should be filtered out
    assert "# This is a comment" not in result


def test_parse_requirements_file_missing():
    """
    Test parse_requirements_file with non-existent file.
    """
    from codeflare_sdk.ray.rayjobs.runtime_env import parse_requirements_file

    result = parse_requirements_file("/non/existent/requirements.txt")
    assert result is None


def test_parse_requirements_file_read_error(tmp_path):
    """
    Test parse_requirements_file with file read error.
    """
    from codeflare_sdk.ray.rayjobs.runtime_env import parse_requirements_file

    # Create a file
    req_file = tmp_path / "requirements.txt"
    req_file.write_text("numpy==1.21.0")

    # Mock open to raise IOError
    with patch("builtins.open", side_effect=IOError("Permission denied")):
        result = parse_requirements_file(str(req_file))
        assert result is None


def test_process_pip_dependencies_list():
    """
    Test process_pip_dependencies with list input.
    """
    from codeflare_sdk.ray.rayjobs.runtime_env import process_pip_dependencies

    rayjob = RayJob(
        job_name="test-job",
        entrypoint="python test.py",
        namespace="test-namespace",
        cluster_name="test-cluster",
    )

    pip_list = ["numpy", "pandas", "scikit-learn"]
    result = process_pip_dependencies(rayjob, pip_list)

    assert result == pip_list


def test_process_pip_dependencies_requirements_file(tmp_path):
    """
    Test process_pip_dependencies with requirements.txt path.
    """
    from codeflare_sdk.ray.rayjobs.runtime_env import process_pip_dependencies

    # Create test requirements file
    req_file = tmp_path / "requirements.txt"
    req_file.write_text("numpy==1.21.0\npandas>=1.3.0")

    rayjob = RayJob(
        job_name="test-job",
        entrypoint="python test.py",
        namespace="test-namespace",
        cluster_name="test-cluster",
    )

    result = process_pip_dependencies(rayjob, str(req_file))

    assert result is not None
    assert len(result) == 2
    assert "numpy==1.21.0" in result
    assert "pandas>=1.3.0" in result


def test_process_pip_dependencies_dict_format():
    """
    Test process_pip_dependencies with dict format containing packages.
    """
    from codeflare_sdk.ray.rayjobs.runtime_env import process_pip_dependencies

    rayjob = RayJob(
        job_name="test-job",
        entrypoint="python test.py",
        namespace="test-namespace",
        cluster_name="test-cluster",
    )

    pip_dict = {"packages": ["numpy", "pandas"], "pip_check": False}
    result = process_pip_dependencies(rayjob, pip_dict)

    assert result == ["numpy", "pandas"]


def test_process_pip_dependencies_unsupported_format():
    """
    Test process_pip_dependencies with unsupported format.
    """
    from codeflare_sdk.ray.rayjobs.runtime_env import process_pip_dependencies

    rayjob = RayJob(
        job_name="test-job",
        entrypoint="python test.py",
        namespace="test-namespace",
        cluster_name="test-cluster",
    )

    # Test with unsupported format (int)
    result = process_pip_dependencies(rayjob, 12345)
    assert result is None


def test_process_runtime_env_local_working_dir(tmp_path):
    """
    Test process_runtime_env with local working directory.
    """
    from codeflare_sdk.ray.rayjobs.runtime_env import process_runtime_env, UNZIP_PATH

    # Create test working directory
    working_dir = tmp_path / "working_dir"
    working_dir.mkdir()
    (working_dir / "script.py").write_text("print('test')")

    runtime_env = RuntimeEnv(
        working_dir=str(working_dir),
        env_vars={"TEST_VAR": "test_value"},
    )

    rayjob = RayJob(
        job_name="test-job",
        entrypoint="python script.py",
        runtime_env=runtime_env,
        namespace="test-namespace",
        cluster_name="test-cluster",
    )

    result = process_runtime_env(rayjob)

    assert result is not None
    assert f"working_dir: {UNZIP_PATH}" in result
    assert "env_vars:" in result
    assert "TEST_VAR: test_value" in result


def test_process_runtime_env_single_file_case(tmp_path):
    """
    Test process_runtime_env with single file case (no working_dir in runtime_env).
    """
    from codeflare_sdk.ray.rayjobs.runtime_env import process_runtime_env
    from codeflare_sdk.common.utils.constants import MOUNT_PATH

    rayjob = RayJob(
        job_name="test-job",
        entrypoint="python test.py",
        namespace="test-namespace",
        cluster_name="test-cluster",
    )

    # Files dict without working_dir.zip (single file case)
    files = {"test.py": "print('test')"}

    result = process_runtime_env(rayjob, files)

    assert result is not None
    assert f"working_dir: {MOUNT_PATH}" in result


def test_process_runtime_env_no_processing_needed():
    """
    Test process_runtime_env returns None when no processing needed.
    """
    from codeflare_sdk.ray.rayjobs.runtime_env import process_runtime_env

    rayjob = RayJob(
        job_name="test-job",
        entrypoint="python test.py",
        namespace="test-namespace",
        cluster_name="test-cluster",
    )

    # No runtime_env and no files
    result = process_runtime_env(rayjob)
    assert result is None


def test_normalize_runtime_env_with_none():
    """
    Test _normalize_runtime_env with None input.
    """
    from codeflare_sdk.ray.rayjobs.runtime_env import _normalize_runtime_env

    result = _normalize_runtime_env(None)
    assert result is None


def test_extract_single_entrypoint_file_no_entrypoint():
    """
    Test _extract_single_entrypoint_file with no entrypoint.
    """
    from codeflare_sdk.ray.rayjobs.runtime_env import _extract_single_entrypoint_file

    rayjob = RayJob(
        job_name="test-job",
        entrypoint=None,  # No entrypoint
        namespace="test-namespace",
        cluster_name="test-cluster",
    )

    result = _extract_single_entrypoint_file(rayjob)
    assert result is None


def test_create_file_configmap_filters_metadata_keys(auto_mock_setup, tmp_path):
    """
    Test create_file_configmap filters out metadata keys from files dict.
    """
    from codeflare_sdk.ray.rayjobs.runtime_env import create_file_configmap

    rayjob = RayJob(
        job_name="test-job",
        cluster_name="existing-cluster",
        entrypoint="python test.py",
        namespace="test-namespace",
    )

    # Files dict with metadata key that should be filtered out
    files = {
        "__entrypoint_path__": "some/path/test.py",  # Should be filtered
        "test.py": "print('test')",  # Should remain
    }

    rayjob_result = {
        "metadata": {
            "name": "test-job",
            "namespace": "test-namespace",
            "uid": "test-uid-12345",
        }
    }

    # This should not raise an error and should filter out metadata keys
    create_file_configmap(rayjob, files, rayjob_result)

    # Verify the ConfigMap was created (mocked)
    mock_api_instance = auto_mock_setup["k8s_api"]
    mock_api_instance.create_namespaced_config_map.assert_called_once()

    # The call should have filtered data (only test.py, not __entrypoint_path__)
    call_args = mock_api_instance.create_namespaced_config_map.call_args
    configmap_data = call_args[1]["body"].data
    assert "test.py" in configmap_data
    assert "__entrypoint_path__" not in configmap_data

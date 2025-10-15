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
import io
from unittest.mock import MagicMock, patch
from codeflare_sdk.common.utils.constants import MOUNT_PATH, RAY_VERSION
from ray.runtime_env import RuntimeEnv

from codeflare_sdk.ray.rayjobs.rayjob import RayJob
from codeflare_sdk.ray.cluster.config import ClusterConfiguration
from codeflare_sdk.ray.rayjobs.config import ManagedClusterConfig
from kubernetes.client import (
    V1Volume,
    V1VolumeMount,
    ApiException,
)

from codeflare_sdk.ray.rayjobs.runtime_env import (
    create_secret_from_spec,
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


def test_build_file_secret_spec():
    """
    Test building Secret specification for files.
    """
    config = ManagedClusterConfig()
    files = {"main.py": "print('main')", "helper.py": "print('helper')"}

    spec = config.build_file_secret_spec(
        job_name="test-job", namespace="test-namespace", files=files
    )

    assert spec["apiVersion"] == "v1"
    assert spec["kind"] == "Secret"
    assert spec["type"] == "Opaque"
    assert spec["metadata"]["name"] == "test-job-files"
    assert spec["metadata"]["namespace"] == "test-namespace"
    assert spec["data"] == files


def test_build_file_volume_specs():
    """
    Test building volume and mount specifications for files.
    """
    config = ManagedClusterConfig()

    volume_spec, mount_spec = config.build_file_volume_specs(
        secret_name="test-files", mount_path="/custom/path"
    )

    assert volume_spec["name"] == "ray-job-files"
    assert volume_spec["secret"]["secretName"] == "test-files"

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

    config.add_file_volumes(secret_name="test-files")

    assert len(config.volumes) == 1
    assert len(config.volume_mounts) == 1

    volume = config.volumes[0]
    mount = config.volume_mounts[0]

    assert volume.name == "ray-job-files"
    assert volume.secret.secret_name == "test-files"

    assert mount.name == "ray-job-files"
    assert mount.mount_path == MOUNT_PATH


def test_add_file_volumes_duplicate_prevention():
    """
    Test that adding file volumes twice doesn't create duplicates.
    """
    config = ManagedClusterConfig()

    # Add volumes twice
    config.add_file_volumes(secret_name="test-files")
    config.add_file_volumes(secret_name="test-files")

    assert len(config.volumes) == 1
    assert len(config.volume_mounts) == 1


def test_create_secret_from_spec(auto_mock_setup):
    """
    Test creating Secret via Kubernetes API.
    """
    mock_api_instance = auto_mock_setup["k8s_api"]

    rayjob = RayJob(
        job_name="test-job",
        cluster_name="existing-cluster",
        entrypoint="python test.py",
        namespace="test-namespace",
    )

    secret_spec = {
        "apiVersion": "v1",
        "kind": "Secret",
        "type": "Opaque",
        "metadata": {"name": "test-files", "namespace": "test-namespace"},
        "data": {"test.py": "print('test')"},
    }

    # Provide valid RayJob result with UID as KubeRay client would
    rayjob_result = {
        "metadata": {
            "name": "test-job",
            "namespace": "test-namespace",
            "uid": "test-uid-12345",
        }
    }

    result = create_secret_from_spec(rayjob, secret_spec, rayjob_result)

    assert result == "test-files"
    mock_api_instance.create_namespaced_secret.assert_called_once()


def test_create_secret_already_exists(auto_mock_setup):
    """
    Test creating Secret when it already exists (409 conflict).
    """
    mock_api_instance = auto_mock_setup["k8s_api"]

    mock_api_instance.create_namespaced_secret.side_effect = ApiException(status=409)

    rayjob = RayJob(
        job_name="test-job",
        cluster_name="existing-cluster",
        entrypoint="python test.py",
        namespace="test-namespace",
    )

    secret_spec = {
        "apiVersion": "v1",
        "kind": "Secret",
        "type": "Opaque",
        "metadata": {"name": "test-files", "namespace": "test-namespace"},
        "data": {"test.py": "print('test')"},
    }

    # Provide valid RayJob result with UID as KubeRay client would
    rayjob_result = {
        "metadata": {
            "name": "test-job",
            "namespace": "test-namespace",
            "uid": "test-uid-67890",
        }
    }

    result = create_secret_from_spec(rayjob, secret_spec, rayjob_result)

    assert result == "test-files"
    mock_api_instance.create_namespaced_secret.assert_called_once()
    mock_api_instance.replace_namespaced_secret.assert_called_once()


def test_create_secret_with_owner_reference_basic(mocker, auto_mock_setup, caplog):
    """
    Test creating Secret with owner reference from valid RayJob result.
    """
    mock_api_instance = auto_mock_setup["k8s_api"]

    # Mock client.V1ObjectMeta and V1Secret
    mock_v1_metadata = mocker.patch("kubernetes.client.V1ObjectMeta")
    mock_metadata_instance = MagicMock()
    mock_v1_metadata.return_value = mock_metadata_instance

    rayjob = RayJob(
        job_name="test-job",
        cluster_name="existing-cluster",
        entrypoint="python test.py",
        namespace="test-namespace",
    )

    secret_spec = {
        "apiVersion": "v1",
        "kind": "Secret",
        "type": "Opaque",
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
        result = create_secret_from_spec(rayjob, secret_spec, rayjob_result)

    assert result == "test-files"

    # Verify owner reference was set
    expected_owner_ref = mocker.ANY  # We'll check via the logs
    assert (
        "Adding owner reference to Secret 'test-files' with RayJob UID: a4dd4c5a-ab61-411d-b4d1-4abb5177422a"
        in caplog.text
    )

    assert mock_metadata_instance.owner_references is not None
    mock_api_instance.create_namespaced_secret.assert_called_once()


def test_file_handling_kubernetes_best_practice_flow(mocker, tmp_path):
    """
    Test the Kubernetes best practice flow: pre-declare volume, submit, create Secret.
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

    # Mock create_file_secret where it's used (imported into rayjob module)
    mock_create_secret = mocker.patch(
        "codeflare_sdk.ray.rayjobs.rayjob.create_file_secret"
    )
    mock_add_volumes = mocker.patch.object(ManagedClusterConfig, "add_file_volumes")

    # RayClusterApi is already mocked by auto_mock_setup

    test_file = tmp_path / "test.py"
    test_file.write_text("print('test')")

    call_order = []

    def track_add_volumes(*args, **kwargs):
        call_order.append("add_volumes")
        # Should be called with Secret name
        assert args[0] == "test-job-files"

    def track_submit(*args, **kwargs):
        call_order.append("submit_job")
        return submit_result

    def track_create_secret(*args, **kwargs):
        call_order.append("create_secret")
        # Args should be: (job, files, rayjob_result)
        assert len(args) >= 3, f"Expected 3 args, got {len(args)}: {args}"
        assert args[2] == submit_result  # rayjob_result should be third arg

    mock_add_volumes.side_effect = track_add_volumes
    mock_api_instance.submit_job.side_effect = track_submit
    mock_create_secret.side_effect = track_create_secret

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

    # Verify the order: submit → create Secret
    assert call_order == ["submit_job", "create_secret"]

    mock_api_instance.submit_job.assert_called_once()
    mock_create_secret.assert_called_once()

    # Verify create_file_secret was called with: (job, files, rayjob_result)
    # Files dict includes metadata key __entrypoint_path__ for single file case
    call_args = mock_create_secret.call_args[0]
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
    mock_api_instance.submit_job.return_value = {
        "metadata": {
            "name": "test-job",
            "namespace": "test-namespace",
            "uid": "test-uid-files-12345",
        }
    }

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

        mock_k8s_instance.create_namespaced_secret.assert_called_once()

        assert len(cluster_config.volumes) == 0
        assert len(cluster_config.volume_mounts) == 0
        # Entrypoint should be adjusted to use just the filename
        assert rayjob.entrypoint == "python test.py"

    finally:
        os.chdir(original_cwd)


def test_create_secret_api_error_non_409(auto_mock_setup):
    """
    Test create_secret_from_spec handles non-409 API errors.
    """
    mock_api_instance = auto_mock_setup["k8s_api"]

    # Configure to raise 500 error
    mock_api_instance.create_namespaced_secret.side_effect = ApiException(status=500)

    rayjob = RayJob(
        job_name="test-job",
        cluster_name="existing-cluster",
        entrypoint="python test.py",
        namespace="test-namespace",
    )

    secret_spec = {
        "apiVersion": "v1",
        "kind": "Secret",
        "type": "Opaque",
        "metadata": {"name": "test-files", "namespace": "test-namespace"},
        "data": {"test.py": "print('test')"},
    }

    # Provide valid RayJob result with UID as KubeRay client would
    rayjob_result = {
        "metadata": {
            "name": "test-job",
            "namespace": "test-namespace",
            "uid": "test-uid-api-error",
        }
    }

    with pytest.raises(RuntimeError, match="Failed to create Secret"):
        create_secret_from_spec(rayjob, secret_spec, rayjob_result)


def test_add_file_volumes_existing_volume_skip():
    """
    Test add_file_volumes skips when volume already exists (missing coverage).
    """
    from kubernetes.client import V1SecretVolumeSource

    config = ManagedClusterConfig()

    # Pre-add a volume with same name
    existing_volume = V1Volume(
        name="ray-job-files",
        secret=V1SecretVolumeSource(secret_name="existing-files"),
    )
    config.volumes.append(existing_volume)

    config.add_file_volumes(secret_name="new-files")
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

    config.add_file_volumes(secret_name="new-files")
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


def test_zip_directory_excludes_jupyter_notebooks(tmp_path, caplog):
    """
    Test that Jupyter notebook files (.ipynb) and markdown files (.md) are excluded from zip.
    """
    from codeflare_sdk.ray.rayjobs.runtime_env import _zip_directory
    import zipfile

    # Create test directory with mixed file types
    test_dir = tmp_path / "working_dir"
    test_dir.mkdir()

    # Create Python files (should be included)
    (test_dir / "main.py").write_text("print('main script')")
    (test_dir / "utils.py").write_text("def helper(): pass")

    # Create Jupyter notebook files (should be excluded)
    (test_dir / "analysis.ipynb").write_text('{"cells": [], "metadata": {}}')
    (test_dir / "experiment.IPYNB").write_text(
        '{"cells": [], "metadata": {}}'
    )  # Test case insensitive

    # Create markdown files (should be excluded)
    (test_dir / "README.md").write_text("# Project Documentation\n")
    (test_dir / "CHANGELOG.MD").write_text("# Changes\n")  # Test case insensitive

    # Create subdirectory with mixed files
    sub_dir = test_dir / "notebooks"
    sub_dir.mkdir()
    (sub_dir / "data_exploration.ipynb").write_text('{"cells": [], "metadata": {}}')
    (sub_dir / "helper.py").write_text("print('nested file')")
    (sub_dir / "guide.md").write_text("# Guide\n")

    # Test zipping
    with caplog.at_level("INFO"):
        zip_data = _zip_directory(str(test_dir))

    assert zip_data is not None
    assert len(zip_data) > 0

    # Verify log message includes exclusion count (3 ipynb + 3 md = 6 total)
    assert "Excluded 6 file(s) (.ipynb, .md)" in caplog.text

    # Verify excluded files are not in the zip
    zip_buffer = io.BytesIO(zip_data)
    with zipfile.ZipFile(zip_buffer, "r") as zipf:
        zip_contents = zipf.namelist()

        # Python files should be present
        assert "main.py" in zip_contents
        assert "utils.py" in zip_contents
        assert "notebooks/helper.py" in zip_contents

        # Jupyter notebooks should be excluded
        assert "analysis.ipynb" not in zip_contents
        assert "experiment.IPYNB" not in zip_contents
        assert "notebooks/data_exploration.ipynb" not in zip_contents

        # Markdown files should be excluded
        assert "README.md" not in zip_contents
        assert "CHANGELOG.MD" not in zip_contents
        assert "notebooks/guide.md" not in zip_contents


def test_zip_directory_no_exclusions_when_no_notebooks(tmp_path, caplog):
    """
    Test that no exclusion message is logged when no notebook or markdown files exist.
    """
    from codeflare_sdk.ray.rayjobs.runtime_env import _zip_directory

    # Create test directory with only Python files
    test_dir = tmp_path / "working_dir"
    test_dir.mkdir()
    (test_dir / "main.py").write_text("print('main script')")
    (test_dir / "utils.py").write_text("def helper(): pass")

    # Test zipping
    with caplog.at_level("INFO"):
        zip_data = _zip_directory(str(test_dir))

    assert zip_data is not None

    # Verify log message does NOT mention exclusions
    assert "Excluded" not in caplog.text


def test_should_exclude_file_function():
    """
    Test the _should_exclude_file helper function directly.
    """
    from codeflare_sdk.ray.rayjobs.runtime_env import _should_exclude_file

    # Should exclude .ipynb files (case insensitive)
    assert _should_exclude_file("notebook.ipynb") is True
    assert _should_exclude_file("analysis.IPYNB") is True
    assert _should_exclude_file("data/exploration.ipynb") is True
    assert _should_exclude_file("subdir/nested.Ipynb") is True

    # Should exclude .md files (case insensitive)
    assert _should_exclude_file("README.md") is True
    assert _should_exclude_file("CHANGELOG.MD") is True
    assert _should_exclude_file("docs/guide.md") is True
    assert _should_exclude_file("subdir/notes.Md") is True

    # Should NOT exclude other files
    assert _should_exclude_file("script.py") is False
    assert _should_exclude_file("data.json") is False
    assert _should_exclude_file("requirements.txt") is False
    assert _should_exclude_file("model.pkl") is False
    assert _should_exclude_file("markdown_parser.py") is False  # Not .md
    assert _should_exclude_file("test.html") is False


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


def test_extract_all_local_files_excludes_notebooks(tmp_path, caplog):
    """
    Test that extract_all_local_files excludes Jupyter notebooks and markdown files when zipping working directory.
    """
    import zipfile
    import base64

    # Create test working directory with mixed files
    working_dir = tmp_path / "working_dir"
    working_dir.mkdir()

    # Python files that should be included
    (working_dir / "main.py").write_text("print('main script')")
    (working_dir / "helper.py").write_text("def helper_function(): pass")

    # Jupyter notebooks that should be excluded
    (working_dir / "analysis.ipynb").write_text(
        '{"cells": [{"cell_type": "code", "source": ["print(\'hello\')"]}]}'
    )
    (working_dir / "data.ipynb").write_text('{"cells": [], "metadata": {}}')

    # Markdown files that should be excluded
    (working_dir / "README.md").write_text("# Project Documentation\n")
    (working_dir / "CHANGELOG.md").write_text("# Changes\n")

    runtime_env = RuntimeEnv(working_dir=str(working_dir))

    rayjob = RayJob(
        job_name="test-job",
        entrypoint="python main.py",
        runtime_env=runtime_env,
        namespace="test-namespace",
        cluster_name="test-cluster",
    )

    # This should zip the directory and exclude notebooks and markdown files
    with caplog.at_level("INFO"):
        files = extract_all_local_files(rayjob)

    assert files is not None
    assert "working_dir.zip" in files

    # Verify exclusion was logged (2 ipynb + 2 md = 4 total)
    assert "Excluded 4 file(s) (.ipynb, .md)" in caplog.text

    # Decode and verify zip contents
    zip_data = base64.b64decode(files["working_dir.zip"])
    zip_buffer = io.BytesIO(zip_data)

    with zipfile.ZipFile(zip_buffer, "r") as zipf:
        zip_contents = zipf.namelist()

        # Python files should be present
        assert "main.py" in zip_contents
        assert "helper.py" in zip_contents

        # Jupyter notebooks should be excluded
        assert "analysis.ipynb" not in zip_contents
        assert "data.ipynb" not in zip_contents

        # Markdown files should be excluded
        assert "README.md" not in zip_contents
        assert "CHANGELOG.md" not in zip_contents


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


def test_create_file_secret_filters_metadata_keys(auto_mock_setup, tmp_path):
    """
    Test create_file_secret filters out metadata keys from files dict.
    """
    from codeflare_sdk.ray.rayjobs.runtime_env import create_file_secret

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
    create_file_secret(rayjob, files, rayjob_result)

    # Verify the Secret was created (mocked)
    mock_api_instance = auto_mock_setup["k8s_api"]
    mock_api_instance.create_namespaced_secret.assert_called_once()

    # The call should have filtered data (only test.py, not __entrypoint_path__)
    call_args = mock_api_instance.create_namespaced_secret.call_args
    secret_data = call_args[1]["body"].string_data  # Changed from data to string_data
    assert "test.py" in secret_data
    assert "__entrypoint_path__" not in secret_data

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
from unittest.mock import MagicMock, patch
from codeflare_sdk.ray.rayjobs.rayjob import RayJob
from codeflare_sdk.ray.cluster.config import ClusterConfiguration


def test_rayjob_submit_success(mocker):
    """Test successful RayJob submission."""
    # Mock kubernetes config loading
    mocker.patch("kubernetes.config.load_kube_config")

    # Mock the RayjobApi class entirely
    mock_api_class = mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")
    mock_api_instance = MagicMock()
    mock_api_class.return_value = mock_api_instance

    # Configure the mock to return success when submit is called
    mock_api_instance.submit.return_value = {"metadata": {"name": "test-rayjob"}}

    # Create RayJob instance
    rayjob = RayJob(
        job_name="test-rayjob",
        cluster_name="test-ray-cluster",
        namespace="test-namespace",
        entrypoint="python -c 'print(\"hello world\")'",
        runtime_env={"pip": ["requests"]},
    )

    # Submit the job
    job_id = rayjob.submit()

    # Assertions
    assert job_id == "test-rayjob"

    # Verify the API was called with correct parameters
    mock_api_instance.submit_job.assert_called_once()
    call_args = mock_api_instance.submit_job.call_args

    # Check the namespace parameter
    assert call_args.kwargs["k8s_namespace"] == "test-namespace"

    # Check the job custom resource
    job_cr = call_args.kwargs["job"]
    assert job_cr["metadata"]["name"] == "test-rayjob"
    assert job_cr["metadata"]["namespace"] == "test-namespace"
    assert job_cr["spec"]["entrypoint"] == "python -c 'print(\"hello world\")'"
    assert job_cr["spec"]["clusterSelector"]["ray.io/cluster"] == "test-ray-cluster"
    assert job_cr["spec"]["runtimeEnvYAML"] == "{'pip': ['requests']}"


def test_rayjob_submit_failure(mocker):
    """Test RayJob submission failure."""
    # Mock kubernetes config loading
    mocker.patch("kubernetes.config.load_kube_config")

    # Mock the RayjobApi class entirely
    mock_api_class = mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")
    mock_api_instance = MagicMock()
    mock_api_class.return_value = mock_api_instance

    # Configure the mock to return failure (False/None) when submit_job is called
    mock_api_instance.submit_job.return_value = None

    # Create a RayJob instance
    rayjob = RayJob(
        job_name="test-rayjob",
        cluster_name="test-ray-cluster",
        namespace="default",
        entrypoint="python script.py",
        runtime_env={"pip": ["numpy"]},
    )

    # Test that RuntimeError is raised on failure
    with pytest.raises(RuntimeError, match="Failed to submit RayJob test-rayjob"):
        rayjob.submit()


def test_rayjob_init_validation_both_provided(mocker):
    """Test that providing both cluster_name and cluster_config raises error."""
    # Mock kubernetes config loading
    mocker.patch("kubernetes.config.load_kube_config")

    # Mock the RayjobApi class entirely
    mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")

    cluster_config = ClusterConfiguration(name="test-cluster", namespace="test")

    with pytest.raises(
        ValueError, match="Cannot specify both cluster_name and cluster_config"
    ):
        RayJob(
            job_name="test-job",
            cluster_name="existing-cluster",
            cluster_config=cluster_config,
            entrypoint="python script.py",
        )


def test_rayjob_init_validation_neither_provided(mocker):
    """Test that providing neither cluster_name nor cluster_config raises error."""
    # Mock kubernetes config loading (though this should fail before reaching it)
    mocker.patch("kubernetes.config.load_kube_config")

    # Mock the RayjobApi class entirely (though this should fail before reaching it)
    mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")

    with pytest.raises(
        ValueError, match="Either cluster_name or cluster_config must be provided"
    ):
        RayJob(job_name="test-job", entrypoint="python script.py")


def test_rayjob_init_with_cluster_config(mocker):
    """Test RayJob initialization with cluster configuration for auto-creation."""
    # Mock kubernetes config loading
    mocker.patch("kubernetes.config.load_kube_config")

    # Mock the RayjobApi class entirely
    mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")

    cluster_config = ClusterConfiguration(
        name="auto-cluster", namespace="test-namespace", num_workers=2
    )

    rayjob = RayJob(
        job_name="test-job",
        cluster_config=cluster_config,
        entrypoint="python script.py",
    )

    assert rayjob.name == "test-job"
    assert rayjob.cluster_name == "auto-cluster"
    assert rayjob._cluster_config == cluster_config
    assert rayjob._cluster_name is None


def test_rayjob_cluster_name_generation(mocker):
    """Test that cluster names are generated when config has empty name."""
    # Mock kubernetes config loading
    mocker.patch("kubernetes.config.load_kube_config")

    # Mock the RayjobApi class entirely
    mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")

    cluster_config = ClusterConfiguration(
        name="",  # Empty name should trigger generation
        namespace="test-namespace",
        num_workers=1,
    )

    rayjob = RayJob(
        job_name="my-job", cluster_config=cluster_config, entrypoint="python script.py"
    )

    assert rayjob.cluster_name == "my-job-cluster"
    assert cluster_config.name == "my-job-cluster"  # Should be updated


def test_rayjob_cluster_config_namespace_none(mocker):
    """Test that cluster config namespace is set when None."""
    # Mock kubernetes config loading
    mocker.patch("kubernetes.config.load_kube_config")

    # Mock the RayjobApi class entirely
    mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")

    cluster_config = ClusterConfiguration(
        name="test-cluster",
        namespace=None,  # This should be set to job namespace
        num_workers=1,
    )

    rayjob = RayJob(
        job_name="test-job",
        cluster_config=cluster_config,
        namespace="job-namespace",
        entrypoint="python script.py",
    )

    assert cluster_config.namespace == "job-namespace"
    assert rayjob.namespace == "job-namespace"


def test_rayjob_with_active_deadline_seconds(mocker):
    """Test RayJob CR generation with active deadline seconds."""
    # Mock kubernetes config loading
    mocker.patch("kubernetes.config.load_kube_config")

    # Mock the RayjobApi class entirely
    mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")

    rayjob = RayJob(
        job_name="test-job",
        cluster_name="test-cluster",
        namespace="test-namespace",
        entrypoint="python main.py",
        active_deadline_seconds=30,
    )

    rayjob_cr = rayjob._build_rayjob_cr()

    assert rayjob_cr["spec"]["activeDeadlineSeconds"] == 30


def test_build_ray_cluster_spec_no_config_error(mocker):
    """Test _build_ray_cluster_spec raises error when no cluster config."""
    # Mock kubernetes config loading
    mocker.patch("kubernetes.config.load_kube_config")

    # Mock the RayjobApi class entirely
    mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")

    # Create RayJob with cluster_name (no cluster_config)
    rayjob = RayJob(
        job_name="test-job",
        cluster_name="existing-cluster",
        entrypoint="python script.py",
    )

    # Line 198: Should raise RuntimeError when trying to build spec without config
    with pytest.raises(RuntimeError, match="No cluster configuration provided"):
        rayjob._build_ray_cluster_spec()


@patch("codeflare_sdk.ray.rayjobs.rayjob.build_ray_cluster")
def test_build_ray_cluster_spec(mock_build_ray_cluster, mocker):
    """Test _build_ray_cluster_spec method."""
    mocker.patch("kubernetes.config.load_kube_config")

    # Mock the RayjobApi class entirely
    mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")

    mock_ray_cluster = {
        "apiVersion": "ray.io/v1",
        "kind": "RayCluster",
        "metadata": {"name": "test-cluster", "namespace": "test"},
        "spec": {
            "rayVersion": "2.9.0",
            "headGroupSpec": {"replicas": 1},
            "workerGroupSpecs": [{"replicas": 2}],
        },
    }
    mock_build_ray_cluster.return_value = mock_ray_cluster

    cluster_config = ClusterConfiguration(
        name="test-cluster", namespace="test", num_workers=2
    )

    rayjob = RayJob(
        job_name="test-job",
        cluster_config=cluster_config,
        entrypoint="python script.py",
    )

    spec = rayjob._build_ray_cluster_spec()

    # Should return only the spec part, not metadata
    assert spec == mock_ray_cluster["spec"]
    assert "metadata" not in spec

    # Verify build_ray_cluster was called with correct parameters
    mock_build_ray_cluster.assert_called_once()
    call_args = mock_build_ray_cluster.call_args[0][0]
    assert call_args.config.appwrapper is False
    assert call_args.config.write_to_file is False


def test_build_rayjob_cr_with_existing_cluster(mocker):
    """Test _build_rayjob_cr method with existing cluster."""
    mocker.patch("kubernetes.config.load_kube_config")

    # Mock the RayjobApi class entirely
    mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")

    rayjob = RayJob(
        job_name="test-job",
        cluster_name="existing-cluster",
        namespace="test-namespace",
        entrypoint="python main.py",
        shutdown_after_job_finishes=False,
        ttl_seconds_after_finished=300,
    )

    rayjob_cr = rayjob._build_rayjob_cr()

    # Check basic structure
    assert rayjob_cr["apiVersion"] == "ray.io/v1"
    assert rayjob_cr["kind"] == "RayJob"
    assert rayjob_cr["metadata"]["name"] == "test-job"

    # Check lifecycle parameters
    spec = rayjob_cr["spec"]
    assert spec["entrypoint"] == "python main.py"
    assert spec["shutdownAfterJobFinishes"] is False
    assert spec["ttlSecondsAfterFinished"] == 300

    # Should use clusterSelector for existing cluster
    assert spec["clusterSelector"]["ray.io/cluster"] == "existing-cluster"
    assert "rayClusterSpec" not in spec


@patch("codeflare_sdk.ray.rayjobs.rayjob.build_ray_cluster")
def test_build_rayjob_cr_with_auto_cluster(mock_build_ray_cluster, mocker):
    """Test _build_rayjob_cr method with auto-created cluster."""
    mocker.patch("kubernetes.config.load_kube_config")

    # Mock the RayjobApi class entirely
    mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")

    mock_ray_cluster = {
        "apiVersion": "ray.io/v1",
        "kind": "RayCluster",
        "metadata": {"name": "auto-cluster", "namespace": "test"},
        "spec": {
            "rayVersion": "2.9.0",
            "headGroupSpec": {"replicas": 1},
            "workerGroupSpecs": [{"replicas": 2}],
        },
    }
    mock_build_ray_cluster.return_value = mock_ray_cluster

    cluster_config = ClusterConfiguration(
        name="auto-cluster", namespace="test-namespace", num_workers=2
    )

    rayjob = RayJob(
        job_name="test-job", cluster_config=cluster_config, entrypoint="python main.py"
    )

    rayjob_cr = rayjob._build_rayjob_cr()

    # Should use rayClusterSpec for auto-created cluster
    assert rayjob_cr["spec"]["rayClusterSpec"] == mock_ray_cluster["spec"]
    assert "clusterSelector" not in rayjob_cr["spec"]


def test_submit_validation_no_entrypoint(mocker):
    """Test that submit() raises error when entrypoint is None."""
    mocker.patch("kubernetes.config.load_kube_config")
    mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")

    rayjob = RayJob(
        job_name="test-job",
        cluster_name="test-cluster",
        entrypoint=None,  # No entrypoint provided
    )

    with pytest.raises(
        ValueError, match="entrypoint must be provided to submit a RayJob"
    ):
        rayjob.submit()


@patch("codeflare_sdk.ray.rayjobs.rayjob.build_ray_cluster")
def test_submit_with_auto_cluster(mock_build_ray_cluster, mocker):
    """Test successful submission with auto-created cluster."""
    mocker.patch("kubernetes.config.load_kube_config")

    mock_ray_cluster = {
        "apiVersion": "ray.io/v1",
        "kind": "RayCluster",
        "spec": {
            "rayVersion": "2.9.0",
            "headGroupSpec": {"replicas": 1},
            "workerGroupSpecs": [{"replicas": 1}],
        },
    }
    mock_build_ray_cluster.return_value = mock_ray_cluster

    # Mock the RayjobApi
    mock_api_class = mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")
    mock_api_instance = MagicMock()
    mock_api_class.return_value = mock_api_instance
    mock_api_instance.submit_job.return_value = True

    cluster_config = ClusterConfiguration(
        name="auto-cluster", namespace="test", num_workers=1
    )

    rayjob = RayJob(
        job_name="test-job",
        cluster_config=cluster_config,
        entrypoint="python script.py",
    )

    result = rayjob.submit()

    assert result == "test-job"

    # Verify the correct RayJob CR was submitted
    mock_api_instance.submit_job.assert_called_once()
    call_args = mock_api_instance.submit_job.call_args

    job_cr = call_args.kwargs["job"]
    assert "rayClusterSpec" in job_cr["spec"]
    assert job_cr["spec"]["rayClusterSpec"] == mock_ray_cluster["spec"]

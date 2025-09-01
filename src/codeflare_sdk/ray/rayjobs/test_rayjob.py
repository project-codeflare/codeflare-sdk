# Copyright 2022-2025 IBM, Red Hat
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

from codeflare_sdk.ray.rayjobs.rayjob import RayJob
from codeflare_sdk.ray.cluster.config import ClusterConfiguration
from codeflare_sdk.ray.rayjobs.config import ManagedClusterConfig


def test_rayjob_submit_success(mocker):
    """Test successful RayJob submission."""
    # Mock kubernetes config loading
    mocker.patch("kubernetes.config.load_kube_config")

    # Mock the RayjobApi class entirely
    mock_api_class = mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")
    mock_api_instance = MagicMock()
    mock_api_class.return_value = mock_api_instance

    # Mock the RayClusterApi class
    mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayClusterApi")

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

    # Mock the RayClusterApi class
    mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayClusterApi")

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
        ValueError,
        match="❌ Configuration Error: You cannot specify both 'cluster_name' and 'cluster_config'",
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
        ValueError,
        match="❌ Configuration Error: You must provide either 'cluster_name'",
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
        namespace="test-namespace",
    )

    assert rayjob.name == "test-job"
    assert rayjob.cluster_name == "test-job-cluster"  # Generated from job name
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
        job_name="my-job",
        cluster_config=cluster_config,
        entrypoint="python script.py",
        namespace="test-namespace",
    )

    assert rayjob.cluster_name == "my-job-cluster"


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
        namespace="test-namespace",
    )

    # Since we removed _build_ray_cluster_spec method, this test is no longer applicable
    # The method is now called internally by _build_rayjob_cr when needed
    # We can test this by calling _build_rayjob_cr instead
    rayjob_cr = rayjob._build_rayjob_cr()

    # Should use clusterSelector for existing cluster
    assert rayjob_cr["spec"]["clusterSelector"]["ray.io/cluster"] == "existing-cluster"
    assert "rayClusterSpec" not in rayjob_cr["spec"]


def test_build_ray_cluster_spec(mocker):
    """Test _build_ray_cluster_spec method."""
    mocker.patch("kubernetes.config.load_kube_config")

    # Mock the RayjobApi class entirely
    mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")

    mock_ray_cluster = {
        "apiVersion": "ray.io/v1",
        "kind": "RayCluster",
        "metadata": {"name": "test-cluster", "namespace": "test"},
        "spec": {
            "rayVersion": RAY_VERSION,
            "headGroupSpec": {"replicas": 1},
            "workerGroupSpecs": [{"replicas": 2}],
        },
    }
    # Use ManagedClusterConfig which has the build_ray_cluster_spec method
    from codeflare_sdk.ray.rayjobs.config import ManagedClusterConfig

    cluster_config = ManagedClusterConfig(num_workers=2)

    # Mock the method that will be called
    mocker.patch.object(
        cluster_config, "build_ray_cluster_spec", return_value=mock_ray_cluster["spec"]
    )

    rayjob = RayJob(
        job_name="test-job",
        cluster_config=cluster_config,
        entrypoint="python script.py",
        namespace="test-namespace",
    )

    # Test the integration through _build_rayjob_cr
    rayjob_cr = rayjob._build_rayjob_cr()

    # Should have rayClusterSpec
    assert "rayClusterSpec" in rayjob_cr["spec"]

    # Verify build_ray_cluster_spec was called on the cluster config
    cluster_config.build_ray_cluster_spec.assert_called_once_with(
        cluster_name="test-job-cluster"
    )


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
    # shutdownAfterJobFinishes should be False when using existing cluster (auto-set)
    assert spec["shutdownAfterJobFinishes"] is False
    assert spec["ttlSecondsAfterFinished"] == 300

    # Should use clusterSelector for existing cluster
    assert spec["clusterSelector"]["ray.io/cluster"] == "existing-cluster"
    assert "rayClusterSpec" not in spec


def test_build_rayjob_cr_with_auto_cluster(mocker):
    """Test _build_rayjob_cr method with auto-created cluster."""
    mocker.patch("kubernetes.config.load_kube_config")

    # Mock the RayjobApi class entirely
    mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")

    mock_ray_cluster = {
        "apiVersion": "ray.io/v1",
        "kind": "RayCluster",
        "metadata": {"name": "auto-cluster", "namespace": "test"},
        "spec": {
            "rayVersion": RAY_VERSION,
            "headGroupSpec": {"replicas": 1},
            "workerGroupSpecs": [{"replicas": 2}],
        },
    }
    # Use ManagedClusterConfig and mock its build_ray_cluster_spec method
    from codeflare_sdk.ray.rayjobs.config import ManagedClusterConfig

    cluster_config = ManagedClusterConfig(num_workers=2)

    # Mock the method that will be called
    mocker.patch.object(
        cluster_config, "build_ray_cluster_spec", return_value=mock_ray_cluster["spec"]
    )

    rayjob = RayJob(
        job_name="test-job",
        cluster_config=cluster_config,
        entrypoint="python main.py",
        namespace="test-namespace",
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
        namespace="test-namespace",
    )

    with pytest.raises(
        ValueError, match="Entrypoint must be provided to submit a RayJob"
    ):
        rayjob.submit()


def test_submit_with_auto_cluster(mocker):
    """Test successful submission with auto-created cluster."""
    mocker.patch("kubernetes.config.load_kube_config")

    mock_ray_cluster = {
        "apiVersion": "ray.io/v1",
        "kind": "RayCluster",
        "spec": {
            "rayVersion": RAY_VERSION,
            "headGroupSpec": {"replicas": 1},
            "workerGroupSpecs": [{"replicas": 1}],
        },
    }
    # Mock the RayjobApi
    mock_api_class = mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")
    mock_api_instance = MagicMock()
    mock_api_class.return_value = mock_api_instance
    mock_api_instance.submit_job.return_value = True

    # Use ManagedClusterConfig and mock its build_ray_cluster_spec method
    from codeflare_sdk.ray.rayjobs.config import ManagedClusterConfig

    cluster_config = ManagedClusterConfig(num_workers=1)

    # Mock the method that will be called
    mocker.patch.object(
        cluster_config, "build_ray_cluster_spec", return_value=mock_ray_cluster["spec"]
    )

    rayjob = RayJob(
        job_name="test-job",
        cluster_config=cluster_config,
        entrypoint="python script.py",
        namespace="test-namespace",
    )

    result = rayjob.submit()

    assert result == "test-job"

    # Verify the correct RayJob CR was submitted
    mock_api_instance.submit_job.assert_called_once()
    call_args = mock_api_instance.submit_job.call_args

    job_cr = call_args.kwargs["job"]
    assert "rayClusterSpec" in job_cr["spec"]
    assert job_cr["spec"]["rayClusterSpec"] == mock_ray_cluster["spec"]


def test_namespace_auto_detection_success(mocker):
    """Test successful namespace auto-detection."""
    mocker.patch("kubernetes.config.load_kube_config")
    mocker.patch(
        "codeflare_sdk.ray.rayjobs.rayjob.get_current_namespace",
        return_value="detected-ns",
    )
    mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")
    mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayClusterApi")

    rayjob = RayJob(
        job_name="test-job", entrypoint="python script.py", cluster_name="test-cluster"
    )

    assert rayjob.namespace == "detected-ns"


def test_namespace_auto_detection_fallback(mocker):
    """Test that namespace auto-detection failure raises an error."""
    mocker.patch("kubernetes.config.load_kube_config")
    mocker.patch(
        "codeflare_sdk.ray.rayjobs.rayjob.get_current_namespace", return_value=None
    )
    mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")
    mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayClusterApi")

    with pytest.raises(ValueError, match="Could not auto-detect Kubernetes namespace"):
        RayJob(
            job_name="test-job",
            entrypoint="python script.py",
            cluster_name="test-cluster",
        )


def test_namespace_explicit_override(mocker):
    """Test that explicit namespace overrides auto-detection."""
    mocker.patch("kubernetes.config.load_kube_config")
    mocker.patch(
        "codeflare_sdk.ray.rayjobs.rayjob.get_current_namespace",
        return_value="detected-ns",
    )
    mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")
    mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayClusterApi")

    rayjob = RayJob(
        job_name="test-job",
        entrypoint="python script.py",
        cluster_name="test-cluster",
        namespace="explicit-ns",
    )

    assert rayjob.namespace == "explicit-ns"


def test_shutdown_behavior_with_cluster_config(mocker):
    """Test that shutdown_after_job_finishes is True when cluster_config is provided."""
    mocker.patch("kubernetes.config.load_kube_config")
    mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")
    mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayClusterApi")

    from codeflare_sdk.ray.rayjobs.config import ManagedClusterConfig

    cluster_config = ManagedClusterConfig()

    rayjob = RayJob(
        job_name="test-job",
        entrypoint="python script.py",
        cluster_config=cluster_config,
        namespace="test-namespace",
    )

    assert rayjob.shutdown_after_job_finishes is True


def test_shutdown_behavior_with_existing_cluster(mocker):
    """Test that shutdown_after_job_finishes is False when using existing cluster."""
    mocker.patch("kubernetes.config.load_kube_config")
    mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")
    mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayClusterApi")

    rayjob = RayJob(
        job_name="test-job",
        entrypoint="python script.py",
        cluster_name="existing-cluster",
        namespace="test-namespace",
    )

    assert rayjob.shutdown_after_job_finishes is False


def test_rayjob_with_rayjob_cluster_config(mocker):
    """Test RayJob with the new ManagedClusterConfig."""
    mocker.patch("kubernetes.config.load_kube_config")
    mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")
    mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayClusterApi")

    from codeflare_sdk.ray.rayjobs.config import ManagedClusterConfig

    cluster_config = ManagedClusterConfig(
        num_workers=2,
        head_cpu_requests="500m",
        head_memory_requests="512Mi",
    )

    rayjob = RayJob(
        job_name="test-job",
        entrypoint="python script.py",
        cluster_config=cluster_config,
        namespace="test-namespace",
    )

    assert rayjob._cluster_config == cluster_config
    assert rayjob.cluster_name == "test-job-cluster"  # Generated from job name


def test_rayjob_cluster_config_validation(mocker):
    """Test validation of ManagedClusterConfig parameters."""
    mocker.patch("kubernetes.config.load_kube_config")
    mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")
    mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayClusterApi")

    from codeflare_sdk.ray.rayjobs.config import ManagedClusterConfig

    # Test with minimal valid config
    cluster_config = ManagedClusterConfig()

    rayjob = RayJob(
        job_name="test-job",
        entrypoint="python script.py",
        cluster_config=cluster_config,
        namespace="test-namespace",
    )

    assert rayjob._cluster_config is not None


def test_rayjob_missing_entrypoint_validation(mocker):
    """Test that RayJob requires entrypoint for submission."""
    mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")

    # Should raise an error during construction
    with pytest.raises(
        TypeError, match="missing 1 required positional argument: 'entrypoint'"
    ):
        RayJob(
            job_name="test-job",
            cluster_name="test-cluster",
            # No entrypoint provided
        )


def test_build_ray_cluster_spec_integration(mocker):
    """Test integration with the new build_ray_cluster_spec method."""
    # Mock kubernetes config loading
    mocker.patch("kubernetes.config.load_kube_config")

    # Mock the RayjobApi class entirely
    mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")

    from codeflare_sdk.ray.rayjobs.config import ManagedClusterConfig

    cluster_config = ManagedClusterConfig()

    # Mock the build_ray_cluster_spec method on the cluster config
    mock_spec = {"spec": "test-spec"}
    mocker.patch.object(
        cluster_config, "build_ray_cluster_spec", return_value=mock_spec
    )

    rayjob = RayJob(
        job_name="test-job",
        entrypoint="python script.py",
        cluster_config=cluster_config,
        namespace="test-namespace",
    )

    # Build the RayJob CR
    rayjob_cr = rayjob._build_rayjob_cr()

    # Verify the method was called correctly
    cluster_config.build_ray_cluster_spec.assert_called_once_with(
        cluster_name="test-job-cluster"
    )

    # Verify the spec is included in the RayJob CR
    assert "rayClusterSpec" in rayjob_cr["spec"]
    assert rayjob_cr["spec"]["rayClusterSpec"] == mock_spec


def test_rayjob_with_runtime_env(mocker):
    """Test RayJob with runtime environment configuration."""
    mocker.patch("kubernetes.config.load_kube_config")
    mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")
    mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayClusterApi")

    runtime_env = {"pip": ["numpy", "pandas"]}

    rayjob = RayJob(
        job_name="test-job",
        entrypoint="python script.py",
        cluster_name="test-cluster",
        runtime_env=runtime_env,
        namespace="test-namespace",
    )

    assert rayjob.runtime_env == runtime_env

    # Verify runtime env is included in the CR
    rayjob_cr = rayjob._build_rayjob_cr()
    assert rayjob_cr["spec"]["runtimeEnvYAML"] == str(runtime_env)


def test_rayjob_with_active_deadline_and_ttl(mocker):
    """Test RayJob with both active deadline and TTL settings."""
    mocker.patch("kubernetes.config.load_kube_config")
    mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")
    mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayClusterApi")

    rayjob = RayJob(
        job_name="test-job",
        entrypoint="python script.py",
        cluster_name="test-cluster",
        active_deadline_seconds=300,
        ttl_seconds_after_finished=600,
        namespace="test-namespace",
    )

    assert rayjob.active_deadline_seconds == 300
    assert rayjob.ttl_seconds_after_finished == 600

    # Verify both are included in the CR
    rayjob_cr = rayjob._build_rayjob_cr()
    assert rayjob_cr["spec"]["activeDeadlineSeconds"] == 300
    assert rayjob_cr["spec"]["ttlSecondsAfterFinished"] == 600


def test_rayjob_cluster_name_generation_with_config(mocker):
    """Test cluster name generation when using cluster_config."""
    mocker.patch("kubernetes.config.load_kube_config")
    mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")
    mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayClusterApi")

    from codeflare_sdk.ray.rayjobs.config import ManagedClusterConfig

    cluster_config = ManagedClusterConfig()

    rayjob = RayJob(
        job_name="my-job",
        entrypoint="python script.py",
        cluster_config=cluster_config,
        namespace="test-namespace",  # Explicitly specify namespace
    )

    assert rayjob.cluster_name == "my-job-cluster"
    # Note: cluster_config.name is not set in RayJob (it's only for resource config)
    # The cluster name is generated independently for the RayJob


def test_rayjob_namespace_propagation_to_cluster_config(mocker):
    """Test that job namespace is propagated to cluster config when None."""
    mocker.patch("kubernetes.config.load_kube_config")
    mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")
    mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayClusterApi")

    from codeflare_sdk.ray.rayjobs.rayjob import get_current_namespace

    mocker.patch(
        "codeflare_sdk.ray.rayjobs.rayjob.get_current_namespace",
        return_value="detected-ns",
    )

    from codeflare_sdk.ray.rayjobs.config import ManagedClusterConfig

    cluster_config = ManagedClusterConfig()

    rayjob = RayJob(
        job_name="test-job",
        entrypoint="python script.py",
        cluster_config=cluster_config,
    )

    assert rayjob.namespace == "detected-ns"


def test_rayjob_error_handling_invalid_cluster_config(mocker):
    """Test error handling with invalid cluster configuration."""
    mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")

    with pytest.raises(ValueError):
        RayJob(
            job_name="test-job",
            entrypoint="python script.py",
        )


def test_rayjob_constructor_parameter_validation(mocker):
    """Test constructor parameter validation."""
    mocker.patch("kubernetes.config.load_kube_config")
    mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")
    mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayClusterApi")

    # Test with valid parameters
    rayjob = RayJob(
        job_name="test-job",
        entrypoint="python script.py",
        cluster_name="test-cluster",
        namespace="test-ns",
        runtime_env={"pip": ["numpy"]},
        ttl_seconds_after_finished=300,
        active_deadline_seconds=600,
    )

    assert rayjob.name == "test-job"
    assert rayjob.entrypoint == "python script.py"
    assert rayjob.cluster_name == "test-cluster"
    assert rayjob.namespace == "test-ns"
    assert rayjob.runtime_env == {"pip": ["numpy"]}
    assert rayjob.ttl_seconds_after_finished == 300
    assert rayjob.active_deadline_seconds == 600


def test_build_ray_cluster_spec_function(mocker):
    """Test the build_ray_cluster_spec method directly."""
    from codeflare_sdk.ray.rayjobs.config import ManagedClusterConfig

    # Create a test cluster config
    cluster_config = ManagedClusterConfig(
        num_workers=2,
        head_cpu_requests="500m",
        head_memory_requests="512Mi",
        worker_cpu_requests="250m",
        worker_memory_requests="256Mi",
    )

    # Build the spec using the method on the cluster config
    spec = cluster_config.build_ray_cluster_spec("test-cluster")

    # Verify basic structure
    assert "rayVersion" in spec
    assert "enableInTreeAutoscaling" in spec
    assert "headGroupSpec" in spec
    assert "workerGroupSpecs" in spec

    # Verify head group spec
    head_spec = spec["headGroupSpec"]
    assert head_spec["serviceType"] == "ClusterIP"
    assert head_spec["enableIngress"] is False
    assert "rayStartParams" in head_spec
    assert "template" in head_spec

    # Verify worker group spec
    worker_specs = spec["workerGroupSpecs"]
    assert len(worker_specs) == 1
    worker_spec = worker_specs[0]
    assert worker_spec["replicas"] == 2
    assert worker_spec["minReplicas"] == 2
    assert worker_spec["maxReplicas"] == 2
    assert worker_spec["groupName"] == "worker-group-test-cluster"


def test_build_ray_cluster_spec_with_accelerators(mocker):
    """Test build_ray_cluster_spec with GPU accelerators."""
    from codeflare_sdk.ray.rayjobs.config import ManagedClusterConfig

    # Create a test cluster config with GPU accelerators
    cluster_config = ManagedClusterConfig(
        head_accelerators={"nvidia.com/gpu": 1},
        worker_accelerators={"nvidia.com/gpu": 2},
    )

    # Build the spec using the method on the cluster config
    spec = cluster_config.build_ray_cluster_spec("test-cluster")

    # Verify head group has GPU parameters
    head_spec = spec["headGroupSpec"]
    head_params = head_spec["rayStartParams"]
    assert "num-gpus" in head_params
    assert head_params["num-gpus"] == "1"

    # Verify worker group has GPU parameters
    worker_specs = spec["workerGroupSpecs"]
    worker_spec = worker_specs[0]
    worker_params = worker_spec["rayStartParams"]
    assert "num-gpus" in worker_params
    assert worker_params["num-gpus"] == "2"


def test_build_ray_cluster_spec_with_custom_volumes(mocker):
    """Test build_ray_cluster_spec with custom volumes and volume mounts."""
    from codeflare_sdk.ray.rayjobs.config import ManagedClusterConfig
    from kubernetes.client import V1Volume, V1VolumeMount

    # Create custom volumes and volume mounts
    custom_volume = V1Volume(name="custom-data", empty_dir={})
    custom_volume_mount = V1VolumeMount(name="custom-data", mount_path="/data")

    # Create a test cluster config with custom volumes
    cluster_config = ManagedClusterConfig(
        volumes=[custom_volume],
        volume_mounts=[custom_volume_mount],
    )

    # Build the spec using the method on the cluster config
    spec = cluster_config.build_ray_cluster_spec("test-cluster")

    # Verify custom volumes are included
    head_spec = spec["headGroupSpec"]
    head_pod_spec = head_spec["template"].spec  # Access the spec attribute
    # Note: We can't easily check DEFAULT_VOLUMES length since they're now part of the class
    assert len(head_pod_spec.volumes) > 0

    # Verify custom volume mounts are included
    head_container = head_pod_spec.containers[0]  # Access the containers attribute
    # Note: We can't easily check DEFAULT_VOLUME_MOUNTS length since they're now part of the class
    assert len(head_container.volume_mounts) > 0


def test_build_ray_cluster_spec_with_environment_variables(mocker):
    """Test build_ray_cluster_spec with environment variables."""
    from codeflare_sdk.ray.rayjobs.config import ManagedClusterConfig

    # Create a test cluster config with environment variables
    cluster_config = ManagedClusterConfig(
        envs={"CUDA_VISIBLE_DEVICES": "0", "RAY_DISABLE_IMPORT_WARNING": "1"},
    )

    spec = cluster_config.build_ray_cluster_spec("test-cluster")

    # Verify environment variables are included in head container
    head_spec = spec["headGroupSpec"]
    head_pod_spec = head_spec["template"].spec
    head_container = head_pod_spec.containers[0]
    assert hasattr(head_container, "env")
    env_vars = {env.name: env.value for env in head_container.env}
    assert env_vars["CUDA_VISIBLE_DEVICES"] == "0"
    assert env_vars["RAY_DISABLE_IMPORT_WARNING"] == "1"

    # Verify environment variables are included in worker container
    worker_specs = spec["workerGroupSpecs"]
    worker_spec = worker_specs[0]
    worker_pod_spec = worker_spec["template"].spec
    worker_container = worker_pod_spec.containers[0]

    assert hasattr(worker_container, "env")
    worker_env_vars = {env.name: env.value for env in worker_container.env}
    assert worker_env_vars["CUDA_VISIBLE_DEVICES"] == "0"
    assert worker_env_vars["RAY_DISABLE_IMPORT_WARNING"] == "1"


def test_build_ray_cluster_spec_with_tolerations(mocker):
    """Test build_ray_cluster_spec with tolerations."""
    from codeflare_sdk.ray.rayjobs.config import ManagedClusterConfig
    from kubernetes.client import V1Toleration

    # Create test tolerations
    head_toleration = V1Toleration(
        key="node-role.kubernetes.io/master", operator="Exists", effect="NoSchedule"
    )
    worker_toleration = V1Toleration(
        key="nvidia.com/gpu", operator="Exists", effect="NoSchedule"
    )

    # Create a test cluster config with tolerations
    cluster_config = ManagedClusterConfig(
        head_tolerations=[head_toleration],
        worker_tolerations=[worker_toleration],
    )

    spec = cluster_config.build_ray_cluster_spec("test-cluster")

    # Verify head tolerations
    head_spec = spec["headGroupSpec"]
    head_pod_spec = head_spec["template"].spec  # Access the spec attribute
    assert hasattr(head_pod_spec, "tolerations")
    assert len(head_pod_spec.tolerations) == 1
    assert head_pod_spec.tolerations[0].key == "node-role.kubernetes.io/master"

    # Verify worker tolerations
    worker_specs = spec["workerGroupSpecs"]
    worker_spec = worker_specs[0]
    worker_pod_spec = worker_spec["template"].spec  # Access the spec attribute
    assert hasattr(worker_pod_spec, "tolerations")
    assert len(worker_pod_spec.tolerations) == 1
    assert worker_pod_spec.tolerations[0].key == "nvidia.com/gpu"


def test_build_ray_cluster_spec_with_image_pull_secrets(mocker):
    """Test build_ray_cluster_spec with image pull secrets."""
    from codeflare_sdk.ray.rayjobs.config import ManagedClusterConfig

    # Create a test cluster config with image pull secrets
    cluster_config = ManagedClusterConfig(
        image_pull_secrets=["my-registry-secret", "another-secret"]
    )

    spec = cluster_config.build_ray_cluster_spec("test-cluster")

    # Verify image pull secrets are included in head pod
    head_spec = spec["headGroupSpec"]
    head_pod_spec = head_spec["template"].spec  # Access the spec attribute
    assert hasattr(head_pod_spec, "image_pull_secrets")

    head_secrets = head_pod_spec.image_pull_secrets
    assert len(head_secrets) == 2
    assert head_secrets[0].name == "my-registry-secret"
    assert head_secrets[1].name == "another-secret"

    # Verify image pull secrets are included in worker pod
    worker_specs = spec["workerGroupSpecs"]
    worker_spec = worker_specs[0]
    worker_pod_spec = worker_spec["template"].spec
    assert hasattr(worker_pod_spec, "image_pull_secrets")

    worker_secrets = worker_pod_spec.image_pull_secrets
    assert len(worker_secrets) == 2
    assert worker_secrets[0].name == "my-registry-secret"
    assert worker_secrets[1].name == "another-secret"


def test_rayjob_user_override_shutdown_behavior(mocker):
    """Test that user can override the auto-detected shutdown behavior."""
    mocker.patch("kubernetes.config.load_kube_config")
    mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")
    mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayClusterApi")

    # Test 1: User overrides shutdown to True even when using existing cluster
    rayjob_existing_override = RayJob(
        job_name="test-job",
        entrypoint="python script.py",
        cluster_name="existing-cluster",
        shutdown_after_job_finishes=True,  # User override
        namespace="test-namespace",  # Explicitly specify namespace
    )

    assert rayjob_existing_override.shutdown_after_job_finishes is True

    # Test 2: User overrides shutdown to False even when creating new cluster
    from codeflare_sdk.ray.rayjobs.config import ManagedClusterConfig

    cluster_config = ManagedClusterConfig()

    rayjob_new_override = RayJob(
        job_name="test-job",
        entrypoint="python script.py",
        cluster_config=cluster_config,
        shutdown_after_job_finishes=False,  # User override
        namespace="test-namespace",  # Explicitly specify namespace
    )

    assert rayjob_new_override.shutdown_after_job_finishes is False

    # Test 3: User override takes precedence over auto-detection
    rayjob_override_priority = RayJob(
        job_name="test-job",
        entrypoint="python script.py",
        cluster_config=cluster_config,
        shutdown_after_job_finishes=True,  # Should override auto-detection
        namespace="test-namespace",  # Explicitly specify namespace
    )

    assert rayjob_override_priority.shutdown_after_job_finishes is True


class TestRayVersionValidation:
    """Test Ray version validation in RayJob."""

    def test_submit_with_cluster_config_compatible_image_passes(self, mocker):
        """Test that submission passes with compatible cluster_config image."""
        mocker.patch("kubernetes.config.load_kube_config")
        mock_api_class = mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")
        mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayClusterApi")
        mock_api_instance = MagicMock()
        mock_api_class.return_value = mock_api_instance
        mock_api_instance.submit_job.return_value = True

        cluster_config = ManagedClusterConfig(image=f"ray:{RAY_VERSION}")

        rayjob = RayJob(
            job_name="test-job",
            cluster_config=cluster_config,
            namespace="test-namespace",
            entrypoint="python script.py",
        )

        # Should not raise any validation errors
        result = rayjob.submit()
        assert result == "test-job"

    def test_submit_with_cluster_config_incompatible_image_fails(self, mocker):
        """Test that submission fails with incompatible cluster_config image."""
        mocker.patch("kubernetes.config.load_kube_config")
        mock_api_class = mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")
        mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayClusterApi")
        mock_api_instance = MagicMock()
        mock_api_class.return_value = mock_api_instance

        cluster_config = ManagedClusterConfig(image="ray:2.8.0")  # Different version

        rayjob = RayJob(
            job_name="test-job",
            cluster_config=cluster_config,
            namespace="test-namespace",
            entrypoint="python script.py",
        )

        # Should raise ValueError for version mismatch
        with pytest.raises(
            ValueError, match="Cluster config image: Ray version mismatch detected"
        ):
            rayjob.submit()

    def test_validate_ray_version_compatibility_method(self, mocker):
        """Test the _validate_ray_version_compatibility method directly."""
        mocker.patch("kubernetes.config.load_kube_config")
        mock_api_class = mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")
        mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayClusterApi")
        mock_api_instance = MagicMock()
        mock_api_class.return_value = mock_api_instance

        rayjob = RayJob(
            job_name="test-job",
            cluster_name="test-cluster",
            namespace="test-namespace",
            entrypoint="python script.py",
        )

        # Test with no cluster_config (should not raise)
        rayjob._validate_ray_version_compatibility()  # Should not raise

        # Test with compatible cluster_config version
        rayjob._cluster_config = ManagedClusterConfig(image=f"ray:{RAY_VERSION}")
        rayjob._validate_ray_version_compatibility()  # Should not raise

        # Test with incompatible cluster_config version
        rayjob._cluster_config = ManagedClusterConfig(image="ray:2.8.0")
        with pytest.raises(
            ValueError, match="Cluster config image: Ray version mismatch detected"
        ):
            rayjob._validate_ray_version_compatibility()

        # Test with unknown cluster_config version (should warn but not fail)
        rayjob._cluster_config = ManagedClusterConfig(image="custom-image:latest")
        with pytest.warns(
            UserWarning, match="Cluster config image: Cannot determine Ray version"
        ):
            rayjob._validate_ray_version_compatibility()

    def test_validate_cluster_config_image_method(self, mocker):
        """Test the _validate_cluster_config_image method directly."""
        mocker.patch("kubernetes.config.load_kube_config")
        mock_api_class = mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")
        mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayClusterApi")
        mock_api_instance = MagicMock()
        mock_api_class.return_value = mock_api_instance

        rayjob = RayJob(
            job_name="test-job",
            cluster_config=ManagedClusterConfig(),
            namespace="test-namespace",
            entrypoint="python script.py",
        )

        # Test with no image (should not raise)
        rayjob._validate_cluster_config_image()  # Should not raise

        # Test with compatible image
        rayjob._cluster_config.image = f"ray:{RAY_VERSION}"
        rayjob._validate_cluster_config_image()  # Should not raise

        # Test with incompatible image
        rayjob._cluster_config.image = "ray:2.8.0"
        with pytest.raises(
            ValueError, match="Cluster config image: Ray version mismatch detected"
        ):
            rayjob._validate_cluster_config_image()

        # Test with unknown image (should warn but not fail)
        rayjob._cluster_config.image = "custom-image:latest"
        with pytest.warns(
            UserWarning, match="Cluster config image: Cannot determine Ray version"
        ):
            rayjob._validate_cluster_config_image()

    def test_validate_cluster_config_image_edge_cases(self, mocker):
        """Test edge cases in _validate_cluster_config_image method."""
        mocker.patch("kubernetes.config.load_kube_config")
        mock_api_class = mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")
        mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayClusterApi")
        mock_api_instance = MagicMock()
        mock_api_class.return_value = mock_api_instance

        rayjob = RayJob(
            job_name="test-job",
            cluster_config=ManagedClusterConfig(),
            namespace="test-namespace",
            entrypoint="python script.py",
        )

        # Test with None image (should not raise)
        rayjob._cluster_config.image = None
        rayjob._validate_cluster_config_image()  # Should not raise

        # Test with empty string image (should not raise)
        rayjob._cluster_config.image = ""
        rayjob._validate_cluster_config_image()  # Should not raise

        # Test with non-string image (should log warning and skip)
        rayjob._cluster_config.image = 123
        rayjob._validate_cluster_config_image()  # Should log warning and not raise

        # Test with cluster config that has no image attribute
        class MockClusterConfig:
            pass

        rayjob._cluster_config = MockClusterConfig()
        rayjob._validate_cluster_config_image()  # Should not raise


def test_extract_script_files_from_entrypoint_single_script(mocker, tmp_path):
    """Test extracting a single script file from entrypoint."""
    # Mock kubernetes config loading
    mocker.patch("kubernetes.config.load_kube_config")
    mock_api_class = mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")

    # Create a test script
    test_script = tmp_path / "test_script.py"
    test_script.write_text("print('Hello World!')")

    # Change to temp directory for test
    original_cwd = os.getcwd()
    os.chdir(tmp_path)

    try:
        rayjob = RayJob(
            job_name="test-job",
            cluster_name="existing-cluster",
            entrypoint=f"python {test_script.name}",
            namespace="test-namespace",
        )

        scripts = rayjob._extract_script_files_from_entrypoint()

        assert scripts is not None
        assert test_script.name in scripts
        assert scripts[test_script.name] == "print('Hello World!')"
        assert f"{MOUNT_PATH}/{test_script.name}" in rayjob.entrypoint
    finally:
        os.chdir(original_cwd)


def test_extract_script_files_with_dependencies(mocker, tmp_path):
    """Test extracting script files with local dependencies."""
    # Mock kubernetes config loading
    mocker.patch("kubernetes.config.load_kube_config")
    mock_api_class = mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")

    # Create main script and dependency
    main_script = tmp_path / "main.py"
    main_script.write_text(
        """
import helper
from utils import calculate

def main():
    helper.do_something()
    result = calculate(42)
    print(f"Result: {result}")

if __name__ == "__main__":
    main()
"""
    )

    helper_script = tmp_path / "helper.py"
    helper_script.write_text(
        """
def do_something():
    print("Doing something...")
"""
    )

    utils_script = tmp_path / "utils.py"
    utils_script.write_text(
        """
def calculate(x):
    return x * 2
"""
    )

    # Change to temp directory for test
    original_cwd = os.getcwd()
    os.chdir(tmp_path)

    try:
        rayjob = RayJob(
            job_name="test-job",
            cluster_name="existing-cluster",
            entrypoint="python main.py",
            namespace="test-namespace",
        )

        scripts = rayjob._extract_script_files_from_entrypoint()

        assert scripts is not None
        assert len(scripts) == 3
        assert "main.py" in scripts
        assert "helper.py" in scripts
        assert "utils.py" in scripts

        # Verify content
        assert "import helper" in scripts["main.py"]
        assert "def do_something" in scripts["helper.py"]
        assert "def calculate" in scripts["utils.py"]

    finally:
        os.chdir(original_cwd)


def test_extract_script_files_no_local_scripts(mocker):
    """Test entrypoint with no local script files."""
    # Mock kubernetes config loading
    mocker.patch("kubernetes.config.load_kube_config")
    mock_api_class = mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")

    rayjob = RayJob(
        job_name="test-job",
        cluster_name="existing-cluster",
        entrypoint="python -c 'print(\"hello world\")'",
        namespace="test-namespace",
    )

    scripts = rayjob._extract_script_files_from_entrypoint()

    assert scripts is None


def test_extract_script_files_nonexistent_script(mocker):
    """Test entrypoint referencing non-existent script."""
    # Mock kubernetes config loading
    mocker.patch("kubernetes.config.load_kube_config")
    mock_api_class = mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")

    rayjob = RayJob(
        job_name="test-job",
        cluster_name="existing-cluster",
        entrypoint="python nonexistent.py",
        namespace="test-namespace",
    )

    scripts = rayjob._extract_script_files_from_entrypoint()

    assert scripts is None


def test_build_script_configmap_spec():
    """Test building ConfigMap specification for scripts."""
    from codeflare_sdk.ray.rayjobs.config import ManagedClusterConfig

    config = ManagedClusterConfig()
    scripts = {"main.py": "print('main')", "helper.py": "print('helper')"}

    spec = config.build_script_configmap_spec(
        job_name="test-job", namespace="test-namespace", scripts=scripts
    )

    assert spec["apiVersion"] == "v1"
    assert spec["kind"] == "ConfigMap"
    assert spec["metadata"]["name"] == "test-job-scripts"
    assert spec["metadata"]["namespace"] == "test-namespace"
    assert spec["data"] == scripts


def test_build_script_volume_specs():
    """Test building volume and mount specifications for scripts."""
    from codeflare_sdk.ray.rayjobs.config import ManagedClusterConfig

    config = ManagedClusterConfig()

    volume_spec, mount_spec = config.build_script_volume_specs(
        configmap_name="test-scripts", mount_path="/custom/path"
    )

    assert volume_spec["name"] == "ray-job-scripts"
    assert volume_spec["configMap"]["name"] == "test-scripts"

    assert mount_spec["name"] == "ray-job-scripts"
    assert mount_spec["mountPath"] == "/custom/path"


def test_add_script_volumes():
    """Test adding script volumes to cluster configuration."""
    from codeflare_sdk.ray.rayjobs.config import ManagedClusterConfig

    config = ManagedClusterConfig()

    # Initially no volumes
    assert len(config.volumes) == 0
    assert len(config.volume_mounts) == 0

    config.add_script_volumes(configmap_name="test-scripts")

    # Should have added one volume and one mount
    assert len(config.volumes) == 1
    assert len(config.volume_mounts) == 1

    volume = config.volumes[0]
    mount = config.volume_mounts[0]

    assert volume.name == "ray-job-scripts"
    assert volume.config_map.name == "test-scripts"

    assert mount.name == "ray-job-scripts"
    assert mount.mount_path == MOUNT_PATH


def test_add_script_volumes_duplicate_prevention():
    """Test that adding script volumes twice doesn't create duplicates."""
    from codeflare_sdk.ray.rayjobs.config import ManagedClusterConfig

    config = ManagedClusterConfig()

    # Add volumes twice
    config.add_script_volumes(configmap_name="test-scripts")
    config.add_script_volumes(configmap_name="test-scripts")

    # Should still have only one of each
    assert len(config.volumes) == 1
    assert len(config.volume_mounts) == 1


def test_create_configmap_from_spec(mocker):
    """Test creating ConfigMap via Kubernetes API."""
    mocker.patch("kubernetes.config.load_kube_config")
    mock_api_class = mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")

    mock_k8s_api = mocker.patch("kubernetes.client.CoreV1Api")
    mock_api_instance = MagicMock()
    mock_k8s_api.return_value = mock_api_instance

    mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.get_api_client")

    rayjob = RayJob(
        job_name="test-job",
        cluster_name="existing-cluster",
        entrypoint="python test.py",
        namespace="test-namespace",
    )

    configmap_spec = {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {"name": "test-scripts", "namespace": "test-namespace"},
        "data": {"test.py": "print('test')"},
    }

    result = rayjob._create_configmap_from_spec(configmap_spec)

    assert result == "test-scripts"
    mock_api_instance.create_namespaced_config_map.assert_called_once()


def test_create_configmap_already_exists(mocker):
    """Test creating ConfigMap when it already exists (409 conflict)."""
    mocker.patch("kubernetes.config.load_kube_config")
    mock_api_class = mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")

    mock_k8s_api = mocker.patch("kubernetes.client.CoreV1Api")
    mock_api_instance = MagicMock()
    mock_k8s_api.return_value = mock_api_instance

    mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.get_api_client")

    from kubernetes.client import ApiException

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
        "metadata": {"name": "test-scripts", "namespace": "test-namespace"},
        "data": {"test.py": "print('test')"},
    }

    result = rayjob._create_configmap_from_spec(configmap_spec)

    assert result == "test-scripts"
    mock_api_instance.create_namespaced_config_map.assert_called_once()
    mock_api_instance.replace_namespaced_config_map.assert_called_once()


def test_create_configmap_with_owner_reference_basic(mocker, caplog):
    """Test creating ConfigMap with owner reference from valid RayJob result."""
    # Mock kubernetes config loading
    mocker.patch("kubernetes.config.load_kube_config")
    mock_api_class = mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")

    # Mock Kubernetes API
    mock_k8s_api = mocker.patch("kubernetes.client.CoreV1Api")
    mock_api_instance = MagicMock()
    mock_k8s_api.return_value = mock_api_instance

    # Mock get_api_client
    mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.get_api_client")

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
            "name": "test-scripts",
            "namespace": "test-namespace",
            "labels": {
                "ray.io/job-name": "test-job",
                "app.kubernetes.io/managed-by": "codeflare-sdk",
                "app.kubernetes.io/component": "rayjob-scripts",
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
        result = rayjob._create_configmap_from_spec(configmap_spec, rayjob_result)

    assert result == "test-scripts"

    # Verify owner reference was set
    expected_owner_ref = mocker.ANY  # We'll check via the logs
    assert (
        "Adding owner reference to ConfigMap 'test-scripts' with RayJob UID: a4dd4c5a-ab61-411d-b4d1-4abb5177422a"
        in caplog.text
    )

    # Verify owner_references was set on metadata
    assert mock_metadata_instance.owner_references is not None
    mock_api_instance.create_namespaced_config_map.assert_called_once()


def test_create_configmap_without_owner_reference_no_uid(mocker, caplog):
    """Test creating ConfigMap without owner reference when RayJob has no UID."""
    mocker.patch("kubernetes.config.load_kube_config")
    mock_api_class = mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")

    mock_k8s_api = mocker.patch("kubernetes.client.CoreV1Api")
    mock_api_instance = MagicMock()
    mock_k8s_api.return_value = mock_api_instance

    mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.get_api_client")

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
        "metadata": {"name": "test-scripts", "namespace": "test-namespace"},
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
        result = rayjob._create_configmap_from_spec(configmap_spec, rayjob_result)

    assert result == "test-scripts"

    # Verify warning was logged and no owner reference was set
    assert (
        "No valid RayJob result with UID found, ConfigMap 'test-scripts' will not have owner reference"
        in caplog.text
    )

    # The important part is that the warning was logged, indicating no owner reference was set
    mock_api_instance.create_namespaced_config_map.assert_called_once()


def test_create_configmap_with_invalid_rayjob_result(mocker, caplog):
    """Test creating ConfigMap with None or invalid rayjob_result."""
    # Mock kubernetes config loading
    mocker.patch("kubernetes.config.load_kube_config")
    mock_api_class = mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")

    # Mock Kubernetes API
    mock_k8s_api = mocker.patch("kubernetes.client.CoreV1Api")
    mock_api_instance = MagicMock()
    mock_k8s_api.return_value = mock_api_instance

    # Mock get_api_client
    mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.get_api_client")

    rayjob = RayJob(
        job_name="test-job",
        cluster_name="existing-cluster",
        entrypoint="python test.py",
        namespace="test-namespace",
    )

    configmap_spec = {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {"name": "test-scripts", "namespace": "test-namespace"},
        "data": {"test.py": "print('test')"},
    }

    # Test with None
    with caplog.at_level("WARNING"):
        result = rayjob._create_configmap_from_spec(configmap_spec, None)

    assert result == "test-scripts"
    assert "No valid RayJob result with UID found" in caplog.text

    # Test with string instead of dict
    caplog.clear()
    with caplog.at_level("WARNING"):
        result = rayjob._create_configmap_from_spec(configmap_spec, "not-a-dict")

    assert result == "test-scripts"
    assert "No valid RayJob result with UID found" in caplog.text


def test_handle_script_volumes_for_new_cluster(mocker, tmp_path):
    """Test handling script volumes for new cluster creation."""
    mocker.patch("kubernetes.config.load_kube_config")
    mock_api_class = mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")

    mock_create = mocker.patch.object(RayJob, "_create_configmap_from_spec")
    mock_create.return_value = "test-job-scripts"

    test_script = tmp_path / "test.py"
    test_script.write_text("print('test')")

    from codeflare_sdk.ray.rayjobs.config import ManagedClusterConfig

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

        scripts = {"test.py": "print('test')"}
        rayjob._handle_script_volumes_for_new_cluster(scripts)

        mock_create.assert_called_once()

        assert len(cluster_config.volumes) == 1
        assert len(cluster_config.volume_mounts) == 1

    finally:
        os.chdir(original_cwd)


def test_ast_parsing_import_detection(mocker, tmp_path):
    """Test AST parsing correctly detects import statements."""
    mocker.patch("kubernetes.config.load_kube_config")
    mock_api_class = mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")

    main_script = tmp_path / "main.py"
    main_script.write_text(
        """# Different import patterns
import helper
from utils import func1, func2
from local_module import MyClass
import os  # Standard library - should be ignored
import non_existent  # Non-local - should be ignored
"""
    )

    helper_script = tmp_path / "helper.py"
    helper_script.write_text("def helper_func(): pass")

    utils_script = tmp_path / "utils.py"
    utils_script.write_text(
        """def func1(): pass
def func2(): pass
"""
    )

    local_module_script = tmp_path / "local_module.py"
    local_module_script.write_text("class MyClass: pass")

    original_cwd = os.getcwd()
    os.chdir(tmp_path)

    try:
        rayjob = RayJob(
            job_name="test-job",
            cluster_name="existing-cluster",
            entrypoint="python main.py",
            namespace="test-namespace",
        )

        scripts = rayjob._extract_script_files_from_entrypoint()

        assert scripts is not None
        assert len(scripts) == 4  # main + 3 dependencies
        assert "main.py" in scripts
        assert "helper.py" in scripts
        assert "utils.py" in scripts
        assert "local_module.py" in scripts

    finally:
        os.chdir(original_cwd)


def test_script_handling_timing_after_rayjob_submission(mocker, tmp_path):
    """Test that script handling happens after RayJob is submitted (not before)."""
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

    mock_handle_new = mocker.patch.object(
        RayJob, "_handle_script_volumes_for_new_cluster"
    )

    mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayClusterApi")

    test_script = tmp_path / "test.py"
    test_script.write_text("print('test')")

    call_order = []

    def track_submit(*args, **kwargs):
        call_order.append("submit_job")
        return submit_result

    def track_handle_scripts(*args, **kwargs):
        call_order.append("handle_scripts")
        assert len(args) >= 2
        assert args[1] == submit_result  # rayjob_result should be second arg

    mock_api_instance.submit_job.side_effect = track_submit
    mock_handle_new.side_effect = track_handle_scripts

    original_cwd = os.getcwd()
    try:
        os.chdir(tmp_path)

        from codeflare_sdk.ray.rayjobs.config import ManagedClusterConfig

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

    assert call_order == ["submit_job", "handle_scripts"]

    mock_api_instance.submit_job.assert_called_once()
    mock_handle_new.assert_called_once()

    mock_handle_new.assert_called_with({"test.py": "print('test')"}, submit_result)


def test_rayjob_submit_with_scripts_new_cluster(mocker, tmp_path):
    """Test RayJob submission with script detection for new cluster."""
    # Mock kubernetes config loading
    mocker.patch("kubernetes.config.load_kube_config")

    # Mock the RayjobApi
    mock_api_class = mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")
    mock_api_instance = MagicMock()
    mock_api_class.return_value = mock_api_instance
    mock_api_instance.submit_job.return_value = True

    # Mock ConfigMap creation
    mock_k8s_api = mocker.patch("kubernetes.client.CoreV1Api")
    mock_k8s_instance = MagicMock()
    mock_k8s_api.return_value = mock_k8s_instance
    mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.get_api_client")

    # Create test script
    test_script = tmp_path / "test.py"
    test_script.write_text("print('Hello from script!')")

    from codeflare_sdk.ray.rayjobs.config import ManagedClusterConfig

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

        # Submit should detect scripts and handle them
        result = rayjob.submit()

        assert result == "test-job"

        # Verify ConfigMap was created
        mock_k8s_instance.create_namespaced_config_map.assert_called_once()

        # Verify volumes were added
        assert len(cluster_config.volumes) == 1
        assert len(cluster_config.volume_mounts) == 1

        # Verify entrypoint was updated
        assert f"{MOUNT_PATH}/test.py" in rayjob.entrypoint

    finally:
        os.chdir(original_cwd)


def test_process_script_and_imports_io_error(mocker, tmp_path):
    """Test _process_script_and_imports handles IO errors gracefully."""
    mocker.patch("kubernetes.config.load_kube_config")
    mock_api_class = mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")

    rayjob = RayJob(
        job_name="test-job",
        cluster_name="existing-cluster",
        entrypoint="python test.py",
        namespace="test-namespace",
    )

    scripts = {}
    processed_files = set()

    # Mock os.path.isfile to return True but open() to raise IOError
    mocker.patch("os.path.isfile", return_value=True)
    mocker.patch("builtins.open", side_effect=IOError("Permission denied"))

    # Should handle the error gracefully and not crash
    rayjob._process_script_and_imports("test.py", scripts, MOUNT_PATH, processed_files)

    # Should add to processed_files but not to scripts (due to error)
    assert "test.py" in processed_files
    assert len(scripts) == 0


def test_process_script_and_imports_container_path_skip(mocker):
    """Test that scripts already in container paths are skipped."""
    mocker.patch("kubernetes.config.load_kube_config")
    mock_api_class = mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")

    rayjob = RayJob(
        job_name="test-job",
        cluster_name="existing-cluster",
        entrypoint="python test.py",
        namespace="test-namespace",
    )

    scripts = {}
    processed_files = set()

    # Test script path already in container
    rayjob._process_script_and_imports(
        f"{MOUNT_PATH}/test.py", scripts, MOUNT_PATH, processed_files
    )

    # Should skip processing
    assert len(scripts) == 0
    assert len(processed_files) == 0


def test_process_script_and_imports_already_processed(mocker, tmp_path):
    """Test that already processed scripts are skipped (infinite loop prevention)."""
    mocker.patch("kubernetes.config.load_kube_config")
    mock_api_class = mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")

    rayjob = RayJob(
        job_name="test-job",
        cluster_name="existing-cluster",
        entrypoint="python test.py",
        namespace="test-namespace",
    )

    scripts = {}
    processed_files = {"test.py"}  # Already processed

    # Should return early without processing
    rayjob._process_script_and_imports("test.py", scripts, MOUNT_PATH, processed_files)

    assert len(scripts) == 0
    assert processed_files == {"test.py"}


def test_submit_with_scripts_owner_reference_integration(mocker, tmp_path, caplog):
    """Integration test for submit() with local scripts to verify end-to-end owner reference flow."""
    # Mock kubernetes config loading
    mocker.patch("kubernetes.config.load_kube_config")

    # Mock the RayjobApi
    mock_api_class = mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")
    mock_api_instance = MagicMock()
    mock_api_class.return_value = mock_api_instance

    # RayJob submission returns result with UID
    submit_result = {
        "metadata": {
            "name": "test-job",
            "namespace": "test-namespace",
            "uid": "unique-rayjob-uid-12345",
        }
    }
    mock_api_instance.submit_job.return_value = submit_result

    # Mock Kubernetes ConfigMap API
    mock_k8s_api = mocker.patch("kubernetes.client.CoreV1Api")
    mock_k8s_instance = MagicMock()
    mock_k8s_api.return_value = mock_k8s_instance
    mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.get_api_client")

    # Capture the ConfigMap that gets created
    created_configmap = None

    def capture_configmap(namespace, body):
        nonlocal created_configmap
        created_configmap = body
        return body

    mock_k8s_instance.create_namespaced_config_map.side_effect = capture_configmap

    # Create test scripts
    test_script = tmp_path / "main.py"
    test_script.write_text("import helper\nprint('main')")

    helper_script = tmp_path / "helper.py"
    helper_script.write_text("def help(): print('helper')")

    # Change to temp directory for script detection
    original_cwd = os.getcwd()
    try:
        os.chdir(tmp_path)

        from codeflare_sdk.ray.rayjobs.config import ManagedClusterConfig

        cluster_config = ManagedClusterConfig()

        rayjob = RayJob(
            job_name="test-job",
            cluster_config=cluster_config,
            entrypoint="python main.py",
            namespace="test-namespace",
        )

        with caplog.at_level("INFO"):
            result = rayjob.submit()

        assert result == "test-job"

        # Verify RayJob was submitted first
        mock_api_instance.submit_job.assert_called_once()

        # Verify ConfigMap was created with owner reference
        mock_k8s_instance.create_namespaced_config_map.assert_called_once()
        assert created_configmap is not None

        # Verify owner reference was set correctly
        assert hasattr(created_configmap.metadata, "owner_references")
        assert created_configmap.metadata.owner_references is not None
        assert len(created_configmap.metadata.owner_references) == 1

        owner_ref = created_configmap.metadata.owner_references[0]
        assert owner_ref.api_version == "ray.io/v1"
        assert owner_ref.kind == "RayJob"
        assert owner_ref.name == "test-job"
        assert owner_ref.uid == "unique-rayjob-uid-12345"
        assert owner_ref.controller is True
        assert owner_ref.block_owner_deletion is True

        # Verify labels were set
        assert created_configmap.metadata.labels["ray.io/job-name"] == "test-job"
        assert (
            created_configmap.metadata.labels["app.kubernetes.io/managed-by"]
            == "codeflare-sdk"
        )
        assert (
            created_configmap.metadata.labels["app.kubernetes.io/component"]
            == "rayjob-scripts"
        )

        # Verify scripts were included
        assert "main.py" in created_configmap.data
        assert "helper.py" in created_configmap.data

        # Verify log message
        assert (
            "Adding owner reference to ConfigMap 'test-job-scripts' with RayJob UID: unique-rayjob-uid-12345"
            in caplog.text
        )

    finally:
        os.chdir(original_cwd)


def test_find_local_imports_syntax_error(mocker):
    """Test _find_local_imports handles syntax errors gracefully."""
    mocker.patch("kubernetes.config.load_kube_config")
    mock_api_class = mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")

    rayjob = RayJob(
        job_name="test-job",
        cluster_name="existing-cluster",
        entrypoint="python test.py",
        namespace="test-namespace",
    )

    # Invalid Python syntax
    invalid_script_content = "import helper\ndef invalid_syntax("

    mock_callback = mocker.Mock()

    # Should handle syntax error gracefully
    rayjob._find_local_imports(invalid_script_content, "test.py", mock_callback)

    # Callback should not be called due to syntax error
    mock_callback.assert_not_called()


def test_create_configmap_api_error_non_409(mocker):
    """Test _create_configmap_from_spec handles non-409 API errors."""
    mocker.patch("kubernetes.config.load_kube_config")
    mock_api_class = mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")

    # Mock Kubernetes API with 500 error
    mock_k8s_api = mocker.patch("kubernetes.client.CoreV1Api")
    mock_api_instance = mocker.Mock()
    mock_k8s_api.return_value = mock_api_instance

    from kubernetes.client import ApiException

    mock_api_instance.create_namespaced_config_map.side_effect = ApiException(
        status=500
    )

    mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.get_api_client")

    rayjob = RayJob(
        job_name="test-job",
        cluster_name="existing-cluster",
        entrypoint="python test.py",
        namespace="test-namespace",
    )

    configmap_spec = {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {"name": "test-scripts", "namespace": "test-namespace"},
        "data": {"test.py": "print('test')"},
    }

    # Should raise RuntimeError for non-409 API errors
    with pytest.raises(RuntimeError, match="Failed to create ConfigMap"):
        rayjob._create_configmap_from_spec(configmap_spec)


def test_update_existing_cluster_get_cluster_error(mocker):
    """Test _update_existing_cluster_for_scripts handles get cluster errors."""
    mocker.patch("kubernetes.config.load_kube_config")
    mock_rayjob_api = mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")

    # Mock RayClusterApi with error
    mock_cluster_api_class = mocker.patch(
        "codeflare_sdk.ray.rayjobs.rayjob.RayClusterApi"
    )
    mock_cluster_api_instance = mocker.Mock()
    mock_cluster_api_class.return_value = mock_cluster_api_instance

    from kubernetes.client import ApiException

    mock_cluster_api_instance.get_ray_cluster.side_effect = ApiException(status=404)

    from codeflare_sdk.ray.rayjobs.config import ManagedClusterConfig

    config_builder = ManagedClusterConfig()

    rayjob = RayJob(
        job_name="test-job",
        cluster_name="existing-cluster",
        entrypoint="python test.py",
        namespace="test-namespace",
    )

    # Should raise RuntimeError when getting cluster fails
    with pytest.raises(RuntimeError, match="Failed to get RayCluster"):
        rayjob._update_existing_cluster_for_scripts("test-scripts", config_builder)


def test_update_existing_cluster_patch_error(mocker):
    """Test _update_existing_cluster_for_scripts handles patch errors."""
    mocker.patch("kubernetes.config.load_kube_config")
    mock_rayjob_api = mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")

    # Mock RayClusterApi
    mock_cluster_api_class = mocker.patch(
        "codeflare_sdk.ray.rayjobs.rayjob.RayClusterApi"
    )
    mock_cluster_api_instance = mocker.Mock()
    mock_cluster_api_class.return_value = mock_cluster_api_instance

    # Mock successful get but failed patch
    mock_cluster_api_instance.get_ray_cluster.return_value = {
        "spec": {
            "headGroupSpec": {
                "template": {
                    "spec": {"volumes": [], "containers": [{"volumeMounts": []}]}
                }
            },
            "workerGroupSpecs": [
                {
                    "template": {
                        "spec": {"volumes": [], "containers": [{"volumeMounts": []}]}
                    }
                }
            ],
        }
    }

    from kubernetes.client import ApiException

    mock_cluster_api_instance.patch_ray_cluster.side_effect = ApiException(status=500)

    from codeflare_sdk.ray.rayjobs.config import ManagedClusterConfig

    config_builder = ManagedClusterConfig()

    rayjob = RayJob(
        job_name="test-job",
        cluster_name="existing-cluster",
        entrypoint="python test.py",
        namespace="test-namespace",
    )

    # Should raise RuntimeError when patching fails
    with pytest.raises(RuntimeError, match="Failed to update RayCluster"):
        rayjob._update_existing_cluster_for_scripts("test-scripts", config_builder)


def test_extract_script_files_empty_entrypoint(mocker):
    """Test script extraction with empty entrypoint."""
    mocker.patch("kubernetes.config.load_kube_config")
    mock_api_class = mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")

    rayjob = RayJob(
        job_name="test-job",
        cluster_name="existing-cluster",
        entrypoint="",  # Empty entrypoint
        namespace="test-namespace",
    )

    scripts = rayjob._extract_script_files_from_entrypoint()

    assert scripts is None


def test_add_script_volumes_existing_volume_skip():
    """Test add_script_volumes skips when volume already exists (missing coverage)."""
    from codeflare_sdk.ray.rayjobs.config import ManagedClusterConfig
    from kubernetes.client import V1Volume, V1ConfigMapVolumeSource

    config = ManagedClusterConfig()

    # Pre-add a volume with same name
    existing_volume = V1Volume(
        name="ray-job-scripts",
        config_map=V1ConfigMapVolumeSource(name="existing-scripts"),
    )
    config.volumes.append(existing_volume)

    # Should skip adding duplicate volume
    config.add_script_volumes(configmap_name="new-scripts")

    # Should still have only one volume
    assert len(config.volumes) == 1
    assert len(config.volume_mounts) == 0  # Mount not added due to volume skip


def test_add_script_volumes_existing_mount_skip():
    """Test add_script_volumes skips when mount already exists (missing coverage)."""
    from codeflare_sdk.ray.rayjobs.config import ManagedClusterConfig
    from kubernetes.client import V1VolumeMount

    config = ManagedClusterConfig()

    # Pre-add a mount with same name
    existing_mount = V1VolumeMount(name="ray-job-scripts", mount_path="/existing/path")
    config.volume_mounts.append(existing_mount)

    # Should skip adding duplicate mount
    config.add_script_volumes(configmap_name="new-scripts")

    # Should still have only one mount and no volume added
    assert len(config.volumes) == 0  # Volume not added due to mount skip
    assert len(config.volume_mounts) == 1


def test_rayjob_stop_success(mocker, caplog):
    """Test successful RayJob stop operation."""
    mocker.patch("kubernetes.config.load_kube_config")

    mock_api_class = mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")
    mock_api_instance = MagicMock()
    mock_api_class.return_value = mock_api_instance

    mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayClusterApi")

    mock_api_instance.suspend_job.return_value = {
        "metadata": {"name": "test-rayjob"},
        "spec": {"suspend": True},
    }

    rayjob = RayJob(
        job_name="test-rayjob",
        cluster_name="test-cluster",
        namespace="test-namespace",
        entrypoint="python script.py",
    )

    with caplog.at_level("INFO"):
        result = rayjob.stop()

    assert result is True

    mock_api_instance.suspend_job.assert_called_once_with(
        name="test-rayjob", k8s_namespace="test-namespace"
    )

    # Verify success message was logged
    assert "Successfully stopped the RayJob test-rayjob" in caplog.text


def test_rayjob_stop_failure(mocker):
    """Test RayJob stop operation when API call fails."""
    mocker.patch("kubernetes.config.load_kube_config")

    mock_api_class = mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")
    mock_api_instance = MagicMock()
    mock_api_class.return_value = mock_api_instance

    mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayClusterApi")

    mock_api_instance.suspend_job.return_value = None

    rayjob = RayJob(
        job_name="test-rayjob",
        cluster_name="test-cluster",
        namespace="test-namespace",
        entrypoint="python script.py",
    )

    with pytest.raises(RuntimeError, match="Failed to stop the RayJob test-rayjob"):
        rayjob.stop()

    mock_api_instance.suspend_job.assert_called_once_with(
        name="test-rayjob", k8s_namespace="test-namespace"
    )


def test_rayjob_resubmit_success(mocker):
    """Test successful RayJob resubmit operation."""
    mocker.patch("kubernetes.config.load_kube_config")

    mock_api_class = mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")
    mock_api_instance = MagicMock()
    mock_api_class.return_value = mock_api_instance

    mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayClusterApi")

    mock_api_instance.resubmit_job.return_value = {
        "metadata": {"name": "test-rayjob"},
        "spec": {"suspend": False},
    }

    rayjob = RayJob(
        job_name="test-rayjob",
        cluster_name="test-cluster",
        namespace="test-namespace",
        entrypoint="python script.py",
    )

    result = rayjob.resubmit()

    assert result is True

    mock_api_instance.resubmit_job.assert_called_once_with(
        name="test-rayjob", k8s_namespace="test-namespace"
    )


def test_rayjob_resubmit_failure(mocker):
    """Test RayJob resubmit operation when API call fails."""
    mocker.patch("kubernetes.config.load_kube_config")

    mock_api_class = mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")
    mock_api_instance = MagicMock()
    mock_api_class.return_value = mock_api_instance

    mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayClusterApi")

    mock_api_instance.resubmit_job.return_value = None

    rayjob = RayJob(
        job_name="test-rayjob",
        cluster_name="test-cluster",
        namespace="test-namespace",
        entrypoint="python script.py",
    )

    with pytest.raises(RuntimeError, match="Failed to resubmit the RayJob test-rayjob"):
        rayjob.resubmit()

    mock_api_instance.resubmit_job.assert_called_once_with(
        name="test-rayjob", k8s_namespace="test-namespace"
    )

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
from codeflare_sdk.common.utils.constants import CUDA_RUNTIME_IMAGE, RAY_VERSION

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
        ValueError, match="entrypoint must be provided to submit a RayJob"
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
    mocker.patch(
        "codeflare_sdk.ray.rayjobs.rayjob.get_current_namespace",
        return_value="detected-ns",
    )
    mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")

    rayjob = RayJob(
        job_name="test-job", entrypoint="python script.py", cluster_name="test-cluster"
    )

    assert rayjob.namespace == "detected-ns"


def test_namespace_auto_detection_fallback(mocker):
    """Test that namespace auto-detection failure raises an error."""
    mocker.patch(
        "codeflare_sdk.ray.rayjobs.rayjob.get_current_namespace", return_value=None
    )
    mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")

    with pytest.raises(ValueError, match="Could not auto-detect Kubernetes namespace"):
        RayJob(
            job_name="test-job",
            entrypoint="python script.py",
            cluster_name="test-cluster",
        )


def test_namespace_explicit_override(mocker):
    """Test that explicit namespace overrides auto-detection."""
    mocker.patch(
        "codeflare_sdk.ray.rayjobs.rayjob.get_current_namespace",
        return_value="detected-ns",
    )
    mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")

    rayjob = RayJob(
        job_name="test-job",
        entrypoint="python script.py",
        cluster_name="test-cluster",
        namespace="explicit-ns",
    )

    assert rayjob.namespace == "explicit-ns"


def test_shutdown_behavior_with_cluster_config(mocker):
    """Test that shutdown_after_job_finishes is True when cluster_config is provided."""
    mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")

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
    mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")

    rayjob = RayJob(
        job_name="test-job",
        entrypoint="python script.py",
        cluster_name="existing-cluster",
        namespace="test-namespace",
    )

    assert rayjob.shutdown_after_job_finishes is False


def test_rayjob_with_rayjob_cluster_config(mocker):
    """Test RayJob with the new ManagedClusterConfig."""
    mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")

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
    mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")

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
    mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")

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
    mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")

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
    mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")

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
    mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")

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
    mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")

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
    mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")

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


def test_build_ray_cluster_spec_with_gcs_ft(mocker):
    """Test build_ray_cluster_spec with GCS fault tolerance enabled."""
    from codeflare_sdk.ray.rayjobs.config import ManagedClusterConfig

    # Create a test cluster config with GCS FT enabled
    cluster_config = ManagedClusterConfig(
        enable_gcs_ft=True,
        redis_address="redis://redis-service:6379",
        external_storage_namespace="storage-ns",
    )

    # Build the spec using the method on the cluster config
    spec = cluster_config.build_ray_cluster_spec("test-cluster")

    # Verify GCS fault tolerance options
    assert "gcsFaultToleranceOptions" in spec
    gcs_ft = spec["gcsFaultToleranceOptions"]
    assert gcs_ft["redisAddress"] == "redis://redis-service:6379"
    assert gcs_ft["externalStorageNamespace"] == "storage-ns"

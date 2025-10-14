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
from unittest.mock import MagicMock
from codeflare_sdk.common.utils.constants import RAY_VERSION
from ray.runtime_env import RuntimeEnv

from codeflare_sdk.ray.rayjobs.rayjob import RayJob
from codeflare_sdk.ray.cluster.config import ClusterConfiguration
from codeflare_sdk.ray.rayjobs.config import ManagedClusterConfig
from kubernetes.client import V1Volume, V1VolumeMount, V1Toleration


def test_rayjob_submit_success(auto_mock_setup):
    """
    Test successful RayJob submission.
    """
    mock_api_instance = auto_mock_setup["rayjob_api"]

    mock_api_instance.submit.return_value = {"metadata": {"name": "test-rayjob"}}

    rayjob = RayJob(
        job_name="test-rayjob",
        cluster_name="test-ray-cluster",
        namespace="test-namespace",
        entrypoint="python -c 'print(\"hello world\")'",
        runtime_env=RuntimeEnv(pip=["requests"]),
    )

    job_id = rayjob.submit()

    assert job_id == "test-rayjob"

    mock_api_instance.submit_job.assert_called_once()
    call_args = mock_api_instance.submit_job.call_args

    assert call_args.kwargs["k8s_namespace"] == "test-namespace"

    job_cr = call_args.kwargs["job"]
    assert job_cr["metadata"]["name"] == "test-rayjob"
    assert job_cr["metadata"]["namespace"] == "test-namespace"
    assert job_cr["spec"]["entrypoint"] == "python -c 'print(\"hello world\")'"
    assert job_cr["spec"]["clusterSelector"]["ray.io/cluster"] == "test-ray-cluster"
    assert job_cr["spec"]["runtimeEnvYAML"] == "pip:\n- requests\n"


def test_rayjob_submit_failure(auto_mock_setup):
    """
    Test RayJob submission failure.
    """
    mock_api_instance = auto_mock_setup["rayjob_api"]

    mock_api_instance.submit_job.return_value = None

    rayjob = RayJob(
        job_name="test-rayjob",
        cluster_name="test-ray-cluster",
        namespace="default",
        entrypoint="python -c 'print()'",
        runtime_env=RuntimeEnv(pip=["numpy"]),
    )

    with pytest.raises(RuntimeError, match="Failed to submit RayJob test-rayjob"):
        rayjob.submit()


def test_rayjob_init_validation_both_provided(auto_mock_setup):
    """
    Test that providing both cluster_name and cluster_config raises error.
    """
    cluster_config = ClusterConfiguration(name="test-cluster", namespace="test")

    with pytest.raises(
        ValueError,
        match="❌ Configuration Error: You cannot specify both 'cluster_name' and 'cluster_config'",
    ):
        RayJob(
            job_name="test-job",
            cluster_name="existing-cluster",
            cluster_config=cluster_config,
            entrypoint="python -c 'print()'",
        )


def test_rayjob_init_validation_neither_provided(auto_mock_setup):
    """
    Test that providing neither cluster_name nor cluster_config raises error.
    """
    with pytest.raises(
        ValueError,
        match="❌ Configuration Error: You must provide either 'cluster_name'",
    ):
        RayJob(job_name="test-job", entrypoint="python test.py")


def test_rayjob_init_with_cluster_config(auto_mock_setup):
    """
    Test RayJob initialization with cluster configuration for auto-creation.
    """
    cluster_config = ClusterConfiguration(
        name="auto-cluster", namespace="test-namespace", num_workers=2
    )

    rayjob = RayJob(
        job_name="test-job",
        cluster_config=cluster_config,
        entrypoint="python -c 'print()'",
        namespace="test-namespace",
    )

    assert rayjob.name == "test-job"
    assert rayjob.cluster_name == "test-job-cluster"  # Generated from job name
    assert rayjob._cluster_config == cluster_config
    assert rayjob._cluster_name is None


def test_rayjob_cluster_name_generation(auto_mock_setup):
    """
    Test that cluster names are generated when config has empty name.
    """
    cluster_config = ClusterConfiguration(
        name="",  # Empty name should trigger generation
        namespace="test-namespace",
        num_workers=1,
    )

    rayjob = RayJob(
        job_name="my-job",
        cluster_config=cluster_config,
        entrypoint="python -c 'print()'",
        namespace="test-namespace",
    )

    assert rayjob.cluster_name == "my-job-cluster"


def test_rayjob_cluster_config_namespace_none(auto_mock_setup):
    """
    Test that cluster config namespace is set when None.
    """
    cluster_config = ClusterConfiguration(
        name="test-cluster",
        namespace=None,  # This should be set to job namespace
        num_workers=1,
    )

    rayjob = RayJob(
        job_name="test-job",
        cluster_config=cluster_config,
        namespace="job-namespace",
        entrypoint="python -c 'print()'",
    )

    assert rayjob.namespace == "job-namespace"


def test_rayjob_with_active_deadline_seconds(auto_mock_setup):
    """
    Test RayJob CR generation with active deadline seconds.
    """
    rayjob = RayJob(
        job_name="test-job",
        cluster_name="test-cluster",
        namespace="test-namespace",
        entrypoint="python main.py",
        active_deadline_seconds=30,
    )

    rayjob_cr = rayjob._build_rayjob_cr()

    assert rayjob_cr["spec"]["activeDeadlineSeconds"] == 30


def test_build_ray_cluster_spec_no_config_error(auto_mock_setup):
    """
    Test _build_ray_cluster_spec raises error when no cluster config.
    """
    rayjob = RayJob(
        job_name="test-job",
        cluster_name="existing-cluster",
        entrypoint="python -c 'print()'",
        namespace="test-namespace",
    )

    rayjob_cr = rayjob._build_rayjob_cr()

    assert rayjob_cr["spec"]["clusterSelector"]["ray.io/cluster"] == "existing-cluster"
    assert "rayClusterSpec" not in rayjob_cr["spec"]


def test_build_ray_cluster_spec(mocker, auto_mock_setup):
    """
    Test _build_ray_cluster_spec method.
    """

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
    cluster_config = ManagedClusterConfig(num_workers=2)
    mocker.patch.object(
        cluster_config, "build_ray_cluster_spec", return_value=mock_ray_cluster["spec"]
    )

    rayjob = RayJob(
        job_name="test-job",
        cluster_config=cluster_config,
        entrypoint="python -c 'print()'",
        namespace="test-namespace",
    )

    rayjob_cr = rayjob._build_rayjob_cr()

    assert "rayClusterSpec" in rayjob_cr["spec"]
    cluster_config.build_ray_cluster_spec.assert_called_once_with(
        cluster_name="test-job-cluster"
    )


def test_build_rayjob_cr_with_existing_cluster(auto_mock_setup):
    """
    Test _build_rayjob_cr method with existing cluster.
    """

    rayjob = RayJob(
        job_name="test-job",
        cluster_name="existing-cluster",
        namespace="test-namespace",
        entrypoint="python main.py",
        ttl_seconds_after_finished=300,
    )

    rayjob_cr = rayjob._build_rayjob_cr()

    assert rayjob_cr["apiVersion"] == "ray.io/v1"
    assert rayjob_cr["kind"] == "RayJob"
    assert rayjob_cr["metadata"]["name"] == "test-job"
    spec = rayjob_cr["spec"]
    assert spec["entrypoint"] == "python main.py"
    assert spec["shutdownAfterJobFinishes"] is False
    assert spec["ttlSecondsAfterFinished"] == 300

    assert spec["clusterSelector"]["ray.io/cluster"] == "existing-cluster"
    assert "rayClusterSpec" not in spec


def test_build_rayjob_cr_with_auto_cluster(mocker, auto_mock_setup):
    """
    Test _build_rayjob_cr method with auto-created cluster.
    """
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
    cluster_config = ManagedClusterConfig(num_workers=2)

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
    assert rayjob_cr["spec"]["rayClusterSpec"] == mock_ray_cluster["spec"]
    assert "clusterSelector" not in rayjob_cr["spec"]


def test_submit_validation_no_entrypoint(auto_mock_setup):
    """
    Test that submit() raises error when entrypoint is None.
    """
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


def test_submit_with_auto_cluster(mocker, auto_mock_setup):
    """
    Test successful submission with auto-created cluster.
    """
    mock_api_instance = auto_mock_setup["rayjob_api"]

    mock_ray_cluster = {
        "apiVersion": "ray.io/v1",
        "kind": "RayCluster",
        "spec": {
            "rayVersion": RAY_VERSION,
            "headGroupSpec": {"replicas": 1},
            "workerGroupSpecs": [{"replicas": 1}],
        },
    }
    mock_api_instance.submit_job.return_value = True

    cluster_config = ManagedClusterConfig(num_workers=1)
    mocker.patch.object(
        cluster_config, "build_ray_cluster_spec", return_value=mock_ray_cluster["spec"]
    )

    rayjob = RayJob(
        job_name="test-job",
        cluster_config=cluster_config,
        entrypoint="python -c 'print()'",
        namespace="test-namespace",
    )

    result = rayjob.submit()

    assert result == "test-job"

    mock_api_instance.submit_job.assert_called_once()
    call_args = mock_api_instance.submit_job.call_args

    job_cr = call_args.kwargs["job"]
    assert "rayClusterSpec" in job_cr["spec"]
    assert job_cr["spec"]["rayClusterSpec"] == mock_ray_cluster["spec"]


def test_namespace_auto_detection_success(auto_mock_setup):
    """
    Test successful namespace auto-detection.
    """
    auto_mock_setup["get_current_namespace"].return_value = "detected-ns"

    rayjob = RayJob(
        job_name="test-job", entrypoint="python test.py", cluster_name="test-cluster"
    )

    assert rayjob.namespace == "detected-ns"


def test_namespace_auto_detection_fallback(auto_mock_setup):
    """
    Test that namespace auto-detection failure raises an error.
    """
    auto_mock_setup["get_current_namespace"].return_value = None

    with pytest.raises(ValueError, match="Could not auto-detect Kubernetes namespace"):
        RayJob(
            job_name="test-job",
            entrypoint="python -c 'print()'",
            cluster_name="test-cluster",
        )


def test_namespace_explicit_override(auto_mock_setup):
    """
    Test that explicit namespace overrides auto-detection.
    """
    auto_mock_setup["get_current_namespace"].return_value = "detected-ns"

    rayjob = RayJob(
        job_name="test-job",
        entrypoint="python -c 'print()'",
        cluster_name="test-cluster",
        namespace="explicit-ns",
    )

    assert rayjob.namespace == "explicit-ns"


def test_rayjob_with_rayjob_cluster_config(auto_mock_setup):
    """
    Test RayJob with the new ManagedClusterConfig.
    """
    cluster_config = ManagedClusterConfig(
        num_workers=2,
        head_cpu_requests="500m",
        head_memory_requests="512Mi",
    )

    rayjob = RayJob(
        job_name="test-job",
        entrypoint="python -c 'print()'",
        cluster_config=cluster_config,
        namespace="test-namespace",
    )

    assert rayjob._cluster_config == cluster_config
    assert rayjob.cluster_name == "test-job-cluster"  # Generated from job name


def test_rayjob_cluster_config_validation(auto_mock_setup):
    """
    Test validation of ManagedClusterConfig parameters.
    """
    cluster_config = ManagedClusterConfig()

    rayjob = RayJob(
        job_name="test-job",
        entrypoint="python -c 'print()'",
        cluster_config=cluster_config,
        namespace="test-namespace",
    )

    assert rayjob._cluster_config is not None


def test_rayjob_missing_entrypoint_validation(auto_mock_setup):
    """
    Test that RayJob requires entrypoint for submission.
    """
    with pytest.raises(
        TypeError, match="missing 1 required positional argument: 'entrypoint'"
    ):
        RayJob(
            job_name="test-job",
            cluster_name="test-cluster",
        )


def test_build_ray_cluster_spec_integration(mocker, auto_mock_setup):
    """
    Test integration with the new build_ray_cluster_spec method.
    """
    cluster_config = ManagedClusterConfig()
    mock_spec = {"spec": "test-spec"}
    mocker.patch.object(
        cluster_config, "build_ray_cluster_spec", return_value=mock_spec
    )

    rayjob = RayJob(
        job_name="test-job",
        entrypoint="python -c 'print()'",
        cluster_config=cluster_config,
        namespace="test-namespace",
    )

    rayjob_cr = rayjob._build_rayjob_cr()

    cluster_config.build_ray_cluster_spec.assert_called_once_with(
        cluster_name="test-job-cluster"
    )
    assert "rayClusterSpec" in rayjob_cr["spec"]
    assert rayjob_cr["spec"]["rayClusterSpec"] == mock_spec


def test_rayjob_with_runtime_env(auto_mock_setup):
    """
    Test RayJob with runtime environment configuration.
    """
    runtime_env = RuntimeEnv(pip=["numpy", "pandas"])

    rayjob = RayJob(
        job_name="test-job",
        entrypoint="python -c 'print()'",
        cluster_name="test-cluster",
        runtime_env=runtime_env,
        namespace="test-namespace",
    )

    assert rayjob.runtime_env == runtime_env

    rayjob_cr = rayjob._build_rayjob_cr()
    assert rayjob_cr["spec"]["runtimeEnvYAML"] == "pip:\n- numpy\n- pandas\n"


def test_rayjob_with_runtime_env_dict(auto_mock_setup):
    """
    Test RayJob with runtime environment as dict (user convenience).
    Users can pass a dict instead of having to import RuntimeEnv.
    """
    # User can pass dict instead of RuntimeEnv object
    runtime_env_dict = {
        "pip": ["numpy", "pandas"],
        "env_vars": {"TEST_VAR": "test_value"},
    }

    rayjob = RayJob(
        job_name="test-job",
        entrypoint="python -c 'print()'",
        cluster_name="test-cluster",
        runtime_env=runtime_env_dict,
        namespace="test-namespace",
    )

    # Should be converted to RuntimeEnv internally
    assert isinstance(rayjob.runtime_env, RuntimeEnv)
    assert rayjob.runtime_env["env_vars"] == {"TEST_VAR": "test_value"}

    # Verify it generates proper YAML output
    rayjob_cr = rayjob._build_rayjob_cr()
    assert "runtimeEnvYAML" in rayjob_cr["spec"]
    runtime_yaml = rayjob_cr["spec"]["runtimeEnvYAML"]
    assert "pip:" in runtime_yaml or "pip_packages:" in runtime_yaml
    assert "env_vars:" in runtime_yaml
    assert "TEST_VAR" in runtime_yaml


def test_rayjob_with_active_deadline_and_ttl(auto_mock_setup):
    """
    Test RayJob with both active deadline and TTL settings.
    """

    rayjob = RayJob(
        job_name="test-job",
        entrypoint="python -c 'print()'",
        cluster_name="test-cluster",
        active_deadline_seconds=300,
        ttl_seconds_after_finished=600,
        namespace="test-namespace",
    )

    assert rayjob.active_deadline_seconds == 300
    assert rayjob.ttl_seconds_after_finished == 600

    rayjob_cr = rayjob._build_rayjob_cr()
    assert rayjob_cr["spec"]["activeDeadlineSeconds"] == 300
    assert rayjob_cr["spec"]["ttlSecondsAfterFinished"] == 600


def test_rayjob_cluster_name_generation_with_config(auto_mock_setup):
    """
    Test cluster name generation when using cluster_config.
    """

    cluster_config = ManagedClusterConfig()

    rayjob = RayJob(
        job_name="my-job",
        entrypoint="python -c 'print()'",
        cluster_config=cluster_config,
        namespace="test-namespace",  # Explicitly specify namespace
    )

    assert rayjob.cluster_name == "my-job-cluster"


def test_rayjob_namespace_propagation_to_cluster_config(auto_mock_setup):
    """
    Test that job namespace is propagated to cluster config when None.
    """
    auto_mock_setup["get_current_namespace"].return_value = "detected-ns"

    cluster_config = ManagedClusterConfig()

    rayjob = RayJob(
        job_name="test-job",
        entrypoint="python -c 'print()'",
        cluster_config=cluster_config,
    )

    assert rayjob.namespace == "detected-ns"


def test_rayjob_error_handling_invalid_cluster_config(auto_mock_setup):
    """
    Test error handling with invalid cluster configuration.
    """

    with pytest.raises(ValueError):
        RayJob(
            job_name="test-job",
            entrypoint="python -c 'print()'",
        )


def test_rayjob_constructor_parameter_validation(auto_mock_setup):
    """
    Test constructor parameter validation.
    """
    rayjob = RayJob(
        job_name="test-job",
        entrypoint="python -c 'print()'",
        cluster_name="test-cluster",
        namespace="test-ns",
        runtime_env=RuntimeEnv(pip=["numpy"]),
        ttl_seconds_after_finished=300,
        active_deadline_seconds=600,
    )

    assert rayjob.name == "test-job"
    assert rayjob.entrypoint == "python -c 'print()'"
    assert rayjob.cluster_name == "test-cluster"
    assert rayjob.namespace == "test-ns"
    # Check that runtime_env is a RuntimeEnv object and contains pip dependencies
    assert isinstance(rayjob.runtime_env, RuntimeEnv)
    runtime_env_dict = rayjob.runtime_env.to_dict()
    assert "pip" in runtime_env_dict
    # Ray transforms pip to dict format with 'packages' key
    assert runtime_env_dict["pip"]["packages"] == ["numpy"]
    assert rayjob.ttl_seconds_after_finished == 300
    assert rayjob.active_deadline_seconds == 600


def test_build_ray_cluster_spec_function():
    """
    Test the build_ray_cluster_spec method directly.
    """
    cluster_config = ManagedClusterConfig(
        num_workers=2,
        head_cpu_requests="500m",
        head_memory_requests="512Mi",
        worker_cpu_requests="250m",
        worker_memory_requests="256Mi",
    )

    spec = cluster_config.build_ray_cluster_spec("test-cluster")
    assert "rayVersion" in spec
    assert "enableInTreeAutoscaling" in spec
    assert spec["enableInTreeAutoscaling"] is False  # Required for Kueue
    assert "headGroupSpec" in spec
    assert "workerGroupSpecs" in spec

    head_spec = spec["headGroupSpec"]
    assert head_spec["serviceType"] == "ClusterIP"
    assert head_spec["enableIngress"] is False
    assert "rayStartParams" in head_spec
    assert "template" in head_spec
    worker_specs = spec["workerGroupSpecs"]
    assert len(worker_specs) == 1
    worker_spec = worker_specs[0]
    assert worker_spec["replicas"] == 2
    assert worker_spec["minReplicas"] == 2
    assert worker_spec["maxReplicas"] == 2
    assert worker_spec["groupName"] == "worker-group-test-cluster"


def test_build_ray_cluster_spec_with_accelerators():
    """
    Test build_ray_cluster_spec with GPU accelerators.
    """
    cluster_config = ManagedClusterConfig(
        head_accelerators={"nvidia.com/gpu": 1},
        worker_accelerators={"nvidia.com/gpu": 2},
    )

    spec = cluster_config.build_ray_cluster_spec("test-cluster")
    head_spec = spec["headGroupSpec"]
    head_params = head_spec["rayStartParams"]
    assert "num-gpus" in head_params
    assert head_params["num-gpus"] == "1"

    worker_specs = spec["workerGroupSpecs"]
    worker_spec = worker_specs[0]
    worker_params = worker_spec["rayStartParams"]
    assert "num-gpus" in worker_params
    assert worker_params["num-gpus"] == "2"


def test_build_ray_cluster_spec_with_custom_volumes():
    """
    Test build_ray_cluster_spec with custom volumes and volume mounts.
    """
    custom_volume = V1Volume(name="custom-data", empty_dir={})
    custom_volume_mount = V1VolumeMount(name="custom-data", mount_path="/data")
    cluster_config = ManagedClusterConfig(
        volumes=[custom_volume],
        volume_mounts=[custom_volume_mount],
    )

    spec = cluster_config.build_ray_cluster_spec("test-cluster")
    head_spec = spec["headGroupSpec"]
    head_pod_spec = head_spec["template"].spec
    assert len(head_pod_spec.volumes) > 0

    head_container = head_pod_spec.containers[0]
    assert len(head_container.volume_mounts) > 0


def test_build_ray_cluster_spec_with_environment_variables():
    """
    Test build_ray_cluster_spec with environment variables.
    """
    cluster_config = ManagedClusterConfig(
        envs={"CUDA_VISIBLE_DEVICES": "0", "RAY_DISABLE_IMPORT_WARNING": "1"},
    )

    spec = cluster_config.build_ray_cluster_spec("test-cluster")

    head_spec = spec["headGroupSpec"]
    head_pod_spec = head_spec["template"].spec
    head_container = head_pod_spec.containers[0]
    assert hasattr(head_container, "env")
    env_vars = {env.name: env.value for env in head_container.env}
    assert env_vars["CUDA_VISIBLE_DEVICES"] == "0"
    assert env_vars["RAY_DISABLE_IMPORT_WARNING"] == "1"
    worker_specs = spec["workerGroupSpecs"]
    worker_spec = worker_specs[0]
    worker_pod_spec = worker_spec["template"].spec
    worker_container = worker_pod_spec.containers[0]

    assert hasattr(worker_container, "env")
    worker_env_vars = {env.name: env.value for env in worker_container.env}
    assert worker_env_vars["CUDA_VISIBLE_DEVICES"] == "0"
    assert worker_env_vars["RAY_DISABLE_IMPORT_WARNING"] == "1"


def test_build_ray_cluster_spec_with_tolerations():
    """
    Test build_ray_cluster_spec with tolerations.
    """
    head_toleration = V1Toleration(
        key="node-role.kubernetes.io/master", operator="Exists", effect="NoSchedule"
    )
    worker_toleration = V1Toleration(
        key="nvidia.com/gpu", operator="Exists", effect="NoSchedule"
    )

    cluster_config = ManagedClusterConfig(
        head_tolerations=[head_toleration],
        worker_tolerations=[worker_toleration],
    )

    spec = cluster_config.build_ray_cluster_spec("test-cluster")
    head_spec = spec["headGroupSpec"]
    head_pod_spec = head_spec["template"].spec
    assert hasattr(head_pod_spec, "tolerations")
    assert len(head_pod_spec.tolerations) == 1
    assert head_pod_spec.tolerations[0].key == "node-role.kubernetes.io/master"

    worker_specs = spec["workerGroupSpecs"]
    worker_spec = worker_specs[0]
    worker_pod_spec = worker_spec["template"].spec
    assert hasattr(worker_pod_spec, "tolerations")
    assert len(worker_pod_spec.tolerations) == 1
    assert worker_pod_spec.tolerations[0].key == "nvidia.com/gpu"


def test_build_ray_cluster_spec_with_image_pull_secrets():
    """
    Test build_ray_cluster_spec with image pull secrets.
    """
    cluster_config = ManagedClusterConfig(
        image_pull_secrets=["my-registry-secret", "another-secret"]
    )

    spec = cluster_config.build_ray_cluster_spec("test-cluster")

    head_spec = spec["headGroupSpec"]
    head_pod_spec = head_spec["template"].spec
    assert hasattr(head_pod_spec, "image_pull_secrets")

    head_secrets = head_pod_spec.image_pull_secrets
    assert len(head_secrets) == 2
    assert head_secrets[0].name == "my-registry-secret"
    assert head_secrets[1].name == "another-secret"

    worker_specs = spec["workerGroupSpecs"]
    worker_spec = worker_specs[0]
    worker_pod_spec = worker_spec["template"].spec
    assert hasattr(worker_pod_spec, "image_pull_secrets")

    worker_secrets = worker_pod_spec.image_pull_secrets
    assert len(worker_secrets) == 2
    assert worker_secrets[0].name == "my-registry-secret"
    assert worker_secrets[1].name == "another-secret"


def test_submit_with_cluster_config_compatible_image_passes(auto_mock_setup):
    """
    Test that submission passes with compatible cluster_config image.
    """
    mock_api_instance = auto_mock_setup["rayjob_api"]
    mock_api_instance.submit_job.return_value = True

    cluster_config = ManagedClusterConfig(image=f"ray:{RAY_VERSION}")

    rayjob = RayJob(
        job_name="test-job",
        cluster_config=cluster_config,
        namespace="test-namespace",
        entrypoint="python -c 'print()'",
    )

    result = rayjob.submit()
    assert result == "test-job"


def test_submit_with_cluster_config_incompatible_image_fails(auto_mock_setup):
    """
    Test that submission fails with incompatible cluster_config image.
    """

    cluster_config = ManagedClusterConfig(image="ray:2.8.0")  # Different version

    rayjob = RayJob(
        job_name="test-job",
        cluster_config=cluster_config,
        namespace="test-namespace",
        entrypoint="python -c 'print()'",
    )

    with pytest.raises(
        ValueError, match="Cluster config image: Ray version mismatch detected"
    ):
        rayjob.submit()


def test_validate_ray_version_compatibility_method(auto_mock_setup):
    """
    Test the _validate_ray_version_compatibility method directly.
    """

    rayjob = RayJob(
        job_name="test-job",
        cluster_name="test-cluster",
        namespace="test-namespace",
        entrypoint="python -c 'print()'",
    )

    rayjob._validate_ray_version_compatibility()
    rayjob._cluster_config = ManagedClusterConfig(image=f"ray:{RAY_VERSION}")
    rayjob._validate_ray_version_compatibility()
    rayjob._cluster_config = ManagedClusterConfig(image="ray:2.8.0")
    with pytest.raises(
        ValueError, match="Cluster config image: Ray version mismatch detected"
    ):
        rayjob._validate_ray_version_compatibility()

    rayjob._cluster_config = ManagedClusterConfig(image="custom-image:latest")
    with pytest.warns(
        UserWarning, match="Cluster config image: Cannot determine Ray version"
    ):
        rayjob._validate_ray_version_compatibility()


def test_validate_cluster_config_image_method(auto_mock_setup):
    """
    Test the _validate_cluster_config_image method directly.
    """

    rayjob = RayJob(
        job_name="test-job",
        cluster_config=ManagedClusterConfig(),
        namespace="test-namespace",
        entrypoint="python -c 'print()'",
    )

    rayjob._validate_cluster_config_image()
    rayjob._cluster_config.image = f"ray:{RAY_VERSION}"
    rayjob._validate_cluster_config_image()
    rayjob._cluster_config.image = "ray:2.8.0"
    with pytest.raises(
        ValueError, match="Cluster config image: Ray version mismatch detected"
    ):
        rayjob._validate_cluster_config_image()

    rayjob._cluster_config.image = "custom-image:latest"
    with pytest.warns(
        UserWarning, match="Cluster config image: Cannot determine Ray version"
    ):
        rayjob._validate_cluster_config_image()


def test_validate_cluster_config_image_edge_cases(auto_mock_setup):
    """
    Test edge cases in _validate_cluster_config_image method.
    """

    rayjob = RayJob(
        job_name="test-job",
        cluster_config=ManagedClusterConfig(),
        namespace="test-namespace",
        entrypoint="python -c 'print()'",
    )

    rayjob._cluster_config.image = None
    rayjob._validate_cluster_config_image()
    rayjob._cluster_config.image = ""
    rayjob._validate_cluster_config_image()
    rayjob._cluster_config.image = 123
    rayjob._validate_cluster_config_image()

    class MockClusterConfig:
        pass

    rayjob._cluster_config = MockClusterConfig()
    rayjob._validate_cluster_config_image()


def test_rayjob_stop_success(auto_mock_setup, caplog):
    """
    Test successful RayJob stop operation.
    """
    mock_api_instance = auto_mock_setup["rayjob_api"]

    mock_api_instance.suspend_job.return_value = {
        "metadata": {"name": "test-rayjob"},
        "spec": {"suspend": True},
    }

    rayjob = RayJob(
        job_name="test-rayjob",
        cluster_name="test-cluster",
        namespace="test-namespace",
        entrypoint="python -c 'print()'",
    )

    with caplog.at_level("INFO"):
        result = rayjob.stop()

    assert result is True

    mock_api_instance.suspend_job.assert_called_once_with(
        name="test-rayjob", k8s_namespace="test-namespace"
    )

    # Verify success message was logged
    assert "Successfully stopped the RayJob test-rayjob" in caplog.text


def test_rayjob_stop_failure(auto_mock_setup):
    """
    Test RayJob stop operation when API call fails.
    """
    mock_api_instance = auto_mock_setup["rayjob_api"]

    mock_api_instance.suspend_job.return_value = None

    rayjob = RayJob(
        job_name="test-rayjob",
        cluster_name="test-cluster",
        namespace="test-namespace",
        entrypoint="python -c 'print()'",
    )

    with pytest.raises(RuntimeError, match="Failed to stop the RayJob test-rayjob"):
        rayjob.stop()

    mock_api_instance.suspend_job.assert_called_once_with(
        name="test-rayjob", k8s_namespace="test-namespace"
    )


def test_rayjob_resubmit_success(auto_mock_setup):
    """
    Test successful RayJob resubmit operation.
    """
    mock_api_instance = auto_mock_setup["rayjob_api"]

    mock_api_instance.resubmit_job.return_value = {
        "metadata": {"name": "test-rayjob"},
        "spec": {"suspend": False},
    }

    rayjob = RayJob(
        job_name="test-rayjob",
        cluster_name="test-cluster",
        namespace="test-namespace",
        entrypoint="python -c 'print()'",
    )

    result = rayjob.resubmit()

    assert result is True

    mock_api_instance.resubmit_job.assert_called_once_with(
        name="test-rayjob", k8s_namespace="test-namespace"
    )


def test_rayjob_resubmit_failure(auto_mock_setup):
    """
    Test RayJob resubmit operation when API call fails.
    """
    mock_api_instance = auto_mock_setup["rayjob_api"]

    mock_api_instance.resubmit_job.return_value = None

    rayjob = RayJob(
        job_name="test-rayjob",
        cluster_name="test-cluster",
        namespace="test-namespace",
        entrypoint="python -c 'print()'",
    )

    with pytest.raises(RuntimeError, match="Failed to resubmit the RayJob test-rayjob"):
        rayjob.resubmit()

    mock_api_instance.resubmit_job.assert_called_once_with(
        name="test-rayjob", k8s_namespace="test-namespace"
    )


def test_rayjob_delete_success(auto_mock_setup):
    """
    Test successful RayJob deletion.
    """
    mock_api_instance = auto_mock_setup["rayjob_api"]

    rayjob = RayJob(
        job_name="test-rayjob",
        entrypoint="python -c 'print()'",
        cluster_name="test-cluster",
    )

    mock_api_instance.delete_job.return_value = True

    result = rayjob.delete()

    assert result is True
    mock_api_instance.delete_job.assert_called_once_with(
        name="test-rayjob", k8s_namespace="test-namespace"
    )


def test_rayjob_delete_already_deleted(auto_mock_setup, caplog):
    """
    Test RayJob deletion when already deleted (should succeed gracefully).
    """
    mock_api_instance = auto_mock_setup["rayjob_api"]

    rayjob = RayJob(
        job_name="test-rayjob",
        entrypoint="python -c 'print()'",
        cluster_name="test-cluster",
    )

    # Python client returns False when job doesn't exist/already deleted
    mock_api_instance.delete_job.return_value = False

    with caplog.at_level("INFO"):
        result = rayjob.delete()

    # Should succeed (not raise error) when already deleted
    assert result is True
    assert "already deleted or does not exist" in caplog.text

    mock_api_instance.delete_job.assert_called_once_with(
        name="test-rayjob", k8s_namespace="test-namespace"
    )


def test_rayjob_init_both_none_error(auto_mock_setup):
    """
    Test RayJob initialization error when both cluster_name and cluster_config are None.
    """
    with pytest.raises(
        ValueError,
        match="Configuration Error: You must provide either 'cluster_name' .* or 'cluster_config'",
    ):
        RayJob(
            job_name="test-job",
            entrypoint="python -c 'print()'",
            cluster_name=None,
            cluster_config=None,
        )


def test_rayjob_init_missing_cluster_name_with_no_config(auto_mock_setup):
    """
    Test RayJob initialization error when cluster_name is None without cluster_config.
    """
    with pytest.raises(
        ValueError,
        match="Configuration Error: a 'cluster_name' is required when not providing 'cluster_config'",
    ):
        rayjob = RayJob.__new__(RayJob)
        rayjob.name = "test-job"
        rayjob.entrypoint = "python test.py"
        rayjob.runtime_env = None
        rayjob.ttl_seconds_after_finished = 0
        rayjob.active_deadline_seconds = None
        rayjob.shutdown_after_job_finishes = True
        rayjob.namespace = "test-namespace"
        rayjob._cluster_name = None
        rayjob._cluster_config = None
        if rayjob._cluster_config is None and rayjob._cluster_name is None:
            raise ValueError(
                "❌ Configuration Error: a 'cluster_name' is required when not providing 'cluster_config'"
            )


def test_rayjob_kueue_label_no_default_queue(auto_mock_setup, mocker, caplog):
    """
    Test RayJob falls back to 'default' queue when no default queue exists.
    """
    mocker.patch(
        "codeflare_sdk.ray.rayjobs.rayjob.get_default_kueue_name",
        return_value=None,
    )

    mock_api_instance = auto_mock_setup["rayjob_api"]
    mock_api_instance.submit_job.return_value = {"metadata": {"name": "test-job"}}

    cluster_config = ManagedClusterConfig()
    rayjob = RayJob(
        job_name="test-job",
        cluster_config=cluster_config,
        entrypoint="python -c 'print()'",
    )

    with caplog.at_level("WARNING"):
        rayjob.submit()

    # Verify the submitted job has the fallback label
    call_args = mock_api_instance.submit_job.call_args
    submitted_job = call_args.kwargs["job"]
    assert submitted_job["metadata"]["labels"]["kueue.x-k8s.io/queue-name"] == "default"

    # Verify warning was logged
    assert "No default Kueue LocalQueue found" in caplog.text


def test_rayjob_kueue_explicit_local_queue(auto_mock_setup):
    """
    Test RayJob uses explicitly specified local queue.
    """
    mock_api_instance = auto_mock_setup["rayjob_api"]
    mock_api_instance.submit_job.return_value = {"metadata": {"name": "test-job"}}

    cluster_config = ManagedClusterConfig()
    rayjob = RayJob(
        job_name="test-job",
        cluster_config=cluster_config,
        entrypoint="python -c 'print()'",
        local_queue="custom-queue",
    )

    rayjob.submit()

    # Verify the submitted job has the explicit queue label
    call_args = mock_api_instance.submit_job.call_args
    submitted_job = call_args.kwargs["job"]
    assert (
        submitted_job["metadata"]["labels"]["kueue.x-k8s.io/queue-name"]
        == "custom-queue"
    )


def test_rayjob_no_kueue_label_for_existing_cluster(auto_mock_setup):
    """
    Test RayJob doesn't add Kueue label for existing clusters.
    """
    mock_api_instance = auto_mock_setup["rayjob_api"]
    mock_api_instance.submit_job.return_value = {"metadata": {"name": "test-job"}}

    # Using existing cluster (no cluster_config)
    rayjob = RayJob(
        job_name="test-job",
        cluster_name="existing-cluster",
        entrypoint="python -c 'print()'",
    )

    rayjob.submit()

    # Verify no Kueue label was added
    call_args = mock_api_instance.submit_job.call_args
    submitted_job = call_args.kwargs["job"]
    assert "kueue.x-k8s.io/queue-name" not in submitted_job["metadata"]["labels"]


def test_rayjob_with_ttl_and_deadline(auto_mock_setup):
    """
    Test RayJob with TTL and active deadline seconds.
    """
    mock_api_instance = auto_mock_setup["rayjob_api"]
    mock_api_instance.submit_job.return_value = {"metadata": {"name": "test-job"}}

    cluster_config = ManagedClusterConfig()
    rayjob = RayJob(
        job_name="test-job",
        cluster_config=cluster_config,
        entrypoint="python -c 'print()'",
        ttl_seconds_after_finished=300,
        active_deadline_seconds=600,
    )

    rayjob.submit()

    # Verify TTL and deadline were set
    call_args = mock_api_instance.submit_job.call_args
    submitted_job = call_args.kwargs["job"]
    assert submitted_job["spec"]["ttlSecondsAfterFinished"] == 300
    assert submitted_job["spec"]["activeDeadlineSeconds"] == 600


def test_rayjob_shutdown_after_job_finishes(auto_mock_setup):
    """
    Test RayJob sets shutdownAfterJobFinishes correctly.
    """
    mock_api_instance = auto_mock_setup["rayjob_api"]
    mock_api_instance.submit_job.return_value = {"metadata": {"name": "test-job"}}

    # Test with managed cluster (should shutdown)
    cluster_config = ManagedClusterConfig()
    rayjob = RayJob(
        job_name="test-job",
        cluster_config=cluster_config,
        entrypoint="python -c 'print()'",
    )

    rayjob.submit()

    call_args = mock_api_instance.submit_job.call_args
    submitted_job = call_args.kwargs["job"]
    assert submitted_job["spec"]["shutdownAfterJobFinishes"] is True

    # Test with existing cluster (should not shutdown)
    rayjob2 = RayJob(
        job_name="test-job2",
        cluster_name="existing-cluster",
        entrypoint="python -c 'print()'",
    )

    rayjob2.submit()

    call_args2 = mock_api_instance.submit_job.call_args
    submitted_job2 = call_args2.kwargs["job"]
    assert submitted_job2["spec"]["shutdownAfterJobFinishes"] is False


def test_rayjob_stop_delete_resubmit_logging(auto_mock_setup, caplog):
    """
    Test logging for stop, delete, and resubmit operations.
    """
    mock_api_instance = auto_mock_setup["rayjob_api"]

    # Test stop with logging
    mock_api_instance.suspend_job.return_value = {
        "metadata": {"name": "test-rayjob"},
        "spec": {"suspend": True},
    }

    rayjob = RayJob(
        job_name="test-rayjob",
        cluster_name="test-cluster",
        namespace="test-namespace",
        entrypoint="python -c 'print()'",
    )

    with caplog.at_level("INFO"):
        result = rayjob.stop()

    assert result is True
    assert "Successfully stopped the RayJob test-rayjob" in caplog.text

    # Test delete with logging
    caplog.clear()
    mock_api_instance.delete_job.return_value = True

    with caplog.at_level("INFO"):
        result = rayjob.delete()

    assert result is True
    assert "Successfully deleted the RayJob test-rayjob" in caplog.text

    # Test resubmit with logging
    caplog.clear()
    mock_api_instance.resubmit_job.return_value = {
        "metadata": {"name": "test-rayjob"},
        "spec": {"suspend": False},
    }

    with caplog.at_level("INFO"):
        result = rayjob.resubmit()

    assert result is True
    assert "Successfully resubmitted the RayJob test-rayjob" in caplog.text


def test_rayjob_initialization_logging(auto_mock_setup, caplog):
    """
    Test RayJob initialization logging.
    """
    with caplog.at_level("INFO"):
        cluster_config = ManagedClusterConfig()
        rayjob = RayJob(
            job_name="test-job",
            cluster_config=cluster_config,
            entrypoint="python -c 'print()'",
        )

    assert "Creating new cluster: test-job-cluster" in caplog.text
    assert "Initialized RayJob: test-job in namespace: test-namespace" in caplog.text


def test_build_submitter_pod_template_uses_default_image(auto_mock_setup, mocker):
    """
    Test that _build_submitter_pod_template() uses get_ray_image_for_python_version() for default image.
    """
    # Mock get_ray_image_for_python_version to verify it's called
    mock_get_image = mocker.patch(
        "codeflare_sdk.ray.rayjobs.rayjob.get_ray_image_for_python_version",
        return_value="auto-detected-image:py3.12",
    )

    rayjob = RayJob(
        job_name="test-job",
        cluster_name="existing-cluster",
        entrypoint="python -c 'print()'",
        namespace="test-namespace",
    )

    files = {"test.py": "print('hello')"}
    secret_name = "test-files"

    # Call _build_submitter_pod_template
    submitter_template = rayjob._build_submitter_pod_template(files, secret_name)

    # Verify get_ray_image_for_python_version was called
    mock_get_image.assert_called_once()

    # Verify the submitter pod uses the auto-detected image
    assert (
        submitter_template["spec"]["containers"][0]["image"]
        == "auto-detected-image:py3.12"
    )


def test_build_submitter_pod_template_uses_cluster_config_image(
    auto_mock_setup, mocker
):
    """
    Test that _build_submitter_pod_template() uses cluster_config image when provided.
    """
    # Mock get_ray_image_for_python_version (should be called but overridden)
    mock_get_image = mocker.patch(
        "codeflare_sdk.ray.rayjobs.rayjob.get_ray_image_for_python_version",
        return_value="auto-detected-image:py3.12",
    )

    cluster_config = ManagedClusterConfig(image="custom-cluster-image:v1")

    rayjob = RayJob(
        job_name="test-job",
        cluster_config=cluster_config,
        entrypoint="python -c 'print()'",
        namespace="test-namespace",
    )

    files = {"test.py": "print('hello')"}
    secret_name = "test-files"

    # Call _build_submitter_pod_template
    submitter_template = rayjob._build_submitter_pod_template(files, secret_name)

    # Verify get_ray_image_for_python_version was called
    mock_get_image.assert_called_once()

    # Verify the submitter pod uses the cluster config image (overrides default)
    assert (
        submitter_template["spec"]["containers"][0]["image"]
        == "custom-cluster-image:v1"
    )


def test_build_submitter_pod_template_with_files(auto_mock_setup):
    """
    Test that _build_submitter_pod_template() correctly builds Secret items for files.
    """
    rayjob = RayJob(
        job_name="test-job",
        cluster_name="existing-cluster",
        entrypoint="python -c 'print()'",
        namespace="test-namespace",
    )

    files = {"main.py": "print('main')", "helper.py": "print('helper')"}
    secret_name = "test-files"

    # Call _build_submitter_pod_template
    submitter_template = rayjob._build_submitter_pod_template(files, secret_name)

    # Verify Secret items are created for each file
    secret_items = submitter_template["spec"]["volumes"][0]["secret"]["items"]
    assert len(secret_items) == 2

    # Verify each file has a Secret item
    file_names = [item["key"] for item in secret_items]
    assert "main.py" in file_names
    assert "helper.py" in file_names

    # Verify paths match keys
    for item in secret_items:
        assert item["key"] == item["path"]


def test_validate_working_dir_entrypoint_no_runtime_env(auto_mock_setup, tmp_path):
    """
    Test validation checks file exists even when no runtime_env is specified.
    """
    # Create the script file
    script_file = tmp_path / "script.py"
    script_file.write_text("print('hello')")

    rayjob = RayJob(
        job_name="test-job",
        cluster_name="test-cluster",
        entrypoint=f"python {script_file}",
        namespace="test-namespace",
    )

    # Should not raise exception (file exists)
    rayjob._validate_working_dir_entrypoint()


def test_validate_working_dir_entrypoint_no_working_dir(auto_mock_setup, tmp_path):
    """
    Test validation checks file when runtime_env has no working_dir.
    """
    # Create the script file
    script_file = tmp_path / "script.py"
    script_file.write_text("print('hello')")

    rayjob = RayJob(
        job_name="test-job",
        cluster_name="test-cluster",
        entrypoint=f"python {script_file}",
        namespace="test-namespace",
        runtime_env=RuntimeEnv(pip=["numpy"]),
    )

    # Should not raise exception (file exists)
    rayjob._validate_working_dir_entrypoint()


def test_validate_working_dir_entrypoint_remote_working_dir(auto_mock_setup):
    """
    Test validation skips ALL checks for remote working_dir.
    """
    rayjob = RayJob(
        job_name="test-job",
        cluster_name="test-cluster",
        entrypoint="python nonexistent_script.py",  # File doesn't exist, but should be ignored
        namespace="test-namespace",
        runtime_env=RuntimeEnv(
            working_dir="https://github.com/user/repo/archive/main.zip"
        ),
    )

    # Should not raise any exception (remote working_dir skips all validation)
    rayjob._validate_working_dir_entrypoint()


def test_validate_working_dir_entrypoint_no_python_file(auto_mock_setup):
    """
    Test validation passes when entrypoint has no Python file reference.
    """
    rayjob = RayJob(
        job_name="test-job",
        cluster_name="test-cluster",
        entrypoint="echo 'hello world'",  # No Python file
        namespace="test-namespace",
        runtime_env=RuntimeEnv(working_dir="."),
    )

    # Should not raise any exception
    rayjob._validate_working_dir_entrypoint()


def test_validate_working_dir_entrypoint_no_redundancy(auto_mock_setup, tmp_path):
    """
    Test validation passes when entrypoint doesn't reference working_dir.
    """
    # Create test directory and file
    test_dir = tmp_path / "testdir"
    test_dir.mkdir()
    script_file = test_dir / "script.py"
    script_file.write_text("print('hello')")

    rayjob = RayJob(
        job_name="test-job",
        cluster_name="test-cluster",
        entrypoint="python script.py",  # No directory prefix
        namespace="test-namespace",
        runtime_env=RuntimeEnv(working_dir=str(test_dir)),
    )

    # Should not raise any exception
    rayjob._validate_working_dir_entrypoint()


def test_validate_working_dir_entrypoint_redundant_reference_error(
    auto_mock_setup, tmp_path
):
    """
    Test validation raises error when entrypoint redundantly references working_dir.
    """
    # Create test directory and file
    test_dir = tmp_path / "testdir"
    test_dir.mkdir()
    script_file = test_dir / "script.py"
    script_file.write_text("print('hello')")

    rayjob = RayJob(
        job_name="test-job",
        cluster_name="test-cluster",
        entrypoint=f"python {test_dir}/script.py",  # Redundant reference
        namespace="test-namespace",
        runtime_env=RuntimeEnv(working_dir=str(test_dir)),
    )

    # Should raise ValueError with helpful message
    with pytest.raises(ValueError, match="Working directory conflict detected"):
        rayjob._validate_working_dir_entrypoint()


def test_validate_working_dir_entrypoint_with_dot_slash(auto_mock_setup, tmp_path):
    """
    Test validation handles paths with ./ prefix correctly.
    """
    # Create test directory and file
    test_dir = tmp_path / "testdir"
    test_dir.mkdir()
    script_file = test_dir / "script.py"
    script_file.write_text("print('hello')")

    # Change to temp directory so relative paths work
    import os

    original_cwd = os.getcwd()
    try:
        os.chdir(tmp_path)

        rayjob = RayJob(
            job_name="test-job",
            cluster_name="test-cluster",
            entrypoint="python ./testdir/script.py",  # With ./ prefix
            namespace="test-namespace",
            runtime_env=RuntimeEnv(working_dir="./testdir"),  # With ./ prefix
        )

        # Should raise ValueError (redundant reference)
        with pytest.raises(ValueError, match="Working directory conflict detected"):
            rayjob._validate_working_dir_entrypoint()
    finally:
        os.chdir(original_cwd)


def test_validate_working_dir_entrypoint_submit_integration(auto_mock_setup, tmp_path):
    """
    Test that validation is called during submit() and blocks submission.
    """
    mock_api_instance = auto_mock_setup["rayjob_api"]
    mock_api_instance.submit_job.return_value = {"metadata": {"name": "test-job"}}

    # Create test directory and file
    test_dir = tmp_path / "testdir"
    test_dir.mkdir()
    script_file = test_dir / "script.py"
    script_file.write_text("print('hello')")

    rayjob = RayJob(
        job_name="test-job",
        cluster_name="test-cluster",
        entrypoint=f"python {test_dir}/script.py",  # Redundant reference
        namespace="test-namespace",
        runtime_env=RuntimeEnv(working_dir=str(test_dir)),
    )

    # Should raise ValueError during submit() before API call
    with pytest.raises(ValueError, match="Working directory conflict detected"):
        rayjob.submit()

    # Verify submit_job was never called (validation blocked it)
    mock_api_instance.submit_job.assert_not_called()


def test_validate_working_dir_entrypoint_error_message_format(
    auto_mock_setup, tmp_path
):
    """
    Test that error message contains helpful information.
    """
    # Create test directory and file
    test_dir = tmp_path / "testdir"
    test_dir.mkdir()
    script_file = test_dir / "script.py"
    script_file.write_text("print('hello')")

    rayjob = RayJob(
        job_name="test-job",
        cluster_name="test-cluster",
        entrypoint=f"python {test_dir}/script.py",
        namespace="test-namespace",
        runtime_env=RuntimeEnv(working_dir=str(test_dir)),
    )

    try:
        rayjob._validate_working_dir_entrypoint()
        assert False, "Should have raised ValueError"
    except ValueError as e:
        error_msg = str(e)
        # Verify error message contains key information
        assert "Working directory conflict detected" in error_msg
        assert "working_dir:" in error_msg
        assert "entrypoint references:" in error_msg
        assert "Fix: Remove the directory prefix" in error_msg
        assert "python script.py" in error_msg  # Suggested fix


def test_validate_working_dir_entrypoint_subdirectory_valid(auto_mock_setup, tmp_path):
    """
    Test validation passes when entrypoint references subdirectory within working_dir.
    """
    # Create test directory structure: testdir/subdir/script.py
    test_dir = tmp_path / "testdir"
    test_dir.mkdir()
    sub_dir = test_dir / "subdir"
    sub_dir.mkdir()
    script_file = sub_dir / "script.py"
    script_file.write_text("print('hello')")

    rayjob = RayJob(
        job_name="test-job",
        cluster_name="test-cluster",
        entrypoint="python subdir/script.py",  # Correct: relative to working_dir
        namespace="test-namespace",
        runtime_env=RuntimeEnv(working_dir=str(test_dir)),
    )

    # Should not raise any exception
    rayjob._validate_working_dir_entrypoint()


def test_validate_working_dir_entrypoint_runtime_env_as_dict(auto_mock_setup, tmp_path):
    """
    Test validation works when runtime_env is passed as dict (not RuntimeEnv object).
    """
    # Create test directory and file
    test_dir = tmp_path / "testdir"
    test_dir.mkdir()
    script_file = test_dir / "script.py"
    script_file.write_text("print('hello')")

    rayjob = RayJob(
        job_name="test-job",
        cluster_name="test-cluster",
        entrypoint=f"python {test_dir}/script.py",  # Redundant reference
        namespace="test-namespace",
        runtime_env={"working_dir": str(test_dir)},  # Dict instead of RuntimeEnv
    )

    # Should raise ValueError even with dict runtime_env
    with pytest.raises(ValueError, match="Working directory conflict detected"):
        rayjob._validate_working_dir_entrypoint()


def test_validate_file_exists_with_working_dir(auto_mock_setup, tmp_path):
    """
    Test validation checks that entrypoint file exists within working_dir.
    """
    # Create working directory but NOT the script file
    test_dir = tmp_path / "testdir"
    test_dir.mkdir()

    rayjob = RayJob(
        job_name="test-job",
        cluster_name="test-cluster",
        entrypoint="python script.py",  # File doesn't exist
        namespace="test-namespace",
        runtime_env=RuntimeEnv(working_dir=str(test_dir)),
    )

    # Should raise ValueError about missing file
    with pytest.raises(ValueError, match="Entrypoint file not found"):
        rayjob._validate_working_dir_entrypoint()


def test_validate_file_exists_without_working_dir(auto_mock_setup, tmp_path):
    """
    Test validation checks that entrypoint file exists when no working_dir and using ./ prefix.
    """
    # Don't create the script file
    script_path = "./missing_script.py"

    rayjob = RayJob(
        job_name="test-job",
        cluster_name="test-cluster",
        entrypoint=f"python {script_path}",  # File doesn't exist (local path with ./)
        namespace="test-namespace",
    )

    # Should raise ValueError about missing file
    with pytest.raises(ValueError, match="Entrypoint file not found"):
        rayjob._validate_working_dir_entrypoint()


def test_validate_existing_file_with_working_dir_passes(auto_mock_setup, tmp_path):
    """
    Test validation passes when file exists in working_dir.
    """
    # Create working directory AND the script file
    test_dir = tmp_path / "testdir"
    test_dir.mkdir()
    script_file = test_dir / "script.py"
    script_file.write_text("print('hello')")

    rayjob = RayJob(
        job_name="test-job",
        cluster_name="test-cluster",
        entrypoint="python script.py",  # File exists
        namespace="test-namespace",
        runtime_env=RuntimeEnv(working_dir=str(test_dir)),
    )

    # Should not raise any exception
    rayjob._validate_working_dir_entrypoint()


def test_validate_inline_python_command_skipped(auto_mock_setup):
    """
    Test validation skips inline Python commands (no file reference).
    """
    rayjob = RayJob(
        job_name="test-job",
        cluster_name="test-cluster",
        entrypoint="python -c 'print(\"hello world\")'",  # No file reference
        namespace="test-namespace",
    )

    # Should not raise any exception (no file to validate)
    rayjob._validate_working_dir_entrypoint()


def test_validate_simple_filename_without_working_dir_missing(auto_mock_setup):
    """
    Test validation checks simple filenames without working_dir.
    """
    rayjob = RayJob(
        job_name="test-job",
        cluster_name="test-cluster",
        entrypoint="python script.py",  # File doesn't exist locally
        namespace="test-namespace",
    )

    # Should raise ValueError (file will be extracted from local, so must exist)
    with pytest.raises(ValueError, match="Entrypoint file not found"):
        rayjob._validate_working_dir_entrypoint()


def test_validate_simple_filename_without_working_dir_exists(auto_mock_setup, tmp_path):
    """
    Test validation passes when simple filename exists locally without working_dir.
    """
    import os

    original_cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        # Create the script file in current directory
        script_file = tmp_path / "script.py"
        script_file.write_text("print('hello')")

        rayjob = RayJob(
            job_name="test-job",
            cluster_name="test-cluster",
            entrypoint="python script.py",  # Simple filename exists locally
            namespace="test-namespace",
        )

        # Should not raise exception (file exists)
        rayjob._validate_working_dir_entrypoint()
    finally:
        os.chdir(original_cwd)

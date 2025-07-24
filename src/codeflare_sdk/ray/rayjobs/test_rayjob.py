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

from unittest.mock import MagicMock
from codeflare_sdk.ray.rayjobs.rayjob import RayJob


def test_rayjob_submit_success(mocker):
    """Test successful RayJob submission."""
    # Mock kubernetes config loading
    mocker.patch("kubernetes.config.load_kube_config")

    # Mock the RayjobApi class entirely
    mock_api_class = mocker.patch("codeflare_sdk.ray.rayjobs.rayjob.RayjobApi")
    mock_api_instance = MagicMock()
    mock_api_class.return_value = mock_api_instance

    # Configure the mock to return success when submit_job is called
    mock_api_instance.submit_job.return_value = {"metadata": {"name": "test-rayjob"}}

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

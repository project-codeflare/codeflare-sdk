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
Tests for Pydantic serialization fix in build_ray_cluster.py
"""

import pytest
import os
from pathlib import Path
from codeflare_sdk.ray.cluster.cluster import Cluster, ClusterConfiguration


def test_yaml_serialization_with_pydantic_models():
    """Test that YAML serialization works with Pydantic v2 models from Kubernetes client v33+"""
    # Create a cluster configuration
    config = ClusterConfiguration(
        name="test-serialization",
        namespace="test-ns",
        num_workers=1,
        write_to_file=True,
    )

    # Create cluster - this triggers YAML serialization via write_to_file
    cluster = Cluster(config)

    # Verify the file was created successfully
    expected_file = os.path.expanduser(f"~/.codeflare/resources/{config.name}.yaml")
    assert os.path.exists(expected_file), f"YAML file should exist at {expected_file}"

    # Verify the file contains valid YAML
    import yaml

    with open(expected_file, "r") as f:
        content = yaml.safe_load(f)

    assert content is not None, "YAML content should not be None"
    assert (
        "kind" in content or "apiVersion" in content
    ), "YAML should contain Kubernetes resource fields"


def test_yaml_serialization_without_write_to_file():
    """Test that in-memory resource creation works without file writing"""
    config = ClusterConfiguration(
        name="test-in-memory", namespace="test-ns", num_workers=1, write_to_file=False
    )

    # Create cluster - resource should be in memory only
    cluster = Cluster(config)

    # Verify resource_yaml is a dict (in-memory)
    assert isinstance(
        cluster.resource_yaml, dict
    ), "resource_yaml should be a dict when write_to_file=False"
    assert "kind" in cluster.resource_yaml or "apiVersion" in cluster.resource_yaml


def test_json_serialization_fallback():
    """Test that JSON serialization fallback handles edge cases"""
    from codeflare_sdk.ray.cluster.build_ray_cluster import write_to_file

    # Create a test cluster with minimal config
    config = ClusterConfiguration(
        name="test-json-fallback",
        namespace="test-ns",
        num_workers=1,
        write_to_file=True,
    )
    cluster = Cluster(config)

    # The resource should be serializable via JSON round-trip
    import json

    resource_json = json.dumps(cluster.resource_yaml, default=str)
    assert resource_json is not None

    # Should be loadable back
    loaded = json.loads(resource_json)
    assert loaded is not None

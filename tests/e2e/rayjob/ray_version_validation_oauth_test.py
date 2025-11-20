import pytest
import sys
import os

# Add the parent directory to the path to import support
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from support import *

from codeflare_sdk import (
    RayJob,
    ManagedClusterConfig,
)


@pytest.mark.smoke
class TestRayJobRayVersionValidationOauth:
    def setup_method(self):
        initialize_kubernetes_client(self)

    def teardown_method(self):
        delete_namespace(self)
        delete_kueue_resources(self)

    def _create_basic_managed_cluster_config(
        self, ray_image: str
    ) -> ManagedClusterConfig:
        """Helper method to create basic managed cluster configuration."""
        return ManagedClusterConfig(
            head_cpu_requests="500m",
            head_cpu_limits="500m",
            head_memory_requests=1,
            head_memory_limits=2,
            num_workers=1,
            worker_cpu_requests="500m",
            worker_cpu_limits="500m",
            worker_memory_requests=1,
            worker_memory_limits=2,
            image=ray_image,
        )

    def test_rayjob_lifecycled_cluster_incompatible_ray_version_oauth(self):
        """Test that RayJob creation fails when cluster config specifies incompatible Ray version."""
        self.setup_method()
        create_namespace(self)
        create_kueue_resources(self)
        self.run_rayjob_lifecycled_cluster_incompatible_version()

    def run_rayjob_lifecycled_cluster_incompatible_version(self):
        """Test Ray version validation with cluster lifecycling using incompatible image."""

        job_name = "incompatible-lifecycle-rayjob"

        # Create cluster configuration with incompatible Ray version (2.46.1 instead of expected 2.47.1)
        incompatible_ray_image = "quay.io/modh/ray:2.46.1-py311-cu121"

        print(
            f"Creating RayJob with incompatible Ray image in cluster config: {incompatible_ray_image}"
        )

        cluster_config = self._create_basic_managed_cluster_config(
            incompatible_ray_image
        )

        # Create RayJob with incompatible cluster config - this should fail during submission
        rayjob = RayJob(
            job_name=job_name,
            cluster_config=cluster_config,
            namespace=self.namespace,
            entrypoint="python -c 'print(\"This should not run due to version mismatch\")'",
            ttl_seconds_after_finished=30,
        )

        print(
            f"Attempting to submit RayJob '{job_name}' with incompatible Ray version..."
        )

        # This should fail during submission due to Ray version validation
        with pytest.raises(ValueError, match="Ray version mismatch detected"):
            rayjob.submit()

        print(
            "✅ Ray version validation correctly prevented RayJob submission with incompatible cluster config!"
        )

    def test_rayjob_lifecycled_cluster_unknown_ray_version_oauth(self):
        """Test that RayJob creation succeeds with warning when Ray version cannot be determined."""
        self.setup_method()
        create_namespace(self)
        create_kueue_resources(self)
        self.run_rayjob_lifecycled_cluster_unknown_version()

    def run_rayjob_lifecycled_cluster_unknown_version(self):
        """Test Ray version validation with unknown image (should warn but not fail)."""

        job_name = "unknown-version-rayjob"

        # Use an image where Ray version cannot be determined (SHA digest)
        unknown_ray_image = "quay.io/modh/ray@sha256:6d076aeb38ab3c34a6a2ef0f58dc667089aa15826fa08a73273c629333e12f1e"

        print(
            f"Creating RayJob with image where Ray version cannot be determined: {unknown_ray_image}"
        )

        cluster_config = self._create_basic_managed_cluster_config(unknown_ray_image)

        # Create RayJob with unknown version image - this should succeed with warning
        rayjob = RayJob(
            job_name=job_name,
            cluster_config=cluster_config,
            namespace=self.namespace,
            entrypoint="python -c 'print(\"Testing unknown Ray version scenario\")'",
            ttl_seconds_after_finished=30,
        )

        print(f"Attempting to submit RayJob '{job_name}' with unknown Ray version...")

        # This should succeed but with a warning
        with pytest.warns(UserWarning, match="Cannot determine Ray version"):
            submission_result = rayjob.submit()

        assert (
            submission_result == job_name
        ), f"Job submission failed, expected {job_name}, got {submission_result}"

        print("✅ RayJob submission succeeded with warning for unknown Ray version!")
        print(
            f"Note: RayJob '{job_name}' was submitted successfully but may need manual cleanup."
        )

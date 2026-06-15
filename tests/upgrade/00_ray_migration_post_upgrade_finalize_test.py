# Copyright 2024 IBM, Red Hat
#
# First post_upgrade step: migrate the qualification RayCluster after RHOAI OLM upgrade.

import pytest

from tests.upgrade.constants import CLUSTER_NAME, NAMESPACE
from tests.upgrade.migration_support import (
    assert_raycluster_migrated_if_present,
    assert_raycluster_ready_after_post_upgrade,
    run_migration_post_upgrade,
)


@pytest.mark.post_upgrade
class TestRayMigrationPostUpgradeFinalize:
    """
    First test in the post_upgrade suite (see conftest collection ordering).

    Invokes ray_cluster_migration.py post-upgrade for the seeded mnist cluster.
    Skips clusters already migrated (3.x→3.x). Required before job/UI post tests
    when upgrading from 2.x with legacy TLS/OAuth on the RayCluster CR.
    """

    def test_ray_migration_post_upgrade_finalize(self):
        result = run_migration_post_upgrade(
            namespace=NAMESPACE,
            cluster_name=CLUSTER_NAME,
        )

        assert result.returncode == 0, (
            f"Migration post-upgrade exited with code {result.returncode}; "
            "migration steps failed."
        )

        assert_raycluster_migrated_if_present()
        assert_raycluster_ready_after_post_upgrade()

        print(
            "\n=== Ray migration post-upgrade finalize complete. "
            "Proceed with post_upgrade job and UI tests. ===\n"
        )

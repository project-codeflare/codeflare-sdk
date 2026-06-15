# Copyright 2024 IBM, Red Hat
#
# Final pre-upgrade step: run rhoai-upgrade-helpers migration script and assert
# the cluster is ready for RHOAI OLM upgrade (codeflare Removed is mandatory).

import pytest

from tests.upgrade.constants import CLUSTER_NAME, NAMESPACE
from tests.upgrade.migration_support import (
    assert_codeflare_removed,
    assert_raycluster_pre_upgrade_artifacts_if_present,
    run_migration_pre_upgrade,
)


@pytest.mark.pre_upgrade
class TestRayMigrationPreUpgradeFinalize:
    """
    Last test in the pre_upgrade suite.

    Invokes ray_cluster_migration.py pre-upgrade (no duplicated logic).
    Must run even when seed/UI tests fail — use session finalizer in conftest as backup.
    After this test, do not use CodeFlare on 2.25 for re-seed without reverting DSC.
    """

    def test_ray_migration_pre_upgrade_finalize(self):
        result = run_migration_pre_upgrade(
            namespace=NAMESPACE,
            cluster_name=CLUSTER_NAME,
        )

        assert result.returncode == 0, (
            f"Migration pre-upgrade exited with code {result.returncode}; "
            "required pre-flight checks or backup steps failed."
        )

        assert_codeflare_removed()
        assert_raycluster_pre_upgrade_artifacts_if_present()

        print(
            "\n=== Ray migration pre-upgrade finalize complete. "
            "Safe to proceed with RHOAI OLM upgrade (no further pre work). ===\n"
        )

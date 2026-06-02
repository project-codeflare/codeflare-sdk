# Copyright 2024 IBM, Red Hat
#
# Conftest for upgrade tests - UI fixtures and post_upgrade test ordering.

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ui.conftest import (
    dashboard_url,
    login_to_dashboard,
    selenium_driver,
    test_credentials,
)

__all__ = [
    "selenium_driver",
    "dashboard_url",
    "test_credentials",
    "login_to_dashboard",
]


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Capture test results for teardown methods (cleanup_on_failure fixtures)."""
    outcome = yield
    rep = outcome.get_result()
    setattr(item, f"rep_{rep.when}", rep)


def pytest_collection_modifyitems(config, items):
    """
    Run Ray migration post-upgrade before other post_upgrade tests (job submit, UI).
    """
    pre_and_other = []
    post_migration = []
    post_other = []

    for item in items:
        if not item.get_closest_marker("post_upgrade"):
            pre_and_other.append(item)
            continue
        if "TestRayMigrationPostUpgradeFinalize" in item.nodeid:
            post_migration.append(item)
        else:
            post_other.append(item)

    if post_migration:
        items[:] = pre_and_other + post_migration + post_other

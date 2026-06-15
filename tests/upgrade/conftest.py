import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ui.conftest import (
    selenium_driver,
    dashboard_url,
    test_credentials,
    login_to_dashboard,
)

from tests.upgrade.migration_support import (
    assert_codeflare_removed,
    migration_pre_upgrade_was_invoked,
    run_migration_pre_upgrade,
)


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    setattr(item, f"rep_{rep.when}", rep)


def _session_includes_pre_upgrade(request) -> bool:
    """True if any collected test in this session uses the pre_upgrade marker."""
    session = request.session
    for item in session.items:
        if item.get_closest_marker("pre_upgrade"):
            return True
    return False


@pytest.fixture(scope="session", autouse=True)
def ensure_migration_pre_upgrade_finalize(request):
    """
    Backup: run migration pre-upgrade if the finalize test did not run
    (e.g. collection order edge case). Idempotent with the finalize test.
    """
    yield

    if not _session_includes_pre_upgrade(request):
        return

    if migration_pre_upgrade_was_invoked():
        return

    print(
        "\n=== Session finalizer: migration pre-upgrade was not invoked by tests; "
        "running now (codeflare Removed is required before OLM upgrade). ===\n"
    )
    result = run_migration_pre_upgrade()
    if result.returncode != 0:
        pytest.fail(
            f"Migration pre-upgrade exited with code {result.returncode} "
            "in session finalizer; required pre-flight checks or backup steps failed."
        )
    assert_codeflare_removed()

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
Conftest for upgrade tests - imports UI fixtures for dashboard tests
"""

import sys
import os
import pytest

# Add parent test directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Import all fixtures from ui/conftest.py
from ui.conftest import (
    selenium_driver,
    dashboard_url,
    test_credentials,
    login_to_dashboard,
)

__all__ = ["selenium_driver", "dashboard_url", "test_credentials", "login_to_dashboard"]


# Hook to capture test results for teardown methods
@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """
    Hook to capture test results and make them available to teardown methods.
    This allows teardown_method to check if the test failed.
    """
    outcome = yield
    rep = outcome.get_result()

    # Store the result in the item so teardown can access it
    setattr(item, f"rep_{rep.when}", rep)

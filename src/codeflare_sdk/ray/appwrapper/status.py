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
The status sub-module defines Enums containing information for
AppWrapper states, as well as dataclasses to store information for AppWrappers.
"""

from dataclasses import dataclass
from enum import Enum


class AppWrapperStatus(Enum):
    """
    Defines the possible reportable phases of an AppWrapper.
    """

    SUSPENDED = "suspended"
    RESUMING = "resuming"
    RUNNING = "running"
    RESETTING = "resetting"
    SUSPENDING = "suspending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TERMINATING = "terminating"


@dataclass
class AppWrapper:
    """
    For storing information about an AppWrapper.
    """

    name: str
    status: AppWrapperStatus

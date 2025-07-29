# Copyright 2025 IBM, Red Hat
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
The status sub-module defines Enums containing information for Ray job
deployment states and CodeFlare job states, as well as
dataclasses to store information for Ray jobs.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class RayJobDeploymentStatus(Enum):
    """
    Defines the possible deployment states of a Ray job (from the KubeRay RayJob API).
    """

    COMPLETE = "Complete"
    RUNNING = "Running"
    FAILED = "Failed"
    SUSPENDED = "Suspended"
    UNKNOWN = "Unknown"


class CodeflareRayJobStatus(Enum):
    """
    Defines the possible reportable states of a CodeFlare Ray job.
    """

    COMPLETE = 1
    RUNNING = 2
    FAILED = 3
    SUSPENDED = 4
    UNKNOWN = 5


@dataclass
class RayJobInfo:
    """
    For storing information about a Ray job.
    """

    name: str
    job_id: str
    status: RayJobDeploymentStatus
    namespace: str
    cluster_name: str
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    failed_attempts: int = 0
    succeeded_attempts: int = 0

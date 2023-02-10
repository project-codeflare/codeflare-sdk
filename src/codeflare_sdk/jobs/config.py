# Copyright 2022 IBM, Red Hat
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
The config sub-module contains the definition of the JobConfiguration dataclass,
which is used to specify requirements and other details when creating a
Job object.
"""

from dataclasses import dataclass, field
from typing import Optional, Dict

@dataclass
class JobConfiguration:
    """
    This dataclass is used to specify resource requirements and other details, and
    is passed in as an argument when creating a Job object.
    """

    name: Optional[str] = None
    script: Optional[str] = None
    m: Optional[str] = None
    h: Optional[str] = None  # custom resource types
    env: Optional[Dict[str, str]] = None
    working_dir: Optional[str] = None
    requirements: Optional[str] = None

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
The jobs sub-module contains the definitions for the Job objects, which represent
the methods by which a user can submit a job to a cluster, check the jobs status and 
access the jobs logs. 
"""

import abc
from .config import JobConfiguration


class Job(metaclass=abc.ABCMeta):
    """
    An abstract class that defines the necessary methods for authenticating to a remote environment.
    Specifically, this class defines the need for a `submit()`, `status` and a `logs` function.
    """

    def submit(self):
        """
        Method for submitting a job.
        """
        pass

    def status(self):
        """
        Method for retrieving the job's current status.
        """
        pass

    def logs(self):
        """
        Method for retrieving the job's logs.
        """


class TorchXJob(Job):
    def __init__(self, config: JobConfiguration):
        """
        Create the TorchXJob object by passing in a JobConfiguration
        (defined in the config sub-module).
        """
        self.config = config

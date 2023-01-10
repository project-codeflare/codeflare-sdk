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
These were the old tests used during initial demo building, and they will soon be fully deprecated.
"""

from codeflare_sdk.cluster.cluster import (
    list_all_clusters,
    list_all_queued,
    _app_wrapper_status,
)
from codeflare_sdk.cluster.cluster import Cluster, ClusterConfiguration

import time

# FIXME - These tests currently assume OC logged in, and not self-contained unit/funcitonal tests


def test_cluster_up():
    cluster = Cluster(ClusterConfiguration(name="raycluster-autoscaler"))
    cluster.up()
    time.sleep(15)


def test_list_clusters():
    clusters = list_all_clusters()


def test_cluster_status():
    cluster = Cluster(ClusterConfiguration(name="raycluster-autoscaler"))
    cluster.status()


def test_app_wrapper_status():
    print(_app_wrapper_status("raycluster-autoscaler"))


def test_cluster_down():
    cluster = Cluster(ClusterConfiguration(name="raycluster-autoscaler"))
    cluster.down()


def test_no_resources_found():
    from codeflare_sdk.utils import pretty_print

    pretty_print.print_no_resources_found()


def test_list_app_wrappers():
    app_wrappers = list_all_queued()

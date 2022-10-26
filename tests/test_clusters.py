from codeflare_sdk.cluster.cluster import list_all_clusters, _app_wrapper_status
from codeflare_sdk.cluster.cluster import Cluster, ClusterConfiguration

import time

def test_cluster_up():
     cluster = Cluster(ClusterConfiguration(name='raycluster-autoscaler'))
     cluster.up()     
     time.sleep(15)

def test_list_clusters():
    clusters = list_all_clusters()

def test_cluster_status():
    cluster = Cluster(ClusterConfiguration(name='raycluster-autoscaler'))
    cluster.status()

def test_app_wrapper_status():
    print(_app_wrapper_status('raycluster-autoscaler'))

def test_cluster_down():
    cluster = Cluster(ClusterConfiguration(name='raycluster-autoscaler'))
    cluster.down()


def test_no_resources_found():
    from codeflare_sdk.utils import pretty_print
    pretty_print.print_no_resources_found()

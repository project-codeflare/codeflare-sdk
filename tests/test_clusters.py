from codeflare_sdk.cluster.cluster import _get_ray_clusters
from codeflare_sdk.utils.pretty_print import print_clusters
def test_list_clusters():
    clusters = _get_ray_clusters()
    print_clusters(clusters)
    

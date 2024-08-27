# Ray Cluster Configuration

To create Ray Clusters using the CodeFlare SDK a cluster configuration needs to be created first.<br>
This is what a typical cluster configuration would look like; Note: The values for CPU and Memory are at the minimum requirements for creating the Ray Cluster.

```python
from codeflare_sdk import Cluster, ClusterConfiguration

cluster = Cluster(ClusterConfiguration(
    name='ray-example', # Mandatory Field
    namespace='default', # Default None
    head_cpus=1, # Default 2
    head_memory=1, # Default 8
    head_extended_resource_requests={'nvidia.com/gpu':0}, # Default 0
    worker_extended_resource_requests={'nvidia.com/gpu':0}, # Default 0
    num_workers=1, # Default 1
    worker_cpu_requests=1, # Default 1
    worker_cpu_limits=1, # Default 1
    worker_memory_requests=2, # Default 2
    worker_memory_limits=2, # Default 2
    # image="", # Default quay.io/rhoai/ray:2.23.0-py39-cu121
    labels={"exampleLabel": "example", "secondLabel": "example"},
))
```
Note: 'quay.io/rhoai/ray:2.23.0-py39-cu121' is the default community image used by the CodeFlare SDK for creating a RayCluster resource. If you have your own Ray image which suits your purposes, specify it in image field to override the default image.

The `labels={"exampleLabel": "example"}` parameter can be used to apply additional labels to the RayCluster resource.

For detailed instructions on the various methods that can be called for interacting with Ray Clusters see [Ray Cluster Interaction](./ray_cluster_interaction.md).

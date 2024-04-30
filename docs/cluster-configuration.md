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
    head_gpus=0, # Default 0
    num_workers=1, # Default 1
    min_cpus=1, # Default 1
    max_cpus=1, # Default 1
    min_memory=2, # Default 2
    max_memory=2, # Default 2
    num_gpus=0, # Default 0
    mcad=True, # Default True
    image="quay.io/project-codeflare/ray:latest-py39-cu118", # Mandatory Field
    machine_types=["m5.xlarge", "g4dn.xlarge"],
    labels={"exampleLabel": "example", "secondLabel": "example"},
))
```

Upon creating a cluster configuration with `mcad=True` an appwrapper will be created featuring the Ray Cluster and any Routes, Ingresses or Secrets that are needed to be created along side it.<br>
From there a user can call `cluster.up()` and `cluster.down()` to create and remove the appwrapper thus creating and removing the Ray Cluster.

In cases where `mcad=False` a yaml file will be created with the individual Ray Cluster, Route/Ingress and Secret included.<br>
The Ray Cluster and service will be created by KubeRay directly and the other components will be individually created.

The `labels={"exampleLabel": "example"}` parameter can be used to apply additional labels to the RayCluster resource.

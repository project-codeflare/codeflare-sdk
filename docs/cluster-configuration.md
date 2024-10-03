# Ray Cluster Configuration

To create Ray Clusters using the CodeFlare SDK a cluster configuration needs to be created first.<br>
This is what a typical cluster configuration would look like; Note: The values for CPU and Memory are at the minimum requirements for creating the Ray Cluster.

```python
from codeflare_sdk import Cluster, ClusterConfiguration

cluster = Cluster(ClusterConfiguration(
    name='ray-example', # Mandatory Field
    namespace='default', # Default None
    head_cpu_requests=1, # Default 2
    head_cpu_limits=1, # Default 2
    head_memory_requests=1, # Default 8
    head_memory_limits=1, # Default 8
    head_extended_resource_requests={'nvidia.com/gpu':0}, # Default 0
    worker_extended_resource_requests={'nvidia.com/gpu':0}, # Default 0
    num_workers=1, # Default 1
    worker_cpu_requests=1, # Default 1
    worker_cpu_limits=1, # Default 1
    worker_memory_requests=2, # Default 2
    worker_memory_limits=2, # Default 2
    # image="", # Optional Field
    machine_types=["m5.xlarge", "g4dn.xlarge"],
    labels={"exampleLabel": "example", "secondLabel": "example"},
))
```
Note: 'quay.io/modh/ray:2.35.0-py39-cu121' is the default image used by the CodeFlare SDK for creating a RayCluster resource. If you have your own Ray image which suits your purposes, specify it in image field to override the default image. If you are using ROCm compatible GPUs you can use 'quay.io/modh/ray:2.35.0-py39-rocm61'. You can also find documentation on building a custom image [here](https://github.com/opendatahub-io/distributed-workloads/tree/main/images/runtime/examples).

The `labels={"exampleLabel": "example"}` parameter can be used to apply additional labels to the RayCluster resource.

After creating their `cluster`, a user can call `cluster.up()` and `cluster.down()` to respectively create or remove the Ray Cluster.

## Parameters of the `ClusterConfiguration`
Below is a table explaining each of the `ClusterConfiguration` parameters and their default values.
| Name | Type | Description | Default |
| :--------- | :-------- | :-------- | :-------- |
| `name` | `str` | The name of the Ray Cluster/AppWrapper | Required - No default |
| `namespace` | `Optional[str]` | The namespace of the Ray Cluster/AppWrapper | `None` |
| `head_cpu_requests` | `Union[int, str]` | CPU resource requests for the Head Node | `2` |
| `head_cpu_limits` | `Union[int, str]` | CPU resource limits for the Head Node | `2` |
| `head_memory_requests` | `Union[int, str]` | Memory resource requests for the Head Node | `8` |
| `head_memory_limits` | `Union[int, str]` | Memory limits for the Head Node | `8` |
| `head_extended_resource_requests` | `Dict[str, Union[str, int]]` | Extended resource requests for the Head Node see example above | `{}` |
| `worker_cpu_requests` | `Union[int, str]` | CPU resource requests for the Worker Node | `1` |
| `worker_cpu_limits` | `Union[int, str]` | CPU resource limits for the Worker Node | `1` |
| `num_workers` | `int` | Number of Worker Nodes for the Ray Cluster | `1` |
| `worker_memory_requests` | `Union[int, str]` | Memory resource requests for the Worker Node | `8` |
| `worker_memory_limits` | `Union[int, str]` | Memory resource limits for the Worker Node | `8` |
| `appwrapper` | `bool` | A boolean that wraps the Ray Cluster in an AppWrapper when set to True | `False` |
| `envs` | `Dict[str, str]` | A dictionary of environment variables to set for the Ray Cluster | `{}` |
| `image` | `str` | A paramater for specifying the Ray Image | `""` |
| `image_pull_secrets` | `List[str]` | A Parameter for providing a list of Image Pull Secrets | `[]` |
| `write_to_file` | `bool` | A boolean for writing the Ray Cluster as a Yaml file if set to True | `False` |
| `verify_tls` | `bool` | A boolean indicating whether to verify TLS when connecting to the cluster | `True` |
| `labels` | `Dict[str, str]` | A dictionary of labels to apply to the cluster | `{}` |
| `worker_extended_resource_requests` | `Dict[str, Union[str, int]]` | Extended resource requests for the Worker Node see example above | `{}` |
| `extended_resource_mapping` | `Dict[str, str]` | A dictionary of custom resource mappings to map extended resource requests to RayCluster resource names | `{}` |
| `overwrite_default_resource_mapping` | `bool` | A boolean indicating whether to overwrite the default resource mapping | `False` |
| `local_queue` | `Optional[str]` | A parameter for specifying the Local Queue label for the Ray Cluster | `None` |





## Deprecating Parameters
The following parameters of the `ClusterConfiguration` are being deprecated.
| Deprecated Parameter | Replaced By |
| :--------- | :-------- |
| `head_cpus` | `head_cpu_requests`, `head_cpu_limits` |
| `head_memory` | `head_memory_requests`, `head_memory_limits` |
| `min_cpus` | `worker_cpu_requests` |
| `max_cpus` | `worker_cpu_limits` |
| `min_memory` | `worker_memory_requests` |
| `max_memory` | `worker_memory_limits` |
| `head_gpus` | `head_extended_resource_requests` |
| `num_gpus` | `worker_extended_resource_requests` |

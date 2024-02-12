# Ray Cluster Configuration

To create Ray Clusters using the CodeFlare SDK a cluster configuration needs to be created first.<br>
This is what a typical cluster configuration would look like; Note: The values for CPU and Memory are at the minimum requirements for creating the Ray Cluster.

```
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
    instascale=False, # Default False
    machine_types=["m5.xlarge", "g4dn.xlarge"],
    ingress_domain="example.com" # Default None, Mandatory for Vanilla Kubernetes Clusters - ingress_domain is ignored on OpenShift Clusters as a route is created.
    local_interactive=False, # Default False
))
```
Note: On OpenShift, the `ingress_domain` is only required when `local_interactive` is enabled. - This may change soon.

Upon creating a cluster configuration with `mcad=True` an appwrapper will be created featuring the Ray Cluster and any Routes, Ingresses or Secrets that are needed to be created along side it.<br>
From there a user can call `cluster.up()` and `cluster.down()` to create and remove the appwrapper thus creating and removing the Ray Cluster.

In cases where `mcad=False` a yaml file will be created with the individual Ray Cluster, Route/Ingress and Secret included.<br>
The Ray Cluster and service will be created by KubeRay directly and the other components will be individually created.

## Ray Cluster Configuration in a Vanilla Kubernetes environment (Non-OpenShift)
To create a Ray Cluster using the CodeFlare SDK in a Vanilla Kubernetes environment an `ingress_domain` must be passed in the Cluster Configuration.
This is used for the creation of the Ray Dashboard and Client ingresses.

`ingress_options` can be passed to create a custom Ray Dashboard ingress, `ingress_domain` is still a required variable for the Client route/ingress.
An example of `ingress_options` would look like this.

```
ingress_options = {
  "ingresses": [
    {
      "ingressName": "<ingress_name>",
      "port": <port_number>,
      "pathType": "<path_type>",
      "path": "<path>",
      "host":"<host>",
      "annotations": {
        "foo": "bar",
        "foo": "bar",
      }
    }
  ]
}
```

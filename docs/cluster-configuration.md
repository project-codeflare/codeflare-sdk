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
    num_gpus=0, # Default 0
    num_workers=1, # Default 1
    min_cpus=1, # Default 1
    max_cpus=1, # Default 1
    min_memory=2, # Default 2
    max_memory=2, # Default 2
    num_gpus=0, # Default 0
    image="quay.io/project-codeflare/ray:latest-py39-cu118", # Mandatory Field
    machine_types=["m5.xlarge", "g4dn.xlarge"],
    labels={"exampleLabel": "example", "secondLabel": "example"},
    volumes=[], # See Custom Volumes/Volume Mounts
    volume_mounts=[], # See Custom Volumes/Volume Mounts
))
```

The `labels={"exampleLabel": "example"}` parameter can be used to apply additional labels to the RayCluster resource.

After creating their`cluster`, a user can call `cluster.up()` and `cluster.down()` to respectively create or remove the Ray Cluster.

## Custom Volumes/Volume Mounts
To add custom Volumes and Volume Mounts to your Ray Cluster you need to create two lists `volumes` and `volume_mounts`.
The lists consist of `V1Volume` and `V1VolumeMount` objects respectively.<br>
Populating these parameters will create Volumes and Volume Mounts for the head and each worker pod.

Below is an example of how a user would create these lists using the Python Kubernetes Library.

```python
from kubernetes.client import V1Volume, V1VolumeMount, V1EmptyDirVolumeSource, V1ConfigMapVolumeSource, V1KeyToPath, V1SecretVolumeSource
# In this example we are using the Config Map, EmptyDir and Secret Volume types
volume_mounts_list = [
    V1VolumeMount(
        mount_path="/home/ray/test1",
        name = "test"
    ),
    V1VolumeMount(
        mount_path = "/home/ray/test2",
        name = "test2",
    ),
    V1VolumeMount(
        mount_path = "/home/ray/test3",
        name = "test3",
    )
]

volumes_list = [
    V1Volume(
        name="test",
        empty_dir=V1EmptyDirVolumeSource(size_limit="2Gi"),
    ),
    V1Volume(
        name="test2",
        config_map=V1ConfigMapVolumeSource(
            name="test-config-map",
            items=[V1KeyToPath(key="test", path="data.txt")]
        )
    ),
    V1Volume(
        name="test3",
        secret=V1SecretVolumeSource(
            secret_name="test-secret"
        )
    )
]
```

For more information on creating Volumes and Volume Mounts with Python check out the Python Kubernetes docs ([Volumes](https://github.com/kubernetes-client/python/blob/master/kubernetes/docs/V1Volume.md), [Volume Mounts](https://github.com/kubernetes-client/python/blob/master/kubernetes/docs/V1VolumeMount.md)).
You can also find further information on Volumes and Volume Mounts by visiting the Kubernetes [documentation](https://kubernetes.io/docs/concepts/storage/volumes/).

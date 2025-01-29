Ray Cluster Configuration
=========================

To create Ray Clusters using the CodeFlare SDK a cluster configuration
needs to be created first. This is what a typical cluster configuration
would look like; Note: The values for CPU and Memory are at the minimum
requirements for creating the Ray Cluster.

.. code:: python

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
       labels={"exampleLabel": "example", "secondLabel": "example"},
       annotations={"key1":"value1", "key2":"value2"},
       volumes=[], # See Custom Volumes/Volume Mounts
       volume_mounts=[], # See Custom Volumes/Volume Mounts
   ))

.. note::
  The default images used by the CodeFlare SDK for creating
  a RayCluster resource depend on the installed Python version:

  - For Python 3.9: `quay.io/modh/ray:2.35.0-py39-cu121`
  - For Python 3.11: `quay.io/modh/ray:2.35.0-py311-cu121`

  If you prefer to use a custom Ray image that better suits your
  needs, you can specify it in the image field to override the default.
  If you are using ROCm compatible GPUs you
  can use `quay.io/modh/ray:2.35.0-py39-rocm61`. You can also find
  documentation on building a custom image
  `here <https://github.com/opendatahub-io/distributed-workloads/tree/main/images/runtime/examples>`__.

The ``labels={"exampleLabel": "example"}`` parameter can be used to
apply additional labels to the RayCluster resource.

After creating their ``cluster``, a user can call ``cluster.up()`` and
``cluster.down()`` to respectively create or remove the Ray Cluster.

Custom Volumes/Volume Mounts
----------------------------
| To add custom Volumes and Volume Mounts to your Ray Cluster you need to create two lists ``volumes`` and ``volume_mounts``. The lists consist of ``V1Volume`` and ``V1VolumeMount`` objects respectively.
| Populating these parameters will create Volumes and Volume Mounts for the head and each worker pod.

.. code:: python

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

| For more information on creating Volumes and Volume Mounts with Python check out the Python Kubernetes docs (`Volumes <https://github.com/kubernetes-client/python/blob/master/kubernetes/docs/V1Volume.md>`__, `Volume Mounts <https://github.com/kubernetes-client/python/blob/master/kubernetes/docs/V1VolumeMount.md>`__).
| You can also find further information on Volumes and Volume Mounts by visiting the Kubernetes `documentation <https://kubernetes.io/docs/concepts/storage/volumes/>`__.

Deprecating Parameters
----------------------

The following parameters of the ``ClusterConfiguration`` are being
deprecated.

.. list-table::
   :header-rows: 1
   :widths: auto

   * - Deprecated Parameter
     - Replaced By
   * - ``head_cpus``
     - ``head_cpu_requests``, ``head_cpu_limits``
   * - ``head_memory``
     - ``head_memory_requests``, ``head_memory_limits``
   * - ``min_cpus``
     - ``worker_cpu_requests``
   * - ``max_cpus``
     - ``worker_cpu_limits``
   * - ``min_memory``
     - ``worker_memory_requests``
   * - ``max_memory``
     - ``worker_memory_limits``
   * - ``head_gpus``
     - ``head_extended_resource_requests``
   * - ``num_gpus``
     - ``worker_extended_resource_requests``

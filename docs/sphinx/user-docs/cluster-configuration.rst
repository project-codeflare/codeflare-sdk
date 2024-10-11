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
       machine_types=["m5.xlarge", "g4dn.xlarge"],
       labels={"exampleLabel": "example", "secondLabel": "example"},
   ))

Note: ‘quay.io/modh/ray:2.35.0-py39-cu121’ is the default image used by
the CodeFlare SDK for creating a RayCluster resource. If you have your
own Ray image which suits your purposes, specify it in image field to
override the default image. If you are using ROCm compatible GPUs you
can use ‘quay.io/modh/ray:2.35.0-py39-rocm61’. You can also find
documentation on building a custom image
`here <https://github.com/opendatahub-io/distributed-workloads/tree/main/images/runtime/examples>`__.

The ``labels={"exampleLabel": "example"}`` parameter can be used to
apply additional labels to the RayCluster resource.

After creating their ``cluster``, a user can call ``cluster.up()`` and
``cluster.down()`` to respectively create or remove the Ray Cluster.

Deprecating Parameters
----------------------

The following parameters of the ``ClusterConfiguration`` are being deprecated.

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

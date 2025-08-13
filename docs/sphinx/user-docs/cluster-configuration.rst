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

  - For Python 3.11: `quay.io/modh/ray:2.47.1-py311-cu121`

  If you prefer to use a custom Ray image that better suits your
  needs, you can specify it in the image field to override the default.
  If you are using ROCm compatible GPUs you
  can use `quay.io/modh/ray:2.47.1-py311-rocm62`. You can also find
  documentation on building a custom image
  `here <https://github.com/opendatahub-io/distributed-workloads/tree/main/images/runtime/examples>`__.

Ray Version Compatibility
-------------------------

 The CodeFlare SDK requires that the Ray version in your runtime image matches the Ray version used by the SDK itself.When you specify a custom runtime image, the SDK will automatically validate that the Ray version in the image matches this requirement.

Version Validation Behavior
~~~~~~~~~~~~~~~~~~~~~~~~~~~

The SDK performs the following validation when creating a cluster:

1. **Compatible versions**: If the runtime image contains Ray 2.47.1, the cluster will be created successfully.

2. **Version mismatch**: If the runtime image contains a different Ray version, cluster creation will fail with a detailed error message explaining the mismatch.

3. **Unknown versions**: If the SDK cannot determine the Ray version from the image name (e.g., SHA-based tags), a warning will be issued but cluster creation will continue.

Examples
~~~~~~~~

**Compatible image (recommended)**:

.. code:: python

   # This will work - versions match
   cluster = Cluster(ClusterConfiguration(
       name='ray-example',
       image='quay.io/modh/ray:2.47.1-py311-cu121'
   ))

**Incompatible image (will fail)**:

.. code:: python

   # This will fail with a version mismatch error
   cluster = Cluster(ClusterConfiguration(
       name='ray-example',
       image='ray:2.46.0'  # Different version!
   ))

**SHA-based image (will warn)**:

.. code:: python

   # This will issue a warning but continue
   cluster = Cluster(ClusterConfiguration(
       name='ray-example',
       image='quay.io/modh/ray@sha256:abc123...'
   ))

Best Practices
~~~~~~~~~~~~~~

- **Use versioned tags**: Always use semantic version tags (e.g., `ray:2.47.1`) rather than `latest` or SHA-based tags for better version detection.

- **Test compatibility**: When building custom images, test them with the CodeFlare SDK to ensure compatibility.

- **Check SDK version**: You can check the Ray version used by the SDK with:

.. code:: python

   from codeflare_sdk.common.utils.constants import RAY_VERSION
   print(f"CodeFlare SDK uses Ray version: {RAY_VERSION}")

**Why is version matching important?**

Ray version mismatches can cause:

- Incompatible API calls between the SDK and Ray cluster
- Unexpected behavior in job submission and cluster management
- Potential data corruption or job failures
- Difficult-to-debug runtime errors


Ray Usage Statistics
-------------------

By default, Ray usage statistics collection is **disabled** in Ray Clusters created with the Codeflare SDK. This prevents statistics from being captured and sent externally. If you want to enable usage statistics collection, you can simply set the ``enable_usage_stats`` parameter to ``True`` in your cluster configuration:

.. code:: python

   from codeflare_sdk import Cluster, ClusterConfiguration

   cluster = Cluster(ClusterConfiguration(
       name='ray-example',
       namespace='default',
       enable_usage_stats=True
   ))

This will automatically set the ``RAY_USAGE_STATS_ENABLED`` environment variable to ``1`` for all Ray pods in the cluster. If you do not set this parameter, usage statistics will remain disabled (``RAY_USAGE_STATS_ENABLED=0``).

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

GCS Fault Tolerance
------------------
By default, the state of the Ray cluster is transient to the head Pod. Whatever triggers a restart of the head Pod results in losing that state, including Ray Cluster history. To make Ray cluster state persistent you can enable Global Control Service (GCS) fault tolerance with an external Redis storage.

To configure GCS fault tolerance you need to set the following parameters:

.. list-table::
   :header-rows: 1
   :widths: auto

   * - Parameter
     - Description
   * - ``enable_gcs_ft``
     - Boolean to enable GCS fault tolerance
   * - ``redis_address``
     - Address of the external Redis service, ex: "redis:6379"
   * - ``redis_password_secret``
     - Dictionary with 'name' and 'key' fields specifying the Kubernetes secret for Redis password
   * - ``external_storage_namespace``
     - Custom storage namespace for GCS fault tolerance (by default, KubeRay sets it to the RayCluster's UID)

Example configuration:

.. code:: python

   from codeflare_sdk import Cluster, ClusterConfiguration

   cluster = Cluster(ClusterConfiguration(
       name='ray-cluster-with-persistence',
       num_workers=2,
       enable_gcs_ft=True,
       redis_address="redis:6379",
       redis_password_secret={
           "name": "redis-password-secret",
           "key": "password"
       },
       # external_storage_namespace="my-custom-namespace" # Optional: Custom namespace for GCS data in Redis
   ))

.. note::
   You need to have a Redis instance deployed in your Kubernetes cluster before using this feature.

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

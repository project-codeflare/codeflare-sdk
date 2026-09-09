Submitting RayJobs
==================

The CodeFlare SDK provides a ``RayJob`` interface for submitting and
managing Ray jobs via the KubeRay operator (RayJob custom resource).
You can either create a short-lived Ray cluster for the job (managed by
the operator and cleaned up after the job finishes) or run the job on an
existing Ray cluster.

Import the following to use RayJob:

::

   from codeflare_sdk import RayJob, ManagedClusterConfig

Submitting a job with a new cluster (ManagedClusterConfig)
---------------------------------------------------------

When you provide ``cluster_config``, the KubeRay operator creates a
Ray cluster for the job and tears it down after the job completes. You
do not need to manage the cluster lifecycle yourself.

| Required: ``job_name`` (str), ``entrypoint`` (str), ``cluster_config`` (ManagedClusterConfig).
| Optional: ``namespace``, ``runtime_env``, ``ttl_seconds_after_finished``, ``active_deadline_seconds``, ``local_queue``, ``priority_class``.

.. code:: python

   from codeflare_sdk import RayJob, ManagedClusterConfig

   cluster_config = ManagedClusterConfig(
       head_memory_requests=6,
       head_memory_limits=8,
       num_workers=2,
       worker_cpu_requests=1,
       worker_cpu_limits=1,
       worker_memory_requests=4,
       worker_memory_limits=6,
       head_accelerators={"nvidia.com/gpu": 0},
       worker_accelerators={"nvidia.com/gpu": 0},
   )

   job = RayJob(
       job_name="my-rayjob",
       entrypoint="python -c 'print(\"Hello from RayJob!\")'",
       cluster_config=cluster_config,
       namespace="default",
   )
   job.submit()

Submitting a job to an existing cluster
--------------------------------------

When you provide ``cluster_name``, the job runs on an existing Ray
cluster. The cluster is not shut down when the job finishes.

| Required: ``job_name`` (str), ``entrypoint`` (str), ``cluster_name`` (str).
| Optional: ``namespace``, ``runtime_env``, ``active_deadline_seconds``, ``local_queue``, ``priority_class``.
| Note: ``ttl_seconds_after_finished`` cannot be set when using an existing cluster.

.. code:: python

   from codeflare_sdk import RayJob

   job = RayJob(
       job_name="my-rayjob",
       entrypoint="python my_script.py",
       cluster_name="my-existing-cluster",
       namespace="default",
   )
   job.submit()

RayJob methods
--------------

| ``job.submit()`` — Submits the RayJob to the KubeRay operator. Returns the job name on success. When using ``cluster_config``, the operator creates the cluster and runs the job; when using ``cluster_name``, the job is submitted to the specified cluster.
| ``job.status(print_to_console=True)`` — Returns the job status (e.g. RUNNING, COMPLETE, FAILED) and a ready flag; optionally prints a formatted status to the console.
| ``job.stop()`` — Suspends the Ray job.
| ``job.resubmit()`` — Resubmits the Ray job.
| ``job.delete()`` — Deletes the RayJob custom resource (and the cluster if it was created by this RayJob).

Runtime environment
-------------------

You can pass ``runtime_env`` when creating a ``RayJob`` to set the Ray
runtime environment (e.g. working directory, pip packages, environment
variables). It can be a Ray ``RuntimeEnv`` object from ``ray.runtime_env``
or a dict with keys such as ``working_dir``, ``pip``, ``env_vars``. For
example: ``runtime_env={"working_dir": "./my-scripts", "pip": ["requests"]}``.
See the Ray documentation for runtime environment options.

Kueue integration
-----------------

When Kueue is installed, you can set ``local_queue`` to the name of a
Kueue LocalQueue and ``priority_class`` to a WorkloadPriorityClass name
for preemption control. These apply to both new clusters (``cluster_config``)
and existing clusters (``cluster_name``). For Kueue setup, see :doc:`./setup-kueue`.

.. note::

   ``RayJob`` is used for the **RayJob custom resource** (batch job
   lifecycle managed by the KubeRay operator). For submitting jobs
   interactively to an already-running cluster via the Ray dashboard API,
   the SDK exposes ``RayJobClient``; see the Code Documentation (modules)
   for the API reference.

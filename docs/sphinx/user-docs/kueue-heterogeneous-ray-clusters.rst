Heterogeneous Ray clusters with Kueue
=====================================

**Jira:** `RHOAIENG-72838 <https://redhat.atlassian.net/browse/RHOAIENG-72838>`__
(related API work: `RHOAIENG-72835 <https://redhat.atlassian.net/browse/RHOAIENG-72835>`__).

.. note::

   **Audience:** cluster administrators and advanced SDK users running
   **multi worker group** Ray clusters under Kueue (for example CPU preprocessing
   workers plus GPU training workers).

When Kueue manages a KubeRay ``RayCluster``, the integration builds a Kueue
``Workload`` whose **pod sets** mirror the Ray cluster layout: one pod set for
the head node and **one pod set per entry** in ``spec.workerGroupSpecs``. Kueue
admits or preempts the **entire** Ray cluster as a single workload; partial
admission is not supported.

If the ``ClusterQueue`` behind your ``LocalQueue`` cannot assign an eligible
``ResourceFlavor`` with sufficient **available quota** for **every** pod set,
admission fails. Misconfiguration often surfaces as a Workload that never
reaches ``Admitted``—not as a clear error in the CodeFlare SDK.

For basic ``ResourceFlavor``, ``ClusterQueue``, and ``LocalQueue`` objects, see
:doc:`./setup-kueue`. This page covers **heterogeneous** clusters (multiple
worker groups) and how they interact with Kueue.

RHOAI and Kueue prerequisites
-----------------------------

Before configuring flavors for heterogeneous Ray clusters, ensure the platform
basics are in place:

1. **Kueue is enabled** on the cluster (for example via the DataScienceCluster
   or an equivalent operator install).
2. **The workload namespace is managed for Kueue.** On OpenShift AI / RHOAI,
   label the namespace with ``kueue.openshift.io/managed: "true"`` so the
   platform admits workloads into Kueue. Current RHOAI 3.x product docs (and
   2.25) use this label. Do not confuse it with ``kueue.x-k8s.io/queue-name``,
   which assigns a workload to a ``LocalQueue``.

3. **The Ray workload is associated with a ``LocalQueue``**—for example via
   ``local_queue`` on a standalone ``Cluster`` / ``ClusterConfiguration``, or
   ``local_queue`` on a lifecycled ``RayJob`` (see below). A namespace default
   ``LocalQueue`` (``kueue.x-k8s.io/default-queue: "true"``) can satisfy this
   when you omit an explicit queue name.

``ResourceFlavor`` and ``ClusterQueue`` objects are configured **after** these
prerequisites. Newer RHOAI versions may relax some platform-side validation
around queue assignment; the workload still must be tied to a queue for Kueue to
manage it.

Platform-specific limits (RHOAI / Kueue version)
------------------------------------------------

Worker-group counts, autoscaling, and validation rules depend on **which Kueue
build is installed** and whether RHOAI **manages** Kueue via the
DataScienceCluster. Current RHOAI typically uses the Red Hat Build of Kueue in
**Unmanaged** mode (the older embedded **Managed** mode is deprecated).

- **Maximum worker groups:** The limit depends on the installed Kueue version.
  Check the ``RayCluster`` / ``RayJob`` Workload limits for that version before
  configuring ``additional_worker_groups``. For example, Red Hat Build of Kueue
  **1.4** (upstream Kueue **0.18**) allows a maximum of 10 PodSets per Workload,
  so a Ray cluster can have the head plus up to **9** ``workerGroupSpecs``.
- **Autoscaling:** Red Hat Build of Kueue at version **1.4** or newer allows
  different autoscaling behavior when combined with ``local_queue`` or a
  namespace default queue—see :doc:`./cluster-configuration`.

Treat these as **release-specific** constraints, not universal Kueue limits.
Confirm behavior against your installed RHOAI and Kueue versions.

How worker groups map to Kueue pod sets
---------------------------------------

KubeRay ``RayCluster`` resources can define multiple ``workerGroupSpecs[]``
entries (each with a unique ``groupName``). The Kueue RayCluster integration
(from Kueue itself, not the CodeFlare SDK) converts that CR into a ``Workload``
with multiple ``spec.podSets``:

+---------------------------+------------------------------------------+
| Ray cluster component     | Kueue ``Workload.spec.podSets`` entry    |
+===========================+==========================================+
| Head group template       | One pod set (head)                       |
+---------------------------+------------------------------------------+
| Each ``workerGroupSpecs`` | One pod set named from ``groupName``     |
| entry                     |                                          |
+---------------------------+------------------------------------------+

Conceptually:

.. code:: text

   WorkerGroup (Ray)
     -> Kueue pod set
     -> resource requests + scheduling constraints
     -> ClusterQueue resource group
     -> eligible ResourceFlavor(s)

Two worker groups can map to the **same** ``ResourceFlavor`` when they share the
same hardware and scheduling class. Use **distinct** flavors only when pod sets
need different node pools, extended resources, or scheduling classes (for example
CPU workers vs GPU workers).

Kueue computes quota usage as the **sum** of resource requests across all pod
sets (each pod set’s pod spec requests × ``count``). During admission, Kueue
assigns ``ResourceFlavor`` objects to the resources requested by each pod set
according to the ``ClusterQueue`` resource groups, **available** quota, and the
pod set’s scheduling constraints (for example ``nodeSelector`` and
tolerations). Available quota may include permitted cohort borrowing when
configured. Resources in the same ``ClusterQueue`` resource group are assigned
from the same set of flavors.

See the upstream Kueue documentation:

- `Workload and pod sets <https://kueue.sigs.k8s.io/docs/concepts/workload/>`__
- `Run a RayCluster <https://kueue.sigs.k8s.io/docs/tasks/run/rayclusters/>`__
- `Resource Flavor <https://kueue.sigs.k8s.io/docs/concepts/resource_flavor/>`__
- `Cluster Queue <https://kueue.sigs.k8s.io/docs/concepts/cluster_queue/>`__

ResourceFlavor requirements for heterogeneous clusters
------------------------------------------------------

Define ``ResourceFlavor`` objects for the **distinct hardware and scheduling
classes** your Ray cluster needs—not one flavor per worker group by default:

1. **Create flavors for each node pool / class** that pod sets must use (for
   example ``cpu-flavor`` on a CPU pool and ``gpu-flavor`` on a GPU pool). Use
   ``spec.nodeLabels`` (and optionally ``spec.tolerations`` on the flavor) so
   flavors match how nodes are labeled and tainted.

2. **Register every flavor** that any pod set might need on the **same**
   ``ClusterQueue`` referenced by your namespace ``LocalQueue``. A heterogeneous
   Ray cluster still uses **one** ``LocalQueue``; the ``ClusterQueue`` must
   expose **all** flavors and **sufficient available quota** for CPU, memory,
   and accelerators **across all pod sets in one admission decision** (quota
   may include cohort borrowing when your ``ClusterQueue`` is configured for it).

3. **Align pod templates with flavors.** After admission, Kueue may inject
   flavor ``nodeLabels`` into pod templates. Worker group templates should use
   tolerations (and affinity, if you set it in raw YAML) compatible with the
   target flavor—especially for GPU nodes.

4. **Head counts too.** The head pod set requests CPU and memory; ensure the
   ``ClusterQueue`` quotas cover head + every worker group simultaneously.

If your platform uses admin-provided queues instead of auto-created defaults, you
remain responsible for flavors and quotas that cover **all** pod sets in the
cluster.

Worked example: CPU workers + GPU workers
-----------------------------------------

The following example uses:

- A **primary** worker group (flat ``worker_*`` fields on
  ``ClusterConfiguration``)—CPU-oriented workers.
- An **additional** GPU worker group via ``additional_worker_groups`` and
  ``WorkerGroup`` (see ``docs/designs/multi-worker-group-design.md``).
- One ``ClusterQueue`` with **two** ``ResourceFlavor`` entries in the same
  resource group so CPU and GPU pod sets can be admitted together.

Adjust names, quotas, and node labels to match your cluster.

Step 1 — Resource flavors
~~~~~~~~~~~~~~~~~~~~~~~~~

.. code:: yaml

   apiVersion: kueue.x-k8s.io/v1beta1
   kind: ResourceFlavor
   metadata:
     name: cpu-flavor
   spec:
     nodeLabels:
       node-pool: cpu

   ---
   apiVersion: kueue.x-k8s.io/v1beta1
   kind: ResourceFlavor
   metadata:
     name: gpu-flavor
   spec:
     nodeLabels:
       node-pool: gpu
     tolerations:
       - key: nvidia.com/gpu
         operator: Exists
         effect: NoSchedule

Flavor ``nodeLabels`` control **placement after a flavor is selected**. They do
not by themselves guarantee that a pod set can only use that flavor. Kueue uses
the pod set’s existing ``nodeSelector`` / affinity when deciding which flavors
are eligible, then injects the selected flavor’s ``nodeLabels``.

``WorkerGroup`` currently does **not** expose a per-group ``nodeSelector``.
Without a selector that requires ``node-pool: cpu``, the GPU flavor can still
be eligible for CPU/memory requests from CPU workers. Strict CPU/GPU pool
isolation requires scheduling constraints that restrict which flavors are
eligible for the pod set (for example a ``nodeSelector`` in raw YAML). The
``gpu-flavor`` tolerations still help GPU workers land on tainted GPU nodes
after that flavor is assigned.

Step 2 — Cluster queue (both flavors, shared resource group)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

List **both** flavors under one ``resourceGroups`` entry so Kueue can admit the
Ray cluster as one Workload and assign flavors to each pod set’s resource
requests:

.. code:: yaml

   apiVersion: kueue.x-k8s.io/v1beta1
   kind: ClusterQueue
   metadata:
     name: heterogeneous-ray-cq
   spec:
     namespaceSelector: {}
     resourceGroups:
       - coveredResources: ["cpu", "memory", "nvidia.com/gpu"]
         flavors:
           - name: cpu-flavor
             resources:
               - name: cpu
                 nominalQuota: 64
               - name: memory
                 nominalQuota: 256Gi
               - name: nvidia.com/gpu
                 nominalQuota: 0
           - name: gpu-flavor
             resources:
               - name: cpu
                 nominalQuota: 32
               - name: memory
                 nominalQuota: 128Gi
               - name: nvidia.com/gpu
                 nominalQuota: 8

Step 3 — Local queue in the workload namespace
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code:: yaml

   apiVersion: kueue.x-k8s.io/v1beta1
   kind: LocalQueue
   metadata:
     name: team-a-heterogeneous
     namespace: team-a
     annotations:
       kueue.x-k8s.io/default-queue: "true"
   spec:
     clusterQueue: heterogeneous-ray-cq

Step 4 — CodeFlare SDK cluster (two worker groups, one LocalQueue)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

For a standalone ``Cluster``, set ``local_queue`` on ``ClusterConfiguration``:

.. code:: python

   from codeflare_sdk import Cluster, ClusterConfiguration, WorkerGroup
   from kubernetes.client import V1Toleration

   config = ClusterConfiguration(
       name="preprocess-and-train",
       namespace="team-a",
       local_queue="team-a-heterogeneous",
       num_workers=2,
       worker_cpu_requests=4,
       worker_cpu_limits=4,
       worker_memory_requests=16,
       worker_memory_limits=16,
       head_cpu_requests=2,
       head_cpu_limits=2,
       head_memory_requests=8,
       head_memory_limits=8,
       additional_worker_groups=[
           WorkerGroup(
               group_name="gpu-trainers",
               replicas=1,
               cpu_requests=8,
               cpu_limits=8,
               memory_requests=32,
               memory_limits=32,
               gpu_type="nvidia.com/gpu",
               gpu_count=1,
               tolerations=[
                   V1Toleration(
                       key="nvidia.com/gpu",
                       operator="Exists",
                       effect="NoSchedule",
                   ),
               ],
           ),
       ],
   )

   cluster = Cluster(config)
   cluster.apply()

The generated ``RayCluster`` contains the default worker group
(``small-group-{name}``) plus ``gpu-trainers``. Kueue creates a ``Workload``
with separate pod sets for the head, ``small-group-preprocess-and-train``, and
``gpu-trainers``. Verify with:

.. code:: bash

   kubectl get raycluster preprocess-and-train -n team-a -o jsonpath='{.spec.workerGroupSpecs[*].groupName}{"\n"}'
   kubectl get workloads.kueue.x-k8s.io -n team-a
   kubectl describe workload.kueue.x-k8s.io -n team-a

When admission succeeds, worker pods for each group should schedule onto nodes
matching the assigned flavors. GPU workers remain ``Pending`` if the cluster has
no GPU capacity even when CPU workers are ready—that is a capacity issue, not
necessarily a Kueue flavor definition bug.

RayJob lifecycled clusters
--------------------------

For a ``RayJob`` that **creates** a new cluster (``cluster_config``), pass
``additional_worker_groups`` on ``ClusterConfiguration`` and set Kueue queue
selection on **`RayJob.local_queue`**—not ``ClusterConfiguration.local_queue``.
Kueue still builds one ``Workload`` for the embedded ``rayClusterSpec`` with
multiple pod sets.

.. code:: python

   from codeflare_sdk import RayJob, ClusterConfiguration, WorkerGroup

   cluster_config = ClusterConfiguration(
       name="rayjob-heterogeneous",
       namespace="team-a",
       num_workers=1,
       worker_cpu_requests=2,
       worker_cpu_limits=2,
       additional_worker_groups=[
           WorkerGroup(
               group_name="gpu-workers",
               replicas=1,
               gpu_type="nvidia.com/gpu",
               gpu_count=1,
           ),
       ],
   )

   job = RayJob(
       job_name="train-heterogeneous",
       entrypoint="python train.py",
       cluster_config=cluster_config,
       local_queue="team-a-heterogeneous",
   )
   job.submit()

Kueue does **not** apply to ``RayJob`` instances that target an existing cluster
via ``cluster_name``; ``local_queue`` and ``priority_class`` on those jobs are
ignored. Submit interactive work to a running cluster with ``RayJobClient``
instead. RHOAI may also reject Kueue-managed ``RayJob`` resources that reference
an existing ``RayCluster``.

SDK limitations (v1)
----------------------

- **Read path:** ``get_cluster()`` does not populate ``additional_worker_groups``
  from multi-group CRs; only the first ``workerGroupSpecs`` entry is reflected in
  the returned ``ClusterConfiguration``. Use the Kubernetes API or ``kubectl`` to
  inspect full ``workerGroupSpecs`` after create.
- **Per-group node selectors:** ``WorkerGroup`` v1 does not expose ``nodeSelector``.
  Flavor ``nodeLabels`` are injected **after** flavor selection; they do not
  restrict which flavors are eligible. Strict CPU/GPU pool isolation needs
  additional scheduling constraints on the pod set.

Troubleshooting failed Kueue admission
--------------------------------------

For the Kueue **RayCluster / RayJob** integration, Kueue typically **suspends**
the Ray CR until the ``Workload`` is admitted. Worker pods may not exist yet
while the Workload is queued—this is different from Kueue’s direct **Pod**
integration, where pods can appear with a scheduling gate
``kueue.x-k8s.io/admission``.

Before admission
~~~~~~~~~~~~~~~~

Symptoms:

- A ``Workload`` exists but stays without ``Admitted`` (or fails
  ``QuotaReserved``).
- The ``RayCluster`` / ``RayJob`` may show as suspended; Ray worker pods may
  not be created yet.
- No obvious error in Python; the failure is on the Kueue side.

Where to look:

1. **Workload object** (primary signal):

   .. code:: bash

      kubectl get workloads.kueue.x-k8s.io -n <namespace>
      kubectl describe workload.kueue.x-k8s.io <workload-name> -n <namespace>

   Inspect ``status.conditions`` (for example ``QuotaReserved``, ``Admitted``,
   or ``Finished``) and status messages about **quota**, **flavor**, or **pod set**
   fit. Workload names are derived from the owning ``RayCluster`` (or ``RayJob``);
   list workloads in the same namespace as the Ray CR.

2. **ClusterQueue utilization**:

   .. code:: bash

      kubectl describe clusterqueue heterogeneous-ray-cq

   Confirm each ``ResourceFlavor`` has **sufficient available quota** for the
   **combined** head and all worker groups, including ``nvidia.com/gpu`` on the
   GPU pod set. Available quota may include permitted **cohort borrowing**, not
   only unused ``nominalQuota``.

3. **Events**:

   .. code:: bash

      kubectl get events -n <namespace> --sort-by='.lastTimestamp'

   Filter for ``Workload``, ``ClusterQueue``, or ``RayCluster`` objects.

4. **No eligible flavor**: If a pod set’s template requires labels or tolerations
   that **no** flavor in the ``ClusterQueue`` can satisfy, admission fails.
   Compare ``WorkerGroup`` tolerations and flavor ``spec.nodeLabels`` /
   ``spec.tolerations``.

After admission
~~~~~~~~~~~~~~~

Symptoms:

- ``RayCluster`` exists and the Workload is ``Admitted``, but some pods stay
  ``Pending`` or never become ``Ready``.

Where to look:

- Pod events and ``kubectl describe pod`` for scheduler failures.
- Node selectors, taints/tolerations, and affinity on worker templates vs nodes.
- GPU or other extended resource capacity on the target node pool.

Common misconfigurations
~~~~~~~~~~~~~~~~~~~~~~~~

- **No eligible ``ResourceFlavor`` for one or more pod sets**—for example GPU
  workers request ``nvidia.com/gpu``, but the ``ClusterQueue`` has no flavor
  with GPU quota and compatible node constraints.
- **Quotas large enough for one group but not all groups at once** (Kueue
  reserves quota for the full Workload).
- **Separate ``ClusterQueue`` per flavor** with only one ``LocalQueue``—the SDK
  submits one queue name; all groups must be satisfiable through that queue’s
  ``ClusterQueue``.
- **Missing GPU quota** on the GPU flavor while requesting ``nvidia.com/gpu`` in
  an additional worker group.

Related SDK topics
------------------

- :doc:`./setup-kueue` — creating flavors, cluster queues, and local queues.
- :doc:`./cluster-configuration` — ``local_queue`` on ``ClusterConfiguration``.
- :doc:`./rayjob` — ``local_queue`` on lifecycled ``RayJob``.
- ``docs/designs/multi-worker-group-design.md`` — ``WorkerGroup`` and
  ``additional_worker_groups`` API details (create path and follow-up work).

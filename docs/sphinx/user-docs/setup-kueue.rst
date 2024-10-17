Basic Kueue Resources configuration
===================================

Introduction:
-------------

This document is designed for administrators who have Kueue installed on
their cluster. We will walk through the process of setting up essential
Kueue resources, namely Cluster Queue, Resource Flavor, and Local Queue.

1. Resource Flavor:
-------------------

Resource Flavors allow the cluster admin to define different types of
resources with specific characteristics, such as CPU, memory, GPU, etc.
These can then be assigned to workloads to ensure they are executed on
appropriate resources.

The YAML configuration provided below creates an empty Resource Flavor
named default-flavor. It serves as a starting point and does not specify
any detailed resource characteristics.

.. code:: yaml

   apiVersion: kueue.x-k8s.io/v1beta1
   kind: ResourceFlavor
   metadata:
     name: default-flavor

For more detailed information on Resource Flavor configuration options,
refer to the Kueue documentation: `Resource Flavor
Configuration <https://kueue.sigs.k8s.io/docs/concepts/resource_flavor/>`__

2. Cluster Queue:
-----------------

A Cluster Queue represents a shared queue across the entire cluster. It
allows the cluster admin to define global settings for workload
prioritization and resource allocation.

When setting up a Cluster Queue in Kueue, it’s crucial that the resource
specifications match the actual capacities and operational requirements
of your cluster. The example provided outlines a basic setup; however,
each cluster may have different resource availabilities and needs.

.. code:: yaml

   apiVersion: kueue.x-k8s.io/v1beta1
   kind: ClusterQueue
   metadata:
     name: "cluster-queue"
   spec:
     namespaceSelector: {} # match all.
     resourceGroups:
     - coveredResources: ["cpu", "memory", "pods", "nvidia.com/gpu"]
       flavors:
       - name: "default-flavor"
         resources:
         - name: "cpu"
           nominalQuota: 9
         - name: "memory"
           nominalQuota: 36Gi
         - name: "pods"
           nominalQuota: 5
         - name: "nvidia.com/gpu"
           nominalQuota: '0'

For more detailed information on Cluster Queue configuration options,
refer to the Kueue documentation: `Cluster Queue
Configuration <https://kueue.sigs.k8s.io/docs/concepts/cluster_queue/>`__

3. Local Queue (With Default Annotation):
-----------------------------------------

A Local Queue represents a queue associated with a specific namespace
within the cluster. It allows namespace-level control over workload
prioritization and resource allocation.

.. code:: yaml

   apiVersion: kueue.x-k8s.io/v1beta1
   kind: LocalQueue
   metadata:
     namespace: team-a
     name: team-a-queue
     annotations:
       kueue.x-k8s.io/default-queue: "true"
   spec:
     clusterQueue: cluster-queue

In the LocalQueue configuration provided above, the annotations field
specifies ``kueue.x-k8s.io/default-queue: "true"``. This annotation
indicates that the team-a-queue is designated as the default queue for
the team-a namespace. When this is set, any workloads submitted to the
team-a namespace without explicitly specifying a queue will
automatically be routed to the team-a-queue.

For more detailed information on Local Queue configuration options,
refer to the Kueue documentation: `Local Queue
Configuration <https://kueue.sigs.k8s.io/docs/concepts/local_queue/>`__

Conclusion:
-----------

By following the steps outlined in this document, the cluster admin can
successfully create the basic Kueue resources necessary for workload
management in the cluster. For more advanced configurations and
features, please refer to the comprehensive `Kueue
documentation <https://kueue.sigs.k8s.io/docs/concepts/>`__.

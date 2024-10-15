Ray Cluster Interaction
=======================

The CodeFlare SDK offers multiple ways to interact with Ray Clusters
including the below methods.

get_cluster()
-------------

The ``get_cluster()`` function is used to initialise a ``Cluster``
object from a pre-existing Ray Cluster/AppWrapper. Below is an example
of it's usage:

::

   from codeflare_sdk import get_cluster
   cluster = get_cluster(cluster_name="raytest", namespace="example", is_appwrapper=False, write_to_file=False)
   -> output: Yaml resources loaded for raytest
   cluster.status()
   -> output:
                       🚀 CodeFlare Cluster Status 🚀
    ╭─────────────────────────────────────────────────────────────────╮
    │   Name                                                          │
    │   raytest                                           Active ✅   │
    │                                                                 │
    │   URI: ray://raytest-head-svc.example.svc:10001                 │
    │                                                                 │
    │   Dashboard🔗                                                   │
    │                                                                 │
    ╰─────────────────────────────────────────────────────────────────╯
   (<CodeFlareClusterStatus.READY: 1>, True)
   cluster.down()
   cluster.up() # This function will create an exact copy of the retrieved Ray Cluster only if the Ray Cluster has been previously deleted.

| These are the parameters the ``get_cluster()`` function accepts:
| ``cluster_name: str # Required`` -> The name of the Ray Cluster.
| ``namespace: str # Default: "default"`` -> The namespace of the Ray Cluster.
| ``is_appwrapper: bool # Default: False`` -> When set to
| ``True`` the function will attempt to retrieve an AppWrapper instead of a Ray Cluster.
| ``write_to_file: bool # Default: False`` -> When set to ``True`` the Ray Cluster/AppWrapper will be written to a file similar to how it is done in ``ClusterConfiguration``.

list_all_queued()
-----------------

| The ``list_all_queued()`` function returns (and prints by default) a list of all currently queued-up Ray Clusters in a given namespace.
| It accepts the following parameters:
| ``namespace: str # Required`` -> The namespace you want to retrieve the list from.
| ``print_to_console: bool # Default: True`` -> Allows the user to print the list to their console.
| ``appwrapper: bool # Default: False`` -> When set to ``True`` allows the user to list queued AppWrappers.

list_all_clusters()
-------------------

| The ``list_all_clusters()`` function will return a list of detailed descriptions of Ray Clusters to the console by default.
| It accepts the following parameters:
| ``namespace: str # Required`` -> The namespace you want to retrieve the list from.
| ``print_to_console: bool # Default: True`` -> A boolean that allows the user to print the list to their console.

.. note::

   The following methods require a ``Cluster`` object to be
   initialized. See :doc:`./cluster-configuration`

cluster.up()
------------

| The ``cluster.up()`` function creates a Ray Cluster in the given namespace.

cluster.down()
--------------

| The ``cluster.down()`` function deletes the Ray Cluster in the given namespace.

cluster.status()
----------------

| The ``cluster.status()`` function prints out the status of the Ray Cluster's state with a link to the Ray Dashboard.

cluster.details()
-----------------

| The ``cluster.details()`` function prints out a detailed description of the Ray Cluster's status, worker resources and a link to the Ray Dashboard.

cluster.wait_ready()
--------------------

| The ``cluster.wait_ready()`` function waits for the requested cluster to be ready, up to an optional timeout and checks every 5 seconds.
| It accepts the following parameters:
| ``timeout: Optional[int] # Default: None`` -> Allows the user to define a timeout for the ``wait_ready()`` function.
| ``dashboard_check: bool # Default: True`` -> If enabled the ``wait_ready()`` function will wait until the Ray Dashboard is ready too.

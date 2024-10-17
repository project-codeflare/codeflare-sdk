Jupyter UI Widgets
==================

Below are some examples of the Jupyter UI Widgets that are included in
the CodeFlare SDK.

.. note::
   To use the widgets functionality you must be using the CodeFlare SDK in a Jupyter Notebook environment.

Cluster Up/Down Buttons
-----------------------

The Cluster Up/Down buttons appear after successfully initialising your
`ClusterConfiguration <cluster-configuration.md#ray-cluster-configuration>`__.
There are two buttons and a checkbox ``Cluster Up``, ``Cluster Down``
and ``Wait for Cluster?`` which mimic the
`cluster.up() <ray-cluster-interaction.md#clusterup>`__,
`cluster.down() <ray-cluster-interaction.md#clusterdown>`__ and
`cluster.wait_ready() <ray-cluster-interaction.md#clusterwait_ready>`__
functionality.

After initialising their ``ClusterConfiguration`` a user can select the
``Wait for Cluster?`` checkbox then click the ``Cluster Up`` button to
create their Ray Cluster and wait until it is ready. The cluster can be
deleted by clicking the ``Cluster Down`` button.

.. image:: images/ui-buttons.png
   :alt: An image of the up/down ui buttons

View Clusters UI Table
----------------------

The View Clusters UI Table allows a user to see a list of Ray Clusters
with information on their configuration including number of workers, CPU
requests and limits along with the clusters status.

.. image:: images/ui-view-clusters.png
   :alt: An image of the view clusters ui table

Above is a list of two Ray Clusters ``raytest`` and ``raytest2`` each of
those headings is clickable and will update the table to view the
selected Cluster's information. There are three buttons under the table
``Cluster Down``, ``View Jobs`` and ``Open Ray Dashboard``. \* The
``Cluster Down`` button will delete the selected Cluster. \* The
``View Jobs`` button will try to open the Ray Dashboard's Jobs view in a
Web Browser. The link will also be printed to the console. \* The
``Open Ray Dashboard`` button will try to open the Ray Dashboard view in
a Web Browser. The link will also be printed to the console.

The UI Table can be viewed by calling the following function.

.. code:: python

   from codeflare_sdk import view_clusters
   view_clusters() # Accepts namespace parameter but will try to gather the namespace from the current context

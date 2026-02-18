Authentication via the CodeFlare SDK
====================================

Currently there are four ways of authenticating to your cluster via the
SDK. Authenticating with your cluster allows you to perform actions such
as creating Ray Clusters and Job Submission.

Method 1 Token Authentication
-----------------------------

This is how a typical user would authenticate to their cluster using
``TokenAuthentication``.

::

   from codeflare_sdk import TokenAuthentication

   auth = TokenAuthentication(
       token = "XXXXX",
       server = "XXXXX",
       skip_tls=False,
       # ca_cert_path="/path/to/cert"
   )
   auth.login()
   # log out with auth.logout()

Setting ``skip_tls=True`` allows interaction with an HTTPS server
bypassing the server certificate checks although this is not secure. You
can pass a custom certificate to ``TokenAuthentication`` by using
``ca_cert_path="/path/to/cert"`` when authenticating provided
``skip_tls=False``. Alternatively you can set the environment variable
``CF_SDK_CA_CERT_PATH`` to the path of your custom certificate.

Method 2 Kubernetes Config File Authentication (Default location)
-----------------------------------------------------------------

If a user has authenticated to their cluster by alternate means e.g. run
a login command like ``oc login --token=<token> --server=<server>``
their kubernetes config file should have updated. If the user has not
specifically authenticated through the SDK by other means such as
``TokenAuthentication`` then the SDK will try to use their default
Kubernetes config file located at ``"$HOME/.kube/config"``.

Method 3 Specifying a Kubernetes Config File
--------------------------------------------

A user can specify a config file via a different authentication class
``KubeConfigFileAuthentication`` for authenticating with the SDK. This
is what loading a custom config file would typically look like.

::

   from codeflare_sdk import KubeConfigFileAuthentication

   auth = KubeConfigFileAuthentication(
       kube_config_path="/path/to/config",
   )
   auth.load_kube_config()
   # log out with auth.logout()

Method 4 In-Cluster Authentication
----------------------------------

If a user does not authenticate by any of the means detailed above and
does not have a config file at ``"$HOME/.kube/config"`` the SDK will try
to authenticate with the in-cluster configuration file.

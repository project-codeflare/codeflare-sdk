Authentication via the CodeFlare SDK
====================================

The CodeFlare SDK uses `kube-authkit <https://github.com/opendatahub-io/kube-authkit>`_
for Kubernetes authentication. Authenticating with your cluster allows you to perform
actions such as creating Ray Clusters and submitting jobs.

Authentication goes through ``Codeflare``, the SDK's single entrypoint. The
``Codeflare`` instance owns the resulting Kubernetes client, and every cluster or job
created from it keeps using that client — so two instances pointed at two clusters do
not interfere with each other. Use ``cf.clusters`` and ``cf.jobs`` for all subsequent
operations.

Method 1: Token-Based Authentication (Recommended for RHOAI Workbenches)
-------------------------------------------------------------------------

Authenticate using an OpenShift or Kubernetes bearer token. This is the recommended
approach when running inside an RHOAI Workbench, as the workbench service account
may not have sufficient RBAC permissions to manage Ray resources.

Get your token with ``oc whoami -t``, or from the OpenShift console via
**username → Copy login command → Display Token**.

::

   from kube_authkit import AuthConfig
   from codeflare_sdk import Codeflare, SDKConfig

   auth_config = AuthConfig(
       method="openshift",
       k8s_api_host="https://api.example.com:6443",
       token="sha256~XXXXX",  # oc whoami -t
   )
   cf = Codeflare(config=SDKConfig(auth=auth_config, namespace="my-project"))

You can also set the environment variable ``CF_SDK_CA_CERT_PATH`` to the path of
a custom CA certificate for TLS verification.

Method 2: Auto-Detection
------------------------

When running with a kubeconfig at ``~/.kube/config``, kube-authkit can
auto-detect and use the available credentials::

   from kube_authkit import AuthConfig
   from codeflare_sdk import Codeflare, SDKConfig

   auth_config = AuthConfig(method="auto")
   cf = Codeflare(config=SDKConfig(auth=auth_config, namespace="my-project"))

.. note::

   In RHOAI Workbenches, ``method="auto"`` picks up the workbench service account
   (in-cluster). This will fail with a permissions error unless the service account
   has been granted Ray RBAC by an admin (see `RHOAIENG-46748
   <https://redhat.atlassian.net/browse/RHOAIENG-46748>`_).
   Use Method 1 (token) instead.

Method 3: OIDC Authentication (for BYOIDC-enabled clusters)
------------------------------------------------------------

For clusters configured with an external OIDC provider (e.g. Red Hat OpenShift AI
3.4+ with BYOIDC), use the device flow for interactive notebook environments::

   from kube_authkit import AuthConfig
   from codeflare_sdk import Codeflare, SDKConfig

   auth_config = AuthConfig(
       method="oidc",
       k8s_api_host="https://api.example.com:6443",
       oidc_issuer="https://your-oidc-provider.com",
       client_id="your-client-id",
       use_device_flow=True,  # Interactive device flow for notebook environments
   )
   cf = Codeflare(config=SDKConfig(auth=auth_config, namespace="my-project"))

Method 4: Kubeconfig File Authentication
-----------------------------------------

To authenticate using a kubeconfig file::

   from kube_authkit import AuthConfig
   from codeflare_sdk import Codeflare, SDKConfig

   auth_config = AuthConfig(method="kubeconfig")
   cf = Codeflare(config=SDKConfig(auth=auth_config, namespace="my-project"))

The ``KUBECONFIG`` environment variable is respected if set. Otherwise kube-authkit
looks for ``~/.kube/config`` by default.

Method 5: OpenShift OAuth (Interactive)
-----------------------------------------

For OpenShift clusters using native OAuth with an interactive browser login flow
(not needed if you already have a token — use Method 1 instead)::

   from kube_authkit import AuthConfig
   from codeflare_sdk import Codeflare, SDKConfig

   auth_config = AuthConfig(
       method="openshift",
       k8s_api_host="https://api.example.com:6443",
   )
   cf = Codeflare(config=SDKConfig(auth=auth_config, namespace="my-project"))

Removed Authentication Methods
-----------------------------------

The ``TokenAuthentication`` and ``KubeConfigFileAuthentication`` classes were
deprecated in v0.34.0 and **removed in v0.40.0**. Earlier documentation said
they would survive until v1.0.0; they did not. Importing either one raises an
``ImportError`` naming its replacement:

.. code-block:: text

   TokenAuthentication was removed in v0.40.0, after being deprecated
   throughout v0.39.x. Use kube-authkit:

       from codeflare_sdk import Codeflare, SDKConfig
       from kube_authkit import AuthConfig

       cf = Codeflare(config=SDKConfig(auth=AuthConfig(
           method="openshift",
           k8s_api_host=<server>,
           token=<token>,
           verify_ssl=not <skip_tls>,   # ca_cert=<ca_cert_path>
       )))

``TokenAuthentication`` maps onto Method 1 above, and
``KubeConfigFileAuthentication`` onto Method 4.

``set_api_client`` is a different case: it was removed in error, having never
carried a deprecation warning, and has been restored. It still works, now with
a ``DeprecationWarning``. Prefer ``Codeflare``, which scopes the client to the
clusters and jobs it creates rather than setting a process-wide global.

Authentication via the CodeFlare SDK
====================================

The CodeFlare SDK uses `kube-authkit <https://github.com/opendatahub-io/kube-authkit>`_
for Kubernetes authentication. Authenticating with your cluster allows you to perform
actions such as creating Ray Clusters and submitting jobs.

Method 1: Token-Based Authentication (Recommended for RHOAI Workbenches)
-------------------------------------------------------------------------

Authenticate using an OpenShift or Kubernetes bearer token. This is the recommended
approach when running inside an RHOAI Workbench, as the workbench service account
may not have sufficient RBAC permissions to manage Ray resources.

Get your token with ``oc whoami -t``, or from the OpenShift console via
**username → Copy login command → Display Token**.

::

   from kube_authkit import AuthConfig, get_k8s_client
   from codeflare_sdk import set_api_client

   auth_config = AuthConfig(
       method="openshift",
       k8s_api_host="https://api.example.com:6443",
       token="sha256~XXXXX",  # oc whoami -t
   )
   api_client = get_k8s_client(config=auth_config)
   set_api_client(api_client)

You can also set the environment variable ``CF_SDK_CA_CERT_PATH`` to the path of
a custom CA certificate for TLS verification.

Method 2: Auto-Detection
------------------------

When running with a kubeconfig at ``~/.kube/config``, kube-authkit can
auto-detect and use the available credentials::

   from kube_authkit import AuthConfig, get_k8s_client
   from codeflare_sdk import set_api_client

   auth_config = AuthConfig(method="auto")
   api_client = get_k8s_client(config=auth_config)
   set_api_client(api_client)

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

   from kube_authkit import AuthConfig, get_k8s_client
   from codeflare_sdk import set_api_client

   auth_config = AuthConfig(
       method="oidc",
       k8s_api_host="https://api.example.com:6443",
       oidc_issuer="https://your-oidc-provider.com",
       client_id="your-client-id",
       use_device_flow=True,  # Interactive device flow for notebook environments
   )
   api_client = get_k8s_client(config=auth_config)
   set_api_client(api_client)

Method 4: Kubeconfig File Authentication
-----------------------------------------

To authenticate using a kubeconfig file::

   from kube_authkit import AuthConfig, get_k8s_client
   from codeflare_sdk import set_api_client

   auth_config = AuthConfig(method="kubeconfig")
   api_client = get_k8s_client(config=auth_config)
   set_api_client(api_client)

The ``KUBECONFIG`` environment variable is respected if set. Otherwise kube-authkit
looks for ``~/.kube/config`` by default.

Method 5: OpenShift OAuth (Interactive)
-----------------------------------------

For OpenShift clusters using native OAuth with an interactive browser login flow
(not needed if you already have a token — use Method 1 instead)::

   from kube_authkit import AuthConfig, get_k8s_client
   from codeflare_sdk import set_api_client

   auth_config = AuthConfig(
       method="openshift",
       k8s_api_host="https://api.example.com:6443",
   )
   api_client = get_k8s_client(config=auth_config)
   set_api_client(api_client)

Deprecated Authentication Methods
-----------------------------------

The ``TokenAuthentication`` and ``KubeConfigFileAuthentication`` classes are
**deprecated** as of v0.34.0 and will be removed in a future release. They
remain functional but will emit deprecation warnings. Please migrate using
the patterns above.

See the `Migration Guide <https://github.com/project-codeflare/codeflare-sdk/blob/main/docs/auth_migration_guide.md>`_
for detailed before/after examples.

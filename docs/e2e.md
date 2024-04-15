# Running e2e tests locally
#### Pre-requisites
- We recommend using Python 3.9, along with Poetry.

## On KinD clusters
Pre-requisite for KinD clusters: please add in your local `/etc/hosts` file `127.0.0.1 kind`. This will map your localhost IP address to the KinD cluster's hostname. This is already performed on [GitHub Actions](https://github.com/project-codeflare/codeflare-common/blob/1edd775e2d4088a5a0bfddafb06ff3a773231c08/github-actions/kind/action.yml#L70-L72)

- Setup Phase:
  - Pull the [codeflare-operator repo](https://github.com/project-codeflare/codeflare-operator) and run the following make targets:
  ```
  make kind-e2e
  export CLUSTER_HOSTNAME=kind
  make setup-e2e
  make deploy -e IMG=quay.io/project-codeflare/codeflare-operator:v1.3.0

  For running tests locally on Kind cluster, we need to disable `rayDashboardOAuthEnabled` in `codeflare-operator-config` ConfigMap and then restart CodeFlare Operator
  ```

  - **(Optional)** - Create and add `sdk-user` with limited permissions to the cluster to run through the e2e tests:
  ```
    # Get KinD certificates
    docker cp kind-control-plane:/etc/kubernetes/pki/ca.crt .
    docker cp kind-control-plane:/etc/kubernetes/pki/ca.key .

    # Generate certificates for new user
    openssl genrsa -out user.key 2048
    openssl req -new -key user.key -out user.csr -subj '/CN=sdk-user/O=tenant'
    openssl x509 -req -in user.csr -CA ca.crt -CAkey ca.key -CAcreateserial -out user.crt -days 360

    # Add generated certificated to KinD context
    user_crt=$(base64 --wrap=0 user.crt)
    user_key=$(base64 --wrap=0 user.key)
    yq eval -i ".contexts += {\"context\": {\"cluster\": \"kind-kind\", \"user\": \"sdk-user\"}, \"name\": \"sdk-user\"}" $HOME/.kube/config
    yq eval -i ".users += {\"name\": \"sdk-user\", \"user\": {\"client-certificate-data\": \"$user_crt\", \"client-key-data\": \"$user_key\"}}" $HOME/.kube/config
    cat $HOME/.kube/config

    # Cleanup
    rm ca.crt
    rm ca.srl
    rm ca.key
    rm user.crt
    rm user.key
    rm user.csr

    # Add RBAC permissions to sdk-user
    kubectl create clusterrole list-ingresses --verb=get,list --resource=ingresses
    kubectl create clusterrolebinding sdk-user-list-ingresses --clusterrole=list-ingresses --user=sdk-user
    kubectl create clusterrole appwrapper-creator --verb=get,list,create,delete,patch --resource=appwrappers
    kubectl create clusterrolebinding sdk-user-appwrapper-creator --clusterrole=appwrapper-creator --user=sdk-user
    kubectl create clusterrole namespace-creator --verb=get,list,create,delete,patch --resource=namespaces
    kubectl create clusterrolebinding sdk-user-namespace-creator --clusterrole=namespace-creator --user=sdk-user
    kubectl create clusterrole list-rayclusters --verb=get,list --resource=rayclusters
    kubectl create clusterrolebinding sdk-user-list-rayclusters --clusterrole=list-rayclusters --user=sdk-user
    kubectl config use-context sdk-user

  ```

  - Install the latest development version of kueue
  ```
  kubectl apply --server-side -k "github.com/opendatahub-io/kueue/config/rhoai?ref=dev"
  ```

- Test Phase:
   - Once we have the codeflare-operator, kuberay-operator and kueue running and ready, we can run the e2e test on the codeflare-sdk repository:
  ```
  poetry install --with test,docs
  poetry run pytest -v -s ./tests/e2e/mnist_raycluster_sdk_test.py
  ```



## On OpenShift clusters
- Setup Phase:
  - Pull the [codeflare-operator repo](https://github.com/project-codeflare/codeflare-operator) and run the following make targets:
  ```

  make setup-e2e
  make deploy -e IMG=quay.io/project-codeflare/codeflare-operator:v1.3.0
  ```

  - Install the latest development version of kueue
  ```
  kubectl apply --server-side -k "github.com/opendatahub-io/kueue/config/rhoai?ref=dev"
  ```

- Test Phase:
   - Once we have the codeflare-operator, kuberay-operator and kueue running and ready, we can run the e2e test on the codeflare-sdk repository:
  ```
  poetry install --with test,docs
  poetry run pytest -v -s ./tests/e2e/mnist_raycluster_sdk_test.py
  ```
  - To run the multiple tests based on the cluster environment, we can run the e2e tests by marking -m with cluster environment (kind or openshift)
  ```
  poetry run pytest -v -s ./tests/e2e -m openshift
  ```
  - By default tests configured with timeout of `15 minutes`. If necessary, we can override the timeout using `--timeout` option
  ```
  poetry run pytest -v -s ./tests/e2e -m openshift --timeout=1200
  ```

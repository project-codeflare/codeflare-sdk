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
  export CODEFLARE_TEST_TIMEOUT_LONG=20m
  make deploy -e IMG=quay.io/project-codeflare/codeflare-operator:v1.1.0
  make setup-e2e
  ```
- Test Phase:
   - Once we have the codeflare-operator and kuberay-operator running and ready, we can run the e2e test on the codeflare-sdk repository:
  ```
  poetry install --with test,docs
  poetry run pytest -v -s ./tests/e2e/mnist_raycluster_sdk_test.py
  ```



## On OpenShift clusters
- Setup Phase:
  - Pull the [codeflare-operator repo](https://github.com/project-codeflare/codeflare-operator) and run the following make targets:
  ```
  make deploy -e IMG=quay.io/project-codeflare/codeflare-operator:v1.1.0
  make setup-e2e
  ```
- Test Phase:
   - Once we have the codeflare-operator and kuberay-operator running and ready, we can run the e2e test on the codeflare-sdk repository:
  ```
  poetry install --with test,docs
  poetry run pytest -v -s ./tests/e2e/mnist_raycluster_sdk_test.py
  ```

#!/bin/bash

# Copyright 2022 IBM, Red Hat
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

set -euo pipefail
: "${INGRESS_NGINX_VERSION:=controller-v1.6.4}"

echo "Creating KinD cluster"
cat <<EOF | kind create cluster --config=-
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
nodes:
  - role: control-plane
    image: kindest/node:v1.25.3@sha256:f52781bc0d7a19fb6c405c2af83abfeb311f130707a0e219175677e366cc45d1
    kubeadmConfigPatches:
      - |
        kind: InitConfiguration
        nodeRegistration:
          kubeletExtraArgs:
            node-labels: "ingress-ready=true"
EOF

echo "Deploying Ingress controller into KinD cluster"
curl https://raw.githubusercontent.com/kubernetes/ingress-nginx/"${INGRESS_NGINX_VERSION}"/deploy/static/provider/kind/deploy.yaml | sed "s/--publish-status-address=localhost/--report-node-internal-ip-address\\n        - --status-update-interval=10/g" | kubectl apply -f -
kubectl annotate ingressclass nginx "ingressclass.kubernetes.io/is-default-class=true"
kubectl -n ingress-nginx wait --timeout=300s --for=condition=Available deployments --all

## Create a user with limited permissions to test the SDK
# Create a CA and a user certificate and key
docker cp kind-control-plane:/etc/kubernetes/pki/ca.crt .
docker cp kind-control-plane:/etc/kubernetes/pki/ca.key .
openssl genrsa -out sdk-user.key 2048
openssl req -new -key sdk-user.key -out sdk-user.csr -subj /CN=sdk-user/O=tenant1
openssl x509 -req -in sdk-user.csr -CA ca.crt -CAkey ca.key -CAcreateserial -out sdk-user.crt -days 360
base64 -w 0 < ca.crt > ca.crt.base64
base64 -w 0 < sdk-user.crt > sdk-user.crt.base64
base64 -w 0 < sdk-user.key > sdk-user.key.base64
SERVER_ADDRESS=$(kubectl cluster-info | grep -o "https://127.0.0.1:[0-9]*" | head -n 1)

# Replace the placeholders in the user config file with the actual values
sed -i 's|certificate-authority-data:.*|certificate-authority-data: '$(cat ca.crt.base64)'|g' ./tests/e2e/config
sed -i 's|client-certificate-data:.*|client-certificate-data: '$(cat sdk-user.crt.base64)'|g' ./tests/e2e/config
sed -i 's|client-key-data:.*|client-key-data: '$(cat sdk-user.key.base64)'|g' ./tests/e2e/config
sed -i 's|server:.*|server: '$(echo $SERVER_ADDRESS)'|g' ./tests/e2e/config

# Apply to the user limited RBAC permissions
cat <<EOF | kubectl apply -f -
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: tenant-user
rules:
- apiGroups: [""]
  resources: ["namespaces"]
  verbs: ["get", "watch", "list"]
- apiGroups: ["mcadv1beta1.groupname"]
  resources: ["appwrappers"]
  verbs: ["get", "create", "delete", "list", "patch", "update"]
- apiGroups: ["rayv1.groupversion.group"]
  resources: ["rayclusters", "rayclusters/status"]
  verbs: ["get", "list"]
- apiGroups: ["route.openshift.io"]
  resources: ["routes"]
  verbs: ["get", "list"]
- apiGroups: ["networking.k8s.io"]
  resources: ["ingresses"]
  verbs: ["get", "list"]
EOF

cat <<EOF | kubectl apply -f -
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: tenant-user
subjects:
- kind: User
  name: sdk-user
  apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: Role
  name: tenant-user
  apiGroup: rbac.authorization.k8s.io
EOF

# Temporary ClusterRoles
cat <<EOF | kubectl apply -f -
kind: ClusterRole
apiVersion: rbac.authorization.k8s.io/v1
metadata:
  name: cr-tenant-user
rules:
- apiGroups: ["config.openshift.io"]
  resources: ["ingresses"]
  verbs: ["get", "list"]
  resourceNames: ["cluster"]
EOF

cat <<EOF | kubectl apply -f -
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: cr-tenant-user
subjects:
- kind: User
  name: sdk-user
  apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: ClusterRole
  name: cr-tenant-user
  apiGroup: rbac.authorization.k8s.io
EOF

# Cleanup csr/crt/keys from local machine
rm -f ca.crt.base64 sdk-user.crt.base64 sdk-user.key.base64 ca.crt sdk-user.crt sdk-user.key sdk-user.csr ca.key ca.srl kind.csr

# Install CodeFlare SDK
chmod +x ./tests/e2e/install-codeflare-sdk.sh
./tests/e2e/install-codeflare-sdk.sh

# Confirming the user can access the cluster
kubectl get ns default --as sdk-user

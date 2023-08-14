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
: "${KUBERAY_VERSION}"

echo Deploying KubeRay "${KUBERAY_VERSION}"
kubectl apply --server-side -k "github.com/ray-project/kuberay/ray-operator/config/default?ref=${KUBERAY_VERSION}&timeout=180s"

cat <<EOF | kubectl apply -f -
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: mcad-controller-rayclusters
rules:
  - apiGroups:
      - ray.io
    resources:
      - rayclusters
      - rayclusters/finalizers
      - rayclusters/status
    verbs:
      - get
      - list
      - watch
      - create
      - update
      - patch
      - delete
EOF

cat <<EOF | kubectl apply -f -
kind: ClusterRoleBinding
apiVersion: rbac.authorization.k8s.io/v1
metadata:
  name: mcad-controller-rayclusters
subjects:
  - kind: ServiceAccount
    name: codeflare-operator-controller-manager
    namespace: openshift-operators
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: mcad-controller-rayclusters
EOF

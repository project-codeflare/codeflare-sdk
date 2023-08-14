# #!/bin/bash

# # Copyright 2022 IBM, Red Hat
# #
# # Licensed under the Apache License, Version 2.0 (the "License");
# # you may not use this file except in compliance with the License.
# # You may obtain a copy of the License at
# #
# #      http://www.apache.org/licenses/LICENSE-2.0
# #
# # Unless required by applicable law or agreed to in writing, software
# # distributed under the License is distributed on an "AS IS" BASIS,
# # WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# # See the License for the specific language governing permissions and
# # limitations under the License.
# set -euo pipefail
# : "${INGRESS_NGINX_VERSION:=controller-v1.6.4}"

# echo "Creating KinD cluster"
# cat <<EOF | kind create cluster --config=-
# kind: Cluster
# apiVersion: kind.x-k8s.io/v1alpha4
# nodes:
#   - role: control-plane
#     image: kindest/node:v1.25.3@sha256:f52781bc0d7a19fb6c405c2af83abfeb311f130707a0e219175677e366cc45d1
#     kubeadmConfigPatches:
#       - |
#         kind: InitConfiguration
#         nodeRegistration:
#           kubeletExtraArgs:
#             node-labels: "ingress-ready=true"
# EOF

# echo "Deploying Ingress controller into KinD cluster"
# curl https://raw.githubusercontent.com/kubernetes/ingress-nginx/"${INGRESS_NGINX_VERSION}"/deploy/static/provider/kind/deploy.yaml | sed "s/--publish-status-address=localhost/--report-node-internal-ip-address\\n        - --status-update-interval=10/g" | kubectl apply -f -
# kubectl annotate ingressclass nginx "ingressclass.kubernetes.io/is-default-class=true"
# kubectl -n ingress-nginx wait --timeout=300s --for=condition=Available deployments --all


cat <<EOF | kind create cluster --config -
apiVersion: kind.x-k8s.io/v1alpha4
kind: Cluster
nodes:
  - role: control-plane
    kubeadmConfigPatches:
      - |
        kind: InitConfiguration
        nodeRegistration:
          kubeletExtraArgs:
            node-labels: "ingress-ready=true"
    extraPortMappings:
      - containerPort: 80
        hostPort: 80
        listenAddress: "0.0.0.0"
        protocol: tcp
      - containerPort: 443
        hostPort: 443
        listenAddress: "0.0.0.0"
        protocol: tcp
EOF


# install ingress controller on the KinD clsuter
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/kind/deploy.yaml
sleep 10 # Wait for the Kubernetes API Server to create the related resources
kubectl -n ingress-nginx wait --timeout=300s --for=condition=Available deployments --all

# enable ssl passthrough
kubectl patch deploy --type json --patch '[{"op":"add","path": "/spec/template/spec/containers/0/args/-","value":"--enable-ssl-passthrough"}]' ingress-nginx-controller -n ingress-nginx
kubectl logs deploy/ingress-nginx-controller -n ingress-nginx

# # # Deploy codeflare-operator
# # cd codeflare-operator 
# # make deploy -e IMG=quay.io/project-codeflare/codeflare-operator:v1.0.0-rc.1

# # # Install RBAC for MCAD to manage RayCluster
oc apply -f https://raw.githubusercontent.com/opendatahub-io/distributed-workloads/main/codeflare-stack/rbac/mcad-controller-ray-clusterrolebinding.yaml
oc apply -f https://raw.githubusercontent.com/opendatahub-io/distributed-workloads/main/codeflare-stack/rbac/mcad-controller-ray-clusterrole.yaml
oc apply -f tmpingressesrole.yaml
oc apply -f tmpingressesroleb.yaml

# # # Install KubeRay
# # helm repo add kuberay https://ray-project.github.io/kuberay-helm/
# # helm repo update
# # helm install kuberay-operator kuberay/kuberay-operator --version 1.0.0-rc.0





# set -euo pipefail
# : "${INGRESS_NGINX_VERSION:=controller-v1.6.4}"

# echo "Creating KinD cluster"
# cat <<EOF | kind create cluster --config=-
# kind: Cluster
# apiVersion: kind.x-k8s.io/v1alpha4
# nodes:
#   - role: control-plane
#     image: kindest/node:v1.25.3@sha256:f52781bc0d7a19fb6c405c2af83abfeb311f130707a0e219175677e366cc45d1
#     kubeadmConfigPatches:
#       - |
#         kind: InitConfiguration
#         nodeRegistration:
#           kubeletExtraArgs:
#             node-labels: "ingress-ready=true"
# EOF

# echo "Deploying Ingress controller into KinD cluster"
# curl https://raw.githubusercontent.com/kubernetes/ingress-nginx/"${INGRESS_NGINX_VERSION}"/deploy/static/provider/kind/deploy.yaml | sed "s/--publish-status-address=localhost/--report-node-internal-ip-address\\n        - --status-update-interval=10/g" | kubectl apply -f -
# kubectl annotate ingressclass nginx "ingressclass.kubernetes.io/is-default-class=true"
# kubectl -n ingress-nginx wait --timeout=300s --for=condition=Available deployments --all

# kubectl patch deploy --type json --patch '[{"op":"add","path": "/spec/template/spec/containers/0/args/-","value":"--enable-ssl-passthrough"}]' ingress-nginx-controller -n ingress-nginx
# kubectl logs deploy/ingress-nginx-controller -n ingress-nginx


# add marks extra argument --enable-ssl-passthrough to ingress DONE
# dnsmasq for domain to add to /etc/hosts to ingress

# ingress domain to cluster configuration.

# This is where dnsmasq comes in. You can configure dnsmasq
# to resolve dashboard.example.com to the IP address of your
# local ingress controller.

# For dnsmasq guide
# On the make immutable step ignore
# Just add address to that file leave everything else alone

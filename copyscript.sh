#!/bin/bash

# command to be ran on local host and not in the pod
# kubectl apply -f temp-pod.yaml
# kubectl cp ./ default/temp-pod4:/mnt



echo "starting"
namespace=$1
# podname=$(kubectl get pods -n "${namespace}" -o custom-columns=:metadata.name | grep "^sdk")
# kubectl cp ./ ${namespace}/${podname}:/codeflare-sdk

# kubectl cp ./ ${namespace}/temp-pod:/mnt

sleep 60

# Get the name of the pod starting with 'sdk' and its status
read podname podstatus <<< $(kubectl get pods -n "${namespace}" -o custom-columns=:metadata.name,:status.phase | grep "^sdk" | awk '{print $1, $2}')

echo "$podname, $podstatus, $namespace"

# Check if the pod is found and is in 'Running' status
if [[ -n "$podname" && "$podstatus" == "Running" ]]; then
    echo "Pod ${podname} is running. Proceeding to copy files."
    kubectl cp ../.././ "${namespace}/${podname}:/codeflare-sdk"
else
    echo "Pod not found or not running."
    exit 1
fi

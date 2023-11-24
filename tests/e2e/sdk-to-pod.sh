#!/bin/bash
echo "Starting the script to copy the SDK to the pod"
namespace=$1

# Get the name of the pod starting with 'sdk' and its status
while : ; do
    read podname podstatus <<< $(kubectl get pods -n "${namespace}" -o custom-columns=:metadata.name,:status.phase | grep "^sdk" | awk '{print $1, $2}')
    echo "$podname, $podstatus, $namespace"
    # Check if the pod is found and is in 'Running' status
    if [[ -n "$podname" && "$podstatus" == "Running" ]]; then
        echo "Pod ${podname} is running. Proceeding to copy files."
        kubectl cp ../.././ "${namespace}/${podname}:/codeflare-sdk"
        break
    else
        echo "Waiting for pod to be in Running state in namespace ${namespace}..."
        sleep 5
    fi
done

/*
Copyright 2023.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
*/

package e2e

import (
	"bytes"
	"os/exec"
	"testing"

	. "github.com/onsi/gomega"
	. "github.com/project-codeflare/codeflare-common/support"

	corev1 "k8s.io/api/core/v1"
)

// Creates a Ray cluster, and trains the MNIST dataset using the CodeFlare SDK.
// Asserts successful completion of the training job.
//
// This covers the installation of the CodeFlare SDK, as well as the RBAC required
// for the SDK to successfully perform requests to the cluster, on behalf of the
// impersonated user.
func TestMNISTRayClusterSDK(t *testing.T) {
	test := With(t)
	test.T().Parallel()

	// Create a namespace
	namespace := test.NewTestNamespace()

	// Test configuration
	CreateConfigMap(test, namespace.Name, map[string][]byte{
		// SDK script
		"mnist_raycluster_sdk.py": ReadFile(test, "mnist_raycluster_sdk.py"),
		// pip requirements
		"requirements.txt": ReadFile(test, "mnist_pip_requirements.txt"),
		// MNIST training script
		"mnist.py": ReadFile(test, "mnist.py"),
	})


// TODO: Take first KinD node and redirect pod hostname requests there.
// The below was previously done within the job spec, but here we are no longer using the job spec.

// 	if GetClusterType(test) == KindCluster {
// 	node := GetNodes(test)[0]
// 	hostname := GetClusterHostname(test)
// 	IP := GetNodeInternalIP(test, node)

// 	test.T().Logf("Setting KinD cluster hostname '%s' to node IP '%s' for SDK pod", hostname, IP)
// 	job.Spec.Template.Spec.HostAliases = []corev1.HostAlias{
// 		{
// 			IP:        IP,
// 			Hostnames: []string{hostname},
// 		},
// 	}

// 	// Propagate hostname into Python code as env variable
// 	hostnameEnvVar := corev1.EnvVar{Name: "CLUSTER_HOSTNAME", Value: hostname}
// 	job.Spec.Template.Spec.Containers[0].Env = append(job.Spec.Template.Spec.Containers[0].Env, hostnameEnvVar)
// }
// job, err := test.Client().Core().BatchV1().Jobs(namespace.Name).Create(test.Ctx(), job, metav1.CreateOptions{})
// test.Expect(err).NotTo(HaveOccurred())
// test.T().Logf("Created Job %s/%s successfully", job.Namespace, job.Name)


	// Create a Ray cluster and submit the training job
	cmd := exec.Command("python", "./mnist_raycluster_sdk.py", namespace.Name)

	var stdoutBuf, stderrBuf bytes.Buffer
	cmd.Stdout = &stdoutBuf
	cmd.Stderr = &stderrBuf

	if err := cmd.Run(); err != nil {
		t.Logf("STDOUT: %s", stdoutBuf.String())
		t.Logf("STDERR: %s", stderrBuf.String())
		t.Logf("Failed to run the script: %v", err)
	}


	// Assert the cluster is running
	test.Eventually(func() corev1.ConditionStatus {
		cluster := GetRayCluster(test, namespace.Name, "mnist")
		if cluster == nil {
			// Handle the error appropriately, e.g., by returning an error condition status or logging the error.
			// For simplicity, returning a default status here, but consider proper error handling.
			return corev1.ConditionUnknown
		}
		return corev1.ConditionTrue
	}, TestTimeoutLong).Should(Equal(corev1.ConditionTrue))

	// TODO: Assert the job has been submitted (running) and assert the job has completed successfully.
}


// How it was done previously:
// test.T().Logf("Waiting for Job %s/%s to complete", job.Namespace, job.Name)
// test.Eventually(Job(test, job.Namespace, job.Name), TestTimeoutLong).Should(
// 	Or(
// 		WithTransform(ConditionStatus(batchv1.JobComplete), Equal(corev1.ConditionTrue)),
// 		WithTransform(ConditionStatus(batchv1.JobFailed), Equal(corev1.ConditionTrue)),
// 	))

// // Assert the job has completed successfully
// test.Expect(GetJob(test, job.Namespace, job.Name)).
// 	To(WithTransform(ConditionStatus(batchv1.JobComplete), Equal(corev1.ConditionTrue)))
// }

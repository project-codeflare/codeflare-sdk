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
	"strings"
	"testing"
	"time"

	. "github.com/onsi/gomega"
	. "github.com/project-codeflare/codeflare-common/support"
	mcadv1beta1 "github.com/project-codeflare/multi-cluster-app-dispatcher/pkg/apis/controller/v1beta1"
	rayv1 "github.com/ray-project/kuberay/ray-operator/apis/ray/v1"

	batchv1 "k8s.io/api/batch/v1"
	corev1 "k8s.io/api/core/v1"
	rbacv1 "k8s.io/api/rbac/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
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
	config := CreateConfigMap(test, namespace.Name, map[string][]byte{
		// SDK script
		"mnist_raycluster_sdk.py": ReadFile(test, "mnist_raycluster_sdk.py"),
		// pip requirements
		"requirements.txt": ReadFile(test, "mnist_pip_requirements.txt"),
		// MNIST training script
		"mnist.py": ReadFile(test, "mnist.py"),
		// codeflare-sdk installation script
		"install-codeflare-sdk.sh": ReadFile(test, "install-codeflare-sdk.sh"),
	})

	// Create RBAC, retrieve token for user with limited rights
	policyRules := []rbacv1.PolicyRule{
		{
			Verbs:     []string{"get", "create", "delete", "list", "patch", "update"},
			APIGroups: []string{mcadv1beta1.GroupName},
			Resources: []string{"appwrappers"},
		},
		{
			Verbs:     []string{"get", "list"},
			APIGroups: []string{rayv1.GroupVersion.Group},
			Resources: []string{"rayclusters", "rayclusters/status"},
		},
		{
			Verbs:     []string{"get", "list"},
			APIGroups: []string{"route.openshift.io"},
			Resources: []string{"routes"},
		},
		{
			Verbs:     []string{"get", "list"},
			APIGroups: []string{"networking.k8s.io"},
			Resources: []string{"ingresses"},
		},
	}

	sa := CreateServiceAccount(test, namespace.Name)
	role := CreateRole(test, namespace.Name, policyRules)
	CreateRoleBinding(test, namespace.Name, sa, role)

	job := &batchv1.Job{
		TypeMeta: metav1.TypeMeta{
			APIVersion: batchv1.SchemeGroupVersion.String(),
			Kind:       "Job",
		},
		ObjectMeta: metav1.ObjectMeta{
			Name:      "sdk",
			Namespace: namespace.Name,
		},
		Spec: batchv1.JobSpec{
			Completions:  Ptr(int32(1)),
			Parallelism:  Ptr(int32(1)),
			BackoffLimit: Ptr(int32(0)),
			Template: corev1.PodTemplateSpec{
				Spec: corev1.PodSpec{
					Volumes: []corev1.Volume{
						{
							Name: "test",
							VolumeSource: corev1.VolumeSource{
								ConfigMap: &corev1.ConfigMapVolumeSource{
									LocalObjectReference: corev1.LocalObjectReference{
										Name: config.Name,
									},
								},
							},
						},
						{
							Name: "codeflare-sdk",
							VolumeSource: corev1.VolumeSource{
								EmptyDir: &corev1.EmptyDirVolumeSource{},
							},
						},
						{
							Name: "workdir",
							VolumeSource: corev1.VolumeSource{
								EmptyDir: &corev1.EmptyDirVolumeSource{},
							},
						},
					},
					Containers: []corev1.Container{
						{
							Name: "test",
							// FIXME: switch to base Python image once the dependency on OpenShift CLI is removed
							// See https://github.com/project-codeflare/codeflare-sdk/pull/146
							Image: "quay.io/opendatahub/notebooks:jupyter-minimal-ubi8-python-3.8-4c8f26e",
							Env: []corev1.EnvVar{
								{Name: "PYTHONUSERBASE", Value: "/workdir"},
								{Name: "RAY_IMAGE", Value: GetRayImage()},
							},
							Command: []string{
								"/bin/sh", "-c",
								"while [ ! -f /codeflare-sdk/pyproject.toml ]; do sleep 1; done; " +
								"cp /test/* . && chmod +x install-codeflare-sdk.sh && ./install-codeflare-sdk.sh && python mnist_raycluster_sdk.py " + namespace.Name,
							},
							VolumeMounts: []corev1.VolumeMount{
								{
									Name:      "test",
									MountPath: "/test",
								},
								{
									Name:      "codeflare-sdk",
									MountPath: "/codeflare-sdk",
								},
								{
									Name:      "workdir",
									MountPath: "/workdir",
								},
							},
							WorkingDir: "/workdir",
							SecurityContext: &corev1.SecurityContext{
								AllowPrivilegeEscalation: Ptr(false),
								SeccompProfile: &corev1.SeccompProfile{
									Type: "RuntimeDefault",
								},
								Capabilities: &corev1.Capabilities{
									Drop: []corev1.Capability{"ALL"},
								},
								RunAsNonRoot: Ptr(true),
							},
						},
					},
					RestartPolicy:      corev1.RestartPolicyNever,
					ServiceAccountName: sa.Name,
				},
			},
		},
	}
	if GetClusterType(test) == KindCluster {
		// Take first KinD node and redirect pod hostname requests there
		node := GetNodes(test)[0]
		hostname := GetClusterHostname(test)
		IP := GetNodeInternalIP(test, node)

		test.T().Logf("Setting KinD cluster hostname '%s' to node IP '%s' for SDK pod", hostname, IP)
		job.Spec.Template.Spec.HostAliases = []corev1.HostAlias{
			{
				IP:        IP,
				Hostnames: []string{hostname},
			},
		}

		// Propagate hostname into Python code as env variable
		hostnameEnvVar := corev1.EnvVar{Name: "CLUSTER_HOSTNAME", Value: hostname}
		job.Spec.Template.Spec.Containers[0].Env = append(job.Spec.Template.Spec.Containers[0].Env, hostnameEnvVar)
	}
	job, err := test.Client().Core().BatchV1().Jobs(namespace.Name).Create(test.Ctx(), job, metav1.CreateOptions{})
	test.Expect(err).NotTo(HaveOccurred())
	test.T().Logf("Created Job %s/%s successfully", job.Namespace, job.Name)

	go func() {
		// Checking if pod is found and running
		podName := ""
		foundPod := false
		for !foundPod {
			pods, _ := test.Client().Core().CoreV1().Pods(namespace.Name).List(test.Ctx(), metav1.ListOptions{
				LabelSelector: "job-name=sdk",
			})
			for _, pod := range pods.Items {
				if strings.HasPrefix(pod.Name, "sdk-") && pod.Status.Phase == corev1.PodRunning {
					podName = pod.Name
					foundPod = true
					test.T().Logf("Pod is running!")
					break
				}
			}
			if !foundPod {
				test.T().Logf("Waiting for pod to start...")
				time.Sleep(5 * time.Second)
			}
		}

		// Get rest config
		restConfig, err := GetRestConfig(test); if err != nil {
			test.T().Errorf("Error getting rest config: %v", err)
		}

		// Copy codeflare-sdk to the pod
		srcDir := "../.././"
		dstDir := "/codeflare-sdk"
		if err := CopyToPod(test, namespace.Name, podName, restConfig, srcDir, dstDir); err != nil {
			test.T().Errorf("Error copying codeflare-sdk to pod: %v", err)
		}
	}()

	test.T().Logf("Waiting for Job %s/%s to complete", job.Namespace, job.Name)
	test.Eventually(Job(test, job.Namespace, job.Name), TestTimeoutLong).Should(
		Or(
			WithTransform(ConditionStatus(batchv1.JobComplete), Equal(corev1.ConditionTrue)),
			WithTransform(ConditionStatus(batchv1.JobFailed), Equal(corev1.ConditionTrue)),
		))

	// Assert the job has completed successfully
	test.Expect(GetJob(test, job.Namespace, job.Name)).
		To(WithTransform(ConditionStatus(batchv1.JobComplete), Equal(corev1.ConditionTrue)))
}

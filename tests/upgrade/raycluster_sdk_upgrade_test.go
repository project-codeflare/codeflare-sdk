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

package upgrade

import (
	"fmt"
	"testing"

	. "github.com/onsi/gomega"
	mcadv1beta2 "github.com/project-codeflare/appwrapper/api/v1beta2"
	. "github.com/project-codeflare/codeflare-common/support"
	rayv1 "github.com/ray-project/kuberay/ray-operator/apis/ray/v1"

	batchv1 "k8s.io/api/batch/v1"
	corev1 "k8s.io/api/core/v1"
	rbacv1 "k8s.io/api/rbac/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"

	. "github.com/project-codeflare/codeflare-sdk/tests/e2e"
)

var (
	nsName = "test-ns-rayclusterupgrade"
)

// Creates a Ray cluster
func TestMNISTRayClusterUp(t *testing.T) {

	test := With(t)

	// Create a namespace
	namespace := CreateTestNamespaceWithName(test, nsName)
	test.T().Logf("Created namespace %s successfully", namespace.Name)

	// Delete namespace only if test failed
	defer func() {
		if t.Failed() {
			DeleteTestNamespace(test, namespace)
		} else {
			StoreNamespaceLogs(test, namespace)
		}
	}()

	// Test configuration
	config := CreateConfigMap(test, namespace.Name, map[string][]byte{
		// SDK script
		"start_ray_cluster.py": ReadFile(test, "start_ray_cluster.py"),
		// codeflare-sdk installation script
		"install-codeflare-sdk.sh": ReadFile(test, "install-codeflare-sdk.sh"),
	})

	// Create RBAC, retrieve token for user with limited rights
	policyRules := []rbacv1.PolicyRule{
		{
			Verbs:     []string{"get", "create", "delete", "list", "patch", "update"},
			APIGroups: []string{mcadv1beta2.GroupVersion.Group},
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
									"cp /test/* . && chmod +x install-codeflare-sdk.sh && ./install-codeflare-sdk.sh && python start_ray_cluster.py " + namespace.Name,
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
		fmt.Printf("CLUSTER_HOSTNAME environment variable value: %s\n", hostname)
		test.T().Logf("CLUSTER_HOSTNAME environment variable value: %s", hostname)
	}

	job, err := test.Client().Core().BatchV1().Jobs(namespace.Name).Create(test.Ctx(), job, metav1.CreateOptions{})
	test.Expect(err).NotTo(HaveOccurred())
	test.T().Logf("Created Job %s/%s successfully", job.Namespace, job.Name)

	// Setup the codeflare-sdk inside the pod associated to the created job
	SetupCodeflareSDKInsidePod(test, namespace, job.Name)

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

// Submit a Job to the Ray cluster and trains the MNIST dataset using the CodeFlare SDK.
func TestMnistJobSubmit(t *testing.T) {

	test := With(t)

	namespace := GetNamespaceWithName(test, nsName)

	//delete the namespace after test complete
	defer DeleteTestNamespace(test, namespace)

	// Test configuration
	config := CreateConfigMap(test, namespace.Name, map[string][]byte{
		// SDK script
		"mnist_rayjob.py": ReadFile(test, "mnist_rayjob.py"),
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
			APIGroups: []string{mcadv1beta2.GroupVersion.Group},
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

	serviceAccount := CreateServiceAccount(test, namespace.Name)
	role := CreateRole(test, namespace.Name, policyRules)
	CreateRoleBinding(test, namespace.Name, serviceAccount, role)

	job := &batchv1.Job{
		TypeMeta: metav1.TypeMeta{
			APIVersion: batchv1.SchemeGroupVersion.String(),
			Kind:       "Job",
		},
		ObjectMeta: metav1.ObjectMeta{
			Name:      "rayjob",
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
									"cp /test/* . && chmod +x install-codeflare-sdk.sh && ./install-codeflare-sdk.sh && python mnist_rayjob.py " + namespace.Name,
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
					ServiceAccountName: serviceAccount.Name,
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

	job, err := test.Client().Core().BatchV1().Jobs(nsName).Create(test.Ctx(), job, metav1.CreateOptions{})
	test.Expect(err).NotTo(HaveOccurred())
	test.T().Logf("Created Job %s/%s successfully", job.Namespace, job.Name)

	// Setup the codeflare-sdk inside the pod associated to the created job
	SetupCodeflareSDKInsidePod(test, namespace, job.Name)

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

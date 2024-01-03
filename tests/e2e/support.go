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
	"embed"
	"os"
	"path/filepath"

	"github.com/onsi/gomega"
	"k8s.io/apimachinery/pkg/api/meta"
	"k8s.io/apimachinery/pkg/runtime/schema"
	"k8s.io/apimachinery/pkg/runtime/serializer"
	"k8s.io/cli-runtime/pkg/genericclioptions"
	"k8s.io/client-go/discovery"
	"k8s.io/client-go/rest"
	"k8s.io/client-go/tools/clientcmd"
	clientcmdapi "k8s.io/client-go/tools/clientcmd/api"
	"k8s.io/kubectl/pkg/cmd/cp"
	"k8s.io/kubectl/pkg/cmd/util"
	"k8s.io/kubectl/pkg/scheme"

	"github.com/project-codeflare/codeflare-common/support"
)

//go:embed *.py *.txt *.sh
var files embed.FS

func ReadFile(t support.Test, fileName string) []byte {
	t.T().Helper()
	file, err := files.ReadFile(fileName)
	t.Expect(err).NotTo(gomega.HaveOccurred())
	return file
}

func GetRestConfig(t support.Test) (*rest.Config, error) {
	const GroupName = ""
	var SchemeGroupVersion = schema.GroupVersion{Group: GroupName, Version: "v1"}
	kubeconfig := filepath.Join(os.Getenv("HOME"), ".kube", "config")
	restConfig, err := clientcmd.BuildConfigFromFlags("", kubeconfig)
	if err != nil {
		t.T().Errorf("Error building kubeconfig: %v", err)
		return restConfig, err
	}
	restConfig.APIPath = "/api"
	restConfig.GroupVersion = &SchemeGroupVersion
	restConfig.NegotiatedSerializer = serializer.WithoutConversionCodecFactory{CodecFactory: scheme.Codecs}
	return restConfig, nil
}

func CopyToPod(t support.Test, namespace string, podName string, restConfig *rest.Config, srcDir string, dstDir string) error {
	ioStreams, _, _, _ := genericclioptions.NewTestIOStreams()
	copyOptions := cp.NewCopyOptions(ioStreams)
	factory := util.NewFactory(newRestClientGetter(namespace, restConfig))
	if err := copyOptions.Complete(factory, cp.NewCmdCp(factory, ioStreams), []string{srcDir, podName + ":" + dstDir}); err != nil {
		t.T().Errorf("error when completing all the required options: %v", err)
		return err
	}
	if err := copyOptions.Validate(); err != nil {
		t.T().Errorf("error when validating the provided values for CopyOptions: %v", err)
		return err
	}
	if err := copyOptions.Run(); err != nil {
		t.T().Errorf("could not run copy operation: %v", err)
		return err
	}
	return nil
}

// restClientGetter interface is used to get a rest client from a kubeconfig
type restClientGetter struct {
	ClientConfig *rest.Config
	ConfigLoader clientcmd.ClientConfig
}

func newRestClientGetter(namespace string, clientConfig *rest.Config) restClientGetter {
	return restClientGetter{
		ClientConfig: clientConfig,
		ConfigLoader: clientcmd.NewDefaultClientConfig(clientcmdapi.Config{}, &clientcmd.ConfigOverrides{Context: clientcmdapi.Context{Namespace: namespace}}),
	}
}

func (r restClientGetter) ToRESTConfig() (*rest.Config, error) {
	return r.ClientConfig, nil
}

func (r restClientGetter) ToRawKubeConfigLoader() clientcmd.ClientConfig {
	return r.ConfigLoader
}

func (r restClientGetter) ToDiscoveryClient() (discovery.CachedDiscoveryInterface, error) {
	return nil, nil
}

func (r restClientGetter) ToRESTMapper() (meta.RESTMapper, error) {
	return nil, nil
}

# VERSION defines the project version for the bundle.
# Update this value when you upgrade the version of your project.
# To re-generate a bundle for another specific version without changing the standard setup, you can:
# - use the VERSION as arg of the bundle target (e.g make bundle VERSION=v0.0.2)
# - use environment variables to overwrite this value (e.g export VERSION=v0.0.2)
# best if we could detect this. If we cannot, we need to document it somewhere.
# then we can add a patch in the `PHONY: bundle`
# BUNDLE_VERSION is declared as bundle versioning doesn't use semver

PREVIOUS_VERSION ?= v0.0.0-dev
VERSION ?= v0.0.0-dev
BUNDLE_VERSION ?= $(VERSION:v%=%)

# INSTASCALE_VERSION defines the default version of the InstaScale controller
INSTASCALE_VERSION ?= v0.0.9
INSTASCALE_REPO ?= github.com/project-codeflare/instascale

# MCAD_VERSION defines the default version of the MCAD controller
MCAD_VERSION ?= 725a614debe3d34d1547c1659ef5ad49f8f6c5df
MCAD_REPO ?= github.com/project-codeflare/multi-cluster-app-dispatcher
# Upstream MCAD is currently only creating release tags of the form `vX.Y.Z` (i.e the version)
MCAD_CRD ?= ${MCAD_REPO}/config/crd?ref=${MCAD_VERSION}

# KUBERAY_VERSION defines the default version of the KubeRay operator (used for testing)
KUBERAY_VERSION ?= v0.6.0

# RAY_VERSION defines the default version of Ray (used for testing)
RAY_VERSION ?= 2.5.0

# CODEFLARE_SDK_VERSION defines the default version of the CodeFlare SDK
CODEFLARE_SDK_VERSION ?= 0.8.0

# OPERATORS_REPO_ORG points to GitHub repository organization where bundle PR is opened against
# OPERATORS_REPO_FORK_ORG points to GitHub repository fork organization where bundle build is pushed to
OPERATORS_REPO_ORG ?= redhat-openshift-ecosystem
OPERATORS_REPO_FORK_ORG ?= project-codeflare

# CHANNELS define the bundle channels used in the bundle.
# Add a new line here if you would like to change its default config. (E.g CHANNELS = "candidate,fast,stable")
# To re-generate a bundle for other specific channels without changing the standard setup, you can:
# - use the CHANNELS as arg of the bundle target (e.g make bundle CHANNELS=candidate,fast,stable)
# - use environment variables to overwrite this value (e.g export CHANNELS="candidate,fast,stable")
ifneq ($(origin CHANNELS), undefined)
BUNDLE_CHANNELS := --channels=$(CHANNELS)
endif

# DEFAULT_CHANNEL defines the default channel used in the bundle.
# Add a new line here if you would like to change its default config. (E.g DEFAULT_CHANNEL = "stable")
# To re-generate a bundle for any other default channel without changing the default setup, you can:
# - use the DEFAULT_CHANNEL as arg of the bundle target (e.g make bundle DEFAULT_CHANNEL=stable)
# - use environment variables to overwrite this value (e.g export DEFAULT_CHANNEL="stable")
ifneq ($(origin DEFAULT_CHANNEL), undefined)
BUNDLE_DEFAULT_CHANNEL := --default-channel=$(DEFAULT_CHANNEL)
endif
BUNDLE_METADATA_OPTS ?= $(BUNDLE_CHANNELS) $(BUNDLE_DEFAULT_CHANNEL)

# IMAGE_ORG_BASE defines the base container registry and organization for container images.
IMAGE_ORG_BASE ?= quay.io/project-codeflare

# IMAGE_TAG_BASE defines the docker.io namespace and part of the image name for remote images.
# This variable is used to construct full image tags for bundle and catalog images.
#
# For example, running 'make bundle-build bundle-push catalog-build catalog-push' will build and push both
# codeflare.dev/codeflare-operator-bundle:$VERSION and codeflare.dev/codeflare-operator-catalog:$VERSION.
IMAGE_TAG_BASE ?= $(IMAGE_ORG_BASE)/codeflare-operator

# RAY_IMAGE defines the default container image for Ray (used for testing)
RAY_IMAGE ?= rayproject/ray:$(RAY_VERSION)

# BUNDLE_IMG defines the image:tag used for the bundle.
# You can use it as an arg. (E.g make bundle-build BUNDLE_IMG=<some-registry>/<project-name-bundle>:<tag>)
BUNDLE_IMG ?= $(IMAGE_TAG_BASE)-bundle:$(VERSION)

# BUNDLE_GEN_FLAGS are the flags passed to the operator-sdk generate bundle command
BUNDLE_GEN_FLAGS ?= -q --overwrite --version $(BUNDLE_VERSION) $(BUNDLE_METADATA_OPTS)

# USE_IMAGE_DIGESTS defines if images are resolved via tags or digests
# You can enable this value if you would like to use SHA Based Digests
# To enable set flag to true
USE_IMAGE_DIGESTS ?= false
ifeq ($(USE_IMAGE_DIGESTS), true)
	BUNDLE_GEN_FLAGS += --use-image-digests
endif

# Image URL to use all building/pushing image targets
IMG ?= ${IMAGE_TAG_BASE}:${VERSION}
# ENVTEST_K8S_VERSION refers to the version of kubebuilder assets to be downloaded by envtest binary.
ENVTEST_K8S_VERSION = 1.24.2

# Get the currently used golang install path (in GOPATH/bin, unless GOBIN is set)
ifeq (,$(shell go env GOBIN))
GOBIN=$(shell go env GOPATH)/bin
else
GOBIN=$(shell go env GOBIN)
endif

# Setting SHELL to bash allows bash commands to be executed by recipes.
# Options are set to exit when a recipe line exits non-zero or a piped command fails.
SHELL = /usr/bin/env bash -o pipefail
.SHELLFLAGS = -ec

.PHONY: all
all: build

##@ General

# The help target prints out all targets with their descriptions organized
# beneath their categories. The categories are represented by '##@' and the
# target descriptions by '##'. The awk commands is responsible for reading the
# entire set of makefiles included in this invocation, looking for lines of the
# file as xyz: ## something, and then pretty-format the target and help. Then,
# if there's a line with ##@ something, that gets pretty-printed as a category.
# More info on the usage of ANSI control characters for terminal formatting:
# https://en.wikipedia.org/wiki/ANSI_escape_code#SGR_parameters
# More info on the awk command:
# http://linuxcommand.org/lc3_adv_awk.php

.PHONY: help
help: ## Display this help.
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage:\n  make \033[36m<target>\033[0m\n"} /^[a-zA-Z_0-9-]+:.*?##/ { printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2 } /^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) } ' $(MAKEFILE_LIST)

##@ Development

DEFAULTS_TEST_FILE := tests/support/defaults.go

.PHONY: defaults
defaults:
	$(info Regenerating $(DEFAULTS_TEST_FILE))
	@echo "package support" > $(DEFAULTS_TEST_FILE)
	@echo "" >> $(DEFAULTS_TEST_FILE)
	@echo "// ***********************" >> $(DEFAULTS_TEST_FILE)
	@echo "//  DO NOT EDIT THIS FILE"  >> $(DEFAULTS_TEST_FILE)
	@echo "// ***********************" >> $(DEFAULTS_TEST_FILE)
	@echo "" >> $(DEFAULTS_TEST_FILE)
	@echo "const (" >> $(DEFAULTS_TEST_FILE)
	@echo "  CodeFlareSDKVersion = \"$(CODEFLARE_SDK_VERSION)\"" >> $(DEFAULTS_TEST_FILE)
	@echo "  RayVersion = \"$(RAY_VERSION)\"" >> $(DEFAULTS_TEST_FILE)
	@echo "  RayImage = \"$(RAY_IMAGE)\"" >> $(DEFAULTS_TEST_FILE)
	@echo "" >> $(DEFAULTS_TEST_FILE)
	@echo ")" >> $(DEFAULTS_TEST_FILE)
	@echo "" >> $(DEFAULTS_TEST_FILE)

	gofmt -w $(DEFAULTS_TEST_FILE)

.PHONY: manifests
manifests: controller-gen ## Generate RBAC objects.
	$(CONTROLLER_GEN) rbac:roleName=manager-role webhook paths="./..."

.PHONY: fmt
fmt: ## Run go fmt against code.
	go fmt ./...

.PHONY: vet
vet: ## Run go vet against code.
	go vet ./...


##@ Build

.PHONY: modules
modules: ## Update Go dependencies.
	go get $(MCAD_REPO)@$(MCAD_VERSION)
	go get $(INSTASCALE_REPO)@$(INSTASCALE_VERSION)
	go get github.com/ray-project/kuberay/ray-operator
	go mod tidy

.PHONY: build
build: modules defaults fmt vet ## Build manager binary.
	go build -o bin/manager main.go

.PHONY: run
run: modules defaults manifests fmt vet ## Run a controller from your host.
	go run ./main.go

.PHONY: image-build
image-build: test-unit ## Build container image with the manager.
	podman build -t ${IMG} .

.PHONY: image-push
image-push: image-build ## Push container image with the manager.
	podman push ${IMG}

##@ Deployment

ifndef ignore-not-found
  ignore-not-found = false
endif

.PHONY: install
install: manifests kustomize ## Install CRDs into the K8s cluster specified in ~/.kube/config.
	$(SED) -i -E "s|(- )\${MCAD_REPO}.*|\1\${MCAD_CRD}|" config/crd/mcad/kustomization.yaml
	$(KUSTOMIZE) build config/crd | kubectl apply -f -
	git restore config/*

.PHONY: uninstall
uninstall: manifests kustomize ## Uninstall CRDs from the K8s cluster specified in ~/.kube/config. Call with ignore-not-found=true to ignore resource not found errors during deletion.
	$(SED) -i -E "s|(- )\${MCAD_REPO}.*|\1\${MCAD_CRD}|" config/crd/mcad/kustomization.yaml
	$(KUSTOMIZE) build config/crd | kubectl delete --ignore-not-found=$(ignore-not-found) -f -
	git restore config/*

.PHONY: deploy
deploy: manifests kustomize ## Deploy controller to the K8s cluster specified in ~/.kube/config.
	$(SED) -i -E "s|(- )\${MCAD_REPO}.*|\1\${MCAD_CRD}|" config/crd/mcad/kustomization.yaml
	cd config/manager && $(KUSTOMIZE) edit set image controller=${IMG}
	$(KUSTOMIZE) build config/default | kubectl apply -f -
	git restore config/*

.PHONY: undeploy
undeploy: ## Undeploy controller from the K8s cluster specified in ~/.kube/config. Call with ignore-not-found=true to ignore resource not found errors during deletion.
	$(SED) -i -E "s|(- )\${MCAD_REPO}.*|\1\${MCAD_CRD}|" config/crd/mcad/kustomization.yaml
	$(KUSTOMIZE) build config/default | kubectl delete --ignore-not-found=$(ignore-not-found) -f -
	git restore config/*

##@ Build Dependencies

## Location to install dependencies to
LOCALBIN ?= $(shell pwd)/bin
$(LOCALBIN):
	mkdir -p $(LOCALBIN)

## Tool Binaries
KUSTOMIZE ?= $(LOCALBIN)/kustomize
CONTROLLER_GEN ?= $(LOCALBIN)/controller-gen
ENVTEST ?= $(LOCALBIN)/setup-envtest
OPENSHIFT-GOIMPORTS ?= $(LOCALBIN)/openshift-goimports
OPERATOR_SDK ?= $(LOCALBIN)/operator-sdk
GH_CLI ?= $(LOCALBIN)/gh
SED ?= /usr/bin/sed

## Tool Versions
KUSTOMIZE_VERSION ?= v4.5.4
CODEGEN_VERSION ?= v0.27.2
CONTROLLER_TOOLS_VERSION ?= v0.9.2
OPERATOR_SDK_VERSION ?= v1.27.0
GH_CLI_VERSION ?= 2.30.0

KUSTOMIZE_INSTALL_SCRIPT ?= "https://raw.githubusercontent.com/kubernetes-sigs/kustomize/master/hack/install_kustomize.sh"
.PHONY: kustomize
kustomize: $(KUSTOMIZE) ## Download kustomize locally if necessary.
$(KUSTOMIZE): $(LOCALBIN)
	test -s $(LOCALBIN)/kustomize || { curl -s $(KUSTOMIZE_INSTALL_SCRIPT) | bash -s -- $(subst v,,$(KUSTOMIZE_VERSION)) $(LOCALBIN); }

GH_CLI_DL_URL := https://github.com/cli/cli/releases/download/v$(GH_CLI_VERSION)
GH_CLI_DL_FILENAME := gh_$(GH_CLI_VERSION)_$(shell go env GOOS)_$(shell go env GOARCH)
.PHONY: install-gh-cli
install-gh-cli: $(GH_CLI)
$(GH_CLI): $(LOCALBIN)
	curl -L $(GH_CLI_DL_URL)/$(GH_CLI_DL_FILENAME).tar.gz --output $(GH_CLI_DL_FILENAME).tar.gz
	tar -xvzf $(GH_CLI_DL_FILENAME).tar.gz
	cp $(GH_CLI_DL_FILENAME)/bin/gh $(GH_CLI)
	rm -rf $(GH_CLI_DL_FILENAME)
	rm $(GH_CLI_DL_FILENAME).tar.gz

.PHONY: controller-gen
controller-gen: $(CONTROLLER_GEN) ## Download controller-gen locally if necessary.
$(CONTROLLER_GEN): $(LOCALBIN)
	test -s $(LOCALBIN)/controller-gen || GOBIN=$(LOCALBIN) go install sigs.k8s.io/controller-tools/cmd/controller-gen@$(CONTROLLER_TOOLS_VERSION)

.PHONY: envtest
envtest: $(ENVTEST) ## Download envtest-setup locally if necessary.
$(ENVTEST): $(LOCALBIN)
	test -s $(LOCALBIN)/setup-envtest || GOBIN=$(LOCALBIN) go install sigs.k8s.io/controller-runtime/tools/setup-envtest@latest

.PHONY: openshift-goimports
openshift-goimports: $(OPENSHIFT-GOIMPORTS) ## Download openshift-goimports locally if necessary.
$(OPENSHIFT-GOIMPORTS): $(LOCALBIN)
	test -s $(LOCALBIN)/openshift-goimports || GOBIN=$(LOCALBIN) go install github.com/openshift-eng/openshift-goimports@latest

OPERATOR_SDK_DL_URL := https://github.com/operator-framework/operator-sdk/releases/download/$(OPERATOR_SDK_VERSION)
.PHONY: install-operator-sdk
install-operator-sdk: $(OPERATOR_SDK) ## Download fixed version operator-sdk binary for consist outcome
$(OPERATOR_SDK): $(LOCALBIN)
	curl -L $(OPERATOR_SDK_DL_URL)/operator-sdk_$(shell go env GOOS)_$(shell go env GOARCH) --output $(LOCALBIN)/operator-sdk
	chmod +x $(OPERATOR_SDK)

.PHONY: validate-bundle
validate-bundle: install-operator-sdk
	$(OPERATOR_SDK) bundle validate ./bundle --select-optional suite=operatorframework

.PHONY: bundle
bundle: defaults manifests kustomize install-operator-sdk ## Generate bundle manifests and metadata, then validate generated files.
	$(OPERATOR_SDK) generate kustomize manifests -q
	$(SED) -i -E "s|(- )\${MCAD_REPO}.*|\1\${MCAD_CRD}|" config/crd/mcad/kustomization.yaml
	cd config/manager && $(KUSTOMIZE) edit set image controller=$(IMG)
	cd config/manifests && $(KUSTOMIZE) edit add patch --patch '[{"op":"add", "path":"/metadata/annotations/containerImage", "value": "$(IMG)" }]' --kind ClusterServiceVersion
	cd config/manifests && $(KUSTOMIZE) edit add patch --patch '[{"op":"add", "path":"/spec/replaces", "value": "codeflare-operator.$(PREVIOUS_VERSION)" }]' --kind ClusterServiceVersion
	$(KUSTOMIZE) build config/manifests | $(OPERATOR_SDK) generate bundle $(BUNDLE_GEN_FLAGS)
	$(MAKE) validate-bundle
	git restore config/*

.PHONY: bundle-build
bundle-build: bundle ## Build the bundle image.
	podman build -f bundle.Dockerfile -t $(BUNDLE_IMG) .

.PHONY: bundle-push
bundle-push: ## Push the bundle image.
	podman push $(BUNDLE_IMG) $(BUNDLE_PUSH_OPT)

.PHONY: openshift-community-operator-release
openshift-community-operator-release: install-gh-cli bundle ## build bundle and create PR in OpenShift community operators repository
	git clone https://x-access-token:$(GH_TOKEN)@github.com/$(OPERATORS_REPO_FORK_ORG)/community-operators-prod.git
	cd community-operators-prod && git remote add upstream https://github.com/$(OPERATORS_REPO_ORG)/community-operators-prod.git && git pull upstream main && git push origin main
	cp -r bundle community-operators-prod/operators/codeflare-operator/$(BUNDLE_VERSION)
	cd community-operators-prod && git checkout -b codeflare-release-$(BUNDLE_VERSION) && git add operators/codeflare-operator/$(BUNDLE_VERSION)/* && git commit -m "add bundle manifests codeflare version $(BUNDLE_VERSION)" --signoff && git push origin codeflare-release-$(BUNDLE_VERSION)
	gh pr create --repo $(OPERATORS_REPO_ORG)/community-operators-prod --title "CodeFlare $(BUNDLE_VERSION)" --body "New release of codeflare operator" --head $(OPERATORS_REPO_FORK_ORG):codeflare-release-$(BUNDLE_VERSION) --base main
	rm -rf community-operators-prod

.PHONY: opm
OPM = ./bin/opm
opm: ## Download opm locally if necessary.
ifeq (,$(wildcard $(OPM)))
ifeq (,$(shell which opm 2>/dev/null))
	@{ \
	set -e ;\
	mkdir -p $(dir $(OPM)) ;\
	OS=$(shell go env GOOS) && ARCH=$(shell go env GOARCH) && \
	curl -sSLo $(OPM) https://github.com/operator-framework/operator-registry/releases/download/v1.23.0/$${OS}-$${ARCH}-opm ;\
	chmod +x $(OPM) ;\
	}
else
OPM = $(shell which opm)
endif
endif

# A comma-separated list of bundle images (e.g. make catalog-build BUNDLE_IMGS=example.com/operator-bundle:v0.1.0,example.com/operator-bundle:v0.2.0).
# These images MUST exist in a registry and be pull-able.
BUNDLE_IMGS ?= $(BUNDLE_IMG)

# The image tag given to the resulting catalog image (e.g. make catalog-build CATALOG_IMG=example.com/operator-catalog:v0.2.0).
CATALOG_IMG ?= $(IMAGE_TAG_BASE)-catalog:$(VERSION)

# Set CATALOG_BASE_IMG to an existing catalog image tag to add $BUNDLE_IMGS to that image.
ifneq ($(origin CATALOG_BASE_IMG), undefined)
FROM_INDEX_OPT := --from-index $(CATALOG_BASE_IMG)
endif

# Build a catalog image by adding bundle images to an empty catalog using the operator package manager tool, 'opm'.
# This recipe invokes 'opm' in 'semver' bundle add mode. For more information on add modes, see:
# https://github.com/operator-framework/community-operators/blob/7f1438c/docs/packaging-operator.md#updating-your-existing-operator
.PHONY: catalog-build
catalog-build: opm ## Build a catalog image.
	$(OPM) index add --container-tool podman --mode semver --tag $(CATALOG_IMG) --bundles $(BUNDLE_IMGS) $(FROM_INDEX_OPT)

# Build a catalog image by adding bundle images to existing catalog using the operator package manager tool, 'opm'.
.PHONY: catalog-build-from-index
catalog-build-from-index: opm ## Build a catalog image.
	mkdir catalog
	$(OPM) render $(CATALOG_BASE_IMG) -o yaml > catalog/bundles.yaml
	$(OPM) render $(BUNDLE_IMG) $(OPM_BUNDLE_OPT) > catalog/codeflare-operator-bundle.yaml
	$(SED) -i -E "s/(.*)(- name: codeflare-operator.$(PREVIOUS_VERSION).*)/\1- name: codeflare-operator.$(VERSION)\n  replaces: codeflare-operator.$(PREVIOUS_VERSION)\n\2/" catalog/bundles.yaml
	$(OPM) validate catalog
	$(OPM) generate dockerfile catalog
	podman build . -f catalog.Dockerfile -t $(CATALOG_IMG)

# Push the catalog image.
.PHONY: catalog-push
catalog-push: ## Push a catalog image.
	podman push $(CATALOG_IMG) $(CATALOG_PUSH_OPT)

.PHONY: test-unit
test-unit: defaults manifests fmt vet envtest ## Run unit tests.
	KUBEBUILDER_ASSETS="$(shell $(ENVTEST) use $(ENVTEST_K8S_VERSION) --bin-dir $(LOCALBIN) -p path)" go test $(go list ./... | grep -v /test/) -coverprofile cover.out

.PHONY: test-e2e
test-e2e: ## Run e2e tests.
	go test -timeout 30m -v ./tests/e2e -run TestMNISTRayClusterSDK

.PHONY: kind-e2e
kind-e2e: ## Set up e2e KinD cluster.
	tests/e2e/kind.sh

.PHONY: setup-e2e
setup-e2e: ## Set up e2e tests.
	KUBERAY_VERSION=$(KUBERAY_VERSION) tests/e2e/setup.sh

.PHONY: imports
imports: openshift-goimports ## Organize imports in go files using openshift-goimports. Example: make imports
	$(OPENSHIFT-GOIMPORTS)

.PHONY: verify-imports
verify-imports: openshift-goimports ## Run import verifications.
	./hack/verify-imports.sh $(OPENSHIFT-GOIMPORTS)

.PHONY: scorecard-bundle
scorecard-bundle: install-operator-sdk ## Run scorecard tests on bundle image.
	$(OPERATOR_SDK) scorecard bundle

# Image tag for image containing e2e tests
E2E_TEST_IMAGE_VERSION ?= latest
E2E_TEST_IMAGE ?= quay.io/opendatahub/codeflare-sdk-tests:${E2E_TEST_IMAGE_VERSION}

# Build the test image
.PHONY: build-test-image
build-test-image:
	@echo "Building test image: $(E2E_TEST_IMAGE)"
	# Build the Docker image using podman
	podman build -f images/tests/Dockerfile -t $(E2E_TEST_IMAGE) .

# Push the test image
.PHONY: push-test-image
push-test-image:
	@echo "Pushing test image: $(E2E_TEST_IMAGE)"
	podman push $(E2E_TEST_IMAGE)


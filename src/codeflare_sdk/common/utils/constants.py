RAY_VERSION = "2.47.1"
"""
The below are used to define the default runtime image for the Ray Cluster.
* For python 3.11:ray:2.47.1-py311-cu121
* For python 3.12:ray:2.47.1-py312-cu121
"""
CUDA_PY311_RUNTIME_IMAGE = "quay.io/modh/ray@sha256:6d076aeb38ab3c34a6a2ef0f58dc667089aa15826fa08a73273c629333e12f1e"
CUDA_PY312_RUNTIME_IMAGE = "quay.io/modh/ray@sha256:23860dfe2e47bb69709b3883b08fd1a4d836ce02eaf8d0afeeafe6986d0fc8fb"

# Centralized image selection
SUPPORTED_PYTHON_VERSIONS = {
    "3.11": CUDA_PY311_RUNTIME_IMAGE,
    "3.12": CUDA_PY312_RUNTIME_IMAGE,
}

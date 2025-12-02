RAY_VERSION = "2.52.1"
"""
The below are used to define the default runtime image for the Ray Cluster.
* For python 3.11:ray:2.52.1-py311-cu121
* For python 3.12:ray:2.52.1-py312-cu128
"""
CUDA_PY311_RUNTIME_IMAGE = "quay.io/modh/ray@sha256:TODO"
CUDA_PY312_RUNTIME_IMAGE = "quay.io/modh/ray@sha256:TODO"

# Centralized image selection
SUPPORTED_PYTHON_VERSIONS = {
    "3.11": CUDA_PY311_RUNTIME_IMAGE,
    "3.12": CUDA_PY312_RUNTIME_IMAGE,
}
MOUNT_PATH = "/home/ray/files"

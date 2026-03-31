RAY_VERSION = "2.52.1"
"""
The below are used to define the default runtime image for the Ray Cluster.
* For python 3.11:ray:2.52.1-py311-cu121
* For python 3.12:ray:2.52.1-py312-cu128
"""
CUDA_PY311_RUNTIME_IMAGE = "quay.io/modh/ray@sha256:595b3acd10244e33fca1ed5469dccb08df66f470df55ae196f80e56edf35ad5a"
CUDA_PY312_RUNTIME_IMAGE = "quay.io/modh/ray@sha256:7b9c6d524b64a07746caa7dc89e691fc40eb4c2b4e41ffde8361bcd8d3c94d68"

# Centralized image selection
SUPPORTED_PYTHON_VERSIONS = {
    "3.11": CUDA_PY311_RUNTIME_IMAGE,
    "3.12": CUDA_PY312_RUNTIME_IMAGE,
}
MOUNT_PATH = "/home/ray/files"

RAY_VERSION = "2.52.1"
"""
The below are used to define the default runtime image for the Ray Cluster.
* For python 3.11:ray:2.52.1-py311-cu121
* For python 3.12:ray:2.52.1-py312-cu128
"""
CUDA_PY311_RUNTIME_IMAGE = "quay.io/modh/ray@sha256:595b3acd10244e33fca1ed5469dccb08df66f470df55ae196f80e56edf35ad5a"
CUDA_PY312_RUNTIME_IMAGE = "quay.io/modh/ray@sha256:6b135421b6e756593a58b4df6664f82fc4b55237ca81475f2867518f15fe6d84"

# Centralized image selection
SUPPORTED_PYTHON_VERSIONS = {
    "3.11": CUDA_PY311_RUNTIME_IMAGE,
    "3.12": CUDA_PY312_RUNTIME_IMAGE,
}
MOUNT_PATH = "/home/ray/files"

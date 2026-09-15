RAY_VERSION = "2.58.0"
"""
The below are used to define the default runtime image for the Ray Cluster.
* For python 3.11:ray:2.52.1-py311-cu121
* For python 3.12:ray:2.58.0-py312-cu128
"""
CUDA_PY311_RUNTIME_IMAGE = "quay.io/modh/ray@sha256:595b3acd10244e33fca1ed5469dccb08df66f470df55ae196f80e56edf35ad5a"
CUDA_PY312_RUNTIME_IMAGE = "quay.io/modh/ray@sha256:8183007c9b46b359bdc75ea74346f10d642e585bb4f22fa3aa02524b3c966fa0"

# Centralized image selection
SUPPORTED_PYTHON_VERSIONS = {
    "3.11": CUDA_PY311_RUNTIME_IMAGE,
    "3.12": CUDA_PY312_RUNTIME_IMAGE,
}
MOUNT_PATH = "/home/ray/files"

import os
import random
import string


def get_ray_image():
    default_ray_image = "quay.io/project-codeflare/ray:latest-py39-cu118"
    return os.getenv("RAY_IMAGE", default_ray_image)


def random_choice():
    alphabet = string.ascii_lowercase + string.digits
    return "".join(random.choices(alphabet, k=5))

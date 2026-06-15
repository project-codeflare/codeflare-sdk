# Copyright 2024 IBM, Red Hat
#
# Shared identifiers for Ray upgrade qualification tests (2.25 pre / 3.x post).

NAMESPACE = "test-ns-rayupgrade"
CLUSTER_NAME = "mnist"

CLUSTER_QUEUE = "cluster-queue-mnist"
RESOURCE_FLAVOR = "default-flavor-mnist"
LOCAL_QUEUE = "local-queue-mnist"

# Matches rhoai-upgrade-helpers ray_cluster_migration.py
PRE_UPGRADE_BACKUP_ANNOTATION = "odh.ray.io/pre-upgrade-backup-taken"
SECURE_NETWORK_ANNOTATION = "odh.ray.io/secure-trusted-network"

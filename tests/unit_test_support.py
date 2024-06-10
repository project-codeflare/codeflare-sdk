from codeflare_sdk.cluster.cluster import (
    Cluster,
    ClusterConfiguration,
)


def createClusterConfig():
    config = ClusterConfiguration(
        name="unit-test-cluster",
        namespace="ns",
        num_workers=2,
        min_cpus=3,
        max_cpus=4,
        min_memory=5,
        max_memory=6,
        num_gpus=7,
        appwrapper=True,
        machine_types=["cpu.small", "gpu.large"],
        image_pull_secrets=["unit-test-pull-secret"],
        image="quay.io/project-codeflare/ray:2.20.0-py39-cu118",
        write_to_file=True,
    )
    return config


def createClusterWithConfig(mocker):
    mocker.patch("kubernetes.config.load_kube_config", return_value="ignore")
    mocker.patch(
        "kubernetes.client.CustomObjectsApi.get_cluster_custom_object",
        return_value={"spec": {"domain": "apps.cluster.awsroute.org"}},
    )
    cluster = Cluster(createClusterConfig())
    return cluster

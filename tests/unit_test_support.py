from codeflare_sdk.job.jobs import (
    DDPJobDefinition,
    DDPJob,
)

from codeflare_sdk.cluster.cluster import (
    Cluster,
    ClusterConfiguration,
)


def createTestDDP():
    ddp = DDPJobDefinition(
        script="test.py",
        m=None,
        script_args=["test"],
        name="test",
        cpu=1,
        gpu=0,
        memMB=1024,
        h=None,
        j="2x1",
        env={"test": "test"},
        max_retries=0,
        mounts=[],
        rdzv_port=29500,
        scheduler_args={"requirements": "test"},
    )
    return ddp


def createDDPJob_no_cluster(ddp_def, cluster):
    return DDPJob(ddp_def, cluster)


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
        instascale=True,
        machine_types=["cpu.small", "gpu.large"],
        image_pull_secrets=["unit-test-pull-secret"],
        ingress_domain="apps.cluster.awsroute.org",
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


def createDDPJob_with_cluster(mocker, ddp_def, cluster=None):
    cluster = createClusterWithConfig(mocker)
    return DDPJob(ddp_def, cluster)

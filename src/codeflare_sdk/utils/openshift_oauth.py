from urllib3.util import parse_url
from .generate_yaml import gen_dashboard_ingress_name
from .kube_api_helpers import _get_api_host
from base64 import b64decode

from ..cluster.auth import config_check, api_config_handler

from kubernetes import client


def create_openshift_oauth_objects(cluster_name, namespace):
    config_check()
    api_client = api_config_handler() or client.ApiClient()
    oauth_port = 8443
    oauth_sa_name = f"{cluster_name}-oauth-proxy"
    tls_secret_name = _gen_tls_secret_name(cluster_name)
    service_name = f"{cluster_name}-oauth"
    port_name = "oauth-proxy"
    host = _get_api_host(api_client)

    # replace "^api" with the expected host
    host = f"{gen_dashboard_ingress_name(cluster_name)}-{namespace}.apps" + host.lstrip(
        "api"
    )

    _create_or_replace_oauth_sa(namespace, oauth_sa_name, host)
    _create_or_replace_oauth_service_obj(
        cluster_name, namespace, oauth_port, tls_secret_name, service_name, port_name
    )
    _create_or_replace_oauth_ingress_object(
        cluster_name, namespace, service_name, port_name, host
    )
    _create_or_replace_oauth_rb(cluster_name, namespace, oauth_sa_name)


def _create_or_replace_oauth_sa(namespace, oauth_sa_name, host):
    api_client = api_config_handler()
    oauth_sa = client.V1ServiceAccount(
        api_version="v1",
        kind="ServiceAccount",
        metadata=client.V1ObjectMeta(
            name=oauth_sa_name,
            namespace=namespace,
            annotations={
                "serviceaccounts.openshift.io/oauth-redirecturi.first": f"https://{host}"
            },
        ),
    )
    try:
        client.CoreV1Api(api_client).create_namespaced_service_account(
            namespace=namespace, body=oauth_sa
        )
    except client.ApiException as e:
        if e.reason == "Conflict":
            client.CoreV1Api(api_client).replace_namespaced_service_account(
                namespace=namespace,
                body=oauth_sa,
                name=oauth_sa_name,
            )
        else:
            raise e


def _create_or_replace_oauth_rb(cluster_name, namespace, oauth_sa_name):
    api_client = api_config_handler()
    oauth_crb = client.V1ClusterRoleBinding(
        api_version="rbac.authorization.k8s.io/v1",
        kind="ClusterRoleBinding",
        metadata=client.V1ObjectMeta(name=f"{cluster_name}-rb"),
        role_ref=client.V1RoleRef(
            api_group="rbac.authorization.k8s.io",
            kind="ClusterRole",
            name="system:auth-delegator",
        ),
        subjects=[
            client.V1Subject(
                kind="ServiceAccount", name=oauth_sa_name, namespace=namespace
            )
        ],
    )
    try:
        client.RbacAuthorizationV1Api(api_client).create_cluster_role_binding(
            body=oauth_crb
        )
    except client.ApiException as e:
        if e.reason == "Conflict":
            client.RbacAuthorizationV1Api(api_client).replace_cluster_role_binding(
                body=oauth_crb, name=f"{cluster_name}-rb"
            )
        else:
            raise e


def _gen_tls_secret_name(cluster_name):
    return f"{cluster_name}-proxy-tls-secret"


def delete_openshift_oauth_objects(cluster_name, namespace):
    # NOTE: it might be worth adding error handling here, but shouldn't be necessary because cluster.down(...) checks
    # for an existing cluster before calling this => the objects should never be deleted twice
    api_client = api_config_handler()
    oauth_sa_name = f"{cluster_name}-oauth-proxy"
    service_name = f"{cluster_name}-oauth"
    client.CoreV1Api(api_client).delete_namespaced_service_account(
        name=oauth_sa_name, namespace=namespace
    )
    client.CoreV1Api(api_client).delete_namespaced_service(
        name=service_name, namespace=namespace
    )
    client.NetworkingV1Api(api_client).delete_namespaced_ingress(
        name=f"{cluster_name}-ingress", namespace=namespace
    )
    client.RbacAuthorizationV1Api(api_client).delete_cluster_role_binding(
        name=f"{cluster_name}-rb"
    )


def _create_or_replace_oauth_service_obj(
    cluster_name: str,
    namespace: str,
    oauth_port: int,
    tls_secret_name: str,
    service_name: str,
    port_name: str,
) -> client.V1Service:
    api_client = api_config_handler()
    oauth_service = client.V1Service(
        api_version="v1",
        kind="Service",
        metadata=client.V1ObjectMeta(
            annotations={
                "service.beta.openshift.io/serving-cert-secret-name": tls_secret_name
            },
            name=service_name,
            namespace=namespace,
        ),
        spec=client.V1ServiceSpec(
            ports=[
                client.V1ServicePort(
                    name=port_name,
                    protocol="TCP",
                    port=443,
                    target_port=oauth_port,
                )
            ],
            selector={
                "app.kubernetes.io/created-by": "kuberay-operator",
                "app.kubernetes.io/name": "kuberay",
                "ray.io/cluster": cluster_name,
                "ray.io/identifier": f"{cluster_name}-head",
                "ray.io/node-type": "head",
            },
        ),
    )
    try:
        client.CoreV1Api(api_client).create_namespaced_service(
            namespace=namespace, body=oauth_service
        )
    except client.ApiException as e:
        if e.reason == "Conflict":
            client.CoreV1Api(api_client).replace_namespaced_service(
                namespace=namespace, body=oauth_service, name=service_name
            )
        else:
            raise e


def _create_or_replace_oauth_ingress_object(
    cluster_name: str,
    namespace: str,
    service_name: str,
    port_name: str,
    host: str,
) -> client.V1Ingress:
    api_client = api_config_handler()
    ingress = client.V1Ingress(
        api_version="networking.k8s.io/v1",
        kind="Ingress",
        metadata=client.V1ObjectMeta(
            annotations={"route.openshift.io/termination": "passthrough"},
            name=f"{cluster_name}-ingress",
            namespace=namespace,
        ),
        spec=client.V1IngressSpec(
            rules=[
                client.V1IngressRule(
                    host=host,
                    http=client.V1HTTPIngressRuleValue(
                        paths=[
                            client.V1HTTPIngressPath(
                                backend=client.V1IngressBackend(
                                    service=client.V1IngressServiceBackend(
                                        name=service_name,
                                        port=client.V1ServiceBackendPort(
                                            name=port_name
                                        ),
                                    )
                                ),
                                path_type="ImplementationSpecific",
                            )
                        ]
                    ),
                )
            ]
        ),
    )
    try:
        client.NetworkingV1Api(api_client).create_namespaced_ingress(
            namespace=namespace, body=ingress
        )
    except client.ApiException as e:
        if e.reason == "Conflict":
            client.NetworkingV1Api(api_client).replace_namespaced_ingress(
                namespace=namespace, body=ingress, name=f"{cluster_name}-ingress"
            )
        else:
            raise e

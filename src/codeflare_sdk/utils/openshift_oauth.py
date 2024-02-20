from urllib3.util import parse_url
import yaml

from ..cluster.auth import config_check, api_config_handler

from kubernetes import client
from kubernetes import dynamic


def _route_api_getter():
    return dynamic.DynamicClient(
        api_config_handler() or client.ApiClient()
    ).resources.get(api_version="route.openshift.io/v1", kind="Route")


def create_openshift_oauth_objects(cluster_name, namespace):
    config_check()
    oauth_port = 8443
    oauth_sa_name = f"{cluster_name}-oauth-proxy"
    tls_secret_name = _gen_tls_secret_name(cluster_name)
    service_name = f"{cluster_name}-oauth"
    port_name = "oauth-proxy"

    _create_or_replace_oauth_sa(namespace, oauth_sa_name, cluster_name)
    _create_or_replace_oauth_service_obj(
        cluster_name, namespace, oauth_port, tls_secret_name, service_name, port_name
    )
    _create_or_replace_oauth_route_object(
        cluster_name,
        namespace,
        service_name,
        port_name,
    )
    _create_or_replace_oauth_rb(cluster_name, namespace, oauth_sa_name)


def _create_or_replace_oauth_sa(namespace, oauth_sa_name, cluster_name):
    oauth_sa = client.V1ServiceAccount(
        api_version="v1",
        kind="ServiceAccount",
        metadata=client.V1ObjectMeta(
            name=oauth_sa_name,
            namespace=namespace,
            annotations={
                "serviceaccounts.openshift.io/oauth-redirectreference.first": '{"kind":"OAuthRedirectReference","apiVersion":"v1","reference":{"kind":"Route","name":"'
                + "ray-dashboard-"
                + cluster_name
                + '"}}'
            },
        ),
    )
    try:
        client.CoreV1Api(api_config_handler()).create_namespaced_service_account(
            namespace=namespace, body=oauth_sa
        )
    except client.ApiException as e:
        if e.reason == "Conflict":
            client.CoreV1Api(api_config_handler()).replace_namespaced_service_account(
                namespace=namespace,
                body=oauth_sa,
                name=oauth_sa_name,
            )
        else:
            raise e


def _create_or_replace_oauth_rb(cluster_name, namespace, oauth_sa_name):
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
        client.RbacAuthorizationV1Api(api_config_handler()).create_cluster_role_binding(
            body=oauth_crb
        )
    except client.ApiException as e:
        if e.reason == "Conflict":
            client.RbacAuthorizationV1Api(
                api_config_handler()
            ).replace_cluster_role_binding(body=oauth_crb, name=f"{cluster_name}-rb")
        else:
            raise e


def _gen_tls_secret_name(cluster_name):
    return f"{cluster_name}-proxy-tls-secret"


def delete_openshift_oauth_objects(cluster_name, namespace):
    # NOTE: it might be worth adding error handling here, but shouldn't be necessary because cluster.down(...) checks
    # for an existing cluster before calling this => the objects should never be deleted twice
    oauth_sa_name = f"{cluster_name}-oauth-proxy"
    service_name = f"{cluster_name}-oauth"
    v1_routes = _route_api_getter()
    client.CoreV1Api(api_config_handler()).delete_namespaced_service_account(
        name=oauth_sa_name, namespace=namespace
    )
    client.CoreV1Api(api_config_handler()).delete_namespaced_service(
        name=service_name, namespace=namespace
    )
    v1_routes.delete(name=f"ray-dashboard-{cluster_name}", namespace=namespace)
    client.RbacAuthorizationV1Api(api_config_handler()).delete_cluster_role_binding(
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
        client.CoreV1Api(api_config_handler()).create_namespaced_service(
            namespace=namespace, body=oauth_service
        )
    except client.ApiException as e:
        if e.reason == "Conflict":
            client.CoreV1Api(api_config_handler()).replace_namespaced_service(
                namespace=namespace, body=oauth_service, name=service_name
            )
        else:
            raise e


def _create_or_replace_oauth_route_object(
    cluster_name: str,
    namespace: str,
    service_name: str,
    port_name: str,
):
    route = f"""
        apiVersion: route.openshift.io/v1
        kind: Route
        metadata:
            name: ray-dashboard-{cluster_name}
            namespace: {namespace}
        spec:
            port:
                targetPort: {port_name}
            tls:
                termination: reencrypt
            to:
                kind: Service
                name: {service_name}
    """
    route_data = yaml.safe_load(route)
    v1_routes = _route_api_getter()
    try:
        existing_route = v1_routes.get(
            name=f"ray-dashboard-{cluster_name}", namespace=namespace
        )
        route_data["metadata"]["resourceVersion"] = existing_route["metadata"][
            "resourceVersion"
        ]
        v1_routes.replace(body=route_data)
    except dynamic.client.ApiException:
        v1_routes.create(body=route_data)

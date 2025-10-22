# Copyright 2024 IBM, Red Hat
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
The cluster sub-module contains the definition of the Cluster object, which represents
the resources requested by the user. It also contains functions for checking the
cluster setup queue, a list of all existing clusters, and the user's working namespace.
"""

from time import sleep
from typing import List as ListType, Optional, Tuple, Dict, Any
import copy

from ray.job_submission import JobSubmissionClient, JobStatus
import time
import uuid
import warnings

from ...common.utils import get_current_namespace

from ...common.kubernetes_cluster.auth import (
    config_check,
    get_api_client,
)
from . import pretty_print
from .build_ray_cluster import build_ray_cluster, head_worker_gpu_count_from_cluster
from .build_ray_cluster import write_to_file as write_cluster_to_file
from ...common import _kube_api_error_handling

from .config import ClusterConfiguration
from .status import (
    CodeFlareClusterStatus,
    RayCluster,
    RayClusterStatus,
)
from ..rayjobs.status import KueueWorkloadInfo
from ..appwrapper import (
    AppWrapper,
    AppWrapperStatus,
)
from ...common.widgets.widgets import (
    cluster_apply_down_buttons,
    is_notebook,
)
from kubernetes import client
import yaml
import os
import requests

from kubernetes import config
from kubernetes.dynamic import DynamicClient
from kubernetes import client as k8s_client
from kubernetes.client.rest import ApiException

# Flag to track if ipywidgets is available
WIDGETS_AVAILABLE = True
try:
    import ipywidgets as widgets
    from IPython.display import display
except ImportError:
    WIDGETS_AVAILABLE = False

CF_SDK_FIELD_MANAGER = "codeflare-sdk"


class Cluster:
    """
    An object for requesting, bringing up, and taking down resources.
    Can also be used for seeing the resource cluster status and details.

    Note that currently, the underlying implementation is a Ray cluster.
    """
    
    # Class variable for global widget preference
    _default_use_widgets = False
    
    @classmethod
    def set_widgets_default(cls, use_widgets: bool) -> None:
        """Set the default widget display preference for all Cluster methods."""
        cls._default_use_widgets = use_widgets
    
    @classmethod
    def get_widgets_default(cls) -> bool:
        """Get the current default widget display preference."""
        return cls._default_use_widgets
        
    @staticmethod
    def Status(cluster_name: str, namespace: str = "default", use_widgets: Optional[bool] = None, return_status: bool = False) -> Optional[Tuple[RayClusterStatus, bool]]:
        """
        Get the status of a RayCluster.
        
        Args:
            cluster_name: Name of the RayCluster
            namespace: Kubernetes namespace
            use_widgets: Whether to use Jupyter widgets for display (overrides global setting)
            return_status: Whether to return the status tuple instead of displaying
            
        Returns:
            Optional[Tuple[RayClusterStatus, bool]]: Status and ready state if return_status=True
        """
        # Check if Kubernetes config is available
        if not config_check():
            return None if not return_status else (RayClusterStatus.UNKNOWN, False)
            
        # Determine widget usage
        use_widgets = use_widgets if use_widgets is not None else Cluster._default_use_widgets
        if use_widgets and not WIDGETS_AVAILABLE:
            # Widgets not available, falling back to console output
            pass
            use_widgets = False
            
        try:
            # Get RayCluster
            api = client.CustomObjectsApi(get_api_client())
            cluster = api.get_namespaced_custom_object(
                group="ray.io",
                version="v1",
                namespace=namespace,
                plural="rayclusters",
                name=cluster_name
            )
            
            if not cluster:
                if use_widgets:
                    Cluster._display_cluster_status_widget(None, cluster_name, namespace)
                else:
                    print_no_resources_found()
                return None if not return_status else (RayClusterStatus.UNKNOWN, False)
                
            # Parse cluster info
            cluster_info = _map_to_ray_cluster(cluster)
            if not cluster_info:
                if use_widgets:
                    Cluster._display_cluster_status_widget(None, cluster_name, namespace)
                else:
                    print_no_resources_found()
                return None if not return_status else (RayClusterStatus.UNKNOWN, False)
                
            # Check if cluster is managed by AppWrapper
            if cluster["metadata"].get("ownerReferences"):
                for owner in cluster["metadata"]["ownerReferences"]:
                    if owner["kind"] == "AppWrapper":
                        cluster_info.is_appwrapper = True
                        break
                        
            # Get Kueue workload info if cluster is managed by AppWrapper
            if cluster_info.is_appwrapper:
                workload_info = Cluster._get_cluster_kueue_workload_info(cluster_name, namespace)
                if workload_info:
                    cluster_info.local_queue = workload_info.name
                    cluster_info.kueue_workload = workload_info
                    
            # Get dashboard URL
            cluster_info.dashboard = Cluster._get_cluster_dashboard_url(cluster_name, namespace)
            
            # Display status
            if use_widgets:
                Cluster._display_cluster_status_widget(cluster_info)
            else:
                print_cluster_status(cluster_info)
                
            # Return status tuple if requested
            if return_status:
                ready = cluster_info.status == RayClusterStatus.READY
                return cluster_info.status, ready
                
            return None
            
        except Exception as e:
            error_msg = _kube_api_error_handling(e)
            if return_status:
                return RayClusterStatus.UNKNOWN, False
            return None
            
    @staticmethod
    def List(namespace: str = "default", page: int = 1, page_size: int = 10, use_widgets: Optional[bool] = None, return_list: bool = False) -> Optional[ListType[RayCluster]]:
        """
        List all RayClusters in the specified namespace with pagination.
        
        Args:
            namespace: Kubernetes namespace
            page: Page number (1-based)
            page_size: Number of items per page
            use_widgets: Whether to use Jupyter widgets for display (overrides global setting)
            return_list: Whether to return the list instead of displaying
            
        Returns:
            Optional[List[RayCluster]]: List of RayCluster objects if return_list=True
        """
        # Check if Kubernetes config is available
        if not config_check():
            return None if not return_list else []
            
        # Determine widget usage
        use_widgets = use_widgets if use_widgets is not None else Cluster._default_use_widgets
        if use_widgets and not WIDGETS_AVAILABLE:
            # Widgets not available, falling back to console output
            pass
            use_widgets = False
            
        try:
            # Get all RayClusters
            api = client.CustomObjectsApi(get_api_client())
            clusters = api.list_namespaced_custom_object(
                group="ray.io",
                version="v1",
                namespace=namespace,
                plural="rayclusters"
            )
            
            if not clusters or not clusters.get("items"):
                if return_list:
                    return []
                if use_widgets:
                    Cluster._display_clusters_list_widget([], page, page_size)
                else:
                    print_no_resources_found()
                return None
                
            # Parse cluster info for each cluster
            cluster_infos = []
            for cluster in clusters["items"]:
                cluster_info = _map_to_ray_cluster(cluster)
                if not cluster_info:
                    continue
                    
                # Check if cluster is managed by AppWrapper
                if cluster["metadata"].get("ownerReferences"):
                    for owner in cluster["metadata"]["ownerReferences"]:
                        if owner["kind"] == "AppWrapper":
                            cluster_info.is_appwrapper = True
                            break
                            
                # Get Kueue workload info if cluster is managed by AppWrapper
                if cluster_info.is_appwrapper:
                    workload_info = Cluster._get_cluster_kueue_workload_info(cluster["metadata"]["name"], namespace)
                    if workload_info:
                        cluster_info.local_queue = workload_info.name
                        cluster_info.kueue_workload = workload_info
                        
                # Get dashboard URL
                cluster_info.dashboard = Cluster._get_cluster_dashboard_url(cluster["metadata"]["name"], namespace)
                
                cluster_infos.append(cluster_info)
                
            # Sort clusters by name
            cluster_infos.sort(key=lambda x: x.name)
            
            # Calculate pagination
            start_idx = (page - 1) * page_size
            end_idx = start_idx + page_size
            total_pages = (len(cluster_infos) + page_size - 1) // page_size
            
            # Get clusters for current page
            current_clusters = cluster_infos[start_idx:end_idx]
            
            # Display clusters
            if use_widgets:
                Cluster._display_clusters_list_widget(current_clusters, page, page_size, total_pages)
            else:
                print_clusters(current_clusters)
                
            # Return full list if requested
            return cluster_infos if return_list else None
            
        except Exception as e:
            error_msg = _kube_api_error_handling(e)
            if return_list:
                return []
            return None
            
    @staticmethod
    def _get_cluster_kueue_workload_info(cluster_name: str, namespace: str) -> Optional[KueueWorkloadInfo]:
        """Get Kueue workload information for a RayCluster."""
        try:
            api = client.CustomObjectsApi(get_api_client())
            workloads = api.list_namespaced_custom_object(
                group="kueue.x-k8s.io",
                version="v1beta1",
                namespace=namespace,
                plural="workloads"
            )
            
            for workload in workloads.get("items", []):
                if workload["metadata"]["ownerReferences"][0]["name"] == cluster_name:
                    status = workload.get("status", {})
                    admission = status.get("admission", {})
                    
                    # Get error information if cluster failed
                    error_msg, error_reason = Cluster._get_workload_error_info(workload)
                    
                    return KueueWorkloadInfo(
                        name=workload["metadata"]["name"],
                        status=status.get("conditions", [{}])[0].get("type", "Unknown"),
                        priority=workload["spec"].get("priority", 0),
                        admission_time=Cluster._get_admission_time(admission),
                        error_message=error_msg,
                        error_reason=error_reason
                    )
            
            return None
            
        except Exception as e:
            # Silently fail - Kueue may not be installed or workload info unavailable
            pass
            return None
            
    @staticmethod
    def _get_admission_time(admission: Dict[str, Any]) -> Optional[str]:
        """Extract admission time from Kueue workload admission data."""
        if not admission:
            return None
        return admission.get("podSetAssignments", [{}])[0].get("admissionTime")
        
    @staticmethod
    def _get_workload_error_info(workload: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
        """Extract error information from a failed Kueue workload."""
        status = workload.get("status", {})
        conditions = status.get("conditions", [])
        
        for condition in conditions:
            if condition.get("type") == "Failed":
                return condition.get("message"), condition.get("reason")
                
        return None, None
        
    @staticmethod
    def _get_cluster_dashboard_url(cluster_name: str, namespace: str) -> str:
        """Get the dashboard URL for a RayCluster."""
        # Try HTTPRoute first (RHOAI v3.0+)
        dashboard_url = _get_dashboard_url_from_httproute(cluster_name, namespace)
        if dashboard_url:
            return dashboard_url
            
        # Fall back to OpenShift Routes or Ingresses
        if _is_openshift_cluster():
            try:
                api = client.CustomObjectsApi(get_api_client())
                routes = api.list_namespaced_custom_object(
                    group="route.openshift.io",
                    version="v1",
                    namespace=namespace,
                    plural="routes"
                )
                
                for route in routes["items"]:
                    if route["metadata"]["name"] == f"ray-dashboard-{cluster_name}" or route["metadata"]["name"].startswith(f"{cluster_name}-ingress"):
                        protocol = "https" if route["spec"].get("tls") else "http"
                        return f"{protocol}://{route['spec']['host']}"
                        
            except Exception as e:
                # Silently fail - routes may not be available
                pass
                
        else:
            try:
                api = client.NetworkingV1Api(get_api_client())
                ingresses = api.list_namespaced_ingress(namespace)
                
                for ingress in ingresses.items:
                    if ingress.metadata.name == f"ray-dashboard-{cluster_name}" or ingress.metadata.name.startswith(f"{cluster_name}-ingress"):
                        protocol = "https" if ingress.metadata.annotations and "route.openshift.io/termination" in ingress.metadata.annotations else "http"
                        return f"{protocol}://{ingress.spec.rules[0].host}"
                        
            except Exception as e:
                # Silently fail - ingresses may not be available
                pass
                
        return "Dashboard not available yet"
        
    @staticmethod
    def _display_cluster_status_widget(cluster_info: Optional[RayCluster], cluster_name: str = None, namespace: str = None) -> None:
        """Display cluster status using ipywidgets."""
        if not cluster_info:
            # Cluster not found
            output = widgets.HTML(
                f'<div style="padding: 10px; border: 1px solid #ff6b6b; border-radius: 4px; background-color: #fff5f5;">'
                f'<span style="color: #ff6b6b;">⚠️ No RayCluster found with name "{cluster_name}" in namespace "{namespace}"</span>'
                '</div>'
            )
            display(output)
            return
            
        # Create status badge
        status_colors = {
            RayClusterStatus.READY: ("#2ecc71", "white"),     # Green
            RayClusterStatus.STARTING: ("#3498db", "white"),  # Blue
            RayClusterStatus.FAILED: ("#e74c3c", "white"),    # Red
            RayClusterStatus.STOPPED: ("#f1c40f", "black")    # Yellow
        }
        status_color = status_colors.get(cluster_info.status, ("#95a5a6", "white"))  # Gray for unknown
        
        # Build HTML table
        html = f'''
        <div style="padding: 15px; border: 1px solid #ddd; border-radius: 4px; background-color: #f8f9fa;">
            <table style="width: 100%; border-collapse: separate; border-spacing: 0 8px;">
                <tr>
                    <td style="padding: 5px;"><strong>Name:</strong></td>
                    <td style="padding: 5px;">{cluster_info.name}</td>
                    <td style="padding: 5px;"><strong>Status:</strong></td>
                    <td style="padding: 5px;">
                        <span style="background-color: {status_color[0]}; color: {status_color[1]}; padding: 3px 8px; border-radius: 3px;">
                            {cluster_info.status.value}
                        </span>
                    </td>
                </tr>
                <tr>
                    <td style="padding: 5px;"><strong>Namespace:</strong></td>
                    <td style="padding: 5px;">{cluster_info.namespace}</td>
                    <td style="padding: 5px;"><strong>Workers:</strong></td>
                    <td style="padding: 5px;">{cluster_info.num_workers}</td>
                </tr>
                <tr>
                    <td style="padding: 5px;"><strong>Head CPU:</strong></td>
                    <td style="padding: 5px;">{cluster_info.head_cpu_requests}/{cluster_info.head_cpu_limits}</td>
                    <td style="padding: 5px;"><strong>Head Memory:</strong></td>
                    <td style="padding: 5px;">{cluster_info.head_mem_requests}/{cluster_info.head_mem_limits}</td>
                </tr>
                <tr>
                    <td style="padding: 5px;"><strong>Worker CPU:</strong></td>
                    <td style="padding: 5px;">{cluster_info.worker_cpu_requests}/{cluster_info.worker_cpu_limits}</td>
                    <td style="padding: 5px;"><strong>Worker Memory:</strong></td>
                    <td style="padding: 5px;">{cluster_info.worker_mem_requests}/{cluster_info.worker_mem_limits}</td>
                </tr>
                <tr>
                    <td style="padding: 5px;"><strong>Dashboard:</strong></td>
                    <td colspan="3" style="padding: 5px;">
                        <a href="{cluster_info.dashboard}" target="_blank" style="color: #007bff; text-decoration: none;">
                            {cluster_info.dashboard}
                        </a>
                    </td>
                </tr>
        '''
        
        # Add extended resources if any
        if cluster_info.head_extended_resources:
            html += '<tr><td style="padding: 5px;"><strong>Head Resources:</strong></td><td colspan="3" style="padding: 5px;">'
            for resource, count in cluster_info.head_extended_resources.items():
                html += f'{resource}: {count}, '
            html = html.rstrip(', ') + '</td></tr>'
            
        if cluster_info.worker_extended_resources:
            html += '<tr><td style="padding: 5px;"><strong>Worker Resources:</strong></td><td colspan="3" style="padding: 5px;">'
            for resource, count in cluster_info.worker_extended_resources.items():
                html += f'{resource}: {count}, '
            html = html.rstrip(', ') + '</td></tr>'
            
        # Add Kueue information if available
        if cluster_info.kueue_workload:
            html += f'''
                <tr>
                    <td style="padding: 5px;"><strong>Queue:</strong></td>
                    <td style="padding: 5px;">{cluster_info.local_queue or 'N/A'}</td>
                    <td style="padding: 5px;"><strong>Priority:</strong></td>
                    <td style="padding: 5px;">{cluster_info.kueue_workload.priority}</td>
                </tr>
                <tr>
                    <td style="padding: 5px;"><strong>Queue Status:</strong></td>
                    <td style="padding: 5px;">{cluster_info.kueue_workload.status}</td>
                    <td style="padding: 5px;"><strong>Admission:</strong></td>
                    <td style="padding: 5px;">{cluster_info.kueue_workload.admission_time or 'N/A'}</td>
                </tr>
            '''
            
            # Add error information for failed clusters
            if cluster_info.status == RayClusterStatus.FAILED and cluster_info.kueue_workload.error_message:
                html += f'''
                    <tr>
                        <td style="padding: 5px;"><strong>Error:</strong></td>
                        <td colspan="3" style="padding: 5px; color: #e74c3c;">
                            {cluster_info.kueue_workload.error_reason}: {cluster_info.kueue_workload.error_message}
                        </td>
                    </tr>
                '''
                
        html += '''
            </table>
        </div>
        '''
        
        # Display the widget
        output = widgets.HTML(html)
        display(output)
        
    @staticmethod
    def _display_clusters_list_widget(clusters: ListType[RayCluster], page: int, page_size: int, total_pages: int = 1) -> None:
        """Display clusters list using ipywidgets."""
        if not clusters:
            output = widgets.HTML(
                '<div style="padding: 10px; border: 1px solid #ff6b6b; border-radius: 4px; background-color: #fff5f5;">'
                '<span style="color: #ff6b6b;">⚠️ No RayClusters found</span>'
                '</div>'
            )
            display(output)
            return
            
        # Create HTML table
        html = '''
        <div style="padding: 15px; border: 1px solid #ddd; border-radius: 4px; background-color: #f8f9fa;">
            <table style="width: 100%; border-collapse: collapse;">
                <thead>
                    <tr style="background-color: #e9ecef;">
                        <th style="padding: 8px; text-align: left; border-bottom: 2px solid #dee2e6;">Name</th>
                        <th style="padding: 8px; text-align: center; border-bottom: 2px solid #dee2e6;">Status</th>
                        <th style="padding: 8px; text-align: center; border-bottom: 2px solid #dee2e6;">Workers</th>
                        <th style="padding: 8px; text-align: center; border-bottom: 2px solid #dee2e6;">Queue</th>
                        <th style="padding: 8px; text-align: center; border-bottom: 2px solid #dee2e6;">Queue Status</th>
                        <th style="padding: 8px; text-align: left; border-bottom: 2px solid #dee2e6;">Dashboard</th>
                    </tr>
                </thead>
                <tbody>
        '''
        
        # Status colors
        status_colors = {
            RayClusterStatus.READY: ("#2ecc71", "white"),     # Green
            RayClusterStatus.STARTING: ("#3498db", "white"),  # Blue
            RayClusterStatus.FAILED: ("#e74c3c", "white"),    # Red
            RayClusterStatus.STOPPED: ("#f1c40f", "black")    # Yellow
        }
        
        # Add rows
        for cluster in clusters:
            status_color = status_colors.get(cluster.status, ("#95a5a6", "white"))  # Gray for unknown
            
            html += f'''
                <tr style="border-bottom: 1px solid #dee2e6;">
                    <td style="padding: 8px;">{cluster.name}</td>
                    <td style="padding: 8px; text-align: center;">
                        <span style="background-color: {status_color[0]}; color: {status_color[1]}; padding: 3px 8px; border-radius: 3px;">
                            {cluster.status.value}
                        </span>
                    </td>
                    <td style="padding: 8px; text-align: center;">{cluster.num_workers}</td>
                    <td style="padding: 8px; text-align: center;">{cluster.local_queue or 'N/A'}</td>
                    <td style="padding: 8px; text-align: center;">{cluster.kueue_workload.status if cluster.kueue_workload else 'N/A'}</td>
                    <td style="padding: 8px;">
                        <a href="{cluster.dashboard}" target="_blank" style="color: #007bff; text-decoration: none;">
                            {cluster.dashboard}
                        </a>
                    </td>
                </tr>
            '''
            
        html += '''
                </tbody>
            </table>
        '''
        
        # Add pagination info
        if total_pages > 1:
            html += f'''
            <div style="margin-top: 10px; text-align: center; color: #6c757d;">
                Page {page} of {total_pages}
            '''
            if page > 1:
                html += f' <span style="color: #007bff;">(use page={page - 1} for previous)</span>'
            if page < total_pages:
                html += f' <span style="color: #007bff;">(page={page + 1} for next)</span>'
            html += '</div>'
            
        html += '</div>'
        
        # Display the widget
        output = widgets.HTML(html)
        display(output)

    def __init__(self, config: ClusterConfiguration):
        """
        Create the resource cluster object by passing in a ClusterConfiguration
        (defined in the config sub-module). An AppWrapper will then be generated
        based off of the configured resources to represent the desired cluster
        request.
        """
        self.config = config
        self._job_submission_client = None
        if self.config is None:
            warnings.warn(
                "Please provide a ClusterConfiguration to initialise the Cluster object"
            )
            return
        else:
            self.resource_yaml = self.create_resource()

        if is_notebook():
            cluster_apply_down_buttons(self)

    def get_dynamic_client(self):  # pragma: no cover
        return DynamicClient(get_api_client())

    def config_check(self):
        return config_check()

    @property
    def _client_headers(self):
        k8_client = get_api_client()
        return {
            "Authorization": k8_client.configuration.get_api_key_with_prefix(
                "authorization"
            )
        }

    @property
    def _client_verify_tls(self):
        return _is_openshift_cluster and self.config.verify_tls

    @property
    def job_client(self):
        k8client = get_api_client()
        if self._job_submission_client:
            return self._job_submission_client
        if _is_openshift_cluster():
            self._job_submission_client = JobSubmissionClient(
                self.cluster_dashboard_uri(),
                headers=self._client_headers,
                verify=self._client_verify_tls,
            )
        else:
            self._job_submission_client = JobSubmissionClient(
                self.cluster_dashboard_uri()
            )
        return self._job_submission_client

    def create_resource(self):
        """
        Called upon cluster object creation, creates an AppWrapper yaml based on
        the specifications of the ClusterConfiguration.
        """
        if self.config.namespace is None:
            self.config.namespace = get_current_namespace()
            if self.config.namespace is None:
                print("Please specify with namespace=<your_current_namespace>")
            elif type(self.config.namespace) is not str:
                raise TypeError(
                    f"Namespace {self.config.namespace} is of type {type(self.config.namespace)}. Check your Kubernetes Authentication."
                )
        return build_ray_cluster(self)

    # creates a new cluster with the provided or default spec
    def up(self):
        """
        Applies the Cluster yaml, pushing the resource request onto
        the Kueue localqueue.
        """
        print(
            "WARNING: The up() function is planned for deprecation in favor of apply()."
        )
        # check if RayCluster CustomResourceDefinition exists if not throw RuntimeError
        self._throw_for_no_raycluster()
        namespace = self.config.namespace

        try:
            config_check()
            api_instance = client.CustomObjectsApi(get_api_client())
            if self.config.appwrapper:
                if self.config.write_to_file:
                    with open(self.resource_yaml) as f:
                        aw = yaml.load(f, Loader=yaml.FullLoader)
                        api_instance.create_namespaced_custom_object(
                            group="workload.codeflare.dev",
                            version="v1beta2",
                            namespace=namespace,
                            plural="appwrappers",
                            body=aw,
                        )
                else:
                    api_instance.create_namespaced_custom_object(
                        group="workload.codeflare.dev",
                        version="v1beta2",
                        namespace=namespace,
                        plural="appwrappers",
                        body=self.resource_yaml,
                    )
                print(f"AppWrapper: '{self.config.name}' has successfully been created")
            else:
                self._component_resources_up(namespace, api_instance)
                print(
                    f"Ray Cluster: '{self.config.name}' has successfully been created"
                )
        except Exception as e:  # pragma: no cover
            if e.status == 422:
                print(
                    "WARNING: RayCluster creation rejected due to invalid Kueue configuration. Please contact your administrator."
                )
            else:
                print(
                    "WARNING: Failed to create RayCluster due to unexpected error. Please contact your administrator."
                )
            return _kube_api_error_handling(e)

    # Applies a new cluster with the provided or default spec
    def apply(self, force=False):
        """
        Applies the Cluster yaml using server-side apply.
        If 'force' is set to True, conflicts will be forced.
        """
        # check if RayCluster CustomResourceDefinition exists if not throw RuntimeError
        self._throw_for_no_raycluster()
        namespace = self.config.namespace
        name = self.config.name

        # Regenerate resource_yaml to reflect any configuration changes
        self.resource_yaml = self.create_resource()

        try:
            self.config_check()
            api_instance = client.CustomObjectsApi(get_api_client())
            crds = self.get_dynamic_client().resources
            if self.config.appwrapper:
                api_version = "workload.codeflare.dev/v1beta2"
                api_instance = crds.get(api_version=api_version, kind="AppWrapper")
                # defaulting body to resource_yaml
                body = self.resource_yaml
                if self.config.write_to_file:
                    # if write_to_file is True, load the file from AppWrapper yaml and update body
                    with open(self.resource_yaml) as f:
                        aw = yaml.load(f, Loader=yaml.FullLoader)
                    body = aw
                api_instance.server_side_apply(
                    field_manager=CF_SDK_FIELD_MANAGER,
                    group="workload.codeflare.dev",
                    version="v1beta2",
                    namespace=namespace,
                    plural="appwrappers",
                    body=body,
                    force_conflicts=force,
                )
                print(
                    f"AppWrapper: '{name}' configuration has successfully been applied. For optimal resource management, you should delete this Ray Cluster when no longer in use."
                )
            else:
                api_version = "ray.io/v1"
                api_instance = crds.get(api_version=api_version, kind="RayCluster")
                self._component_resources_apply(
                    namespace=namespace, api_instance=api_instance
                )
                print(
                    f"Ray Cluster: '{name}' has successfully been applied. For optimal resource management, you should delete this Ray Cluster when no longer in use."
                )
        except AttributeError as e:
            raise RuntimeError(f"Failed to initialize DynamicClient: {e}")
        except Exception as e:  # pragma: no cover
            if (
                hasattr(e, "status") and e.status == 422
            ):  # adding status check to avoid returning false positive
                print(
                    "WARNING: RayCluster creation rejected due to invalid Kueue configuration. Please contact your administrator."
                )
            else:
                print(
                    "WARNING: Failed to create RayCluster due to unexpected error. Please contact your administrator."
                )
            return _kube_api_error_handling(e)

    def _throw_for_no_raycluster(self):
        api_instance = client.CustomObjectsApi(get_api_client())
        try:
            api_instance.list_namespaced_custom_object(
                group="ray.io",
                version="v1",
                namespace=self.config.namespace,
                plural="rayclusters",
            )
        except ApiException as e:
            if e.status == 404:
                raise RuntimeError(
                    "RayCluster CustomResourceDefinition unavailable contact your administrator."
                )
            else:
                raise RuntimeError(
                    "Failed to get RayCluster CustomResourceDefinition: " + str(e)
                )

    def down(self):
        """
        Deletes the AppWrapper yaml, scaling-down and deleting all resources
        associated with the cluster.
        """
        namespace = self.config.namespace
        resource_name = self.config.name
        self._throw_for_no_raycluster()
        try:
            self.config_check()
            api_instance = client.CustomObjectsApi(get_api_client())
            if self.config.appwrapper:
                api_instance.delete_namespaced_custom_object(
                    group="workload.codeflare.dev",
                    version="v1beta2",
                    namespace=namespace,
                    plural="appwrappers",
                    name=resource_name,
                )
                print(f"AppWrapper: '{resource_name}' has successfully been deleted")
            else:
                _delete_resources(resource_name, namespace, api_instance)
                print(
                    f"Ray Cluster: '{self.config.name}' has successfully been deleted"
                )
        except Exception as e:  # pragma: no cover
            return _kube_api_error_handling(e)

    def status(
        self, print_to_console: bool = True
    ) -> Tuple[CodeFlareClusterStatus, bool]:
        """
        Returns the requested cluster's status, as well as whether or not
        it is ready for use.
        """
        ready = False
        status = CodeFlareClusterStatus.UNKNOWN
        if self.config.appwrapper:
            # check the app wrapper status
            appwrapper = _app_wrapper_status(self.config.name, self.config.namespace)
            if appwrapper:
                if appwrapper.status in [
                    AppWrapperStatus.RESUMING,
                    AppWrapperStatus.RESETTING,
                ]:
                    ready = False
                    status = CodeFlareClusterStatus.STARTING
                elif appwrapper.status in [
                    AppWrapperStatus.FAILED,
                ]:
                    ready = False
                    status = CodeFlareClusterStatus.FAILED  # should deleted be separate
                    return status, ready  # exit early, no need to check ray status
                elif appwrapper.status in [
                    AppWrapperStatus.SUSPENDED,
                    AppWrapperStatus.SUSPENDING,
                ]:
                    ready = False
                    if appwrapper.status == AppWrapperStatus.SUSPENDED:
                        status = CodeFlareClusterStatus.QUEUED
                    else:
                        status = CodeFlareClusterStatus.QUEUEING
                    if print_to_console:
                        pretty_print.print_app_wrappers_status([appwrapper])
                    return (
                        status,
                        ready,
                    )  # no need to check the ray status since still in queue

        # check the ray cluster status
        cluster = _ray_cluster_status(self.config.name, self.config.namespace)
        if cluster:
            if cluster.status == RayClusterStatus.SUSPENDED:
                ready = False
                status = CodeFlareClusterStatus.SUSPENDED
            if cluster.status == RayClusterStatus.UNKNOWN:
                ready = False
                status = CodeFlareClusterStatus.STARTING
            if cluster.status == RayClusterStatus.READY:
                ready = True
                status = CodeFlareClusterStatus.READY
            elif cluster.status in [
                RayClusterStatus.UNHEALTHY,
                RayClusterStatus.FAILED,
            ]:
                ready = False
                status = CodeFlareClusterStatus.FAILED

            if print_to_console:
                # overriding the number of gpus with requested
                _, cluster.worker_gpu = head_worker_gpu_count_from_cluster(self)
                pretty_print.print_cluster_status(cluster)
        elif print_to_console:
            if status == CodeFlareClusterStatus.UNKNOWN:
                pretty_print.print_no_resources_found()
            else:
                pretty_print.print_app_wrappers_status([appwrapper], starting=True)

        return status, ready

    def is_dashboard_ready(self) -> bool:
        """
        Checks if the cluster's dashboard is ready and accessible.

        This method attempts to send a GET request to the cluster dashboard URI.
        If the request is successful (HTTP status code 200), it returns True.
        If an SSL error occurs, it returns False, indicating the dashboard is not ready.

        Returns:
            bool:
                True if the dashboard is ready, False otherwise.
        """

        dashboard_uri = self.cluster_dashboard_uri()
        if dashboard_uri is None:
            return False

        try:
            response = requests.get(
                dashboard_uri,
                headers=self._client_headers,
                timeout=5,
                verify=self._client_verify_tls,
            )
        except requests.exceptions.SSLError:  # pragma no cover
            # SSL exception occurs when oauth ingress has been created but cluster is not up
            return False
        except Exception:  # pragma no cover
            # Any other exception (connection errors, timeouts, etc.)
            return False

        if response.status_code == 200:
            return True
        else:
            return False

    def wait_ready(self, timeout: Optional[int] = None, dashboard_check: bool = True):
        """
        Waits for the requested cluster to be ready, up to an optional timeout.

        This method checks the status of the cluster every five seconds until it is
        ready or the timeout is reached. If dashboard_check is enabled, it will also
        check for the readiness of the dashboard.

        Args:
            timeout (Optional[int]):
                The maximum time to wait for the cluster to be ready in seconds. If None, waits indefinitely.
            dashboard_check (bool):
                Flag to determine if the dashboard readiness should
                be checked. Defaults to True.

        Raises:
            TimeoutError:
                If the timeout is reached before the cluster or dashboard is ready.
        """
        print("Waiting for requested resources to be set up...")
        time = 0
        while True:
            if timeout and time >= timeout:
                raise TimeoutError(
                    f"wait() timed out after waiting {timeout}s for cluster to be ready"
                )
            status, ready = self.status(print_to_console=False)
            if status == CodeFlareClusterStatus.UNKNOWN:
                print(
                    "WARNING: Current cluster status is unknown, have you run cluster.apply() yet? Run cluster.details() to check if it's ready."
                )
            if ready:
                break
            sleep(5)
            time += 5
        print("Requested cluster is up and running!")

        while dashboard_check:
            if timeout and time >= timeout:
                raise TimeoutError(
                    f"wait() timed out after waiting {timeout}s for dashboard to be ready"
                )
            if self.is_dashboard_ready():
                print("Dashboard is ready!")
                break
            sleep(5)
            time += 5

    def details(self, print_to_console: bool = True) -> RayCluster:
        """
        Retrieves details about the Ray Cluster.

        This method returns a copy of the Ray Cluster information and optionally prints
        the details to the console.

        Args:
            print_to_console (bool):
                Flag to determine if the cluster details should be
                printed to the console. Defaults to True.

        Returns:
            RayCluster:
                A copy of the Ray Cluster details.
        """
        cluster = _copy_to_ray(self)
        if print_to_console:
            pretty_print.print_clusters([cluster])
        return cluster

    def cluster_uri(self) -> str:
        """
        Returns a string containing the cluster's URI.
        """
        return f"ray://{self.config.name}-head-svc.{self.config.namespace}.svc:10001"

    def cluster_dashboard_uri(self) -> str:
        """
        Returns a string containing the cluster's dashboard URI.
        Tries HTTPRoute first (RHOAI v3.0+), then falls back to OpenShift Routes or Ingresses.
        """
        config_check()

        # Try HTTPRoute first (RHOAI v3.0+)
        # This will return None if HTTPRoute is not found (SDK v0.31.1 and below or Kind clusters)
        httproute_url = _get_dashboard_url_from_httproute(
            self.config.name, self.config.namespace
        )
        if httproute_url:
            return httproute_url

        # Fall back to OpenShift Routes (pre-v3.0) or Ingresses (Kind)
        if _is_openshift_cluster():
            try:
                api_instance = client.CustomObjectsApi(get_api_client())
                routes = api_instance.list_namespaced_custom_object(
                    group="route.openshift.io",
                    version="v1",
                    namespace=self.config.namespace,
                    plural="routes",
                )
            except Exception as e:  # pragma: no cover
                return _kube_api_error_handling(e)

            for route in routes["items"]:
                if route["metadata"][
                    "name"
                ] == f"ray-dashboard-{self.config.name}" or route["metadata"][
                    "name"
                ].startswith(
                    f"{self.config.name}-ingress"
                ):
                    protocol = "https" if route["spec"].get("tls") else "http"
                    return f"{protocol}://{route['spec']['host']}"
            # No route found for this cluster
            return "Dashboard not available yet, have you run cluster.apply()?"
        else:
            try:
                api_instance = client.NetworkingV1Api(get_api_client())
                ingresses = api_instance.list_namespaced_ingress(self.config.namespace)
            except Exception as e:  # pragma no cover
                return _kube_api_error_handling(e)

            for ingress in ingresses.items:
                annotations = ingress.metadata.annotations
                protocol = "http"
                if (
                    ingress.metadata.name == f"ray-dashboard-{self.config.name}"
                    or ingress.metadata.name.startswith(f"{self.config.name}-ingress")
                ):
                    if annotations == None:
                        protocol = "http"
                    elif "route.openshift.io/termination" in annotations:
                        protocol = "https"
                return f"{protocol}://{ingress.spec.rules[0].host}"
        return "Dashboard not available yet, have you run cluster.apply()? Run cluster.details() to check if it's ready."

    def list_jobs(self) -> List:
        """
        This method accesses the head ray node in your cluster and lists the running jobs.
        """
        return self.job_client.list_jobs()

    def job_status(self, job_id: str) -> str:
        """
        This method accesses the head ray node in your cluster and returns the job status for the provided job id.
        """
        return self.job_client.get_job_status(job_id)

    def job_logs(self, job_id: str) -> str:
        """
        This method accesses the head ray node in your cluster and returns the logs for the provided job id.
        """
        return self.job_client.get_job_logs(job_id)

    @staticmethod
    def _head_worker_extended_resources_from_rc_dict(rc: Dict) -> Tuple[dict, dict]:
        head_extended_resources, worker_extended_resources = {}, {}
        for resource in rc["spec"]["workerGroupSpecs"][0]["template"]["spec"][
            "containers"
        ][0]["resources"]["limits"].keys():
            if resource in ["memory", "cpu"]:
                continue
            worker_extended_resources[resource] = rc["spec"]["workerGroupSpecs"][0][
                "template"
            ]["spec"]["containers"][0]["resources"]["limits"][resource]

        for resource in rc["spec"]["headGroupSpec"]["template"]["spec"]["containers"][
            0
        ]["resources"]["limits"].keys():
            if resource in ["memory", "cpu"]:
                continue
            head_extended_resources[resource] = rc["spec"]["headGroupSpec"]["template"][
                "spec"
            ]["containers"][0]["resources"]["limits"][resource]

        return head_extended_resources, worker_extended_resources

    def local_client_url(self):
        """
        Constructs the URL for the local Ray client.

        Returns:
            str:
                The Ray client URL based on the ingress domain.
        """
        ingress_domain = _get_ingress_domain(self)
        return f"ray://{ingress_domain}"

    def _component_resources_up(
        self, namespace: str, api_instance: client.CustomObjectsApi
    ):
        if self.config.write_to_file:
            with open(self.resource_yaml) as f:
                ray_cluster = yaml.safe_load(f)
                _create_resources(ray_cluster, namespace, api_instance)
        else:
            _create_resources(self.resource_yaml, namespace, api_instance)

    def _component_resources_apply(
        self, namespace: str, api_instance: client.CustomObjectsApi
    ):
        if self.config.write_to_file:
            with open(self.resource_yaml) as f:
                ray_cluster = yaml.safe_load(f)
                _apply_ray_cluster(ray_cluster, namespace, api_instance)
        else:
            _apply_ray_cluster(self.resource_yaml, namespace, api_instance)

    def _component_resources_down(
        self, namespace: str, api_instance: client.CustomObjectsApi
    ):
        cluster_name = self.config.name
        if self.config.write_to_file:
            with open(self.resource_yaml) as f:
                yamls = yaml.load_all(f, Loader=yaml.FullLoader)
                _delete_resources(yamls, namespace, api_instance, cluster_name)
        else:
            yamls = yaml.safe_load_all(self.resource_yaml)
            _delete_resources(yamls, namespace, api_instance, cluster_name)


def list_all_clusters(namespace: str, print_to_console: bool = True):
    """
    Returns (and prints by default) a list of all clusters in a given namespace.
    """
    clusters = _get_ray_clusters(namespace)
    if print_to_console:
        pretty_print.print_clusters(clusters)
    return clusters


def list_all_queued(
    namespace: str, print_to_console: bool = True, appwrapper: bool = False
):
    """
    Returns (and prints by default) a list of all currently queued-up Ray Clusters
    in a given namespace.
    """
    if appwrapper:
        resources = _get_app_wrappers(namespace, filter=[AppWrapperStatus.SUSPENDED])
        if print_to_console:
            pretty_print.print_app_wrappers_status(resources)
    else:
        resources = _get_ray_clusters(
            namespace, filter=[RayClusterStatus.READY, RayClusterStatus.SUSPENDED]
        )
        if print_to_console:
            pretty_print.print_ray_clusters_status(resources)
    return resources


def get_cluster(
    cluster_name: str,
    namespace: str = "default",
    verify_tls: bool = True,
    write_to_file: bool = False,
):
    """
    Retrieves an existing Ray Cluster or AppWrapper as a Cluster object.

    This function fetches an existing Ray Cluster or AppWrapper from the Kubernetes cluster and returns
    it as a `Cluster` object, including its YAML configuration under `Cluster.resource_yaml`.

    Args:
        cluster_name (str):
            The name of the Ray Cluster or AppWrapper.
        namespace (str, optional):
            The Kubernetes namespace where the Ray Cluster or AppWrapper is located. Default is "default".
        verify_tls (bool, optional):
            Whether to verify TLS when connecting to the cluster. Default is True.
        write_to_file (bool, optional):
            If True, writes the resource configuration to a YAML file. Default is False.

    Returns:
        Cluster:
            A Cluster object representing the retrieved Ray Cluster or AppWrapper.

    Raises:
        Exception:
            If the Ray Cluster or AppWrapper cannot be found or does not exist.
    """
    config_check()
    api_instance = client.CustomObjectsApi(get_api_client())
    # Check/Get the AppWrapper if it exists
    is_appwrapper = _check_aw_exists(cluster_name, namespace)
    if is_appwrapper:
        try:
            resource = api_instance.get_namespaced_custom_object(
                group="workload.codeflare.dev",
                version="v1beta2",
                namespace=namespace,
                plural="appwrappers",
                name=cluster_name,
            )
            resource_extraction = resource["spec"]["components"][0]["template"]
        except Exception as e:
            return _kube_api_error_handling(e)
    else:
        # Get the Ray Cluster
        try:
            resource = api_instance.get_namespaced_custom_object(
                group="ray.io",
                version="v1",
                namespace=namespace,
                plural="rayclusters",
                name=cluster_name,
            )
            resource_extraction = resource
        except Exception as e:
            return _kube_api_error_handling(e)

    (
        head_extended_resources,
        worker_extended_resources,
    ) = Cluster._head_worker_extended_resources_from_rc_dict(resource_extraction)
    # Create a Cluster Configuration with just the necessary provided parameters
    cluster_config = ClusterConfiguration(
        name=cluster_name,
        namespace=namespace,
        verify_tls=verify_tls,
        write_to_file=write_to_file,
        appwrapper=is_appwrapper,
        head_cpu_limits=resource_extraction["spec"]["headGroupSpec"]["template"][
            "spec"
        ]["containers"][0]["resources"]["requests"]["cpu"],
        head_cpu_requests=resource_extraction["spec"]["headGroupSpec"]["template"][
            "spec"
        ]["containers"][0]["resources"]["limits"]["cpu"],
        head_memory_limits=resource_extraction["spec"]["headGroupSpec"]["template"][
            "spec"
        ]["containers"][0]["resources"]["requests"]["memory"],
        head_memory_requests=resource_extraction["spec"]["headGroupSpec"]["template"][
            "spec"
        ]["containers"][0]["resources"]["limits"]["memory"],
        num_workers=resource_extraction["spec"]["workerGroupSpecs"][0]["minReplicas"],
        worker_cpu_limits=resource_extraction["spec"]["workerGroupSpecs"][0][
            "template"
        ]["spec"]["containers"][0]["resources"]["limits"]["cpu"],
        worker_cpu_requests=resource_extraction["spec"]["workerGroupSpecs"][0][
            "template"
        ]["spec"]["containers"][0]["resources"]["requests"]["cpu"],
        worker_memory_limits=resource_extraction["spec"]["workerGroupSpecs"][0][
            "template"
        ]["spec"]["containers"][0]["resources"]["requests"]["memory"],
        worker_memory_requests=resource_extraction["spec"]["workerGroupSpecs"][0][
            "template"
        ]["spec"]["containers"][0]["resources"]["limits"]["memory"],
        head_extended_resource_requests=head_extended_resources,
        worker_extended_resource_requests=worker_extended_resources,
    )

    # Ignore the warning here for the lack of a ClusterConfiguration
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="Please provide a ClusterConfiguration to initialise the Cluster object",
        )
        cluster = Cluster(None)
        cluster.config = cluster_config

        # Remove auto-generated fields like creationTimestamp, uid and etc.
        remove_autogenerated_fields(resource)

        if write_to_file:
            cluster.resource_yaml = write_cluster_to_file(cluster, resource)
        else:
            # Update the Cluster's resource_yaml to reflect the retrieved Ray Cluster/AppWrapper
            cluster.resource_yaml = resource
            print(f"Yaml resources loaded for {cluster.config.name}")

        return cluster


def remove_autogenerated_fields(resource):
    """Recursively remove autogenerated fields from a dictionary."""
    if isinstance(resource, dict):
        for key in list(resource.keys()):
            if key in [
                "creationTimestamp",
                "resourceVersion",
                "uid",
                "selfLink",
                "managedFields",
                "finalizers",
                "generation",
                "status",
                "suspend",
                "workload.codeflare.dev/user",  # AppWrapper field
                "workload.codeflare.dev/userid",  # AppWrapper field
                "podSetInfos",  # AppWrapper field
            ]:
                del resource[key]
            else:
                remove_autogenerated_fields(resource[key])

    elif isinstance(resource, list):
        for item in resource:
            remove_autogenerated_fields(item)


# private methods
def _delete_resources(name: str, namespace: str, api_instance: client.CustomObjectsApi):
    api_instance.delete_namespaced_custom_object(
        group="ray.io",
        version="v1",
        namespace=namespace,
        plural="rayclusters",
        name=name,
    )


def _create_resources(yamls, namespace: str, api_instance: client.CustomObjectsApi):
    api_instance.create_namespaced_custom_object(
        group="ray.io",
        version="v1",
        namespace=namespace,
        plural="rayclusters",
        body=yamls,
    )


def _apply_ray_cluster(
    yamls, namespace: str, api_instance: client.CustomObjectsApi, force=False
):
    api_instance.server_side_apply(
        field_manager=CF_SDK_FIELD_MANAGER,
        group="ray.io",
        version="v1",
        namespace=namespace,
        plural="rayclusters",
        body=yamls,
        force_conflicts=force,  # Allow forcing conflicts if needed
    )


def _check_aw_exists(name: str, namespace: str) -> bool:
    try:
        config_check()
        api_instance = client.CustomObjectsApi(get_api_client())
        aws = api_instance.list_namespaced_custom_object(
            group="workload.codeflare.dev",
            version="v1beta2",
            namespace=namespace,
            plural="appwrappers",
        )
    except Exception as e:  # pragma: no cover
        return _kube_api_error_handling(e, print_error=False)
    for aw in aws["items"]:
        if aw["metadata"]["name"] == name:
            return True
    return False


# Cant test this until get_current_namespace is fixed and placed in this function over using `self`
def _get_ingress_domain(self):  # pragma: no cover
    config_check()

    if self.config.namespace != None:
        namespace = self.config.namespace
    else:
        namespace = get_current_namespace()
    domain = None

    if _is_openshift_cluster():
        try:
            api_instance = client.CustomObjectsApi(get_api_client())

            routes = api_instance.list_namespaced_custom_object(
                group="route.openshift.io",
                version="v1",
                namespace=namespace,
                plural="routes",
            )
        except Exception as e:  # pragma: no cover
            return _kube_api_error_handling(e)

        for route in routes["items"]:
            if (
                route["spec"]["port"]["targetPort"] == "client"
                or route["spec"]["port"]["targetPort"] == 10001
            ):
                domain = route["spec"]["host"]
    else:
        try:
            api_client = client.NetworkingV1Api(get_api_client())
            ingresses = api_client.list_namespaced_ingress(namespace)
        except Exception as e:  # pragma: no cover
            return _kube_api_error_handling(e)

        for ingress in ingresses.items:
            if ingress.spec.rules[0].http.paths[0].backend.service.port.number == 10001:
                domain = ingress.spec.rules[0].host
    return domain


def _app_wrapper_status(name, namespace="default") -> Optional[AppWrapper]:
    try:
        config_check()
        api_instance = client.CustomObjectsApi(get_api_client())
        aws = api_instance.list_namespaced_custom_object(
            group="workload.codeflare.dev",
            version="v1beta2",
            namespace=namespace,
            plural="appwrappers",
        )
    except Exception as e:  # pragma: no cover
        return _kube_api_error_handling(e)

    for aw in aws["items"]:
        if aw["metadata"]["name"] == name:
            return _map_to_app_wrapper(aw)
    return None


def _ray_cluster_status(name, namespace="default") -> Optional[RayCluster]:
    try:
        config_check()
        api_instance = client.CustomObjectsApi(get_api_client())
        rcs = api_instance.list_namespaced_custom_object(
            group="ray.io",
            version="v1",
            namespace=namespace,
            plural="rayclusters",
        )
    except Exception as e:  # pragma: no cover
        return _kube_api_error_handling(e)

    for rc in rcs["items"]:
        if rc["metadata"]["name"] == name:
            return _map_to_ray_cluster(rc)
    return None


def _get_ray_clusters(
    namespace="default", filter: Optional[ListType[RayClusterStatus]] = None
) -> ListType[RayCluster]:
    list_of_clusters = []
    try:
        config_check()
        api_instance = client.CustomObjectsApi(get_api_client())
        rcs = api_instance.list_namespaced_custom_object(
            group="ray.io",
            version="v1",
            namespace=namespace,
            plural="rayclusters",
        )
    except Exception as e:  # pragma: no cover
        return _kube_api_error_handling(e)

    # Get a list of RCs with the filter if it is passed to the function
    if filter is not None:
        for rc in rcs["items"]:
            ray_cluster = _map_to_ray_cluster(rc)
            if filter and ray_cluster.status in filter:
                # Check for AppWrapper ownership
                metadata = rc.get("metadata", {})
                owner_refs = metadata.get("ownerReferences", [])
                for owner in owner_refs:
                    if owner.get("kind") == "AppWrapper":
                        ray_cluster.is_appwrapper = True
                        break
                
                # Fetch Kueue workload info for all clusters
                workload_info = _get_cluster_kueue_workload_info_func(
                    metadata.get("name"), namespace
                )
                if workload_info:
                    ray_cluster.local_queue = workload_info.queue_name
                    ray_cluster.kueue_workload = workload_info
                
                list_of_clusters.append(ray_cluster)
    else:
        for rc in rcs["items"]:
            ray_cluster = _map_to_ray_cluster(rc)
            # Check for AppWrapper ownership
            metadata = rc.get("metadata", {})
            owner_refs = metadata.get("ownerReferences", [])
            for owner in owner_refs:
                if owner.get("kind") == "AppWrapper":
                    ray_cluster.is_appwrapper = True
                    break
            
            # Fetch Kueue workload info for all clusters
            workload_info = _get_cluster_kueue_workload_info_func(
                metadata.get("name"), namespace
            )
            if workload_info:
                ray_cluster.local_queue = workload_info.queue_name
                ray_cluster.kueue_workload = workload_info
            
            list_of_clusters.append(ray_cluster)
    return list_of_clusters


def _get_cluster_kueue_workload_info_func(
    cluster_name: str, namespace: str
) -> Optional[KueueWorkloadInfo]:
    """
    Get Kueue workload information for a RayCluster.
    
    This function looks for Kueue workloads that have a RayCluster owner reference
    matching the given cluster name. Works for all RayClusters, whether they're
    AppWrapper-managed or directly managed by Kueue.
    
    Args:
        cluster_name: Name of the RayCluster
        namespace: Kubernetes namespace
        
    Returns:
        KueueWorkloadInfo if found, None otherwise
    """
    try:
        api = client.CustomObjectsApi(get_api_client())
        workloads = api.list_namespaced_custom_object(
            group="kueue.x-k8s.io",
            version="v1beta1",
            namespace=namespace,
            plural="workloads",
        )

        for workload in workloads.get("items", []):
            owner_refs = workload.get("metadata", {}).get("ownerReferences", [])
            for owner_ref in owner_refs:
                if (
                    owner_ref.get("kind") == "RayCluster"
                    and owner_ref.get("name") == cluster_name
                ):
                    # Found the workload for this RayCluster
                    metadata = workload.get("metadata", {})
                    status = workload.get("status", {})
                    spec = workload.get("spec", {})
                    admission = status.get("admission", {})

                    # Get queue name from workload spec
                    queue_name = spec.get("queueName", "")

                    # Get status from conditions
                    conditions = status.get("conditions", [])
                    workload_status = "Unknown"
                    for condition in conditions:
                        if condition.get("status") == "True":
                            workload_status = condition.get("type", "Unknown")
                            break

                    # Get admission time
                    admission_time = None
                    if admission:
                        admission_time = admission.get("clusterQueue")

                    # Get error information if available
                    error_msg = None
                    error_reason = None
                    for condition in conditions:
                        if condition.get("type") == "Finished" and condition.get(
                            "status"
                        ) == "True":
                            if condition.get("reason") == "Failed":
                                error_reason = condition.get("reason")
                                error_msg = condition.get("message")

                    return KueueWorkloadInfo(
                        name=metadata.get("name", "unknown"),
                        queue_name=queue_name,
                        status=workload_status,
                        priority=spec.get("priority"),
                        creation_time=metadata.get("creationTimestamp"),
                        admission_time=admission_time,
                        error_message=error_msg,
                        error_reason=error_reason,
                    )

        return None

    except Exception as e:
        # Silently fail if Kueue is not installed or workload info unavailable
        return None


def _get_app_wrappers(
    namespace="default", filter=ListType[AppWrapperStatus]
) -> ListType[AppWrapper]:
    list_of_app_wrappers = []

    try:
        config_check()
        api_instance = client.CustomObjectsApi(get_api_client())
        aws = api_instance.list_namespaced_custom_object(
            group="workload.codeflare.dev",
            version="v1beta2",
            namespace=namespace,
            plural="appwrappers",
        )
    except Exception as e:  # pragma: no cover
        return _kube_api_error_handling(e)

    for item in aws["items"]:
        app_wrapper = _map_to_app_wrapper(item)
        if filter and app_wrapper.status in filter:
            list_of_app_wrappers.append(app_wrapper)
        else:
            # Unsure what the purpose of the filter is
            list_of_app_wrappers.append(app_wrapper)
    return list_of_app_wrappers


def _map_to_ray_cluster(rc) -> Optional[RayCluster]:
    if "status" in rc and "state" in rc["status"]:
        status = RayClusterStatus(rc["status"]["state"].lower())
    else:
        status = RayClusterStatus.UNKNOWN
    config_check()
    dashboard_url = None

    # Try HTTPRoute first (RHOAI v3.0+)
    rc_name = rc["metadata"]["name"]
    rc_namespace = rc["metadata"]["namespace"]
    dashboard_url = _get_dashboard_url_from_httproute(rc_name, rc_namespace)

    # Fall back to OpenShift Routes or Ingresses if HTTPRoute not found
    if not dashboard_url:
        if _is_openshift_cluster():
            try:
                api_instance = client.CustomObjectsApi(get_api_client())
                routes = api_instance.list_namespaced_custom_object(
                    group="route.openshift.io",
                    version="v1",
                    namespace=rc_namespace,
                    plural="routes",
                )
            except Exception as e:  # pragma: no cover
                return _kube_api_error_handling(e)

            for route in routes["items"]:
                if route["metadata"]["name"] == f"ray-dashboard-{rc_name}" or route[
                    "metadata"
                ]["name"].startswith(f"{rc_name}-ingress"):
                    protocol = "https" if route["spec"].get("tls") else "http"
                    dashboard_url = f"{protocol}://{route['spec']['host']}"
                    break
        else:
            try:
                api_instance = client.NetworkingV1Api(get_api_client())
                ingresses = api_instance.list_namespaced_ingress(rc_namespace)
            except Exception as e:  # pragma no cover
                return _kube_api_error_handling(e)
            for ingress in ingresses.items:
                annotations = ingress.metadata.annotations
                protocol = "http"
                if (
                    ingress.metadata.name == f"ray-dashboard-{rc_name}"
                    or ingress.metadata.name.startswith(f"{rc_name}-ingress")
                ):
                    if annotations == None:
                        protocol = "http"
                    elif "route.openshift.io/termination" in annotations:
                        protocol = "https"
                dashboard_url = f"{protocol}://{ingress.spec.rules[0].host}"

    (
        head_extended_resources,
        worker_extended_resources,
    ) = Cluster._head_worker_extended_resources_from_rc_dict(rc)

    return RayCluster(
        name=rc["metadata"]["name"],
        status=status,
        # for now we are not using autoscaling so same replicas is fine
        num_workers=rc["spec"]["workerGroupSpecs"][0]["replicas"],
        worker_mem_limits=rc["spec"]["workerGroupSpecs"][0]["template"]["spec"][
            "containers"
        ][0]["resources"]["limits"]["memory"],
        worker_mem_requests=rc["spec"]["workerGroupSpecs"][0]["template"]["spec"][
            "containers"
        ][0]["resources"]["requests"]["memory"],
        worker_cpu_requests=rc["spec"]["workerGroupSpecs"][0]["template"]["spec"][
            "containers"
        ][0]["resources"]["requests"]["cpu"],
        worker_cpu_limits=rc["spec"]["workerGroupSpecs"][0]["template"]["spec"][
            "containers"
        ][0]["resources"]["limits"]["cpu"],
        worker_extended_resources=worker_extended_resources,
        namespace=rc["metadata"]["namespace"],
        head_cpu_requests=rc["spec"]["headGroupSpec"]["template"]["spec"]["containers"][
            0
        ]["resources"]["requests"]["cpu"],
        head_cpu_limits=rc["spec"]["headGroupSpec"]["template"]["spec"]["containers"][
            0
        ]["resources"]["limits"]["cpu"],
        head_mem_requests=rc["spec"]["headGroupSpec"]["template"]["spec"]["containers"][
            0
        ]["resources"]["requests"]["memory"],
        head_mem_limits=rc["spec"]["headGroupSpec"]["template"]["spec"]["containers"][
            0
        ]["resources"]["limits"]["memory"],
        head_extended_resources=head_extended_resources,
        dashboard=dashboard_url,
    )


def _map_to_app_wrapper(aw) -> AppWrapper:
    if "status" in aw:
        return AppWrapper(
            name=aw["metadata"]["name"],
            status=AppWrapperStatus(aw["status"]["phase"].lower()),
        )
    return AppWrapper(
        name=aw["metadata"]["name"],
        status=AppWrapperStatus("suspended"),
    )


def _copy_to_ray(cluster: Cluster) -> RayCluster:
    ray = RayCluster(
        name=cluster.config.name,
        status=cluster.status(print_to_console=False)[0],
        num_workers=cluster.config.num_workers,
        worker_mem_requests=cluster.config.worker_memory_requests,
        worker_mem_limits=cluster.config.worker_memory_limits,
        worker_cpu_requests=cluster.config.worker_cpu_requests,
        worker_cpu_limits=cluster.config.worker_cpu_limits,
        worker_extended_resources=cluster.config.worker_extended_resource_requests,
        namespace=cluster.config.namespace,
        dashboard=cluster.cluster_dashboard_uri(),
        head_mem_requests=cluster.config.head_memory_requests,
        head_mem_limits=cluster.config.head_memory_limits,
        head_cpu_requests=cluster.config.head_cpu_requests,
        head_cpu_limits=cluster.config.head_cpu_limits,
        head_extended_resources=cluster.config.head_extended_resource_requests,
    )
    if ray.status == CodeFlareClusterStatus.READY:
        ray.status = RayClusterStatus.READY
    return ray


# Check if the routes api exists
def _is_openshift_cluster():
    try:
        config_check()
        for api in client.ApisApi(get_api_client()).get_api_versions().groups:
            for v in api.versions:
                if "route.openshift.io/v1" in v.group_version:
                    return True
        else:
            return False
    except Exception as e:  # pragma: no cover
        return _kube_api_error_handling(e)


# Get dashboard URL from HTTPRoute (RHOAI v3.0+)
def _get_dashboard_url_from_httproute(
    cluster_name: str, namespace: str
) -> Optional[str]:
    """
    Attempts to get the Ray dashboard URL from an HTTPRoute resource.
    This is used for RHOAI v3.0+ clusters that use Gateway API.

    Args:
        cluster_name: Name of the Ray cluster
        namespace: Namespace of the Ray cluster

    Returns:
        Dashboard URL if HTTPRoute is found, None otherwise
    """
    try:
        config_check()
        api_instance = client.CustomObjectsApi(get_api_client())

        # Try to get HTTPRoute for this Ray cluster
        try:
            httproute = api_instance.get_namespaced_custom_object(
                group="gateway.networking.k8s.io",
                version="v1",
                namespace=namespace,
                plural="httproutes",
                name=cluster_name,
            )
        except client.exceptions.ApiException as e:
            if e.status == 404:
                # HTTPRoute not found - this is expected for SDK v0.31.1 and below or Kind clusters
                return None
            raise

        # Get the Gateway reference from HTTPRoute
        parent_refs = httproute.get("spec", {}).get("parentRefs", [])
        if not parent_refs:
            return None

        gateway_ref = parent_refs[0]
        gateway_name = gateway_ref.get("name")
        gateway_namespace = gateway_ref.get("namespace")

        if not gateway_name or not gateway_namespace:
            return None

        # Get the Gateway to retrieve the hostname
        gateway = api_instance.get_namespaced_custom_object(
            group="gateway.networking.k8s.io",
            version="v1",
            namespace=gateway_namespace,
            plural="gateways",
            name=gateway_name,
        )

        # Extract hostname from Gateway listeners
        listeners = gateway.get("spec", {}).get("listeners", [])
        if not listeners:
            return None

        hostname = listeners[0].get("hostname")
        if not hostname:
            return None

        # Construct the dashboard URL using RHOAI v3.0+ Gateway API pattern
        # The HTTPRoute existence confirms v3.0+, so we use the standard path pattern
        # Format: https://{hostname}/ray/{namespace}/{cluster-name}
        protocol = "https"  # Gateway API uses HTTPS
        dashboard_url = f"{protocol}://{hostname}/ray/{namespace}/{cluster_name}"

        return dashboard_url

    except Exception as e:  # pragma: no cover
        # If any error occurs, return None to fall back to OpenShift Route
        return None

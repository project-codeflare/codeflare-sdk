"""
Set of APIs to manage rayjobs.
"""

import logging
import time
from kubernetes import client, config
from kubernetes.client.rest import ApiException
from typing import Any, Optional
from codeflare_sdk.vendored.python_client import constants


log = logging.getLogger(__name__)
if logging.getLevelName(log.level) == "NOTSET":
    logging.basicConfig(format="%(asctime)s %(message)s", level=constants.LOGLEVEL)

TERMINAL_JOB_STATUSES = [
    "STOPPED",
    "SUCCEEDED",
    "FAILED",
]


def _format_combined_status(name: str, deployment_status: str, job_status: str) -> str:
    """
    Format combined deployment and job status into a single readable message.

    Args:
        name: The name of the RayJob
        deployment_status: The jobDeploymentStatus value (e.g., "Initializing", "Running", "Complete")
        job_status: The jobStatus value (e.g., "PENDING", "RUNNING", "SUCCEEDED")

    Returns:
        A formatted log message showing both statuses with context
    """
    deployment_status = deployment_status or "Unknown"
    job_status = job_status or "PENDING"

    # Provide contextual descriptions for common state combinations
    if deployment_status == "Initializing":
        context = "RayCluster starting, job waiting"
    elif deployment_status == "Running" and job_status in ["", "PENDING"]:
        context = "RayCluster ready, job starting"
    elif deployment_status == "Running" and job_status == "RUNNING":
        context = "RayCluster ready, job running"
    elif deployment_status == "Suspended":
        context = "RayCluster suspended"
    elif deployment_status == "Suspending":
        context = "RayCluster suspending"
    elif deployment_status in ["Complete", "Failed"]:
        context = "finished"
    elif job_status in TERMINAL_JOB_STATUSES:
        context = "finished"
    else:
        context = ""

    # Build the message - keep it simple and human-readable
    if context:
        return "RayJob '{}': {}".format(name, context)
    else:
        return "RayJob '{}': cluster={}, job={}".format(
            name, deployment_status, job_status
        )


class RayjobApi:
    """
    RayjobApi provides APIs to list, get, create, build, update, delete rayjobs.
    Methods:
    - submit_job(k8s_namespace: str, job: Any) -> Any: Submit and execute a job asynchronously.
    - suspend_job(name: str, k8s_namespace: str) -> bool: Stop a job by suspending it.
    - resubmit_job(name: str, k8s_namespace: str) -> bool: Resubmit a job that has been suspended.
    - get_job(name: str, k8s_namespace: str) -> Any: Get a job.
    - list_jobs(k8s_namespace: str) -> Any: List all jobs.
    - get_job_status(name: str, k8s_namespace: str, timeout: int, delay_between_attempts: int) -> Any: Get the most recent status of a job.
    - wait_until_job_finished(name: str, k8s_namespace: str, timeout: int, delay_between_attempts: int) -> bool: Wait until a job is completed.
    - wait_until_job_running(name: str, k8s_namespace: str, timeout: int, delay_between_attempts: int) -> bool: Wait until a job reaches running state.
    - delete_job(name: str, k8s_namespace: str) -> bool: Delete a job and all of its associated data.
    """

    # initial config to setup the kube client
    def __init__(self):
        # loading the config
        try:
            self.kube_config: Optional[Any] = config.load_kube_config()
        except config.ConfigException:
            # No kubeconfig found, try in-cluster config
            try:
                self.kube_config: Optional[Any] = config.load_incluster_config()
            except config.ConfigException:
                log.error("Failed to load both kubeconfig and in-cluster config")
                raise

        self.api = client.CustomObjectsApi()

    def __del__(self):
        self.api = None
        self.kube_config = None

    def submit_job(self, k8s_namespace: str = "default", job: Any = None) -> Any:
        """Submit a Ray job to a given namespace."""
        try:
            rayjob = self.api.create_namespaced_custom_object(
                group=constants.GROUP,
                version=constants.JOB_VERSION,
                plural=constants.JOB_PLURAL,
                body=job,
                namespace=k8s_namespace,
            )
            return rayjob
        except ApiException as e:
            log.error("error submitting ray job: {}".format(e))
            return None

    def get_job_status(
        self,
        name: str,
        k8s_namespace: str = "default",
        timeout: int = 60,
        delay_between_attempts: int = 5,
    ) -> Any:
        """Get a specific Ray job status in a given namespace.

        This method waits until the job has a status field populated by the operator.

        Parameters:
        - name (str): The name of the Ray job custom resource.
        - k8s_namespace (str, optional): The namespace in which to retrieve the Ray job. Defaults to "default".
        - timeout (int, optional): The duration in seconds after which we stop trying to get status. Defaults to 60 seconds.
        - delay_between_attempts (int, optional): The duration in seconds to wait between attempts. Defaults to 5 seconds.

        Returns:
            Any: The custom resource status for the specified Ray job, or None if not found or timeout.
        """
        while timeout > 0:
            try:
                resource: Any = self.api.get_namespaced_custom_object_status(
                    group=constants.GROUP,
                    version=constants.JOB_VERSION,
                    plural=constants.JOB_PLURAL,
                    name=name,
                    namespace=k8s_namespace,
                )
            except ApiException as e:
                if e.status == 404:
                    log.error("rayjob resource is not found. error = {}".format(e))
                    return None
                else:
                    log.error("error fetching custom resource: {}".format(e))
                    return None

            if resource and "status" in resource and resource["status"]:
                return resource["status"]
            else:
                log.info("rayjob {} status not set yet, waiting...".format(name))
                time.sleep(delay_between_attempts)
                timeout -= delay_between_attempts

        log.info("rayjob {} status not set yet, timing out...".format(name))
        return None

    def wait_until_job_finished(
        self,
        name: str,
        k8s_namespace: str = "default",
        timeout: int = 60,
        delay_between_attempts: int = 5,
    ) -> bool:
        """Wait until a Ray job reaches a terminal status.

        This method waits for the job to reach a terminal state by checking both jobStatus
        (STOPPED, SUCCEEDED, FAILED) and jobDeploymentStatus (Complete, Failed).

        Logs combined status messages showing both deployment and job status together,
        only logging when status changes to reduce noise.

        Parameters:
        - name (str): The name of the Ray job custom resource.
        - k8s_namespace (str, optional): The namespace in which to retrieve the Ray job. Defaults to "default".
        - timeout (int, optional): The duration in seconds after which we stop trying. Defaults to 60 seconds.
        - delay_between_attempts (int, optional): The duration in seconds to wait between attempts. Defaults to 5 seconds.

        Returns:
            bool: True if the rayjob reaches a terminal status, False otherwise.
        """
        prev_deployment_status = None
        prev_job_status = None

        while timeout > 0:
            status = self.get_job_status(
                name, k8s_namespace, timeout, delay_between_attempts
            )

            if status:
                deployment_status = status.get("jobDeploymentStatus", "")
                job_status = status.get("jobStatus", "")

                # Check for terminal states first
                is_terminal = (
                    deployment_status in ["Complete", "Failed"]
                    or job_status in TERMINAL_JOB_STATUSES
                )

                # Log combined status only when there's a change (skip if terminal, we'll log final message instead)
                if (
                    deployment_status != prev_deployment_status
                    or job_status != prev_job_status
                ) and not is_terminal:
                    log.info(
                        _format_combined_status(name, deployment_status, job_status)
                    )
                    prev_deployment_status = deployment_status
                    prev_job_status = job_status

                if is_terminal:
                    log.info(
                        "RayJob '{}': finished with status {}".format(
                            name, job_status or deployment_status
                        )
                    )
                    return True
            else:
                # No status available yet
                if prev_deployment_status is None and prev_job_status is None:
                    log.info("RayJob '{}': waiting for status...".format(name))

            time.sleep(delay_between_attempts)
            timeout -= delay_between_attempts

        log.info("RayJob '{}': timed out waiting for completion".format(name))
        return False

    def wait_until_job_running(
        self,
        name: str,
        k8s_namespace: str = "default",
        timeout: int = 60,
        delay_between_attempts: int = 5,
    ) -> bool:
        """Wait until a Ray job reaches Running state.

        This method waits for the job's jobDeploymentStatus to reach "Running".
        Useful for confirming a job has started after submission or resubmission.

        Logs combined status messages and only logs when status changes to reduce noise.

        Parameters:
        - name (str): The name of the Ray job custom resource.
        - k8s_namespace (str, optional): The namespace in which to retrieve the Ray job. Defaults to "default".
        - timeout (int, optional): The duration in seconds after which we stop trying. Defaults to 60 seconds.
        - delay_between_attempts (int, optional): The duration in seconds to wait between attempts. Defaults to 5 seconds.

        Returns:
            bool: True if the rayjob reaches Running status, False otherwise.
        """
        prev_deployment_status = None
        prev_job_status = None

        while timeout > 0:
            status = self.get_job_status(
                name, k8s_namespace, timeout, delay_between_attempts
            )

            if status:
                deployment_status = status.get("jobDeploymentStatus", "")
                job_status = status.get("jobStatus", "")

                # Log combined status only when there's a change
                if (
                    deployment_status != prev_deployment_status
                    or job_status != prev_job_status
                ):
                    log.info(
                        _format_combined_status(name, deployment_status, job_status)
                    )
                    prev_deployment_status = deployment_status
                    prev_job_status = job_status

                if deployment_status == "Running":
                    return True
                elif deployment_status in ["Complete", "Failed", "Suspended"]:
                    log.info(
                        "RayJob '{}': reached {} before running".format(
                            name, deployment_status
                        )
                    )
                    return False
            else:
                if prev_deployment_status is None:
                    log.info("RayJob '{}': waiting for status...".format(name))

            time.sleep(delay_between_attempts)
            timeout -= delay_between_attempts

        log.info("RayJob '{}': timed out waiting for running state".format(name))
        return False

    def suspend_job(self, name: str, k8s_namespace: str = "default") -> bool:
        """Stop a Ray job by setting the suspend field to True.

        This will delete the associated RayCluster and transition the job to 'Suspended' status.
        Only works on jobs in 'Running' or 'Initializing' status.

        Parameters:
        - name (str): The name of the Ray job custom resource.
        - k8s_namespace (str, optional): The namespace in which to stop the Ray job. Defaults to "default".

        Returns:
            bool: True if the job was successfully suspended, False otherwise.
        """
        try:
            patch_body = {"spec": {"suspend": True}}
            self.api.patch_namespaced_custom_object(
                group=constants.GROUP,
                version=constants.JOB_VERSION,
                plural=constants.JOB_PLURAL,
                name=name,
                namespace=k8s_namespace,
                body=patch_body,
            )
            log.info(
                f"Successfully suspended rayjob {name} in namespace {k8s_namespace}"
            )
            return True
        except ApiException as e:
            if e.status == 404:
                log.error(f"rayjob {name} not found in namespace {k8s_namespace}")
            else:
                log.error(f"error stopping rayjob {name}: {e.reason}")
            return False

    def resubmit_job(self, name: str, k8s_namespace: str = "default") -> bool:
        """Resubmit a suspended Ray job by setting the suspend field to False.

        This will create a new RayCluster and resubmit the job.
        Only works on jobs in 'Suspended' status.

        Parameters:
        - name (str): The name of the Ray job custom resource.
        - k8s_namespace (str, optional): The namespace in which to resubmit the Ray job. Defaults to "default".

        Returns:
            bool: True if the job was successfully resubmitted, False otherwise.
        """
        try:
            # Patch the RayJob to set suspend=false
            patch_body = {"spec": {"suspend": False}}
            self.api.patch_namespaced_custom_object(
                group=constants.GROUP,
                version=constants.JOB_VERSION,
                plural=constants.JOB_PLURAL,
                name=name,
                namespace=k8s_namespace,
                body=patch_body,
            )
            log.info(
                f"Successfully resubmitted rayjob {name} in namespace {k8s_namespace}"
            )
            return True
        except ApiException as e:
            if e.status == 404:
                log.error(f"rayjob {name} not found in namespace {k8s_namespace}")
            else:
                log.error(f"error resubmitting rayjob {name}: {e.reason}")
            return False

    def delete_job(self, name: str, k8s_namespace: str = "default") -> bool:
        """Delete a Ray job and all of its associated data.

        Parameters:
        - name (str): The name of the Ray job custom resource.
        - k8s_namespace (str, optional): The namespace in which to delete the Ray job. Defaults to "default".

        Returns:
            bool: True if the job was successfully deleted, False otherwise.
        """
        try:
            self.api.delete_namespaced_custom_object(
                group=constants.GROUP,
                version=constants.JOB_VERSION,
                plural=constants.JOB_PLURAL,
                name=name,
                namespace=k8s_namespace,
            )
            log.info(f"Successfully deleted rayjob {name} in namespace {k8s_namespace}")
            return True
        except ApiException as e:
            if e.status == 404:
                log.error(f"rayjob custom resource already deleted. error = {e.reason}")
                return False
            else:
                log.error(f"error deleting the rayjob custom resource: {e.reason}")
                return False

    def get_job(self, name: str, k8s_namespace: str = "default") -> Any:
        """Get a Ray job in a given namespace."""
        try:
            return self.api.get_namespaced_custom_object(
                group=constants.GROUP,
                version=constants.JOB_VERSION,
                plural=constants.JOB_PLURAL,
                name=name,
                namespace=k8s_namespace,
            )
        except ApiException as e:
            if e.status == 404:
                log.error(f"rayjob {name} not found in namespace {k8s_namespace}")
                return None
            else:
                log.error(f"error fetching rayjob {name}: {e.reason}")
                return None

    def list_jobs(self, k8s_namespace: str = "default") -> Any:
        """List all Ray jobs in a given namespace."""
        try:
            return self.api.list_namespaced_custom_object(
                group=constants.GROUP,
                version=constants.JOB_VERSION,
                plural=constants.JOB_PLURAL,
                namespace=k8s_namespace,
            )
        except ApiException as e:
            log.error(f"error fetching rayjobs: {e.reason}")
            return None

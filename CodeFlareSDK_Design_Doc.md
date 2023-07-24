# CodeFlare SDK Design Doc

## Context and Scope

The primary purpose for the CodeFlare SDK is to provide a pythonic interaction layer between a user and the CodeFlare Stack (a set of services that enable advanced queuing, resource management and distributed compute on Kubernetes).

The reason that this SDK is needed is due to the fact that many of the benefits associated with the CodeFlare stack are aimed at making the work of data scientists simpler and more efficient. However, since all parts of the CodeFlare stack are separate Kubernetes services, there needs to be something that unifies the interactions between the user and these separate services. Furthermore, we do not expect the average user to be experienced working with Kubernetes infrastructure, and want to provide them with a Python native way of interacting with these services.

The SDK should support any operation that a user would need to do in order to successfully submit machine learning training jobs to their kubernetes cluster.

## Goals

* Serve as an interaction layer between a data scientist and the CodeFlare Stack (MCAD, InstaScale, KubeRay)
* Abstract away user’s infrastructure concerns; Specifically, dealing with Kubernetes resources, consoles, or CLI’s (kubectl).
* Provide users the ability to programmatically request, monitor, and stop the kubernetes resources associated with the CodeFlare stack.

## Non-Goals

* We do not want to re-implement any existing SDK’s or clients for Ray, MCAD, or any other service.

## Architecture and Design

The CodeFlare SDK is a python package that allows a user to programmatically define, create, monitor, and shutdown framework clusters (RayClusters for now) as well as define, submit, monitor and cancel distributed training jobs for machine learning models on an authenticated Kubernetes cluster that has the CodeFlare Stack installed.

In order to achieve this we need the capacity to:

* Generate valid AppWrapper yaml files based on user provided parameters
* Get, list, watch, create, update, patch, and delete AppWrapper custom resources on a kubernetes cluster
* Get, list, watch, create, update, patch, and delete RayCluster custom resources on a kubernetes cluster.
* Expose a secure route to the Ray Dashboard endpoint.
* Define, submit, monitor and cancel Jobs submitted via TorchX. TorchX jobs must support both Ray and MCAD-Kubernetes scheduler backends.
* Provide means of authenticating to a Kubernetes cluster

![](/assets/images/sdk-diagram.png)

### Framework Clusters:

In order to create these framework clusters, we will start with a [template AppWrapper yaml file](/src/codeflare_sdk/templates/base-template.yaml) with reasonable defaults that will generate a valid RayCluster via MCAD.

Users can customize their AppWrapper by passing their desired parameters to `ClusterConfig()` and applying that configuration when initializing a `Cluster()` object. When a `Cluster()` is initialized, it will update the AppWrapper template with the user’s specified requirements, and save it to the current working directory.

Our aim is to simplify the process of generating valid AppWrappers for RayClusters, so we will strive to find the appropriate balance between ease of use and exposing all possible AppWrapper parameters. And we will find this balance through user feedback.

With a valid AppWrapper, we will use the Kubernetes python client to apply the AppWrapper to our Kubernetes cluster via a call to `cluster.up()`

We will also use the Kubernetes python client to get information about both the RayCluster and AppWrapper custom resources to monitor the status of our Framework Cluster via `cluster.status()` and `cluster.details()`.

The RayCluster deployed on your Kubernetes cluster can be interacted with in two ways: Either through an interactive session via `ray.init()` or through the submission of batch jobs.

Finally we will use the Kubernetes python client to delete the AppWrapper via `cluster.down()`

### Training Jobs:

For the submission of Jobs we will rely on the [TorchX](https://pytorch.org/torchx/latest/) job launcher to handle orchestrating the distribution of our model training jobs across the available resources on our cluster. We will support two distributed backend schedulers: Ray and Kubernetes-MCAD. TorchX is designed to be used primarily as a CLI, so we will wrap a limited subset of its functionality into our SDK so that it can be used as part of a python script.

Users can define their jobs with `DDPJobDefinition()` providing parameters for the script they want to run as part of the job, the resources required for the job, additional args specific to the script being run and scheduler being used.

Once a job is defined it can be submitted to the Kubernetes cluster to be run via `job.submit()`. If `job.submit()` is left empty the SDK will assume the Kubernetes-MCAD scheduler is being used. If a RayCluster is specified like, `job.submit(cluster)`, then the SDK will assume that the Ray scheduler is being used and submit the job to that RayCluster.

After the job is submitted, a user can monitor its progress via `job.status()` and `job.logs()` to retrieve the status and logs output by the job. At any point the user can also call `job.cancel()` to stop the job.

### Authentication:

Since we are dealing with controlling and accessing different resources on a Kubernetes cluster, the user will need to have certain permissions on that cluster granted to them by their cluster administrator.

The SDK itself will not enforce any authentication, however, it will provide simple interfaces to allow users to authenticate themselves to their Kubernetes cluster. By default, if a user is already authenticated with a `~/.kube/config` file, that authentication will automatically be picked up by the SDK and no additional authentication is required.

Users can authorize themselves by calling `TokenAuthentication()` and providing their access token and server address. This will populate the Kubernetes python configuration of the ApiClient object and allow users to be properly authenticated to the cluster. Users are also able to toggle whether or not they want to skip tls verification.

Alternatively users can provide their own custom kubeconfig file with `KubeConfigFileAuthentication()` and pass it the correct path.

In either case, users can log out and clear the authentication inputs with `.logout()`

## Alternatives Considered

* Ray API Server
    * Has no notion of MCAD. Does not support any other backends beside Ray. (However, this may change in the near future)
* Ray Python Client
    * Has no notion of MCAD. Does not support any other backends besides Ray
* Existing CodeFlare CLI
    * Is not pythonic.
* Nothing (let users define their own AppWrappers manually)
    * Antithetical to the purpose of the SDK.

## Security Considerations


We will rely on the Kubernetes cluster’s default security, where users cannot perform any operations on a cluster if they are not authenticated correctly.

## Testing and Validation

* Testing plan and strategies

    * Unit testing for all SDK functionality
    * Integration testing of SDK interactions with OpenShift and Kubernetes
    * System tests of SDK as part of the entire CodeFlare stack for main scenarios
* Unit testing, integration testing, and system testing approaches
    * Unit testing will occur with every PR.
    * For system testing we can leverage [current e2e](https://github.com/project-codeflare/codeflare-operator/tree/main/test/e2e) tests from the operator repo.
* Validation criteria and expected outcomes
    * Minimum of 95% code coverage at all times.
    * Expect all unit tests to pass before a PR is merged.
    * Expect all integration and system tests to pass before a new release.

## Deployment and Rollout

* Deployment strategy and considerations
    * The SDK is part of the wider project CodeFlare ecosystem, and serves as the primary interaction layer between the user and the rest of the CodeFlare stack. Therefore, deployment and release strategies cannot occur in isolation, but must take into consideration the current state of the other pieces of the CodeFlare stack (MCAD, KubeRay, Instascale)

* Versioning and release management
    * Releases are performed automatically via a github action.
    * The SDK can have minor releases for urgent bug fixes.
    * The SDK will normally have a new release alongside the rest of the CodeFlare stack with the same version number.

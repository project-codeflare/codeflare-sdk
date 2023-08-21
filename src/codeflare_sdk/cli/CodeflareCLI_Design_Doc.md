# CodeFlare CLI Design


## Context and Scope


The primary purpose of the CLI is to serve as an interaction layer between a user and the CodeFlare stack (MCAD, InstaScale, KubeRay) from within the terminal. This addition is required due to the fact that a large set of our target users come from a high-performance computing background and are most familiar and comfortable submitting jobs to a cluster via a CLI.


The CLI will utilize the existing CodeFlare SDK. It will allow for similar operations that the SDK provides (such as Ray Cluster and job management) but in the terminal. The CLI adds some additional functions, allows for saved time, simpler workspaces, and automation of certain processes via bash scripts on top of the existing SDK.




## Goals


- Provide users the ability to request, monitor and stop the Kubernetes resources associated with the CodeFlare stack within the terminal.
- Serve as an interaction layer between the data scientist and CodeFlare stack  (MCAD, InstaScale, KubeRay)
- Allow for a user-friendly workflow  within the terminal
- Allow for automation and scripting of job/RayCluster management via bash scripts


## Non-Goals


- Do not want to re-make the functionality that is found in the existing CodeFlare SDK or any of the SDK’s clients for Ray, MCAD, or any other service


## Architecture and Design


The CodeFlare CLI is an extension to the  CodeFlare SDK package that allows a user to create, monitor, and shut down framework clusters (RayClusters for now) and distributed training jobs on an authenticated Kubernetes cluster from the terminal.


The user should have the ability to do the following from within the terminal:
- Create, view details, view status, submit, delete Ray Clusters via appwrappers
- Create, view logs, view status, submit, delete jobs
- List out all jobs
- List out all ray clusters
- Login to Kubernetes cluster
- Logout of Kubernetes cluster


To support these operations, additional functions to the SDK may include:
- Formatted listing ray clusters
- Formatted listing jobs
- Getting a job given the name


For the majority of functionality, the CLI will utilize the SDK’s already built functionality.


### CLI Framework:


[Click](https://click.palletsprojects.com/en/8.1.x/) is the chosen CLI framework for the following reasons
- Simple syntax/layout: Since the CLI commands are very complex, it is important that the CLI framework doesn’t add any unnecessary complexity
- Supports functional commands instead of objects: This is important because the SDK is designed with various functions, and the CLI being similar improves readability
- Comes with testing and help generation: Testing library and automatic help generation quickens development process
- Large community support/documentation: extensive documentation and large community leads to less errors and easier development.


### Framework Clusters:


When the user invokes the `define raycluster` command, a yaml file with default values is created and put in the user’s current working directory. Users can customize their clusters by adding parameters to the define command and these values will override the defaults when creating the AppWrapper yaml file.


Once the appwrapper is defined, the user can create the ray cluster via a create command. When the user invokes the `create raycluster`, they will specify the name of the cluster to submit. The CLI will first check to see whether or not the specified name is already present in the Kubernetes cluster. If it isn’t already present, then it will search the current working directory for a yaml file corresponding to cluster name and apply it to the K8S cluster. If the wait flag is specified, then the CLI will display a loading sign with status updates until the cluster is up.


We will try to find a good balance between exposing more parameters and simplifying the process by acting on feedback from CLI users.


For `delete raycluster`, the user will invoke the command, and the CLI will shut it down and delete it.


### Training Jobs


When the user invokes `define job` command, a DDPJobDefiniton object will be created and saved into a file. Users can customize their jobs using parameters to the define command.


Once the job is defined, the user can submit the job via a `job submit` command. When the user submits a job, the user will specify the job name. The CLI will then check to see if the job is already on the Kubernetes cluster and if not it will submit the job. The job submitted will be a DDPJob and it will be submitted onto a specified ray cluster.


When the user wants to delete a job, they just invoke the job delete command, and the CLI will stop the job and delete it. This can happen at any time assuming there is a job running.


### Authentication


Users will need to be authenticated into a Kubernetes cluster in order to be able to perform all operations.


If the user tries to perform any operation without being logged in, the CLI will prompt them to authenticate. A kubeconfig will have to be valid in the users environment in order to perform any operation.


The user will be able to login using a simple `login` command and will have the choice of logging in via server + token. The user can also choose whether or not they want tls-verification. If there is a kubeconfig, the CLI will update it, else it will create one for the user.


Alternatively, the user can invoke the login command with their kubeconfig file path, and this will login the user using their kubeconfig file.


Users can logout of their cluster using the `logout` command.




### Listing Info


Users can list both ray cluster information and job information by invoking respective commands. CLI will list information for each raycluster/job such as requested resources, status, name, and namespace.


## Alternatives Considered


- Existing CodeFlare CLI
   - Written in TypeScript and overcomplicated. Did not support
- Just using SDK
   - Making a CLI saves a lot of time and is easier for the user in some cases
- Interactive CLI
   - Interactive CLIs make it harder for automation via bash scripts
- Other CLI libraries
   - **Cliff:** Ugly syntax, less readability, not much functionality.
   - **Argparse:** Less functionality out of the box. More time spent on unnecessary reimplementation.
   - **Cement:** Ugly syntax and low community support.


## Security Considerations


We will rely on Kubernetes default security, where users can not perform any operations on a cluster if they are not authenticated correctly.


## Testing and Validation
The CLI is found within the SDK, so it will be [tested](https://github.com/project-codeflare/codeflare-sdk/blob/main/CodeFlareSDK_Design_Doc.md#testing-and-validation) the same way.


## Deployment and Rollout
- The CLI will be deployed within the CodeFlare SDK so similar [considerations](https://github.com/project-codeflare/codeflare-sdk/blob/main/CodeFlareSDK_Design_Doc.md#deployment-and-rollout) will be taken into account.


## Command Usage Examples
Create ray cluster
- `codeflare create raycluster [options]`


Doing something to a ray cluster:
- `codeflare {operation} raycluster {cluster_name} [options e.g. --gpu=0]`


Create job
- `codeflare create job [options]`


Doing something to a job:
- `codeflare {operation} job {job_name} [options e.g. cluster-name=”mycluster”]`
- Namespace and ray cluster name will be required as options


Listing out clusters
- `codeflare list raycluster -n {namespace} OR codeflare list ray-cluster –all`


Listing out jobs
- `codeflare list job -c {cluster_name} -n {namespace}`
- `codeflare list job -n {namespace}`
- `codeflare list job --all`


Login to kubernetes cluster
- `codeflare login [options e.g. --configpath={path/to/kubeconfig}]` (if configpath is left blank default value is used)


Logout of kubernetes cluster
- `codeflare logout`

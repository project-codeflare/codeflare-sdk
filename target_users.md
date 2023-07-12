# CodeFlare Stack Target Users

[Cluster Admin](#cluster-administrator)

[Data Scientist I](#data-scientist-i)

[Data Scientist II](#data-scientist-ii)



## Cluster Administrator

* Quota Management
* Gang-Scheduling for Distributed Compute
* Job/Infrastructure Queuing

I want to enable a team of data scientists to have self-serve, but limited, access to a shared pool of distributed compute resources such as GPUs for large scale machine learning model training jobs. If the existing pool of resources is insufficient, I want my cluster to scale up (to a defined quota) to meet my users’ needs and scale back down automatically when their jobs have completed. I want these features to be made available through simple installation of generic modules via a user-friendly interface. I also want the ability to monitor current queue of pending tasks, the utilization of active resources, and the progress of all current jobs visualized in a simple dashboard.

## Data Scientist I

* Training Mid-Size Models (less than 1,000 nodes)
* Fine-Tuning Existing Models
* Distributed Compute Framework

I need temporary access to a reasonably large set of GPU enabled nodes on my team’s shared cluster for short term experimentation, parallelizing my existing ML workflow, or fine-tuning existing large scale models. I’d prefer to work from a notebook environment with access to a python sdk that I can use to request the creation of Framework Clusters that I can distribute my workloads across. In addition to interactive experimentation work, I also want the ability to “fire-and-forget” longer running ML jobs onto temporarily deployed Framework Clusters with the ability to monitor these jobs while they are running and access to all of their artifacts once complete.  I also want to see where my jobs are in the current queue and the progress of all my current jobs visualized in a simple dashboard.

## Data Scientist II
* Training Foundation Models (1,000+ nodes)
* Distributed Compute Framework

I need temporary (but long term) access to a massive amount of GPU enabled infrastructure to train a foundation model. I want to be able to “fire-and-forget” my ML Job into this environment. Due to the size and cost associated with this job, it has already been well tested and validated, so access to jupyter notebooks is unnecessary.  I would prefer to write my job as a bash script leveraging a CLI, or as a python script leveraging an SDK. I need the ability to monitor the job while it is running, as well as access to all of its artifacts once complete. I also want to see where my jobs are in the current queue and the progress of all my current jobs visualized in a simple dashboard.

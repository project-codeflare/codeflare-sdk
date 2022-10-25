import yaml
import sys
import argparse
import uuid

def readTemplate(template):
    with open(template, "r") as stream:
        try:
            return yaml.safe_load(stream)
        except yaml.YAMLError as exc:
            print(exc)

def gen_names():
    gen_id = str(uuid.uuid4())
    appwrapper_name = "appwrapper-" + gen_id
    cluster_name = "cluster-" + gen_id
    return appwrapper_name, cluster_name

def update_names(yaml, item, appwrapper_name, cluster_name):
    metadata = yaml.get("metadata")
    metadata["name"] = appwrapper_name
    lower_meta = item.get("generictemplate", {}).get("metadata")
    lower_meta["labels"]["appwrapper.mcad.ibm.com"] = appwrapper_name
    lower_meta["name"] = cluster_name

def updateCustompodresources(item, cpu, memory, gpu, workers):
    if 'custompodresources' in item.keys():
        custompodresources = item.get('custompodresources')
        for resource in custompodresources:
            for k,v in resource.items():
                if k == "replicas":
                    resource[k] = workers
                if k == "requests" or k == "limits":
                    for spec,_ in v.items():
                        if spec == "cpu":
                            resource[k][spec] = cpu
                        if spec == "memory":
                            resource[k][spec] = str(memory) + "G"
                        if spec == "nvidia.com/gpu":
                            resource[k][spec] = gpu
    else:
        sys.exit("Error: malformed template")

def update_affinity(spec, appwrapper_name):
    node_selector_terms = spec.get("affinity").get("nodeAffinity").get("requiredDuringSchedulingIgnoredDuringExecution").get("nodeSelectorTerms")
    node_selector_terms[0]["matchExpressions"][0]["values"][0] = appwrapper_name

def update_resources(spec, cpu, memory, gpu):
    container = spec.get("containers")
    for resource in container:
        requests = resource.get('resources').get('requests')
        if requests is not None:
            requests["cpu"] = cpu
            requests["memory"] = str(memory) + "G"
            requests["nvidia.com/gpu"] = gpu
        limits = resource.get('resources').get('limits')
        if limits is not None:
            limits["cpu"] = cpu
            limits["memory"] = str(memory) + "G"
            limits["nvidia.com/gpu"] = gpu

def update_nodes(item, appwrapper_name, cpu, memory, gpu, workers):
    if "generictemplate" in item.keys():
        head = item.get("generictemplate").get("spec").get("headGroupSpec")
        worker = item.get("generictemplate").get("spec").get("workerGroupSpecs")[0]

        # Head counts as first worker
        worker["replicas"] = workers - 1
        worker["minReplicas"] = workers - 1
        worker["maxReplicas"] = workers - 1

        for comp in [head, worker]:
            spec = comp.get("template").get("spec")
            update_affinity(spec, appwrapper_name)
            update_resources(spec, cpu, memory, gpu)

def generateAppwrapper(cpu, memory, gpu, workers, template):
        user_yaml = readTemplate(template)
        appwrapper_name, cluster_name = gen_names()
        resources = user_yaml.get("spec","resources")
        item = resources["resources"].get("GenericItems")[0]
        update_names(user_yaml, item, appwrapper_name, cluster_name)
        updateCustompodresources(item, cpu, memory, gpu, workers)
        update_nodes(item, appwrapper_name, cpu, memory, gpu, workers)
        writeUserAppwrapper(user_yaml, appwrapper_name)

def writeUserAppwrapper(user_yaml, appwrapper_name):
    with open(f'{appwrapper_name}.yaml','w') as outfile:
        yaml.dump(user_yaml, outfile, default_flow_style=False)

def main():
    parser = argparse.ArgumentParser(description='Generate user AppWrapper')
    parser.add_argument("--cpu", type=int, required=True, help="number of CPU(s) in a worker required for running job")
    parser.add_argument("--memory", required=True, help="RAM required in a worker for running job")
    parser.add_argument("--gpu",type=int, required=True, help="GPU(s) required in a worker for running job")
    parser.add_argument("--workers", type=int, required=True, help="How many workers are required in the cluster")
    parser.add_argument("--template", required=True, help="Template AppWrapper yaml file")
    
    args = parser.parse_args()
    cpu = args.cpu
    memory = args.memory
    gpu = args.gpu
    workers = args.workers
    template = args.template

    generateAppwrapper(cpu, memory, gpu, workers, template)

if __name__=="__main__":
    main()

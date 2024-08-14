from IPython.display import display, Markdown
from IPython import get_ipython


def generateClusterConfig():
    """
    Generate a ClusterConfiguration template and insert it into a new cell in the Jupyter notebook.
    """
    config_code = """cluster = Cluster(ClusterConfiguration(
    name='',
    head_cpus='',
    head_memory='',
    head_gpus='', # For GPU enabled workloads set the head_gpus and num_gpus
    num_gpus='',
    num_workers='',
    min_cpus='',
    max_cpus='',
    min_memory='',
    max_memory='',
    image="", # Optional Field
    write_to_file=False, # When enabled Ray Cluster yaml files are written to /HOME/.codeflare/resources
    local_queue="" # Specify the local queue manually
))"""

    # Add the generated ClusterConfiguration template into the next cell
    get_ipython().set_next_input(config_code)

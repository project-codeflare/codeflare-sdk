"""
Helper script for testing multiple script mounting in RayJobs
"""
import ray
from datetime import datetime


def get_cluster_info():
    """Get information about the Ray cluster"""
    try:
        cluster_info = {
            "ray_version": ray.__version__,
            "cluster_resources": ray.cluster_resources(),
            "available_resources": ray.available_resources(),
            "nodes": len(ray.nodes()),
            "timestamp": datetime.now().isoformat(),
        }
        return cluster_info
    except Exception as e:
        return {"error": str(e), "timestamp": datetime.now().isoformat()}


def run_simple_ray_task():
    """Run a simple Ray task to test cluster functionality"""

    @ray.remote
    def hello_task(name):
        import time

        time.sleep(1)  # Simulate some work
        return f"Hello {name} from Ray worker!"

    # Submit multiple tasks
    tasks = [hello_task.remote(f"Task-{i}") for i in range(3)]
    results = ray.get(tasks)

    return results


def print_mounted_files():
    """Check what files are available in the scripts directory"""
    import os

    script_dir = "/home/ray/scripts"

    print(f"📁 Contents of {script_dir}:")
    try:
        if os.path.exists(script_dir):
            files = os.listdir(script_dir)
            for file in sorted(files):
                file_path = os.path.join(script_dir, file)
                if os.path.isfile(file_path):
                    size = os.path.getsize(file_path)
                    print(f"  📄 {file} ({size} bytes)")
        else:
            print(f"  ❌ Directory {script_dir} does not exist")
    except Exception as e:
        print(f"  ❌ Error listing files: {e}")

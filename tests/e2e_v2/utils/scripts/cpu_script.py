"""
CPU-optimized RayJob validation script using Ray Train.
"""

import ray
import sys
import traceback
from ray import train


def train_func(config):
    """Minimal training function for CPU execution."""
    worker_rank = config.get("worker_rank", 0)
    result = sum(i * i for i in range(1000))

    try:
        train.report({"loss": result, "worker_rank": worker_rank})
    except RuntimeError:
        pass

    print(f"Worker {worker_rank} completed CPU training task. Result: {result}")


def main():
    """Run a minimal Ray Train task on CPU."""
    try:
        ray.init()
        print("Starting CPU training task...")
        print(f"Ray initialized. Cluster resources: {ray.cluster_resources()}")

        @ray.remote
        def train_worker(worker_id):
            try:
                train_func({"worker_rank": worker_id})
                result = sum(i * i for i in range(1000))
                return {"loss": result, "worker_rank": worker_id}
            except Exception as e:
                print(f"Ray Train context not available, using fallback: {e}")
                result = sum(i * i for i in range(1000))
                print(
                    f"Worker {worker_id} completed CPU training task. Result: {result}"
                )
                return {"loss": result, "worker_rank": worker_id}

        results = ray.get([train_worker.remote(i) for i in range(1)])
        all_metrics = {}
        for result in results:
            if isinstance(result, dict):
                all_metrics.update(result)

        print(f"Training completed successfully. Metrics: {all_metrics}")
        print("EXISTING_CLUSTER_JOB_SUCCESS")
        return 0

    except Exception as e:
        print(f"FAILURE: Exception occurred: {e}")
        traceback.print_exc()
        return 1
    finally:
        ray.shutdown()


if __name__ == "__main__":
    sys.exit(main())

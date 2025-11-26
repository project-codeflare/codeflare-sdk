"""
GPU-optimized RayJob validation script using Ray Train.

This script performs a minimal Ray Train task suitable for GPU execution
to validate that a RayJob can successfully connect to and use an existing Ray cluster
with GPU resources.

Usage as RayJob entrypoint:
    python gpu_script.py
"""

import ray
import sys
from ray import train
from ray.train import ScalingConfig
from ray.train.torch import TorchTrainer


def train_func(config):
    """
    Minimal training function for GPU execution.

    This performs a simple computation task that validates:
    1. Ray Train can initialize with GPU
    2. GPU workers can execute tasks
    3. Results can be aggregated

    Args:
        config: Training configuration dict
    """
    # Get the current worker context
    worker_rank = train.get_context().get_world_rank()

    # Check if GPU is available
    try:
        import torch

        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        print(f"Worker {worker_rank} using device: {device}")

        if torch.cuda.is_available():
            # Simple GPU computation task
            # Create a small tensor and perform computation on GPU
            x = torch.randn(100, 100, device=device)
            y = torch.randn(100, 100, device=device)
            result = torch.matmul(x, y).sum().item()
            print(f"Worker {worker_rank} completed GPU computation. Result: {result}")
        else:
            # Fallback to CPU if GPU not available
            print(f"Worker {worker_rank}: GPU not available, using CPU fallback")
            result = sum(i * i for i in range(1000))
    except ImportError:
        # If PyTorch is not available, use simple CPU computation
        print(f"Worker {worker_rank}: PyTorch not available, using CPU computation")
        result = sum(i * i for i in range(1000))

    # Report metrics back
    train.report({"loss": result, "worker_rank": worker_rank})


def main():
    """
    Run a minimal Ray Train task on GPU.

    This validates that:
    1. Ray can be initialized (auto-connects to cluster when run as RayJob)
    2. Ray Train can execute a distributed task with GPU
    3. The job can complete successfully

    Returns:
        0 on success, 1 on failure
    """
    try:
        # Initialize Ray (auto-connects to cluster when run as RayJob)
        ray.init()

        print("Starting GPU training task...")

        # Check cluster resources
        resources = ray.cluster_resources()
        print(f"Cluster resources: {resources}")

        # Check if GPU is available in the cluster
        gpu_available = "GPU" in resources and resources.get("GPU", 0) > 0
        print(f"GPU available in cluster: {gpu_available}")

        # Create a minimal Ray Train trainer for GPU
        # Using TorchTrainer (the current Ray Train API) with GPU configuration
        trainer = TorchTrainer(
            train_func,
            scaling_config=ScalingConfig(
                num_workers=1,  # Use 1 worker for minimal test
                use_gpu=True,  # Request GPU
            ),
        )

        # Run the training
        result = trainer.fit()

        print(f"Training completed successfully. Metrics: {result.metrics}")

        # Print success marker that tests can check for
        print("EXISTING_CLUSTER_JOB_SUCCESS")

        return 0

    except Exception as e:
        print(f"FAILURE: Exception occurred: {e}")
        import traceback

        traceback.print_exc()
        return 1
    finally:
        ray.shutdown()


if __name__ == "__main__":
    sys.exit(main())

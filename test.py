from time import sleep
import ray

# Import from our helper script (tests multi-script mounting)
from helper import get_cluster_info, run_simple_ray_task, print_mounted_files

print("🚀 Starting Ray job with multiple scripts...")

# Initialize Ray
ray.init(address="auto")

# Test 1: Check mounted files
print("\n" + "=" * 50)
print("TEST 1: Checking mounted script files")
print("=" * 50)
print_mounted_files()

# Test 2: Get cluster information
print("\n" + "=" * 50)
print("TEST 2: Ray cluster information")
print("=" * 50)
cluster_info = get_cluster_info()
for key, value in cluster_info.items():
    print(f"  {key}: {value}")

# Test 3: Run Ray tasks
print("\n" + "=" * 50)
print("TEST 3: Running Ray tasks")
print("=" * 50)
try:
    task_results = run_simple_ray_task()
    for i, result in enumerate(task_results):
        print(f"  Task {i+1}: {result}")
except Exception as e:
    print(f"  ❌ Task execution failed: {e}")

# Test 4: Sleep to simulate work
print("\n" + "=" * 50)
print("TEST 4: Simulating work...")
print("=" * 50)
sleep(5)

print("\n✅ Ray job with multiple scripts completed successfully!")
print("📊 Summary:")
print(f"   • Scripts mounted: test.py, helper.py")
print(f"   • Ray cluster: {cluster_info.get('nodes', 'unknown')} nodes")
print(f"   • Ray version: {cluster_info.get('ray_version', 'unknown')}")

ray.shutdown()

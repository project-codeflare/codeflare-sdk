"""
Ray remote functions example script.

This script demonstrates various Ray remote function patterns
and is used as an entrypoint for RayJobs in E2E tests.

Usage as RayJob entrypoint:
    python ray_remote_functions.py
"""

import ray
import sys
import time


@ray.remote
def simple_task(x):
    """Simple task that doubles a number."""
    return x * 2


@ray.remote
def slow_task(seconds):
    """Task that sleeps for a specified time."""
    time.sleep(seconds)
    return f"Slept for {seconds} seconds"


@ray.remote
def chained_task(x):
    """Task that calls another remote task."""
    result = ray.get(simple_task.remote(x))
    return result + 10


@ray.remote
class Counter:
    """Simple actor for stateful computation."""

    def __init__(self, initial_value=0):
        self.value = initial_value

    def increment(self, amount=1):
        self.value += amount
        return self.value

    def get_value(self):
        return self.value


def test_simple_tasks():
    """Test basic remote function calls."""
    print("Testing simple tasks...")

    results = ray.get([simple_task.remote(i) for i in range(5)])
    expected = [0, 2, 4, 6, 8]

    if results == expected:
        print(f"  PASS: Simple tasks returned {results}")
        return True
    else:
        print(f"  FAIL: Expected {expected}, got {results}")
        return False


def test_parallel_execution():
    """Test that tasks run in parallel."""
    print("Testing parallel execution...")

    start_time = time.time()

    # Launch 3 tasks that each sleep for 1 second
    futures = [slow_task.remote(1) for _ in range(3)]
    results = ray.get(futures)

    elapsed = time.time() - start_time

    # If parallel, should complete in ~1-2 seconds, not 3+ seconds
    if elapsed < 2.5:
        print(f"  PASS: Parallel tasks completed in {elapsed:.2f}s")
        return True
    else:
        print(f"  FAIL: Tasks took {elapsed:.2f}s (should be ~1s if parallel)")
        return False


def test_chained_tasks():
    """Test tasks calling other tasks."""
    print("Testing chained tasks...")

    result = ray.get(chained_task.remote(5))
    expected = 20  # (5 * 2) + 10 = 20

    if result == expected:
        print(f"  PASS: Chained task returned {result}")
        return True
    else:
        print(f"  FAIL: Expected {expected}, got {result}")
        return False


def test_actors():
    """Test Ray actor functionality."""
    print("Testing actors...")

    counter = Counter.remote(0)

    # Increment several times
    for i in range(1, 6):
        ray.get(counter.increment.remote(i))

    final_value = ray.get(counter.get_value.remote())
    expected = 15  # 1 + 2 + 3 + 4 + 5 = 15

    if final_value == expected:
        print(f"  PASS: Counter value is {final_value}")
        return True
    else:
        print(f"  FAIL: Expected {expected}, got {final_value}")
        return False


def main():
    """Run all remote function tests."""
    print("Starting ray remote functions test...")

    try:
        ray.init()
        print(f"Ray initialized. Cluster resources: {ray.cluster_resources()}")

        tests = [
            test_simple_tasks,
            test_parallel_execution,
            test_chained_tasks,
            test_actors,
        ]

        results = []
        for test_fn in tests:
            try:
                results.append(test_fn())
            except Exception as e:
                print(f"  ERROR in {test_fn.__name__}: {e}")
                results.append(False)

        passed = sum(results)
        total = len(results)

        print(f"\nResults: {passed}/{total} tests passed")

        if all(results):
            print("SUCCESS: All remote function tests passed")
            return 0
        else:
            print("FAILURE: Some tests failed")
            return 1

    except Exception as e:
        print(f"FAILURE: Exception occurred: {e}")
        return 1
    finally:
        ray.shutdown()
        print("Ray shutdown complete")


if __name__ == "__main__":
    sys.exit(main())

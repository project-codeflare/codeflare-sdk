"""Unit tests for RayJob status formatting functions."""

import unittest
from codeflare_sdk.vendored.python_client.kuberay_job_api import (
    _format_combined_status,
    TERMINAL_JOB_STATUSES,
)


class TestFormatCombinedStatus(unittest.TestCase):
    """Tests for the _format_combined_status helper function."""

    def test_initializing_status(self):
        """Test formatting when cluster is initializing."""
        result = _format_combined_status("my-job", "Initializing", "PENDING")
        self.assertEqual(result, "RayJob 'my-job': RayCluster starting, job waiting")

    def test_initializing_with_empty_job_status(self):
        """Test formatting when cluster is initializing with empty job status."""
        result = _format_combined_status("my-job", "Initializing", "")
        self.assertEqual(result, "RayJob 'my-job': RayCluster starting, job waiting")

    def test_running_pending(self):
        """Test formatting when cluster is running but job is pending."""
        result = _format_combined_status("my-job", "Running", "PENDING")
        self.assertEqual(result, "RayJob 'my-job': RayCluster ready, job starting")

    def test_running_with_empty_job_status(self):
        """Test formatting when cluster is running with empty job status."""
        result = _format_combined_status("my-job", "Running", "")
        self.assertEqual(result, "RayJob 'my-job': RayCluster ready, job starting")

    def test_running_running(self):
        """Test formatting when both cluster and job are running."""
        result = _format_combined_status("my-job", "Running", "RUNNING")
        self.assertEqual(result, "RayJob 'my-job': RayCluster ready, job running")

    def test_suspended(self):
        """Test formatting when cluster is suspended."""
        result = _format_combined_status("my-job", "Suspended", "PENDING")
        self.assertEqual(result, "RayJob 'my-job': RayCluster suspended")

    def test_suspending(self):
        """Test formatting when cluster is suspending."""
        result = _format_combined_status("my-job", "Suspending", "RUNNING")
        self.assertEqual(result, "RayJob 'my-job': RayCluster suspending")

    def test_complete(self):
        """Test formatting when deployment is complete."""
        result = _format_combined_status("my-job", "Complete", "SUCCEEDED")
        self.assertEqual(result, "RayJob 'my-job': finished")

    def test_failed_deployment(self):
        """Test formatting when deployment failed."""
        result = _format_combined_status("my-job", "Failed", "FAILED")
        self.assertEqual(result, "RayJob 'my-job': finished")

    def test_terminal_job_statuses(self):
        """Test formatting with terminal job statuses."""
        for status in TERMINAL_JOB_STATUSES:
            result = _format_combined_status("my-job", "Running", status)
            self.assertEqual(result, "RayJob 'my-job': finished")

    def test_unknown_status_combination(self):
        """Test formatting with unknown status combination falls back to showing raw values."""
        result = _format_combined_status("my-job", "Unknown", "UNKNOWN")
        self.assertEqual(result, "RayJob 'my-job': cluster=Unknown, job=UNKNOWN")

    def test_none_deployment_status(self):
        """Test formatting with None deployment status."""
        result = _format_combined_status("my-job", None, "PENDING")
        self.assertEqual(result, "RayJob 'my-job': cluster=Unknown, job=PENDING")

    def test_none_job_status(self):
        """Test formatting with None job status defaults to PENDING."""
        result = _format_combined_status("my-job", "Running", None)
        self.assertEqual(result, "RayJob 'my-job': RayCluster ready, job starting")

    def test_both_none(self):
        """Test formatting with both statuses as None."""
        result = _format_combined_status("my-job", None, None)
        self.assertEqual(result, "RayJob 'my-job': cluster=Unknown, job=PENDING")

    def test_empty_strings(self):
        """Test formatting with empty strings."""
        result = _format_combined_status("my-job", "", "")
        self.assertEqual(result, "RayJob 'my-job': cluster=Unknown, job=PENDING")

    def test_job_name_preserved(self):
        """Test that job name is preserved exactly in output."""
        result = _format_combined_status(
            "test-rayjob-test-ns-abc123", "Running", "RUNNING"
        )
        self.assertEqual(
            result, "RayJob 'test-rayjob-test-ns-abc123': RayCluster ready, job running"
        )


if __name__ == "__main__":
    unittest.main()

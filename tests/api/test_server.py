"""Tests for the IntentOS API Bridge server.

TDD: These tests were written BEFORE the implementation.
Uses handler functions directly for unit tests, and a live server for
integration tests (CORS, routing, error handling).
"""

import json
import threading
import time
import unittest
import urllib.error
import urllib.request

from core.api.server import APIBridge


# ---------------------------------------------------------------------------
# Helper: make HTTP requests to the test server
# ---------------------------------------------------------------------------

def _request(method, url, body=None, headers=None):
    """Make an HTTP request and return (status_code, parsed_json, response_headers)."""
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")

    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)

    try:
        resp = urllib.request.urlopen(req, timeout=5)
        raw = resp.read().decode("utf-8")
        return resp.status, json.loads(raw) if raw else {}, dict(resp.headers)
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8")
        return e.code, json.loads(raw) if raw else {}, dict(e.headers)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

class _ServerTestBase(unittest.TestCase):
    """Base class that starts/stops a shared APIBridge server."""

    bridge: APIBridge = None
    port: int = 17891  # high port unlikely to conflict

    @classmethod
    def setUpClass(cls):
        cls.bridge = APIBridge(kernel=None)
        cls.bridge.start(host="127.0.0.1", port=cls.port)
        # Give the server thread a moment to bind
        time.sleep(0.3)

    @classmethod
    def tearDownClass(cls):
        if cls.bridge:
            cls.bridge.stop()

    @property
    def base(self):
        return f"http://127.0.0.1:{self.port}"


# ===========================================================================
# 1. Task endpoint tests
# ===========================================================================

class TestTaskEndpoints(_ServerTestBase):
    """Tests 1-3: submit, get, list tasks."""

    def test_01_submit_task(self):
        """handle_submit_task returns task_id and accepted status."""
        status, body, _ = _request("POST", f"{self.base}/api/task", {"input": "list my files"})
        self.assertEqual(status, 200)
        self.assertIn("task_id", body)
        self.assertEqual(body["status"], "accepted")
        self.__class__._last_task_id = body["task_id"]

    def test_02_get_task(self):
        """handle_get_task returns task info by id."""
        # Submit one first
        _, submit_body, _ = _request("POST", f"{self.base}/api/task", {"input": "test task"})
        task_id = submit_body["task_id"]

        status, body, _ = _request("GET", f"{self.base}/api/task/{task_id}")
        self.assertEqual(status, 200)
        self.assertIn("task_id", body)
        self.assertEqual(body["task_id"], task_id)
        self.assertIn("status", body)
        self.assertIn("input", body)

    def test_03_get_task_not_found(self):
        """Getting a non-existent task returns 404."""
        status, body, _ = _request("GET", f"{self.base}/api/task/nonexistent-id-12345")
        self.assertEqual(status, 404)
        self.assertIn("error", body)

    def test_04_list_tasks(self):
        """handle_list_tasks returns a list of recent tasks."""
        # Submit a couple
        _request("POST", f"{self.base}/api/task", {"input": "task A"})
        _request("POST", f"{self.base}/api/task", {"input": "task B"})

        status, body, _ = _request("GET", f"{self.base}/api/tasks?limit=10")
        self.assertEqual(status, 200)
        self.assertIn("tasks", body)
        self.assertIsInstance(body["tasks"], list)
        self.assertGreaterEqual(len(body["tasks"]), 2)


# ===========================================================================
# 2. Status endpoint tests
# ===========================================================================

class TestStatusEndpoints(_ServerTestBase):
    """Tests 4-5: status and health."""

    def test_05_get_status(self):
        """handle_get_status returns version, model, privacy_mode, hardware."""
        status, body, _ = _request("GET", f"{self.base}/api/status")
        self.assertEqual(status, 200)
        self.assertIn("version", body)
        self.assertIn("model", body)
        self.assertIn("privacy_mode", body)
        self.assertIn("hardware", body)
        self.assertIsInstance(body["hardware"], dict)

    def test_06_get_health(self):
        """handle_get_health returns ok status and uptime."""
        status, body, _ = _request("GET", f"{self.base}/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(body["status"], "ok")
        self.assertIn("uptime_seconds", body)
        self.assertIsInstance(body["uptime_seconds"], (int, float))
        self.assertGreaterEqual(body["uptime_seconds"], 0)


# ===========================================================================
# 3. Settings endpoint tests
# ===========================================================================

class TestSettingsEndpoints(_ServerTestBase):
    """Tests 6-7: get and update settings."""

    def test_07_get_settings(self):
        """handle_get_settings returns a settings dict."""
        status, body, _ = _request("GET", f"{self.base}/api/settings")
        self.assertEqual(status, 200)
        self.assertIn("privacy_mode", body)

    def test_08_update_settings(self):
        """handle_update_settings applies changes and returns updated settings."""
        status, body, _ = _request("PUT", f"{self.base}/api/settings", {"privacy_mode": "local_only"})
        self.assertEqual(status, 200)
        self.assertEqual(body["privacy_mode"], "local_only")

        # Verify it persisted
        status2, body2, _ = _request("GET", f"{self.base}/api/settings")
        self.assertEqual(body2["privacy_mode"], "local_only")


# ===========================================================================
# 4. Cost endpoint tests
# ===========================================================================

class TestCostEndpoints(_ServerTestBase):
    """Tests 8-9: cost report and per-task cost."""

    def test_09_get_cost(self):
        """handle_get_cost returns a cost report."""
        status, body, _ = _request("GET", f"{self.base}/api/cost")
        self.assertEqual(status, 200)
        self.assertIn("total_spent_usd", body)
        self.assertIn("call_count", body)

    def test_10_get_cost_by_task(self):
        """handle_get_cost with task_id query param returns per-task cost."""
        status, body, _ = _request("GET", f"{self.base}/api/cost?task_id=some-task-id")
        self.assertEqual(status, 200)
        # Even if no data, should return a valid structure
        self.assertIn("task_id", body)


# ===========================================================================
# 5. History endpoint tests
# ===========================================================================

class TestHistoryEndpoints(_ServerTestBase):
    """Tests 10-11: paginated history and search."""

    def test_11_get_history(self):
        """handle_get_history returns paginated task history."""
        status, body, _ = _request("GET", f"{self.base}/api/history?limit=20&offset=0")
        self.assertEqual(status, 200)
        self.assertIn("tasks", body)
        self.assertIn("total", body)
        self.assertIsInstance(body["tasks"], list)

    def test_12_search_history(self):
        """handle_search_history searches past tasks by query."""
        # Submit a task with a distinctive keyword
        _request("POST", f"{self.base}/api/task", {"input": "organize my photos uniqueword123"})

        status, body, _ = _request("GET", f"{self.base}/api/history?query=uniqueword123")
        self.assertEqual(status, 200)
        self.assertIn("tasks", body)


# ===========================================================================
# 6. Security endpoint tests
# ===========================================================================

class TestSecurityEndpoints(_ServerTestBase):
    """Test 12: security stats."""

    def test_13_get_security_stats(self):
        """handle_get_security_stats returns pipeline stats."""
        status, body, _ = _request("GET", f"{self.base}/api/security")
        self.assertEqual(status, 200)
        self.assertIn("total_scans", body)
        self.assertIn("inputs_blocked", body)
        self.assertIn("leaks_redacted", body)


# ===========================================================================
# 7. Credential endpoint tests
# ===========================================================================

class TestCredentialEndpoints(_ServerTestBase):
    """Tests 13-15: list, store, delete credentials."""

    def test_14_store_credential(self):
        """handle_store_credential stores a credential and returns success."""
        status, body, _ = _request(
            "POST",
            f"{self.base}/api/credentials",
            {"name": "TEST_API_KEY", "value": "sk-test-12345"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["status"], "stored")

    def test_15_list_credentials(self):
        """handle_list_credentials returns credential names (not values)."""
        # Store one first
        _request("POST", f"{self.base}/api/credentials", {"name": "LIST_TEST_KEY", "value": "secret"})

        status, body, _ = _request("GET", f"{self.base}/api/credentials")
        self.assertEqual(status, 200)
        self.assertIn("credentials", body)
        self.assertIsInstance(body["credentials"], list)
        # Values must NOT appear
        for name in body["credentials"]:
            self.assertIsInstance(name, str)
            self.assertNotIn("secret", name)

    def test_16_delete_credential(self):
        """handle_delete_credential removes a credential."""
        # Store then delete
        _request("POST", f"{self.base}/api/credentials", {"name": "DEL_KEY", "value": "todelete"})

        status, body, _ = _request("DELETE", f"{self.base}/api/credentials/DEL_KEY")
        self.assertEqual(status, 200)
        self.assertEqual(body["status"], "deleted")


# ===========================================================================
# 8. APIBridge class tests
# ===========================================================================

class TestAPIBridgeClass(unittest.TestCase):
    """Tests 16-19: construction, start/stop, routing."""

    def test_17_create_without_kernel(self):
        """APIBridge can be created without a kernel (uses mock)."""
        bridge = APIBridge(kernel=None)
        self.assertIsNotNone(bridge)

    def test_18_create_with_kernel(self):
        """APIBridge can be created with a kernel object."""

        class FakeKernel:
            pass

        bridge = APIBridge(kernel=FakeKernel())
        self.assertIsNotNone(bridge)

    def test_19_start_and_stop(self):
        """APIBridge starts and stops cleanly."""
        bridge = APIBridge(kernel=None)
        bridge.start(host="127.0.0.1", port=17892)
        time.sleep(0.2)

        # Verify it's listening
        try:
            status, body, _ = _request("GET", "http://127.0.0.1:17892/api/health")
            self.assertEqual(status, 200)
        finally:
            bridge.stop()

        # Verify it stopped — connection should be refused
        time.sleep(0.2)
        with self.assertRaises(Exception):
            _request("GET", "http://127.0.0.1:17892/api/health")

    def test_20_routes_map_to_handlers(self):
        """Route table maps URL paths to handler functions."""
        bridge = APIBridge(kernel=None)
        # The bridge should have a routes/handlers structure
        self.assertTrue(hasattr(bridge, "_routes") or hasattr(bridge, "_handlers"))


# ===========================================================================
# 9. CORS tests
# ===========================================================================

class TestCORS(_ServerTestBase):
    """Test 20: CORS headers on all responses."""

    def test_21_cors_headers_present(self):
        """All responses include CORS headers."""
        status, body, headers = _request("GET", f"{self.base}/api/health")
        # Check for Access-Control-Allow-Origin
        cors_header = headers.get("Access-Control-Allow-Origin", "")
        self.assertIn("*", cors_header)

    def test_22_options_preflight(self):
        """OPTIONS request returns CORS preflight headers."""
        req = urllib.request.Request(f"{self.base}/api/health", method="OPTIONS")
        try:
            resp = urllib.request.urlopen(req, timeout=5)
            self.assertIn(resp.status, (200, 204))
            self.assertIn("Access-Control-Allow-Origin", dict(resp.headers))
            self.assertIn("Access-Control-Allow-Methods", dict(resp.headers))
        except urllib.error.HTTPError as e:
            # Some implementations return 200 for OPTIONS
            self.assertIn(e.code, (200, 204))


# ===========================================================================
# 10. Error handling tests
# ===========================================================================

class TestErrorHandling(_ServerTestBase):
    """Tests 21-23: 404, 500, 400."""

    def test_23_unknown_endpoint_returns_404(self):
        """Unknown endpoint returns 404 with error message."""
        status, body, _ = _request("GET", f"{self.base}/api/nonexistent")
        self.assertEqual(status, 404)
        self.assertIn("error", body)

    def test_24_invalid_json_returns_400(self):
        """Invalid JSON body returns 400."""
        # Send raw invalid JSON
        data = b"this is not json{"
        req = urllib.request.Request(
            f"{self.base}/api/task",
            data=data,
            method="POST",
        )
        req.add_header("Content-Type", "application/json")
        try:
            resp = urllib.request.urlopen(req, timeout=5)
            self.fail("Expected HTTPError")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 400)
            body = json.loads(e.read().decode("utf-8"))
            self.assertIn("error", body)

    def test_25_submit_task_missing_input(self):
        """Submit task without 'input' field returns 400."""
        status, body, _ = _request("POST", f"{self.base}/api/task", {"no_input_field": True})
        self.assertEqual(status, 400)
        self.assertIn("error", body)


# ===========================================================================
# 11. Execution bridge tests — API → kernel.process_task()
# ===========================================================================

class _FakeExecutionResult:
    """Minimal stand-in for ExecutionResult."""
    def __init__(self, agent_name, action, status, output=None, error=None):
        self.agent_name = agent_name
        self.action = action
        self.status = status
        self.output = output or {}
        self.error = error
        self.paths_accessed = []


class _FakeTaskResult:
    """Minimal stand-in for TaskResult returned by IntentKernel.process_task()."""
    def __init__(self, status="success", report="Done.", cost_usd=0.0,
                 duration_ms=42, intent=None, execution_results=None, error=None):
        self.task_id = "fake-id"
        self.status = status
        self.report = report
        self.cost_usd = cost_usd
        self.duration_ms = duration_ms
        self.intent = intent or {"intent": "file.list", "subtasks": []}
        self.execution_results = execution_results or []
        self.error = error
        self.security_warnings = []
        self.sop_result = None


class _ExecutableKernel:
    """Fake kernel with a working process_task() for testing the execution bridge."""
    model = "test-model"
    settings = {"privacy_mode": "local_only"}

    def __init__(self, result=None, delay=0):
        self._result = result or _FakeTaskResult()
        self._delay = delay
        self.called_with = None

    def process_task(self, user_input):
        self.called_with = user_input
        if self._delay:
            time.sleep(self._delay)
        return self._result


class TestExecutionBridge(unittest.TestCase):
    """Tests 26-30: API server actually executes tasks via the kernel."""

    def test_26_task_executes_and_completes(self):
        """Submitting a task to a kernel-backed bridge results in completed status."""
        fake_result = _FakeTaskResult(
            status="success",
            report="Found 5 files.",
            cost_usd=0.001,
            duration_ms=150,
            execution_results=[
                _FakeExecutionResult(
                    "file_agent", "list_files", "success",
                    output={"action_performed": "Listed 5 files", "result": ["a.txt", "b.txt"]},
                ),
            ],
        )
        kernel = _ExecutableKernel(result=fake_result)
        bridge = APIBridge(kernel=kernel)
        bridge.start(host="127.0.0.1", port=17893)
        time.sleep(0.2)

        try:
            # Submit
            status, body, _ = _request("POST", "http://127.0.0.1:17893/api/task",
                                       {"input": "list my files"})
            self.assertEqual(status, 200)
            task_id = body["task_id"]

            # Poll until completed (max 3 seconds)
            for _ in range(30):
                time.sleep(0.1)
                status, body, _ = _request("GET", f"http://127.0.0.1:17893/api/task/{task_id}")
                if body.get("status") in ("completed", "success", "error"):
                    break

            # Verify the kernel was called
            self.assertEqual(kernel.called_with, "list my files")

            # Verify the task completed with results
            self.assertIn(body["status"], ("completed", "success"))
            self.assertEqual(body["report"], "Found 5 files.")
            self.assertIsNotNone(body["result"])
            self.assertGreater(body["duration_ms"], 0)
        finally:
            bridge.stop()

    def test_27_task_error_propagates(self):
        """A kernel error is reflected in the task status."""
        fake_result = _FakeTaskResult(
            status="error",
            error="Could not understand that instruction",
        )
        kernel = _ExecutableKernel(result=fake_result)
        bridge = APIBridge(kernel=kernel)
        bridge.start(host="127.0.0.1", port=17894)
        time.sleep(0.2)

        try:
            _, body, _ = _request("POST", "http://127.0.0.1:17894/api/task",
                                  {"input": "do something impossible"})
            task_id = body["task_id"]

            for _ in range(30):
                time.sleep(0.1)
                _, body, _ = _request("GET", f"http://127.0.0.1:17894/api/task/{task_id}")
                if body.get("status") != "running" and body.get("status") != "accepted":
                    break

            self.assertEqual(body["status"], "error")
            self.assertIn("Could not understand", body["error"])
        finally:
            bridge.stop()

    def test_28_mock_kernel_skips_execution(self):
        """With no real kernel (mock), task stays at accepted — no background execution."""
        bridge = APIBridge(kernel=None)
        bridge.start(host="127.0.0.1", port=17895)
        time.sleep(0.2)

        try:
            _, body, _ = _request("POST", "http://127.0.0.1:17895/api/task",
                                  {"input": "list files"})
            task_id = body["task_id"]
            time.sleep(0.3)

            _, body, _ = _request("GET", f"http://127.0.0.1:17895/api/task/{task_id}")
            self.assertEqual(body["status"], "accepted")
        finally:
            bridge.stop()

    def test_29_task_shows_running_state(self):
        """While kernel is processing, task status should be 'running'."""
        # Use a slow kernel to catch the running state
        fake_result = _FakeTaskResult(status="success", report="Done")
        kernel = _ExecutableKernel(result=fake_result, delay=1)
        bridge = APIBridge(kernel=kernel)
        bridge.start(host="127.0.0.1", port=17896)
        time.sleep(0.2)

        try:
            _, body, _ = _request("POST", "http://127.0.0.1:17896/api/task",
                                  {"input": "slow task"})
            task_id = body["task_id"]
            time.sleep(0.2)  # should be running by now

            _, body, _ = _request("GET", f"http://127.0.0.1:17896/api/task/{task_id}")
            self.assertEqual(body["status"], "running")

            # Wait for completion
            time.sleep(1.5)
            _, body, _ = _request("GET", f"http://127.0.0.1:17896/api/task/{task_id}")
            self.assertIn(body["status"], ("completed", "success"))
        finally:
            bridge.stop()


if __name__ == "__main__":
    unittest.main()

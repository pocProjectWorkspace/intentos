"""IntentOS API Bridge — HTTP server connecting the kernel to GUI/admin console.

Uses only Python built-in modules (http.server, json, threading).
Designed for testability: handler functions take parsed data and return
response data; the HTTP layer is a thin wrapper.

Route table:
    POST   /api/task              -> handle_submit_task
    GET    /api/task/:id          -> handle_get_task
    GET    /api/tasks             -> handle_list_tasks
    GET    /api/status            -> handle_get_status
    GET    /api/health            -> handle_get_health
    GET    /api/settings          -> handle_get_settings
    PUT    /api/settings          -> handle_update_settings
    GET    /api/cost              -> handle_get_cost
    GET    /api/history           -> handle_get_history
    GET    /api/security          -> handle_get_security_stats
    GET    /api/credentials       -> handle_list_credentials
    POST   /api/credentials       -> handle_store_credential
    DELETE /api/credentials/:name -> handle_delete_credential
"""

from __future__ import annotations

import json
import platform
import re
import threading
import time
import uuid
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlparse, parse_qs


# ---------------------------------------------------------------------------
# Version
# ---------------------------------------------------------------------------

VERSION = "2.0.0"


# ---------------------------------------------------------------------------
# Lightweight mock kernel for when no real kernel is provided
# ---------------------------------------------------------------------------

class _MockKernel:
    """Provides stubs so the API can run without a real kernel (testing/dev)."""

    def __init__(self):
        self.model = "claude-sonnet-4-20250514"
        self.settings = {
            "privacy_mode": "standard",
            "model": "claude-sonnet-4-20250514",
            "verbose": False,
            "dry_run_preview": True,
            "budget_limit_usd": None,
        }


# ---------------------------------------------------------------------------
# APIBridge
# ---------------------------------------------------------------------------

class APIBridge:
    """HTTP API bridge between the IntentOS kernel and GUI/admin frontends.

    Args:
        kernel: A kernel instance (or None for a lightweight mock).
    """

    def __init__(self, kernel=None):
        self._kernel = kernel or _MockKernel()
        self._server: Optional[HTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._start_time: float = time.monotonic()

        # In-memory stores (production would back these with persistence)
        self._tasks: Dict[str, dict] = {}
        self._task_order: List[str] = []  # ordered by submission time
        self._credentials: Dict[str, str] = {}

        # Security pipeline stats (mock if no real pipeline)
        self._security_stats = {
            "total_scans": 0,
            "inputs_blocked": 0,
            "outputs_blocked": 0,
            "leaks_redacted": 0,
            "policy_violations": 0,
        }

        # Cost manager (mock if no real one)
        self._cost_data = {
            "total_spent_usd": 0.0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "by_model": {},
            "by_task": {},
            "call_count": 0,
        }

        # Try to wire real subsystems from kernel
        self._wire_kernel_subsystems()

        # Build route table
        self._routes = self._build_routes()
        # Also expose as _handlers for compatibility
        self._handlers = self._routes

    def _wire_kernel_subsystems(self):
        """If the kernel has real subsystems, use them."""
        kernel = self._kernel

        # Security pipeline
        if hasattr(kernel, "security_pipeline"):
            pipeline = kernel.security_pipeline
            if hasattr(pipeline, "get_stats"):
                self._get_security_stats_fn = pipeline.get_stats
            else:
                self._get_security_stats_fn = None
        else:
            self._get_security_stats_fn = None

        # Cost manager
        if hasattr(kernel, "cost_manager"):
            self._cost_manager = kernel.cost_manager
        else:
            self._cost_manager = None

        # Credential provider
        if hasattr(kernel, "credential_provider"):
            self._credential_provider = kernel.credential_provider
        else:
            self._credential_provider = None

    # -- Route table --------------------------------------------------------

    def _build_routes(self) -> List[Tuple[str, str, Callable]]:
        """Build the route table: list of (method, path_pattern, handler).

        Path patterns use :param for path parameters.
        """
        return [
            ("POST",   r"/api/task$",                self.handle_submit_task),
            ("GET",    r"/api/task/(?P<task_id>[^/]+)$", self.handle_get_task),
            ("GET",    r"/api/tasks$",               self.handle_list_tasks),
            ("GET",    r"/api/status$",              self.handle_get_status),
            ("GET",    r"/api/health$",              self.handle_get_health),
            ("GET",    r"/api/settings$",            self.handle_get_settings),
            ("PUT",    r"/api/settings$",            self.handle_update_settings),
            ("GET",    r"/api/cost$",                self.handle_get_cost),
            ("GET",    r"/api/history$",             self.handle_get_history),
            ("GET",    r"/api/security$",            self.handle_get_security_stats),
            ("GET",    r"/api/credentials$",         self.handle_list_credentials),
            ("POST",   r"/api/credentials$",         self.handle_store_credential),
            ("DELETE", r"/api/credentials/(?P<name>[^/]+)$", self.handle_delete_credential),
            ("POST",   r"/api/voice/listen$",            self.handle_voice_listen),
        ]

    def _match_route(self, method: str, path: str) -> Optional[Tuple[Callable, dict]]:
        """Find a matching route for the given method and path.

        Returns (handler, path_params) or None.
        """
        for route_method, pattern, handler in self._routes:
            if route_method != method:
                continue
            m = re.match(pattern, path)
            if m:
                return handler, m.groupdict()
        return None

    # -- Server lifecycle ---------------------------------------------------

    def start(self, host: str = "127.0.0.1", port: int = 7891) -> None:
        """Start the HTTP server in a background thread."""
        bridge = self

        class _Handler(BaseHTTPRequestHandler):
            """Request handler that delegates to APIBridge methods."""

            def log_message(self, format, *args):
                # Suppress default stderr logging during tests
                pass

            # -- CORS & preflight -------------------------------------------

            def _send_cors_headers(self):
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

            def do_OPTIONS(self):
                self.send_response(200)
                self._send_cors_headers()
                self.send_header("Content-Length", "0")
                self.end_headers()

            # -- Dispatch ---------------------------------------------------

            def _dispatch(self, method: str):
                parsed = urlparse(self.path)
                path = parsed.path.rstrip("/") if parsed.path != "/" else "/"
                query_params = parse_qs(parsed.query)

                # Flatten single-value query params
                flat_query = {k: v[0] if len(v) == 1 else v for k, v in query_params.items()}

                match = bridge._match_route(method, path)
                if match is None:
                    self._send_json(404, {"error": "Not found"})
                    return

                handler, path_params = match

                # Parse body for POST/PUT
                body = None
                if method in ("POST", "PUT"):
                    content_length = int(self.headers.get("Content-Length", 0))
                    if content_length > 0:
                        raw = self.rfile.read(content_length)
                        try:
                            body = json.loads(raw)
                        except (json.JSONDecodeError, UnicodeDecodeError):
                            self._send_json(400, {"error": "Invalid JSON in request body"})
                            return

                # Build request context
                request_data = {
                    "body": body or {},
                    "query": flat_query,
                    "path_params": path_params,
                }

                try:
                    status_code, response_body = handler(request_data)
                except Exception:
                    self._send_json(500, {"error": "Internal error"})
                    return

                self._send_json(status_code, response_body)

            def _send_json(self, status: int, data: dict):
                payload = json.dumps(data).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self._send_cors_headers()
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def do_GET(self):
                self._dispatch("GET")

            def do_POST(self):
                self._dispatch("POST")

            def do_PUT(self):
                self._dispatch("PUT")

            def do_DELETE(self):
                self._dispatch("DELETE")

        self._server = HTTPServer((host, port), _Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Shut down the HTTP server."""
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None

    # ======================================================================
    # Handler functions
    #
    # Each handler receives a request_data dict:
    #   {"body": dict, "query": dict, "path_params": dict}
    # and returns (status_code: int, response_body: dict).
    # ======================================================================

    # -- Task endpoints -----------------------------------------------------

    def handle_submit_task(self, req: dict) -> Tuple[int, dict]:
        """POST /api/task — submit a new task."""
        body = req["body"]
        user_input = body.get("input")
        if not user_input:
            return 400, {"error": "Missing required field: input"}

        task_id = str(uuid.uuid4())
        task = {
            "task_id": task_id,
            "input": user_input,
            "status": "accepted",
            "created_at": time.time(),
            "result": None,
        }
        self._tasks[task_id] = task
        self._task_order.append(task_id)

        return 200, {"task_id": task_id, "status": "accepted"}

    def handle_get_task(self, req: dict) -> Tuple[int, dict]:
        """GET /api/task/:id — get task status and result."""
        task_id = req["path_params"]["task_id"]
        task = self._tasks.get(task_id)
        if task is None:
            return 404, {"error": f"Task not found: {task_id}"}
        return 200, task

    def handle_list_tasks(self, req: dict) -> Tuple[int, dict]:
        """GET /api/tasks — list recent tasks."""
        limit = int(req["query"].get("limit", 10))
        # Return most recent first
        recent_ids = list(reversed(self._task_order[-limit:]))
        tasks = [self._tasks[tid] for tid in recent_ids if tid in self._tasks]
        return 200, {"tasks": tasks}

    # -- Status endpoints ---------------------------------------------------

    def handle_get_status(self, req: dict) -> Tuple[int, dict]:
        """GET /api/status — system status."""
        return 200, {
            "version": VERSION,
            "model": getattr(self._kernel, "model", "unknown"),
            "privacy_mode": self._get_setting("privacy_mode", "standard"),
            "hardware": {
                "platform": platform.system(),
                "arch": platform.machine(),
                "python": platform.python_version(),
            },
        }

    def handle_get_health(self, req: dict) -> Tuple[int, dict]:
        """GET /api/health — health check."""
        uptime = time.monotonic() - self._start_time
        return 200, {
            "status": "ok",
            "uptime_seconds": round(uptime, 2),
        }

    # -- Settings endpoints -------------------------------------------------

    def _get_setting(self, key: str, default: Any = None) -> Any:
        """Get a setting from the kernel."""
        settings = getattr(self._kernel, "settings", {})
        return settings.get(key, default)

    def handle_get_settings(self, req: dict) -> Tuple[int, dict]:
        """GET /api/settings — current settings."""
        settings = getattr(self._kernel, "settings", {})
        return 200, dict(settings)

    def handle_update_settings(self, req: dict) -> Tuple[int, dict]:
        """PUT /api/settings — update settings."""
        body = req["body"]
        settings = getattr(self._kernel, "settings", {})
        for key, value in body.items():
            settings[key] = value
        # Write back in case it was a copy
        if hasattr(self._kernel, "settings"):
            self._kernel.settings = settings
        return 200, dict(settings)

    # -- Cost endpoints -----------------------------------------------------

    def handle_get_cost(self, req: dict) -> Tuple[int, dict]:
        """GET /api/cost — cost report (optionally per task)."""
        task_id = req["query"].get("task_id")

        if task_id:
            # Per-task cost
            if self._cost_manager:
                usage = self._cost_manager.get_task_report(task_id)
                if usage:
                    return 200, {
                        "task_id": task_id,
                        "input_tokens": usage.input_tokens,
                        "output_tokens": usage.output_tokens,
                        "cost_usd": usage.cost_usd,
                        "call_count": usage.call_count,
                    }
            return 200, {
                "task_id": task_id,
                "input_tokens": 0,
                "output_tokens": 0,
                "cost_usd": 0.0,
                "call_count": 0,
            }

        # Full cost report
        if self._cost_manager:
            report = self._cost_manager.get_report()
            return 200, report.to_dict()

        return 200, dict(self._cost_data)

    # -- History endpoints --------------------------------------------------

    def handle_get_history(self, req: dict) -> Tuple[int, dict]:
        """GET /api/history — paginated task history, optionally searched."""
        limit = int(req["query"].get("limit", 20))
        offset = int(req["query"].get("offset", 0))
        query = req["query"].get("query", "")

        all_ids = list(reversed(self._task_order))

        if query:
            # Filter by search term in input
            filtered = [
                tid for tid in all_ids
                if query.lower() in self._tasks.get(tid, {}).get("input", "").lower()
            ]
        else:
            filtered = all_ids

        total = len(filtered)
        page_ids = filtered[offset : offset + limit]
        tasks = [self._tasks[tid] for tid in page_ids if tid in self._tasks]

        return 200, {"tasks": tasks, "total": total, "limit": limit, "offset": offset}

    # -- Security endpoints -------------------------------------------------

    def handle_get_security_stats(self, req: dict) -> Tuple[int, dict]:
        """GET /api/security — security pipeline stats."""
        if self._get_security_stats_fn:
            return 200, self._get_security_stats_fn()
        return 200, dict(self._security_stats)

    # -- Credential endpoints -----------------------------------------------

    def handle_list_credentials(self, req: dict) -> Tuple[int, dict]:
        """GET /api/credentials — list credential names (never values)."""
        if self._credential_provider:
            names = self._credential_provider.list_stored()
        else:
            names = list(self._credentials.keys())
        return 200, {"credentials": names}

    def handle_store_credential(self, req: dict) -> Tuple[int, dict]:
        """POST /api/credentials — store a credential."""
        body = req["body"]
        name = body.get("name")
        value = body.get("value")

        if not name or not value:
            return 400, {"error": "Missing required fields: name, value"}

        if self._credential_provider:
            self._credential_provider.store(name, value)
        else:
            self._credentials[name] = value

        return 200, {"status": "stored", "name": name}

    def handle_delete_credential(self, req: dict) -> Tuple[int, dict]:
        """DELETE /api/credentials/:name — delete a credential."""
        name = req["path_params"]["name"]

        if self._credential_provider:
            self._credential_provider.delete(name)
        else:
            self._credentials.pop(name, None)

        return 200, {"status": "deleted", "name": name}

    # -- Voice endpoints ----------------------------------------------------

    def handle_voice_listen(self, req: dict) -> Tuple[int, dict]:
        """POST /api/voice/listen — record from microphone and transcribe."""
        try:
            from core.voice.stt import VoiceInput
        except ImportError:
            return 500, {"error": "Voice module not available"}

        body = req.get("body", {})
        duration = body.get("duration", 5)

        vi = VoiceInput()
        if not vi.is_available():
            return 503, {
                "error": "Voice input not available. Install: pip install SpeechRecognition pyaudio",
            }

        result = vi.listen_and_transcribe(duration=duration)
        if result and result.text:
            return 200, {
                "text": result.text,
                "confidence": result.confidence,
                "provider": result.provider,
                "duration_seconds": result.duration_seconds,
                "language": result.language,
            }

        return 200, {
            "text": None,
            "confidence": 0.0,
            "error": "Could not understand audio",
        }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    """Start the API bridge as a standalone server."""
    import argparse

    parser = argparse.ArgumentParser(description="IntentOS API Bridge")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address")
    parser.add_argument("--port", type=int, default=7891, help="Port number")
    args = parser.parse_args()

    bridge = APIBridge(kernel=None)
    bridge.start(host=args.host, port=args.port)
    print(f"IntentOS API Bridge running on http://{args.host}:{args.port}")
    print("Press Ctrl+C to stop.")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down...")
        bridge.stop()


if __name__ == "__main__":
    main()

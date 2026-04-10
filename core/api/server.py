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

import base64
import json
import os
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
        self._uploaded_files: Dict[str, dict] = {}  # file_id -> {path, name, mime}

        # Upload directory
        self._upload_dir = os.path.join(
            os.path.expanduser("~"), ".intentos", "workspace", "uploads"
        )
        os.makedirs(self._upload_dir, exist_ok=True)

        # Chat persistence
        try:
            from core.storage.chat_store import ChatStore
            self._chat_store = ChatStore()
        except Exception:
            self._chat_store = None

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
            ("GET",    r"/api/sessions$",               self.handle_list_sessions),
            ("POST",   r"/api/sessions$",               self.handle_create_session),
            ("GET",    r"/api/sessions/(?P<session_id>[^/]+)/messages$", self.handle_get_messages),
            ("DELETE", r"/api/sessions/(?P<session_id>[^/]+)$", self.handle_delete_session),
            ("POST",   r"/api/upload$",                 self.handle_upload_file),
            ("POST",   r"/api/voice/listen$",            self.handle_voice_listen),
            ("POST",   r"/api/voice/speak$",             self.handle_voice_speak),
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
                parsed = urlparse(self.path)
                path = parsed.path.rstrip("/") if parsed.path != "/" else "/"

                # SSE streaming endpoint — handled directly (not via JSON dispatch)
                if path == "/api/task/stream":
                    self._handle_stream()
                    return

                self._dispatch("POST")

            def _handle_stream(self):
                """Handle POST /api/task/stream via Server-Sent Events."""
                content_length = int(self.headers.get("Content-Length", 0))
                if content_length <= 0:
                    self._send_json(400, {"error": "Missing request body"})
                    return

                raw = self.rfile.read(content_length)
                try:
                    body = json.loads(raw)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    self._send_json(400, {"error": "Invalid JSON"})
                    return

                user_input = body.get("input", "")
                file_id = body.get("file_id")
                session_id = body.get("session_id")
                if not user_input:
                    self._send_json(400, {"error": "Missing 'input'"})
                    return

                file_info = None
                if file_id:
                    file_info = bridge._uploaded_files.get(file_id)

                # Auto-create session if none provided
                if not session_id and bridge._chat_store:
                    session = bridge._chat_store.create_session(title=user_input[:80])
                    session_id = session.id

                # Save user message
                if session_id and bridge._chat_store:
                    bridge._chat_store.add_message(
                        session_id, "user", user_input,
                        file_name=file_info["name"] if file_info else None,
                    )

                # Send SSE headers
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self._send_cors_headers()
                self.end_headers()

                def send_event(event: str, data: dict):
                    try:
                        # Inject session_id into done event
                        if event == "done" and session_id:
                            data["session_id"] = session_id
                        payload = f"event: {event}\ndata: {json.dumps(data)}\n\n"
                        self.wfile.write(payload.encode("utf-8"))
                        self.wfile.flush()
                    except Exception:
                        pass  # client disconnected

                bridge._execute_task_streaming(
                    user_input, file_info, send_event,
                    session_id=session_id,
                )

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
        """POST /api/task — submit a new task.

        If a real kernel with process_task() is available, the task is executed
        in a background thread.  The caller can poll GET /api/task/:id to watch
        status transition: accepted → running → completed | error.

        Optional: include "file_id" from a prior /api/upload call to attach
        a document or image for analysis.
        """
        body = req["body"]
        user_input = body.get("input")
        if not user_input:
            return 400, {"error": "Missing required field: input"}

        file_id = body.get("file_id")
        file_info = None
        if file_id:
            file_info = self._uploaded_files.get(file_id)
            if not file_info:
                return 400, {"error": f"File not found: {file_id}"}

        task_id = str(uuid.uuid4())
        task = {
            "task_id": task_id,
            "input": user_input,
            "status": "accepted",
            "created_at": time.time(),
            "result": None,
            "report": None,
            "error": None,
            "cost_usd": 0.0,
            "duration_ms": 0,
            "file": {"name": file_info["name"], "mime": file_info["mime"]}
                    if file_info else None,
        }
        self._tasks[task_id] = task
        self._task_order.append(task_id)

        # If the kernel can execute tasks, run in background thread
        if hasattr(self._kernel, "process_task") and callable(
            getattr(self._kernel, "process_task", None)
        ):
            thread = threading.Thread(
                target=self._execute_task,
                args=(task_id, user_input, file_info),
                daemon=True,
            )
            thread.start()

        return 200, {"task_id": task_id, "status": "accepted"}

    def _execute_task(self, task_id: str, user_input: str,
                      file_info: Optional[dict] = None) -> None:
        """Run kernel.process_task() in a background thread and update the task dict."""
        task = self._tasks.get(task_id)
        if task is None:
            return

        task["status"] = "running"

        try:
            # If a file is attached, use file-aware processing
            if file_info and hasattr(self._kernel, "process_task_with_file"):
                result = self._kernel.process_task_with_file(
                    user_input, file_info["path"], file_info["name"], file_info["mime"],
                )
            else:
                result = self._kernel.process_task(user_input)

            task["status"] = result.status if result.status != "blocked" else "error"
            task["duration_ms"] = result.duration_ms
            task["cost_usd"] = result.cost_usd
            task["report"] = result.report or None

            if result.status == "success":
                # Build a serialisable result payload
                exec_summaries = []
                for r in (result.execution_results or []):
                    summary = {
                        "agent": getattr(r, "agent_name", ""),
                        "action": getattr(r, "action", ""),
                        "status": getattr(r, "status", ""),
                    }
                    output = getattr(r, "output", None)
                    if isinstance(output, dict):
                        summary["action_performed"] = output.get("action_performed", "")
                        res_data = output.get("result")
                        if isinstance(res_data, list):
                            summary["count"] = len(res_data)
                            summary["items"] = res_data[:50]
                        elif res_data is not None:
                            summary["result"] = res_data
                    if getattr(r, "error", None):
                        summary["error"] = r.error
                    exec_summaries.append(summary)

                task["result"] = {
                    "intent": result.intent,
                    "execution": exec_summaries,
                }
            elif result.status == "blocked":
                task["error"] = result.error or "Blocked by security pipeline"
            else:
                # Extract error message from SOP phases if result.error is empty
                error_msg = result.error
                if not error_msg and result.sop_result:
                    for pr in result.sop_result.phases:
                        if pr.status == "error" and pr.error_message:
                            error_msg = pr.error_message
                            break
                if error_msg:
                    task["error"] = error_msg

            # Update cost tracking
            self._cost_data["total_spent_usd"] += result.cost_usd
            self._cost_data["call_count"] += 1

        except Exception as exc:
            task["status"] = "error"
            task["error"] = f"Something went wrong — {exc}"
            task["duration_ms"] = 0

    def _execute_task_streaming(
        self, user_input: str, file_info: Optional[dict],
        send_event: Any, session_id: Optional[str] = None,
    ) -> None:
        """Execute a task and stream SSE events for status + response tokens.

        The done event is ALWAYS sent via try/finally so the client never hangs.
        """
        import time as _time

        task_start = _time.monotonic()
        kernel = self._kernel
        cost_usd = 0.0
        task_status = "error"
        task_id_val = ""
        full_report = ""

        try:
            if not hasattr(kernel, "process_task"):
                send_event("error", {"message": "No AI backend available"})
                return

            # Phase 1: Status updates
            send_event("status", {"phase": "parse", "message": "Understanding your request..."})

            try:
                # Determine execution mode:
                # 1. File attached → process_task_with_file (LLM + document)
                # 2. Follow-up in existing session → process_chat (conversational)
                # 3. New standalone request → process_task (agent routing)

                has_history = False
                history = []
                if session_id and self._chat_store:
                    msgs = self._chat_store.get_messages(session_id)
                    # >1 because the user message was already saved above
                    has_history = len(msgs) > 1
                    history = [{"role": m.role, "content": m.content} for m in msgs]

                if file_info and hasattr(kernel, "process_task_with_file"):
                    is_image = file_info["mime"].startswith("image/")
                    send_event("status", {
                        "phase": "file",
                        "message": f"Reading {file_info['name']}..."
                            if not is_image else f"Analyzing image: {file_info['name']}...",
                    })
                    result = kernel.process_task_with_file(
                        user_input, file_info["path"], file_info["name"], file_info["mime"],
                    )
                elif has_history and hasattr(kernel, "process_chat"):
                    send_event("status", {"phase": "chat", "message": "Continuing conversation..."})
                    result = kernel.process_chat(user_input, history)
                else:
                    send_event("status", {"phase": "route", "message": "Routing to agents..."})
                    result = kernel.process_task(user_input)

            except Exception as exc:
                send_event("error", {"message": str(exc)})
                return

            task_id_val = getattr(result, "task_id", "")
            cost_usd = getattr(result, "cost_usd", 0.0)
            task_status = getattr(result, "status", "error")

            # Phase 2: Execution details
            for r in (getattr(result, "execution_results", None) or []):
                agent = getattr(r, "agent_name", "")
                action = getattr(r, "action", "")
                if agent:
                    send_event("status", {
                        "phase": "execute",
                        "message": f"Running {agent}.{action}...",
                        "agent": agent,
                        "action": action,
                        "result": getattr(r, "status", ""),
                    })

            # Phase 3: Stream the report text
            send_event("status", {"phase": "respond", "message": "Generating response..."})

            report = getattr(result, "report", "") or ""
            if result.status == "error":
                error_msg = getattr(result, "error", "") or ""
                if not error_msg and getattr(result, "sop_result", None):
                    for pr in result.sop_result.phases:
                        if pr.status == "error" and pr.error_message:
                            error_msg = pr.error_message
                            break
                send_event("error", {"message": error_msg or "Something went wrong"})
            elif report:
                full_report = report
                words = report.split(" ")
                chunk = ""
                for i, word in enumerate(words):
                    chunk += word + " "
                    if len(chunk) > 20 or i == len(words) - 1:
                        send_event("token", {"text": chunk})
                        chunk = ""
                        _time.sleep(0.02)
            else:
                full_report = "Done."
                send_event("token", {"text": "Done."})

        except Exception:
            pass  # client may have disconnected — done event still sent below

        finally:
            # Save assistant message to chat store
            if session_id and self._chat_store and full_report:
                try:
                    self._chat_store.add_message(
                        session_id, "assistant", full_report,
                        cost_usd=cost_usd,
                        duration_ms=int((_time.monotonic() - task_start) * 1000),
                    )
                except Exception:
                    pass

            # Generate follow-up suggestions
            fname = file_info["name"] if file_info else None
            suggestions = self._generate_suggestions(user_input, full_report, file_name=fname)

            # ALWAYS send done so the client never hangs
            duration = int((_time.monotonic() - task_start) * 1000)
            send_event("done", {
                "task_id": task_id_val,
                "status": task_status,
                "duration_ms": duration,
                "cost_usd": cost_usd,
                "suggestions": suggestions,
            })

    def _generate_suggestions(
        self, user_input: str, report: str,
        file_name: Optional[str] = None,
    ) -> List[str]:
        """Generate 3 contextual follow-up suggestions based on the conversation.

        These must be deeply relevant to the specific content discussed —
        not generic actions. If the user summarised a CV, the suggestions
        should reference that CV's content.
        """
        if not report or not hasattr(self._kernel, "llm"):
            return []

        try:
            file_context = ""
            if file_name:
                file_context = f"The user uploaded a file called '{file_name}'. "

            prompt = (
                "You are a helpful AI assistant. The user just completed a task. "
                "Based on the SPECIFIC content of their conversation below, suggest "
                "exactly 3 follow-up actions they would logically want to do next.\n\n"
                "Rules:\n"
                "- Each suggestion must be DIRECTLY related to the content discussed\n"
                "- Be specific, not generic (e.g. 'Rewrite the experience section "
                "to highlight leadership' NOT 'Edit the document')\n"
                "- Each under 60 characters\n"
                "- Phrased as natural commands the user would type\n"
                "- Return ONLY a JSON array of 3 strings\n\n"
                f"{file_context}"
                f"User asked: {user_input}\n\n"
                f"Assistant responded:\n{report[:1500]}\n\n"
                "JSON array of 3 specific follow-up suggestions:"
            )
            result = self._kernel.llm.generate(prompt)
            if result and result.text:
                text = result.text.strip()
                import re as _re
                match = _re.search(r'\[.*?\]', text, _re.DOTALL)
                if match:
                    suggestions = json.loads(match.group())
                    if isinstance(suggestions, list):
                        return [s for s in suggestions if isinstance(s, str)][:3]
        except Exception:
            pass

        return []

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

    # -- Session endpoints (chat persistence) ---------------------------------

    def handle_list_sessions(self, req: dict) -> Tuple[int, dict]:
        """GET /api/sessions — list chat sessions, most recent first."""
        if not self._chat_store:
            return 200, {"sessions": []}

        limit = int(req["query"].get("limit", 50))
        offset = int(req["query"].get("offset", 0))
        sessions = self._chat_store.list_sessions(limit=limit, offset=offset)
        return 200, {"sessions": [s.to_dict() for s in sessions]}

    def handle_create_session(self, req: dict) -> Tuple[int, dict]:
        """POST /api/sessions — create a new chat session."""
        if not self._chat_store:
            return 503, {"error": "Chat storage not available"}

        title = req["body"].get("title", "New conversation")
        session = self._chat_store.create_session(title=title)
        return 200, session.to_dict()

    def handle_get_messages(self, req: dict) -> Tuple[int, dict]:
        """GET /api/sessions/:id/messages — get all messages in a session."""
        if not self._chat_store:
            return 200, {"messages": []}

        session_id = req["path_params"]["session_id"]
        session = self._chat_store.get_session(session_id)
        if not session:
            return 404, {"error": "Session not found"}

        messages = self._chat_store.get_messages(session_id)
        return 200, {
            "session": session.to_dict(),
            "messages": [m.to_dict() for m in messages],
        }

    def handle_delete_session(self, req: dict) -> Tuple[int, dict]:
        """DELETE /api/sessions/:id — delete a chat session."""
        if not self._chat_store:
            return 503, {"error": "Chat storage not available"}

        session_id = req["path_params"]["session_id"]
        self._chat_store.delete_session(session_id)
        return 200, {"status": "deleted"}

    # -- File upload endpoints ------------------------------------------------

    # Max upload size: 50 MB
    _MAX_UPLOAD_BYTES = 50 * 1024 * 1024

    # Allowed MIME types
    _ALLOWED_MIMES = {
        # Documents
        "application/pdf", "text/plain", "text/csv", "text/markdown",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/msword", "application/json",
        # Images (Gemma 4 multimodal)
        "image/png", "image/jpeg", "image/gif", "image/webp",
    }

    def handle_upload_file(self, req: dict) -> Tuple[int, dict]:
        """POST /api/upload — accept a base64-encoded file, save to workspace.

        Request body: {"name": "file.pdf", "mime": "application/pdf", "data": "<base64>"}
        Returns: {"file_id": "...", "name": "...", "size_bytes": ...}
        """
        body = req["body"]
        name = body.get("name", "")
        mime = body.get("mime", "application/octet-stream")
        data_b64 = body.get("data", "")

        if not name or not data_b64:
            return 400, {"error": "Missing required fields: name, data"}

        if mime not in self._ALLOWED_MIMES:
            return 400, {
                "error": f"File type not supported: {mime}. "
                         "Supported: PDF, DOCX, TXT, CSV, images (PNG/JPG/GIF/WebP)"
            }

        try:
            raw_bytes = base64.b64decode(data_b64)
        except Exception:
            return 400, {"error": "Invalid base64 data"}

        if len(raw_bytes) > self._MAX_UPLOAD_BYTES:
            return 400, {"error": "File too large (max 50 MB)"}

        # Save to workspace/uploads/
        file_id = str(uuid.uuid4())
        safe_name = re.sub(r"[^\w.\-]", "_", name)  # sanitise filename
        ext = os.path.splitext(safe_name)[1] or ""
        saved_name = f"{file_id}{ext}"
        save_path = os.path.join(self._upload_dir, saved_name)

        with open(save_path, "wb") as f:
            f.write(raw_bytes)

        self._uploaded_files[file_id] = {
            "path": save_path,
            "name": name,
            "mime": mime,
            "size_bytes": len(raw_bytes),
        }

        return 200, {
            "file_id": file_id,
            "name": name,
            "size_bytes": len(raw_bytes),
        }

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

    def handle_voice_speak(self, req: dict) -> Tuple[int, dict]:
        """POST /api/voice/speak — synthesize speech from text."""
        try:
            from core.voice.tts import VoiceOutput
        except ImportError:
            return 500, {"error": "TTS module not available"}

        body = req.get("body", {})
        text = body.get("text", "")
        if not text:
            return 400, {"error": "Missing 'text' field"}

        play = body.get("play", False)
        tts = VoiceOutput()
        best = tts.get_best_available()

        if play:
            result = tts.speak_and_play(text)
        else:
            result = tts.speak(text)

        if result:
            return 200, {
                "audio_path": result.audio_path,
                "text": result.text,
                "duration_seconds": result.duration_seconds,
                "provider": result.provider,
            }

        return 503, {
            "error": f"Voice output not available. Best provider: {best.value}",
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

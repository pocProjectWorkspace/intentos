"""Enterprise Telemetry Reporter.

Periodically POSTs a heartbeat with usage stats, compliance status, and
security metrics to the IntentOS Console. Uses only stdlib — zero new
pip dependencies.

The heartbeat response may contain a ``policy_update`` payload which is
written to disk and triggers a policy reload.
"""

from __future__ import annotations

import json
import logging
import os
import platform
import threading
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_VERSION = "0.1.0"


class TelemetryReporter:
    """Background reporter that sends heartbeats to IntentOS Console.

    Parameters
    ----------
    console_url:
        Base URL of the Console (e.g. ``https://console.company.com``).
    device_token:
        Opaque token for device authentication (``X-Device-Token`` header).
    interval:
        Seconds between heartbeats.
    policy_engine:
        Reference to the :class:`PolicyEngine` (for compliance data and
        writing policy updates received from Console).
    llm_service:
        Reference to the :class:`LLMService` (for inference stats).
    security_pipeline:
        Reference to the :class:`SecurityPipeline` (for security stats).
    base_path:
        IntentOS data directory (``~/.intentos``).
    """

    def __init__(
        self,
        console_url: str,
        device_token: str,
        interval: int = 300,
        policy_engine: Any = None,
        llm_service: Any = None,
        security_pipeline: Any = None,
        base_path: Optional[Path] = None,
    ) -> None:
        self._console_url = console_url.rstrip("/")
        self._device_token = device_token
        self._interval = max(interval, 30)  # minimum 30 s
        self._policy = policy_engine
        self._llm = llm_service
        self._security = security_pipeline
        self._base = base_path or Path.home() / ".intentos"

        self._timer: Optional[threading.Timer] = None
        self._running = False
        self._last_send_time: Optional[str] = None
        self._last_send_ok: bool = False
        self._send_count: int = 0
        self._error_count: int = 0

    # -- lifecycle -----------------------------------------------------------

    def start(self) -> None:
        """Begin periodic heartbeats in a background thread."""
        if self._running:
            return
        self._running = True
        self._schedule_next()
        logger.info(
            "Telemetry reporter started (interval=%ds, console=%s)",
            self._interval,
            self._console_url,
        )

    def stop(self) -> None:
        """Cancel the background timer."""
        self._running = False
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def _schedule_next(self) -> None:
        if not self._running:
            return
        self._timer = threading.Timer(self._interval, self._tick)
        self._timer.daemon = True
        self._timer.start()

    def _tick(self) -> None:
        """Timer callback — collect and send, then reschedule."""
        try:
            self.send_now()
        except Exception:
            logger.debug("Telemetry tick failed", exc_info=True)
        finally:
            self._schedule_next()

    # -- public send ---------------------------------------------------------

    def send_now(self) -> bool:
        """Collect a payload and POST it immediately. Returns True on success."""
        payload = self._collect_payload()
        ok = self._send(payload)
        self._last_send_time = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self._last_send_ok = ok
        self._send_count += 1
        if not ok:
            self._error_count += 1
        return ok

    # -- payload collection --------------------------------------------------

    def _collect_payload(self) -> Dict:
        compliance = self._collect_compliance()
        usage = self._collect_usage()
        security = self._collect_security()

        return {
            "schema_version": "1.0",
            "device_id": compliance.get("device_id", ""),
            "org_id": compliance.get("org_id", ""),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "type": "heartbeat",
            "system": {
                "hostname": platform.node(),
                "os": f"{platform.system()} {platform.release()}",
                "intentos_version": _VERSION,
                "uptime_seconds": 0,  # placeholder
            },
            "compliance": compliance,
            "usage": usage,
            "security": security,
        }

    def _collect_compliance(self) -> Dict:
        if self._policy is None or not self._policy.is_managed:
            return {"policy_loaded": False}
        status = self._policy.get_compliance_status()
        return {
            "policy_loaded": True,
            "policy_version": status.get("policy_version", ""),
            "policy_signature_valid": True,
            "privacy_mode": status.get("privacy_mode", ""),
            "org_id": status.get("org_id", ""),
            "device_id": status.get("device_id", ""),
            "license": status.get("license", {}),
            "violations_since_last_report": 0,
            "blocked_attempts": [],
        }

    def _collect_usage(self) -> Dict:
        result: Dict[str, Any] = {
            "period_start": time.strftime("%Y-%m-%dT00:00:00Z", time.gmtime()),
            "total_tasks": 0,
            "tasks_blocked": 0,
            "inference": {},
            "agents_used": {},
        }
        if self._llm is None:
            return result

        # Inference stats
        if hasattr(self._llm, "get_inference_stats"):
            stats = self._llm.get_inference_stats()
            result["inference"] = {
                "calls_local": stats.get("calls_local", 0),
                "calls_cloud": stats.get("calls_cloud", 0),
                "total_cost_usd": 0.0,
                "by_model": {},
            }

        # Cost breakdown from cost manager
        if hasattr(self._llm, "get_cost_report"):
            report = self._llm.get_cost_report()
            result["inference"]["total_cost_usd"] = round(report.total_spent_usd, 4)
            by_model = {}
            for model_name, usage in report.by_model.items():
                by_model[model_name] = {
                    "calls": usage.call_count,
                    "cost_usd": round(usage.cost_usd, 4),
                }
            result["inference"]["by_model"] = by_model

        return result

    def _collect_security(self) -> Dict:
        if self._security is None or not hasattr(self._security, "get_stats"):
            return {}
        return dict(self._security.get_stats())

    # -- network -------------------------------------------------------------

    def _send(self, payload: Dict) -> bool:
        """POST the heartbeat payload to Console. Returns True on success."""
        url = f"{self._console_url}/api/v1/telemetry/heartbeat"
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")

        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("X-Device-Token", self._device_token)

        try:
            resp = urllib.request.urlopen(req, timeout=15)
            resp_data = json.loads(resp.read())
            self._handle_response(resp_data)
            return True
        except urllib.error.HTTPError as e:
            logger.debug("Telemetry POST failed: HTTP %d", e.code)
            try:
                err_data = json.loads(e.read())
                self._handle_response(err_data)
            except Exception:
                pass
            return False
        except Exception:
            logger.debug("Telemetry POST failed", exc_info=True)
            return False

    def _handle_response(self, data: Dict) -> None:
        """Process Console response — may contain a policy update or error."""
        # Detect license/seat errors from Console
        status = data.get("status", "")
        message = data.get("message", "")
        if status == "error":
            if "Seat limit exceeded" in message:
                logger.warning(
                    "Console rejected heartbeat: seat limit exceeded — "
                    "contact your IT administrator to add more seats"
                )
            elif "License expired" in message:
                logger.warning(
                    "Console rejected heartbeat: license expired — "
                    "contact your IT administrator to renew the license"
                )
            else:
                logger.warning("Console rejected heartbeat: %s", message)
            return

        policy_update = data.get("policy_update")
        if policy_update is None:
            return

        policy_json = policy_update.get("policy_json")
        signature = policy_update.get("signature")
        if not policy_json or not signature:
            return

        # Write the new policy to disk
        try:
            policy_json["signature"] = signature
            policy_path = self._base / "policy.json"
            policy_path.write_text(
                json.dumps(policy_json, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            # Reload the policy engine
            if self._policy is not None:
                self._policy.reload()
            logger.info(
                "Policy updated via Console (version=%s)",
                policy_json.get("version", "?"),
            )
        except Exception:
            logger.warning("Failed to apply policy update from Console", exc_info=True)

    # -- status API ----------------------------------------------------------

    def get_status(self) -> Dict:
        """Return status summary for /api/telemetry-status."""
        return {
            "running": self._running,
            "console_url": self._console_url,
            "interval_seconds": self._interval,
            "last_send_time": self._last_send_time,
            "last_send_ok": self._last_send_ok,
            "send_count": self._send_count,
            "error_count": self._error_count,
        }

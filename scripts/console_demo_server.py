#!/usr/bin/env python3
"""IntentOS Console Demo Server — stdlib only, zero dependencies.

Self-contained IT admin console for IntentOS enterprise fleet management.
Uses http.server + sqlite3 + json. No third-party packages.
"""

import hashlib
import json
import os
import random
import re
import sqlite3
import uuid
from datetime import datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

DB_PATH = Path.home() / ".intentos" / "console_demo.db"

LICENSE_SECRET = b"intentos-license-signing-key-v1"


def generate_license_key(tier: str, year: str, max_seats: int, org_id: str) -> str:
    """Generate a verifiable license key."""
    import hmac as _hmac
    payload = f"{tier}-{year}-{max_seats}-{org_id}"
    h = _hmac.new(LICENSE_SECRET, payload.encode(), hashlib.sha256).hexdigest()[:8].upper()
    tier_code = {"free": "FREE", "pro": "PRO", "enterprise": "ENT"}.get(tier, "PRO")
    return f"INTENT-{tier_code}-{year}-{h}"


def validate_license_key(key: str) -> bool:
    """Check if a license key has valid format and structure."""
    parts = key.split("-")
    if len(parts) != 4 or parts[0] != "INTENT":
        return False
    if parts[1] not in ("FREE", "PRO", "ENT"):
        return False
    if not parts[2].isdigit() or len(parts[2]) != 4:
        return False
    if len(parts[3]) != 8:
        return False
    return True

# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def get_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(conn: sqlite3.Connection):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS devices (
        id TEXT PRIMARY KEY,
        hostname TEXT,
        os TEXT,
        status TEXT DEFAULT 'offline',
        intentos_version TEXT,
        privacy_mode TEXT DEFAULT 'local_only',
        policy_compliant BOOLEAN DEFAULT 1,
        last_heartbeat_at TEXT,
        created_at TEXT,
        cloud_access BOOLEAN DEFAULT 0,
        assigned_api_keys TEXT DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS inference_usage (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        device_id TEXT,
        period_date TEXT,
        model TEXT,
        provider TEXT,
        total_calls INTEGER DEFAULT 0,
        input_tokens INTEGER DEFAULT 0,
        output_tokens INTEGER DEFAULT 0,
        cost_usd REAL DEFAULT 0.0
    );
    CREATE TABLE IF NOT EXISTS compliance_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        device_id TEXT,
        event_type TEXT,
        severity TEXT,
        details TEXT,
        created_at TEXT
    );
    CREATE TABLE IF NOT EXISTS policy_templates (
        id TEXT PRIMARY KEY,
        name TEXT,
        description TEXT,
        policy_json TEXT,
        is_default BOOLEAN DEFAULT 0,
        created_at TEXT,
        updated_at TEXT
    );
    CREATE TABLE IF NOT EXISTS audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        device_id TEXT,
        device_hostname TEXT,
        action TEXT,
        agent TEXT,
        details TEXT,
        cost_usd REAL DEFAULT 0.0,
        created_at TEXT
    );
    CREATE TABLE IF NOT EXISTS api_keys (
        id TEXT PRIMARY KEY,
        name TEXT,
        provider TEXT,
        key_masked TEXT,
        assigned_devices TEXT DEFAULT '',
        created_at TEXT,
        last_rotated TEXT
    );
    CREATE TABLE IF NOT EXISTS connectors (
        id TEXT PRIMARY KEY,
        type TEXT NOT NULL,
        name TEXT NOT NULL,
        config TEXT DEFAULT '{}',
        status TEXT DEFAULT 'not_configured',
        last_tested TEXT,
        created_at TEXT
    );
    CREATE TABLE IF NOT EXISTS users (
        username TEXT PRIMARY KEY,
        password_hash TEXT,
        role TEXT,
        name TEXT
    );
    CREATE TABLE IF NOT EXISTS sessions (
        token TEXT PRIMARY KEY,
        username TEXT,
        role TEXT,
        created_at TEXT,
        expires_at TEXT
    );
    CREATE TABLE IF NOT EXISTS licenses (
        id TEXT PRIMARY KEY,
        license_key TEXT,
        tier TEXT,
        max_seats INTEGER,
        used_seats INTEGER,
        expires_at TEXT,
        activated_at TEXT,
        status TEXT
    );
    """)
    conn.commit()


def seed_data(conn: sqlite3.Connection):
    if conn.execute("SELECT COUNT(*) FROM devices").fetchone()[0] > 0:
        _seed_users(conn)
        _seed_licenses(conn)
        _seed_connectors(conn)
        return
    now = datetime.utcnow()

    # Device IDs
    alice_id = str(uuid.uuid4())
    bob_id = str(uuid.uuid4())
    carol_id = str(uuid.uuid4())

    # API Key IDs
    key_anthropic = str(uuid.uuid4())
    key_openai = str(uuid.uuid4())
    key_google = str(uuid.uuid4())

    devices = [
        (alice_id, "alice-macbook", "macOS 15.2", "online", "1.2.0",
         "smart_routing", True,
         (now - timedelta(seconds=30)).isoformat(), now.isoformat(),
         True, key_anthropic),
        (bob_id, "bob-thinkpad", "Ubuntu 24.04", "online", "1.2.0",
         "local_only", True,
         (now - timedelta(seconds=12)).isoformat(), now.isoformat(),
         False, ""),
        (carol_id, "carol-surface", "Windows 11", "offline", "1.1.8",
         "smart_routing", False,
         (now - timedelta(hours=4)).isoformat(), now.isoformat(),
         True, key_google),
    ]
    conn.executemany(
        "INSERT INTO devices VALUES (?,?,?,?,?,?,?,?,?,?,?)", devices)

    # Policy templates
    conn.executemany(
        "INSERT INTO policy_templates VALUES (?,?,?,?,?,?,?)", [
            (str(uuid.uuid4()), "Enterprise Standard",
             "Default security policy for all managed devices. Local-only inference with restricted agent access.",
             json.dumps({
                 "privacy_mode": "local_only",
                 "max_daily_spend_usd": 10.0,
                 "allowed_agents": ["file_agent", "document_agent", "system_agent"],
                 "allowed_cloud_models": [],
                 "require_confirmation_destructive": True
             }),
             True, now.isoformat(), now.isoformat()),
            (str(uuid.uuid4()), "Executive Access",
             "Elevated access for executive devices. Smart routing with all agents enabled.",
             json.dumps({
                 "privacy_mode": "smart_routing",
                 "max_daily_spend_usd": 50.0,
                 "allowed_agents": ["file_agent", "document_agent", "system_agent",
                                    "browser_agent", "image_agent"],
                 "allowed_cloud_models": ["claude-3.5-sonnet", "gpt-4o", "gemini-pro"],
                 "require_confirmation_destructive": True
             }),
             False, now.isoformat(), now.isoformat()),
        ])

    # API keys
    conn.executemany(
        "INSERT INTO api_keys VALUES (?,?,?,?,?,?,?)", [
            (key_anthropic, "Production Anthropic", "anthropic",
             "sk-ant-...7x4f", alice_id,
             (now - timedelta(days=30)).isoformat(), (now - timedelta(days=5)).isoformat()),
            (key_openai, "Backup OpenAI", "openai",
             "sk-...9k2m", "",
             (now - timedelta(days=20)).isoformat(), (now - timedelta(days=20)).isoformat()),
            (key_google, "Google Gemini", "google",
             "AIza...8n3p", carol_id,
             (now - timedelta(days=15)).isoformat(), (now - timedelta(days=3)).isoformat()),
        ])

    # 7 days of inference usage
    usage_rows = []
    for i in range(7):
        d = (now - timedelta(days=i)).strftime("%Y-%m-%d")
        usage_rows += [
            (alice_id, d, "claude-3.5-sonnet", "cloud", 42 - i * 3,
             18500 - i * 1200, 6200 - i * 400, round(2.34 - i * 0.22, 2)),
            (alice_id, d, "llama-3.1-8b", "local", 110 + i * 5,
             32000 + i * 800, 9800 + i * 300, 0.0),
            (bob_id, d, "llama-3.1-8b", "local", 87 + i * 2,
             25000 + i * 600, 7400 + i * 200, 0.0),
            (carol_id, d, "claude-3.5-sonnet", "cloud", 15 - i,
             6200 - i * 400, 2100 - i * 150, round(0.89 - i * 0.08, 2)),
            (carol_id, d, "mistral-7b", "local", 34 + i,
             9800 + i * 300, 3100 + i * 100, 0.0),
        ]
    conn.executemany(
        "INSERT INTO inference_usage (device_id,period_date,model,provider,"
        "total_calls,input_tokens,output_tokens,cost_usd) VALUES (?,?,?,?,?,?,?,?)",
        usage_rows)

    # Compliance events for carol
    events = [
        (carol_id, "agent_blocked", "high",
         "File agent attempted access outside granted paths",
         (now - timedelta(hours=2)).isoformat()),
        (carol_id, "spending_alert", "medium",
         "Daily cloud spend exceeded $5.00 threshold",
         (now - timedelta(hours=1)).isoformat()),
        (carol_id, "privacy_mode_violation", "critical",
         "Device in smart_routing mode sent file contents to cloud API without confirmation",
         (now - timedelta(minutes=45)).isoformat()),
    ]
    conn.executemany(
        "INSERT INTO compliance_events (device_id,event_type,severity,details,created_at) "
        "VALUES (?,?,?,?,?)", events)

    # 30 audit log entries
    actions = [
        ("file.list_files", "file_agent", 0.0),
        ("file.find_files", "file_agent", 0.0),
        ("file.get_disk_usage", "file_agent", 0.0),
        ("document.create", "document_agent", 0.12),
        ("system.get_date", "system_agent", 0.0),
        ("file.list_files", "file_agent", 0.0),
        ("document.create", "document_agent", 0.18),
        ("file.find_files", "file_agent", 0.05),
        ("system.get_date", "system_agent", 0.0),
        ("file.list_files", "file_agent", 0.0),
    ]
    device_map = [
        (alice_id, "alice-macbook"),
        (bob_id, "bob-thinkpad"),
        (carol_id, "carol-surface"),
    ]
    audit_rows = []
    for i in range(30):
        dev_id, dev_host = device_map[i % 3]
        action, agent, base_cost = actions[i % len(actions)]
        ts = (now - timedelta(minutes=i * 45 + random.randint(0, 30))).isoformat()
        details = f"Executed {action} successfully"
        if "document.create" in action:
            details = "Created quarterly report document"
        elif "find_files" in action:
            details = "Searched workspace for matching files"
        elif "disk_usage" in action:
            details = "Retrieved disk usage statistics"
        elif "get_date" in action:
            details = "Retrieved current system date/time"
        cost = round(base_cost + random.random() * 0.05, 4) if base_cost > 0 else 0.0
        audit_rows.append((dev_id, dev_host, action, agent, details, cost, ts))
    conn.executemany(
        "INSERT INTO audit_log (device_id,device_hostname,action,agent,details,cost_usd,created_at) "
        "VALUES (?,?,?,?,?,?,?)", audit_rows)

    conn.commit()
    _seed_users(conn)
    _seed_licenses(conn)
    _seed_connectors(conn)


def _seed_users(conn: sqlite3.Connection):
    """Seed the users table if empty."""
    if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] > 0:
        return
    pw_hash = hashlib.sha256("intentos".encode()).hexdigest()
    conn.executemany(
        "INSERT INTO users VALUES (?,?,?,?)", [
            ("admin", pw_hash, "admin", "IT Administrator"),
            ("analyst", pw_hash, "analyst", "SOC Analyst"),
        ])
    conn.commit()


def _seed_licenses(conn: sqlite3.Connection):
    """Seed the licenses table if empty."""
    if conn.execute("SELECT COUNT(*) FROM licenses").fetchone()[0] > 0:
        return
    now = datetime.utcnow()
    # Generate a real verifiable license key
    key = generate_license_key("enterprise", "2026", 500, "demo-org")
    # Seat count reflects actual device count in the database
    device_count = conn.execute("SELECT COUNT(*) FROM devices").fetchone()[0]
    conn.execute(
        "INSERT INTO licenses VALUES (?,?,?,?,?,?,?,?)",
        (str(uuid.uuid4()), key, "enterprise", 500, device_count,
         "2027-12-31T23:59:59", (now - timedelta(days=90)).isoformat(), "active"))
    conn.commit()


def _seed_connectors(conn: sqlite3.Connection):
    """Seed the connectors table if empty."""
    if conn.execute("SELECT COUNT(*) FROM connectors").fetchone()[0] > 0:
        return
    now = datetime.utcnow().isoformat()
    connectors = [
        ("slack", "webhook", "Slack", json.dumps({
            "webhook_url": "https://hooks.slack.com/services/T00.../B00.../xxx",
            "events": {"policy_violations": True, "spending_alerts": True,
                       "device_offline": False, "new_device_registered": True}
        }), "connected", now, now),
        ("teams", "webhook", "Microsoft Teams", json.dumps({
            "webhook_url": "https://outlook.office.com/webhook/...",
            "events": {"policy_violations": True, "spending_alerts": True,
                       "device_offline": True, "new_device_registered": False}
        }), "connected", now, now),
        ("splunk", "siem", "Splunk SIEM", json.dumps({
            "hec_url": "https://splunk.corp.example.com:8088/services/collector",
            "hec_token": "****-****-****-****",
            "index": "intentos",
            "source_type": "intentos:audit"
        }), "connected", now, now),
        ("jira", "ticketing", "Jira", json.dumps({
            "project_key": "",
            "api_token": "",
            "create_on_violation": False
        }), "not_configured", None, now),
        ("okta", "sso", "Okta SSO", json.dumps({
            "domain": "",
            "client_id": "",
            "client_secret": ""
        }), "not_configured", None, now),
        ("email", "digest", "Email Digest", json.dumps({
            "method": "sendgrid",
            "recipients": ["security@corp.example.com", "it-admin@corp.example.com"],
            "schedule": "Weekly on Monday 9:00 AM"
        }), "connected", now, now),
    ]
    conn.executemany(
        "INSERT INTO connectors VALUES (?,?,?,?,?,?,?)", connectors)
    conn.commit()


# ---------------------------------------------------------------------------
# API logic
# ---------------------------------------------------------------------------

def api_fleet_overview(conn: sqlite3.Connection) -> dict:
    rows = conn.execute("SELECT * FROM devices ORDER BY last_heartbeat_at DESC").fetchall()
    cutoff = (datetime.utcnow() - timedelta(minutes=5)).isoformat()
    devices = []
    online = compliant = 0
    total_cost = conn.execute("SELECT COALESCE(SUM(cost_usd),0) FROM inference_usage").fetchone()[0]
    for r in rows:
        d = dict(r)
        is_online = (d["last_heartbeat_at"] or "") >= cutoff
        d["status"] = "online" if is_online else "offline"
        if is_online:
            online += 1
        if d["policy_compliant"]:
            compliant += 1
        devices.append(d)
    # Fetch active license info
    lic = conn.execute(
        "SELECT * FROM licenses WHERE status='active' ORDER BY activated_at DESC LIMIT 1"
    ).fetchone()
    license_info = None
    if lic:
        now_str = datetime.utcnow().isoformat()
        lic_status = "active" if (lic["expires_at"] or "") >= now_str else "expired"
        license_info = {
            "key": lic["license_key"],
            "tier": lic["tier"],
            "seats_used": lic["used_seats"] or 0,
            "seats_max": lic["max_seats"] or 0,
            "expires_at": lic["expires_at"],
            "status": lic_status
        }

    result = {
        "total_devices": len(rows), "online": online,
        "offline": len(rows) - online, "compliant": compliant,
        "non_compliant": len(rows) - compliant,
        "total_cost_usd": round(total_cost, 2),
        "devices": devices
    }
    if license_info:
        result["license"] = license_info
    return result


def api_ai_usage(conn: sqlite3.Connection) -> dict:
    rows = conn.execute(
        "SELECT model, provider, SUM(total_calls) as calls, SUM(input_tokens) as inp, "
        "SUM(output_tokens) as outp, SUM(cost_usd) as cost FROM inference_usage "
        "GROUP BY model").fetchall()
    total_cost = total_calls = total_inp = total_outp = 0
    cloud_calls = local_calls = 0
    by_model = {}
    for r in rows:
        c, cost = r["calls"] or 0, r["cost"] or 0.0
        total_cost += cost
        total_calls += c
        total_inp += r["inp"] or 0
        total_outp += r["outp"] or 0
        if r["provider"] == "cloud":
            cloud_calls += c
        else:
            local_calls += c
        by_model[r["model"]] = {"calls": c, "cost_usd": round(cost, 2)}
    return {
        "total_cost_usd": round(total_cost, 2), "total_calls": total_calls,
        "total_input_tokens": total_inp, "total_output_tokens": total_outp,
        "cloud_calls": cloud_calls, "local_calls": local_calls,
        "by_model": by_model
    }


def api_cost_trend(conn: sqlite3.Connection) -> dict:
    rows = conn.execute(
        "SELECT period_date, SUM(cost_usd) as cost, SUM(total_calls) as calls "
        "FROM inference_usage GROUP BY period_date ORDER BY period_date DESC LIMIT 30"
    ).fetchall()
    return {"days": [{"date": r["period_date"], "cost_usd": round(r["cost"] or 0, 2),
                       "calls": r["calls"] or 0} for r in rows]}


def api_compliance(conn: sqlite3.Connection) -> dict:
    by_type = {r[0]: r[1] for r in conn.execute(
        "SELECT event_type, COUNT(*) FROM compliance_events GROUP BY event_type").fetchall()}
    recent = [dict(r) for r in conn.execute(
        "SELECT ce.*, d.hostname FROM compliance_events ce "
        "LEFT JOIN devices d ON ce.device_id = d.id "
        "ORDER BY ce.created_at DESC LIMIT 20").fetchall()]
    total = conn.execute("SELECT COUNT(*) FROM compliance_events").fetchone()[0]
    return {"total_events": total, "by_type": by_type, "recent": recent}


def api_heartbeat(body: dict, headers: dict, conn: sqlite3.Connection) -> dict:
    device_id = headers.get("x-device-token", body.get("device_id", str(uuid.uuid4())))
    now = datetime.utcnow().isoformat()

    # --- License checks: expiry and seat limit ---
    lic = conn.execute(
        "SELECT * FROM licenses WHERE status='active' ORDER BY activated_at DESC LIMIT 1"
    ).fetchone()
    if lic:
        # Check expiry
        expires_at = lic["expires_at"] or ""
        if expires_at and expires_at < now:
            return {"status": "error", "message": "License expired."}
        # Check if this is a NEW device (not seen before)
        existing = conn.execute("SELECT id FROM devices WHERE id=?", (device_id,)).fetchone()
        if not existing:
            used = lic["used_seats"] or 0
            max_s = lic["max_seats"] or 0
            if used >= max_s:
                return {"status": "error", "message": "Seat limit exceeded. Contact your IT administrator."}
            # Increment used_seats for this new device
            conn.execute("UPDATE licenses SET used_seats=? WHERE id=?", (used + 1, lic["id"]))

    conn.execute("""INSERT INTO devices (id,hostname,os,status,intentos_version,privacy_mode,
        policy_compliant,last_heartbeat_at,created_at,cloud_access,assigned_api_keys)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(id) DO UPDATE SET hostname=excluded.hostname, os=excluded.os,
        status='online', intentos_version=excluded.intentos_version,
        privacy_mode=excluded.privacy_mode, policy_compliant=excluded.policy_compliant,
        last_heartbeat_at=excluded.last_heartbeat_at""",
        (device_id, body.get("hostname", "unknown"), body.get("os", "unknown"),
         "online", body.get("intentos_version", "0.0.0"),
         body.get("privacy_mode", "local_only"),
         body.get("violations", 0) == 0, now, now, False, ""))
    for u in body.get("inference_usage", []):
        conn.execute(
            "INSERT INTO inference_usage (device_id,period_date,model,provider,"
            "total_calls,input_tokens,output_tokens,cost_usd) VALUES (?,?,?,?,?,?,?,?)",
            (device_id, u.get("period_date", now[:10]), u.get("model", "unknown"),
             u.get("provider", "local"), u.get("total_calls", 0),
             u.get("input_tokens", 0), u.get("output_tokens", 0), u.get("cost_usd", 0.0)))
    for e in body.get("compliance_events", []):
        conn.execute(
            "INSERT INTO compliance_events (device_id,event_type,severity,details,created_at) "
            "VALUES (?,?,?,?,?)",
            (device_id, e.get("event_type"), e.get("severity", "medium"),
             e.get("details", ""), now))
    hostname = body.get("hostname", "unknown")
    for a in body.get("audit_log", []):
        conn.execute(
            "INSERT INTO audit_log (device_id,device_hostname,action,agent,details,cost_usd,created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (device_id, hostname, a.get("action", ""), a.get("agent", ""),
             a.get("details", ""), a.get("cost_usd", 0.0), now))

    # Slack/Teams webhook alert on compliance violations
    violations = body.get("violations", 0)
    if violations > 0:
        _check_connector_alerts(conn, hostname, now)

    conn.commit()
    return {"status": "ok", "device_id": device_id}


def _check_connector_alerts(conn: sqlite3.Connection, hostname: str, now: str):
    """Log alerts for configured Slack/Teams connectors on policy violations."""
    rows = conn.execute(
        "SELECT id, type, name, status FROM connectors WHERE type='webhook' AND status='connected'"
    ).fetchall()
    for r in rows:
        conn.execute(
            "INSERT INTO audit_log (device_id,device_hostname,action,agent,details,cost_usd,created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            ("console", "console", "connector.alert", "console",
             f"Alert sent to {r['name']}: policy violation on {hostname}",
             0.0, now))


def api_policies_list(conn: sqlite3.Connection) -> list:
    return [dict(r) for r in conn.execute(
        "SELECT * FROM policy_templates ORDER BY is_default DESC, name").fetchall()]


def api_policies_create(body: dict, conn: sqlite3.Connection) -> dict:
    pid = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    conn.execute("INSERT INTO policy_templates VALUES (?,?,?,?,?,?,?)",
                 (pid, body.get("name", "Untitled"),
                  body.get("description", ""),
                  json.dumps(body.get("policy_json", {})),
                  body.get("is_default", False), now, now))
    conn.commit()
    return {"id": pid, "status": "created"}


def api_policies_update(policy_id: str, body: dict, conn: sqlite3.Connection) -> dict:
    now = datetime.utcnow().isoformat()
    existing = conn.execute("SELECT id FROM policy_templates WHERE id=?", (policy_id,)).fetchone()
    if not existing:
        return None
    conn.execute(
        "UPDATE policy_templates SET name=?, description=?, policy_json=?, is_default=?, updated_at=? WHERE id=?",
        (body.get("name", "Untitled"), body.get("description", ""),
         json.dumps(body.get("policy_json", {})),
         body.get("is_default", False), now, policy_id))
    conn.commit()
    return {"id": policy_id, "status": "updated"}


def api_policies_delete(policy_id: str, conn: sqlite3.Connection) -> dict:
    existing = conn.execute("SELECT id FROM policy_templates WHERE id=?", (policy_id,)).fetchone()
    if not existing:
        return None
    conn.execute("DELETE FROM policy_templates WHERE id=?", (policy_id,))
    conn.commit()
    return {"status": "deleted"}


def api_devices_list(conn: sqlite3.Connection) -> list:
    cutoff = (datetime.utcnow() - timedelta(minutes=5)).isoformat()
    rows = conn.execute("SELECT * FROM devices ORDER BY hostname").fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["status"] = "online" if (d["last_heartbeat_at"] or "") >= cutoff else "offline"
        result.append(d)
    return result


def api_device_detail(device_id: str, conn: sqlite3.Connection) -> dict:
    cutoff = (datetime.utcnow() - timedelta(minutes=5)).isoformat()
    row = conn.execute("SELECT * FROM devices WHERE id=?", (device_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    d["status"] = "online" if (d["last_heartbeat_at"] or "") >= cutoff else "offline"
    d["usage_history"] = [dict(r) for r in conn.execute(
        "SELECT * FROM inference_usage WHERE device_id=? ORDER BY period_date DESC LIMIT 30",
        (device_id,)).fetchall()]
    d["recent_audit"] = [dict(r) for r in conn.execute(
        "SELECT * FROM audit_log WHERE device_id=? ORDER BY created_at DESC LIMIT 10",
        (device_id,)).fetchall()]
    return d


def api_device_cloud_access(device_id: str, body: dict, conn: sqlite3.Connection) -> dict:
    existing = conn.execute("SELECT id FROM devices WHERE id=?", (device_id,)).fetchone()
    if not existing:
        return None
    enabled = body.get("enabled", False)
    conn.execute("UPDATE devices SET cloud_access=? WHERE id=?", (enabled, device_id))
    conn.commit()
    return {"device_id": device_id, "cloud_access": enabled}


def api_device_api_keys(device_id: str, body: dict, conn: sqlite3.Connection) -> dict:
    existing = conn.execute("SELECT id FROM devices WHERE id=?", (device_id,)).fetchone()
    if not existing:
        return None
    key_ids = body.get("key_ids", [])
    conn.execute("UPDATE devices SET assigned_api_keys=? WHERE id=?",
                 (",".join(key_ids), device_id))
    # Update api_keys assigned_devices
    all_keys = conn.execute("SELECT id, assigned_devices FROM api_keys").fetchall()
    for k in all_keys:
        devs = set(filter(None, (k["assigned_devices"] or "").split(",")))
        if k["id"] in key_ids:
            devs.add(device_id)
        else:
            devs.discard(device_id)
        conn.execute("UPDATE api_keys SET assigned_devices=? WHERE id=?",
                     (",".join(devs), k["id"]))
    conn.commit()
    return {"device_id": device_id, "assigned_api_keys": key_ids}


def api_audit_log(params: dict, conn: sqlite3.Connection) -> dict:
    where = []
    args = []
    if params.get("device_id"):
        where.append("device_id=?")
        args.append(params["device_id"][0] if isinstance(params["device_id"], list) else params["device_id"])
    if params.get("agent"):
        where.append("agent=?")
        args.append(params["agent"][0] if isinstance(params["agent"], list) else params["agent"])
    where_sql = (" WHERE " + " AND ".join(where)) if where else ""
    limit = int((params.get("limit", [20])[0]) if isinstance(params.get("limit"), list) else params.get("limit", 20))
    offset = int((params.get("offset", [0])[0]) if isinstance(params.get("offset"), list) else params.get("offset", 0))
    total = conn.execute(f"SELECT COUNT(*) FROM audit_log{where_sql}", args).fetchone()[0]
    rows = conn.execute(
        f"SELECT * FROM audit_log{where_sql} ORDER BY created_at DESC LIMIT ? OFFSET ?",
        args + [limit, offset]).fetchall()
    return {"total": total, "limit": limit, "offset": offset, "entries": [dict(r) for r in rows]}


def api_keys_list(conn: sqlite3.Connection) -> list:
    return [dict(r) for r in conn.execute("SELECT * FROM api_keys ORDER BY name").fetchall()]


def api_keys_create(body: dict, conn: sqlite3.Connection) -> dict:
    kid = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    key_value = body.get("key_value", "")
    # Mask the key
    if len(key_value) > 8:
        masked = key_value[:4] + "..." + key_value[-4:]
    elif key_value:
        masked = key_value[:2] + "..." + key_value[-2:]
    else:
        masked = "****"
    conn.execute("INSERT INTO api_keys VALUES (?,?,?,?,?,?,?)",
                 (kid, body.get("name", "Untitled"), body.get("provider", "unknown"),
                  masked, "", now, now))
    conn.commit()
    return {"id": kid, "status": "created"}


def api_keys_delete(key_id: str, conn: sqlite3.Connection) -> dict:
    existing = conn.execute("SELECT id FROM api_keys WHERE id=?", (key_id,)).fetchone()
    if not existing:
        return None
    conn.execute("DELETE FROM api_keys WHERE id=?", (key_id,))
    # Remove from devices
    conn.execute("UPDATE devices SET assigned_api_keys=REPLACE(assigned_api_keys,?,'')", (key_id,))
    conn.commit()
    return {"status": "deleted"}


def api_keys_rotate(key_id: str, conn: sqlite3.Connection) -> dict:
    existing = conn.execute("SELECT id, key_masked FROM api_keys WHERE id=?", (key_id,)).fetchone()
    if not existing:
        return None
    now = datetime.utcnow().isoformat()
    # Generate new masked placeholder
    new_suffix = uuid.uuid4().hex[:4]
    old_masked = existing["key_masked"]
    prefix = old_masked.split("...")[0] if "..." in old_masked else "sk-"
    new_masked = f"{prefix}...{new_suffix}"
    conn.execute("UPDATE api_keys SET key_masked=?, last_rotated=? WHERE id=?",
                 (new_masked, now, key_id))
    conn.commit()
    return {"id": key_id, "key_masked": new_masked, "last_rotated": now}


def api_connectors_list(conn: sqlite3.Connection) -> list:
    return [dict(r) for r in conn.execute("SELECT * FROM connectors ORDER BY name").fetchall()]


def api_connectors_update(connector_id: str, body: dict, conn: sqlite3.Connection) -> dict:
    existing = conn.execute("SELECT id FROM connectors WHERE id=?", (connector_id,)).fetchone()
    if not existing:
        return None
    now = datetime.utcnow().isoformat()
    config = json.dumps(body.get("config", {}))
    status = body.get("status", "connected")
    conn.execute("UPDATE connectors SET config=?, status=?, last_tested=? WHERE id=?",
                 (config, status, now, connector_id))
    conn.commit()
    return {"id": connector_id, "status": "updated"}


def api_connectors_test(connector_id: str, conn: sqlite3.Connection) -> dict:
    existing = conn.execute("SELECT id, name, type FROM connectors WHERE id=?", (connector_id,)).fetchone()
    if not existing:
        return None
    now = datetime.utcnow().isoformat()
    conn.execute("UPDATE connectors SET last_tested=?, status='connected' WHERE id=?", (now, connector_id))
    conn.commit()
    messages = {
        "slack": "Message sent to #security-alerts",
        "teams": "Message sent to Security Alerts channel",
        "splunk": "Test event indexed successfully",
        "jira": "Connection to Jira project verified",
        "okta": "SSO endpoint responded OK",
        "email": "Test digest email sent to recipients",
    }
    return {"success": True, "message": messages.get(existing["id"], "Connection test passed")}


def api_auth_login(body: dict, conn: sqlite3.Connection) -> dict:
    username = body.get("username", "")
    password = body.get("password", "")
    pw_hash = hashlib.sha256(password.encode()).hexdigest()
    user = conn.execute(
        "SELECT username, role, name FROM users WHERE username=? AND password_hash=?",
        (username, pw_hash)).fetchone()
    if not user:
        return None
    token = uuid.uuid4().hex
    now = datetime.utcnow()
    expires = now + timedelta(hours=24)
    conn.execute("INSERT INTO sessions VALUES (?,?,?,?,?)",
                 (token, user["username"], user["role"],
                  now.isoformat(), expires.isoformat()))
    conn.commit()
    return {
        "token": token,
        "user": {"username": user["username"], "role": user["role"], "name": user["name"]}
    }


def api_auth_me(token: str, conn: sqlite3.Connection) -> dict:
    now = datetime.utcnow().isoformat()
    session = conn.execute(
        "SELECT s.username, s.role, u.name FROM sessions s "
        "JOIN users u ON s.username = u.username "
        "WHERE s.token=? AND s.expires_at>?",
        (token, now)).fetchone()
    if not session:
        return None
    return {"username": session["username"], "role": session["role"], "name": session["name"]}


def verify_token(headers: dict, conn: sqlite3.Connection) -> dict:
    """Verify Bearer token. Returns user dict or None."""
    auth = headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth[7:]
    return api_auth_me(token, conn)


def api_licenses_list(conn: sqlite3.Connection) -> list:
    device_count = conn.execute("SELECT COUNT(*) FROM devices").fetchone()[0]
    licenses = []
    for r in conn.execute("SELECT * FROM licenses ORDER BY activated_at DESC").fetchall():
        lic = dict(r)
        # For the active license, reflect actual device count as used_seats
        if lic.get("status") == "active":
            lic["used_seats"] = device_count
        licenses.append(lic)
    return licenses


def api_licenses_activate(body: dict, conn: sqlite3.Connection) -> dict:
    key = body.get("license_key", "")
    org_name = body.get("org_name", "Unknown Org")
    if not validate_license_key(key):
        return {"error": "Invalid license key format. Expected: INTENT-XXX-XXXX-XXXXXXXX"}
    # Determine tier and seat allocation from key
    parts = key.split("-")
    tier_code = parts[1]
    tier_map = {"FREE": ("free", 5), "PRO": ("pro", 50), "ENT": ("enterprise", 500)}
    tier, max_seats = tier_map.get(tier_code, ("pro", 50))
    now = datetime.utcnow()
    lid = str(uuid.uuid4())
    expires_at = (now + timedelta(days=365)).isoformat()
    conn.execute(
        "INSERT INTO licenses VALUES (?,?,?,?,?,?,?,?)",
        (lid, key, tier, max_seats, 0, expires_at, now.isoformat(), "active"))
    conn.commit()
    return {
        "id": lid, "status": "activated", "license_key": key,
        "tier": tier, "max_seats": max_seats, "expires_at": expires_at,
        "org_name": org_name
    }


# ---------------------------------------------------------------------------
# Dashboard HTML — single-page app with hash routing
# ---------------------------------------------------------------------------

DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>IntentOS Console</title>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;600;700&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{--bg:#0a0a1a;--card:rgba(255,255,255,0.04);--card-border:rgba(255,255,255,0.08);
  --text:#e2e8f0;--dim:#64748b;--blue:#2563eb;--cyan:#06b6d4;--green:#22c55e;
  --red:#ef4444;--amber:#f59e0b;--purple:#7c3aed}
body{font-family:'Inter',sans-serif;background:var(--bg);color:var(--text);min-height:100vh;display:flex}
h1,h2,h3{font-family:'Space Grotesk',sans-serif}
code,.mono{font-family:'JetBrains Mono',monospace}

/* Sidebar */
.sidebar{width:220px;min-height:100vh;background:rgba(255,255,255,0.02);border-right:1px solid var(--card-border);
  position:fixed;top:0;left:0;bottom:0;display:flex;flex-direction:column;padding:20px 0;z-index:10}
.sidebar-logo{display:flex;align-items:center;gap:10px;padding:0 20px 24px;font-size:18px;font-weight:700;
  font-family:'Space Grotesk',sans-serif;border-bottom:1px solid var(--card-border);margin-bottom:8px}
.sidebar-logo .dot{width:10px;height:10px;border-radius:50%;background:var(--green);box-shadow:0 0 8px var(--green);flex-shrink:0}
.nav-items{flex:1;padding:8px 0}
.nav-item{display:flex;align-items:center;gap:10px;padding:10px 20px;cursor:pointer;color:var(--dim);
  font-size:14px;transition:all .15s;border-left:3px solid transparent}
.nav-item:hover{color:var(--text);background:rgba(255,255,255,0.03)}
.nav-item.active{color:#fff;background:rgba(37,99,235,0.15);border-left-color:var(--blue)}
.nav-item .icon{width:20px;text-align:center;font-size:16px}
.sidebar-footer{padding:16px 20px;border-top:1px solid var(--card-border);font-size:12px;color:var(--dim)}
.sidebar-footer .online-count{color:var(--green);font-weight:600}

/* Main content */
.main{margin-left:220px;flex:1;padding:28px 32px;max-width:1200px}
.page-title{font-size:22px;font-weight:700;margin-bottom:20px}

/* Cards */
.grid4{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:28px}
.grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-bottom:28px}
.grid2{display:grid;grid-template-columns:repeat(2,1fr);gap:16px;margin-bottom:28px}
.card{background:var(--card);border:1px solid var(--card-border);border-radius:12px;padding:20px;
  backdrop-filter:blur(12px);transition:border-color .2s}
.card:hover{border-color:rgba(255,255,255,0.15)}
.card .label{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--dim);margin-bottom:6px}
.card .value{font-size:28px;font-weight:700;font-family:'Space Grotesk',sans-serif}
.card .value.green{color:var(--green)}.card .value.red{color:var(--red)}
.card .value.cyan{color:var(--cyan)}.card .value.blue{color:var(--blue)}.card .value.purple{color:var(--purple)}

/* Sections */
section{margin-bottom:28px}
section h2{font-size:15px;margin-bottom:14px;color:var(--dim);text-transform:uppercase;letter-spacing:.06em}

/* Chart */
.chart-wrap{background:var(--card);border:1px solid var(--card-border);border-radius:12px;padding:20px 20px 16px;
  min-height:250px;margin-bottom:40px}
svg text{font-family:'JetBrains Mono',monospace;fill:var(--dim);font-size:11px}

/* Tables */
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--card-border);border-radius:12px;overflow:hidden}
th{text-align:left;padding:10px 14px;font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--dim);
  border-bottom:1px solid var(--card-border);font-family:'Space Grotesk',sans-serif}
td{padding:10px 14px;font-size:13px;border-bottom:1px solid rgba(255,255,255,0.04)}
tr:last-child td{border-bottom:none}
tr:hover td{background:rgba(255,255,255,0.02)}

/* Badges */
.badge{display:inline-block;padding:2px 10px;border-radius:9999px;font-size:11px;font-weight:600}
.badge.online,.badge.connected{background:#22c55e18;color:var(--green)}
.badge.offline,.badge.not_configured{background:#ef444418;color:var(--dim)}
.badge.critical{background:#ef444418;color:var(--red)}.badge.high{background:#f59e0b18;color:var(--amber)}
.badge.medium{background:#2563eb18;color:var(--blue)}.badge.low{background:#64748b18;color:var(--dim)}
.badge.default{background:#7c3aed18;color:var(--purple)}
.badge.anthropic{background:#d9976618;color:#d99766}.badge.openai{background:#22c55e18;color:var(--green)}
.badge.google{background:#2563eb18;color:var(--blue)}
.check{color:var(--green)}.cross{color:var(--red)}

/* Buttons */
.btn{display:inline-flex;align-items:center;gap:6px;padding:8px 16px;border-radius:8px;border:1px solid var(--card-border);
  background:var(--card);color:var(--text);font-size:13px;cursor:pointer;font-family:'Inter',sans-serif;transition:all .15s}
.btn:hover{border-color:rgba(255,255,255,0.2);background:rgba(255,255,255,0.06)}
.btn.primary{background:var(--blue);border-color:var(--blue);color:#fff}.btn.primary:hover{opacity:.9}
.btn.danger{border-color:var(--red);color:var(--red)}.btn.danger:hover{background:rgba(239,68,68,0.1)}
.btn.sm{padding:4px 10px;font-size:12px}

/* Forms */
.form-group{margin-bottom:14px}
.form-group label{display:block;font-size:12px;color:var(--dim);margin-bottom:4px;text-transform:uppercase;letter-spacing:.05em}
input[type="text"],input[type="password"],input[type="number"],select,textarea{width:100%;padding:8px 12px;border-radius:8px;
  border:1px solid var(--card-border);background:rgba(255,255,255,0.03);color:var(--text);
  font-size:13px;font-family:'Inter',sans-serif;outline:none;transition:border-color .15s}
input:focus,select:focus,textarea:focus{border-color:var(--blue)}
textarea{font-family:'JetBrains Mono',monospace;min-height:120px;resize:vertical}
input[type="range"]{width:100%;accent-color:var(--cyan)}

/* Toggle switch */
.toggle{position:relative;width:44px;height:24px;cursor:pointer}
.toggle input{opacity:0;width:0;height:0}
.toggle .slider{position:absolute;inset:0;background:rgba(255,255,255,0.1);border-radius:24px;transition:.2s}
.toggle .slider:before{content:'';position:absolute;height:18px;width:18px;left:3px;bottom:3px;
  background:#fff;border-radius:50%;transition:.2s}
.toggle input:checked+.slider{background:var(--green)}
.toggle input:checked+.slider:before{transform:translateX(20px)}

/* Filter bar */
.filter-bar{display:flex;gap:12px;margin-bottom:16px;align-items:center;flex-wrap:wrap}
.filter-bar select,.filter-bar input{max-width:200px}

/* Pagination */
.pagination{display:flex;gap:8px;margin-top:16px;align-items:center;justify-content:center}
.pagination .info{font-size:12px;color:var(--dim)}

/* Device detail */
.device-detail{display:grid;grid-template-columns:1fr 1fr;gap:20px}
.device-info-card{grid-column:1/-1}
.detail-back{font-size:13px;color:var(--blue);cursor:pointer;margin-bottom:12px;display:inline-block}
.detail-back:hover{text-decoration:underline}

/* Inline form */
.inline-form{background:var(--card);border:1px solid var(--card-border);border-radius:12px;padding:20px;margin-bottom:20px}
.inline-form h3{margin-bottom:14px;font-size:16px}
.form-actions{display:flex;gap:8px;margin-top:12px}

/* Hidden */
.hidden{display:none!important}

/* Security page */
.sec-section{margin-bottom:48px}
.sec-section h2{font-family:'Space Grotesk',sans-serif;font-size:20px;font-weight:700;color:var(--text);
  border-left:4px solid var(--cyan);padding-left:16px;margin-bottom:16px}
.sec-section p{color:var(--dim);line-height:1.7;font-size:14px;margin-bottom:12px;max-width:800px}
.sec-table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--card-border);border-radius:12px;overflow:hidden;margin-top:12px;margin-bottom:12px}
.sec-table th{text-align:left;padding:10px 14px;font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--dim);
  border-bottom:1px solid var(--card-border);font-family:'Space Grotesk',sans-serif;background:rgba(255,255,255,0.02)}
.sec-table td{padding:10px 14px;font-size:13px;border-bottom:1px solid rgba(255,255,255,0.04);color:var(--text)}
.sec-table tr:last-child td{border-bottom:none}
.arch-diagram{background:rgba(255,255,255,0.03);border:1px solid var(--card-border);border-radius:12px;padding:24px;
  font-family:'JetBrains Mono',monospace;font-size:13px;line-height:1.6;color:var(--cyan);white-space:pre;overflow-x:auto;margin:12px 0}

/* Connector cards */
.connector-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:16px}
.connector-card{background:var(--card);border:1px solid var(--card-border);border-radius:12px;padding:20px;transition:border-color .2s}
.connector-card:hover{border-color:rgba(255,255,255,0.15)}
.connector-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:12px}
.connector-config{margin-top:14px;border-top:1px solid var(--card-border);padding-top:14px}

/* ROI */
.roi-inputs{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.roi-output{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-top:24px}
.roi-big{font-size:36px;font-weight:700;font-family:'Space Grotesk',sans-serif}
.roi-summary{background:var(--card);border:1px solid var(--card-border);border-radius:12px;padding:24px;margin-top:24px;
  font-size:15px;line-height:1.7;color:var(--text)}

/* Toast */
.toast{position:fixed;top:20px;right:20px;background:var(--green);color:#fff;padding:12px 20px;border-radius:8px;
  font-size:13px;font-weight:600;z-index:9999;opacity:0;transform:translateY(-10px);transition:all .3s;pointer-events:none}
.toast.show{opacity:1;transform:translateY(0)}

/* Responsive */
@media(max-width:900px){
  .grid4{grid-template-columns:repeat(2,1fr)}
  .device-detail{grid-template-columns:1fr}
  .connector-grid{grid-template-columns:1fr}
  .roi-inputs{grid-template-columns:1fr}
  .roi-output{grid-template-columns:1fr}
}
</style></head><body>

<!-- Login Screen -->
<div id="login-screen" class="hidden" style="min-height:100vh;display:flex;align-items:center;justify-content:center;background:var(--bg)">
  <div style="width:380px;background:var(--card);border:1px solid var(--card-border);border-radius:16px;padding:40px;backdrop-filter:blur(12px)">
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">
      <div style="width:12px;height:12px;border-radius:50%;background:var(--green);box-shadow:0 0 8px var(--green)"></div>
      <h1 style="font-family:'Space Grotesk',sans-serif;font-size:22px;font-weight:700">IntentOS Console</h1>
    </div>
    <p style="color:var(--dim);font-size:13px;margin-bottom:28px">Sign in to manage your fleet</p>
    <div id="login-error" style="display:none;background:#ef444418;color:var(--red);padding:10px 14px;border-radius:8px;font-size:13px;margin-bottom:16px"></div>
    <div class="form-group">
      <label>Username</label>
      <input type="text" id="login-username" placeholder="admin" autofocus>
    </div>
    <div class="form-group">
      <label>Password</label>
      <input type="password" id="login-password" placeholder="Password" onkeydown="if(event.key==='Enter')doLogin()">
    </div>
    <button class="btn primary" style="width:100%;justify-content:center;padding:10px;margin-top:8px" onclick="doLogin()">Sign In</button>
    <div style="position:relative;margin-top:12px">
      <button class="btn" style="width:100%;justify-content:center;padding:10px;opacity:0.5;cursor:default" title="Coming soon"
        onmouseover="document.getElementById('sso-tooltip').style.display='block'"
        onmouseout="document.getElementById('sso-tooltip').style.display='none'">
        Sign in with Okta SSO
      </button>
      <div id="sso-tooltip" style="display:none;position:absolute;top:-32px;left:50%;transform:translateX(-50%);background:var(--card);border:1px solid var(--card-border);color:var(--amber);font-size:11px;padding:4px 10px;border-radius:6px;white-space:nowrap">Coming soon</div>
    </div>
  </div>
</div>

<div class="toast" id="toast"></div>

<nav class="sidebar" id="sidebar-nav" class="hidden">
  <div class="sidebar-logo"><div class="dot"></div>IntentOS Console</div>
  <div class="nav-items">
    <div class="nav-item active" data-page="dashboard"><span class="icon">&#128202;</span> Dashboard</div>
    <div class="nav-item" data-page="security"><span class="icon">&#128737;</span> Security</div>
    <div class="nav-item" data-page="policies"><span class="icon">&#128203;</span> Policy Manager</div>
    <div class="nav-item" data-page="devices"><span class="icon">&#128187;</span> Devices</div>
    <div class="nav-item" data-page="audit"><span class="icon">&#128220;</span> Audit Log</div>
    <div class="nav-item" data-page="api-keys"><span class="icon">&#128273;</span> API Keys</div>
    <div class="nav-item" data-page="connectors"><span class="icon">&#128268;</span> Connectors</div>
    <div class="nav-item" data-page="licenses"><span class="icon">&#127991;</span> Licenses</div>
    <div class="nav-item" data-page="roi"><span class="icon">&#128176;</span> ROI Calculator</div>
  </div>
  <div class="sidebar-footer">
    <div><span class="online-count" id="online-count">0</span> devices online</div>
    <div id="user-info" style="margin-top:8px;font-size:11px;color:var(--dim)"></div>
    <button class="btn sm" onclick="doLogout()" style="margin-top:8px;width:100%;justify-content:center;font-size:11px">Sign Out</button>
  </div>
</nav>

<div class="main" id="app">Loading...</div>

<script>
const BASE = '';
const $ = s => document.querySelector(s);
const $$ = s => document.querySelectorAll(s);
const fmt = n => n>=1e6?(n/1e6).toFixed(1)+'M':n>=1e3?(n/1e3).toFixed(1)+'K':String(n);
const ago = iso => {
  if(!iso) return 'never';
  const s = Math.floor((Date.now() - new Date(iso+'Z').getTime()) / 1000);
  if(s<0) return 'just now';
  if(s<60) return s+'s ago';
  if(s<3600) return Math.floor(s/60)+'m ago';
  if(s<86400) return Math.floor(s/3600)+'h ago';
  return Math.floor(s/86400)+'d ago';
};
const api = async (path, opts={}) => {
  const token = localStorage.getItem('intentos_token');
  const headers = {'Content-Type':'application/json'};
  if(token) headers['Authorization'] = 'Bearer ' + token;
  const r = await fetch(BASE+path, {headers, ...opts});
  if(r.status === 401 && !path.includes('/auth/')) { doLogout(); return {}; }
  return r.json();
};
function showToast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 3000);
}

// -- Auth --
window.doLogin = async () => {
  const username = document.getElementById('login-username').value;
  const password = document.getElementById('login-password').value;
  const errEl = document.getElementById('login-error');
  errEl.style.display = 'none';
  try {
    const r = await fetch(BASE+'/api/v1/auth/login', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({username, password})
    });
    const data = await r.json();
    if(r.ok && data.token) {
      localStorage.setItem('intentos_token', data.token);
      localStorage.setItem('intentos_user', JSON.stringify(data.user));
      showApp();
    } else {
      errEl.textContent = data.error || 'Invalid username or password';
      errEl.style.display = 'block';
    }
  } catch(e) {
    errEl.textContent = 'Could not connect to server';
    errEl.style.display = 'block';
  }
};
window.doLogout = () => {
  localStorage.removeItem('intentos_token');
  localStorage.removeItem('intentos_user');
  showLogin();
};
function showLogin() {
  document.getElementById('login-screen').classList.remove('hidden');
  document.getElementById('login-screen').style.display = 'flex';
  document.getElementById('sidebar-nav').style.display = 'none';
  document.getElementById('app').style.display = 'none';
}
function showApp() {
  document.getElementById('login-screen').style.display = 'none';
  document.getElementById('sidebar-nav').style.display = 'flex';
  document.getElementById('app').style.display = 'block';
  const user = JSON.parse(localStorage.getItem('intentos_user')||'{}');
  const userInfo = document.getElementById('user-info');
  if(userInfo && user.name) userInfo.textContent = user.name + ' (' + user.role + ')';
  const initHash = window.location.hash.replace('#','') || 'dashboard';
  if(!window.location.hash) window.location.hash = '#dashboard';
  setActivePage(initHash.split('/')[0]);
}

let refreshTimer = null;
let currentPage = 'dashboard';

// -- Navigation --
document.querySelectorAll('.nav-item').forEach(el => {
  el.addEventListener('click', () => {
    const page = el.dataset.page;
    window.location.hash = '#' + page;
  });
});

function setActivePage(page) {
  currentPage = page;
  $$('.nav-item').forEach(n => n.classList.toggle('active', n.dataset.page === page));
  if(refreshTimer) clearInterval(refreshTimer);
  renderPage(page);
  if(page === 'dashboard') refreshTimer = setInterval(() => renderPage('dashboard'), 15000);
}

window.addEventListener('hashchange', () => {
  const hash = window.location.hash.replace('#','') || 'dashboard';
  setActivePage(hash.split('/')[0]);
});

// -- Page Router --
async function renderPage(page) {
  const app = $('#app');
  try {
    if(page === 'dashboard') await renderDashboard(app);
    else if(page === 'security') renderSecurity(app);
    else if(page === 'policies') await renderPolicies(app);
    else if(page === 'devices') await renderDevices(app);
    else if(page === 'audit') await renderAudit(app);
    else if(page === 'api-keys') await renderApiKeys(app);
    else if(page === 'connectors') await renderConnectors(app);
    else if(page === 'licenses') await renderLicenses(app);
    else if(page === 'roi') renderROI(app);
    else app.innerHTML = '<div style="padding:40px;color:var(--dim)">Page not found</div>';
  } catch(e) { console.error(e); app.innerHTML = '<div style="padding:40px;color:var(--red)">Error loading page</div>'; }
}

// -- Dashboard --
async function renderDashboard(app) {
  const [fleet, usage, trend, comp] = await Promise.all([
    api('/api/v1/dashboard/fleet-overview'),
    api('/api/v1/dashboard/ai-usage'),
    api('/api/v1/dashboard/cost-trend'),
    api('/api/v1/dashboard/compliance')
  ]);
  $('#online-count').textContent = fleet.online;
  const totalTok = usage.total_input_tokens + usage.total_output_tokens;
  const localPct = usage.total_calls > 0 ? Math.round(usage.local_calls / usage.total_calls * 100) : 0;
  const days = trend.days.slice().reverse().slice(-7);
  const maxCost = Math.max(...days.map(d => d.cost_usd), 0.01);

  // SVG chart
  const chartW = 700, barArea = 200, padL = 50, padR = 20, padT = 30, padB = 40;
  const usableW = chartW - padL - padR;
  const barW = Math.min(50, usableW / days.length * 0.7);
  const gap = days.length > 1 ? usableW / days.length : usableW;
  const bars = days.map((d, i) => {
    const cx = padL + i * gap + gap / 2;
    const h = (d.cost_usd / maxCost) * barArea;
    const y = padT + barArea - h;
    return `<rect x="${cx - barW/2}" y="${y}" width="${barW}" height="${h}" rx="4" fill="url(#barGrad)" opacity="0.85"/>
      <text x="${cx}" y="${padT + barArea + 18}" text-anchor="middle" font-size="10">${d.date.slice(5)}</text>
      <text x="${cx}" y="${y - 6}" text-anchor="middle" fill="#e2e8f0" font-size="10">$${d.cost_usd.toFixed(2)}</text>`;
  }).join('');
  const svgH = padT + barArea + padB;

  const devRows = fleet.devices.map(d => `<tr>
    <td><strong>${d.hostname}</strong></td>
    <td><span class="badge ${d.status}">${d.status === 'online' ? '&#9679; ' : '&#9675; '}${d.status}</span></td>
    <td><span class="mono" style="font-size:12px">${d.privacy_mode}</span></td>
    <td>${ago(d.last_heartbeat_at)}</td>
    <td>${d.policy_compliant ? '<span class="check">&#10003;</span>' : '<span class="cross">&#10007;</span>'}</td>
  </tr>`).join('');

  const evtRows = (comp.recent || []).slice(0, 5).map(e => `<tr>
    <td>${e.event_type.replace(/_/g,' ')}</td>
    <td><span class="badge ${e.severity}">${e.severity}</span></td>
    <td>${e.hostname || 'unknown'}</td>
    <td>${ago(e.created_at)}</td>
    <td style="font-size:12px;color:var(--dim);max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${e.details||''}</td>
  </tr>`).join('');

  app.innerHTML = `
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px">
    <h1 class="page-title" style="margin-bottom:0">Dashboard</h1>
    <button class="btn primary" onclick="downloadReport()">&#128196; Download Report</button>
  </div>
  <div class="grid4">
    <div class="card"><div class="label">Total Devices</div><div class="value blue">${fleet.total_devices}</div></div>
    <div class="card"><div class="label">Online Now</div><div class="value green">${fleet.online}</div></div>
    <div class="card"><div class="label">Compliant</div><div class="value cyan">${fleet.compliant}/${fleet.total_devices}</div></div>
    <div class="card"><div class="label">Total AI Spend</div><div class="value purple">$${fleet.total_cost_usd.toFixed(2)}</div></div>
  </div>

  <section><h2>Cost Trend (7 Days)</h2>
  <div class="chart-wrap">
    <svg width="100%" viewBox="0 0 ${chartW} ${svgH}" preserveAspectRatio="xMidYMid meet">
      <defs><linearGradient id="barGrad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="#06b6d4" stop-opacity="0.8"/>
        <stop offset="100%" stop-color="#2563eb" stop-opacity="0.35"/></linearGradient></defs>
      <line x1="${padL}" y1="${padT+barArea}" x2="${chartW-padR}" y2="${padT+barArea}" stroke="rgba(255,255,255,0.08)" stroke-width="1"/>
      ${bars}
    </svg>
  </div></section>

  <section><h2>Fleet Devices</h2>
  <table><thead><tr><th>Hostname</th><th>Status</th><th>Privacy Mode</th><th>Last Heartbeat</th><th>Compliant</th></tr></thead>
  <tbody>${devRows}</tbody></table></section>

  <section><h2>Recent Compliance Events</h2>
  ${comp.total_events ? `<table><thead><tr><th>Event</th><th>Severity</th><th>Device</th><th>When</th><th>Details</th></tr></thead>
  <tbody>${evtRows}</tbody></table>` : '<div class="card" style="text-align:center;color:var(--dim);padding:30px">No compliance events recorded</div>'}
  </section>`;

  // Store data for report generation
  window._dashData = {fleet, usage, trend, comp, days};
}

// -- Download Report --
window.downloadReport = async () => {
  // Fetch fresh data if needed
  let d = window._dashData;
  if(!d) {
    const [fleet, usage, trend, comp] = await Promise.all([
      api('/api/v1/dashboard/fleet-overview'),
      api('/api/v1/dashboard/ai-usage'),
      api('/api/v1/dashboard/cost-trend'),
      api('/api/v1/dashboard/compliance')
    ]);
    const days = trend.days.slice().reverse().slice(-7);
    d = {fleet, usage, trend, comp, days};
  }
  const now = new Date().toLocaleDateString('en-US', {year:'numeric',month:'long',day:'numeric'});

  const modelRows = Object.entries(d.usage.by_model).map(([m,v]) =>
    `<tr><td>${m}</td><td>${v.calls}</td><td>$${v.cost_usd.toFixed(2)}</td></tr>`).join('');

  const devRows = d.fleet.devices.map(dev =>
    `<tr><td>${dev.hostname}</td><td>${dev.status}</td><td>${dev.os}</td><td>${dev.privacy_mode}</td><td>${dev.policy_compliant?'Yes':'No'}</td></tr>`).join('');

  const evtRows = (d.comp.recent||[]).slice(0,10).map(e =>
    `<tr><td>${e.event_type.replace(/_/g,' ')}</td><td>${e.severity}</td><td>${e.hostname||'unknown'}</td><td>${e.details||''}</td></tr>`).join('');

  const costRows = (d.days||[]).map(day =>
    `<tr><td>${day.date}</td><td>${day.calls}</td><td>$${day.cost_usd.toFixed(2)}</td></tr>`).join('');

  const html = `<!DOCTYPE html><html><head><meta charset="UTF-8"><title>IntentOS Fleet Report</title>
<style>
  body{font-family:Arial,Helvetica,sans-serif;max-width:800px;margin:40px auto;color:#1a1a2e;line-height:1.6}
  h1{font-size:24px;margin-bottom:4px} h2{font-size:18px;margin-top:32px;margin-bottom:12px;border-bottom:2px solid #06b6d4;padding-bottom:4px}
  table{width:100%;border-collapse:collapse;margin:12px 0}
  th,td{border:1px solid #ddd;padding:8px 12px;text-align:left;font-size:13px}
  th{background:#f5f5f5;font-weight:600} .kpi{display:inline-block;width:23%;text-align:center;margin:8px 0}
  .kpi .num{font-size:28px;font-weight:700;color:#2563eb} .kpi .lbl{font-size:11px;color:#666;text-transform:uppercase}
  .footer{margin-top:40px;padding-top:16px;border-top:1px solid #ddd;font-size:11px;color:#999;text-align:center}
  @media print{body{margin:20px}}
</style></head><body>
<h1>IntentOS Fleet Report</h1>
<p style="color:#666;margin-bottom:24px">${now}</p>

<h2>Fleet Overview</h2>
<div>
  <div class="kpi"><div class="num">${d.fleet.total_devices}</div><div class="lbl">Total Devices</div></div>
  <div class="kpi"><div class="num">${d.fleet.online}</div><div class="lbl">Online</div></div>
  <div class="kpi"><div class="num">${d.fleet.compliant}/${d.fleet.total_devices}</div><div class="lbl">Compliant</div></div>
  <div class="kpi"><div class="num">$${d.fleet.total_cost_usd.toFixed(2)}</div><div class="lbl">Total Spend</div></div>
</div>

<h2>AI Usage Summary</h2>
<p>Total calls: ${d.usage.total_calls} | Cloud: ${d.usage.cloud_calls} | Local: ${d.usage.local_calls} | Total cost: $${d.usage.total_cost_usd.toFixed(2)}</p>
<table><thead><tr><th>Model</th><th>Calls</th><th>Cost</th></tr></thead><tbody>${modelRows}</tbody></table>

<h2>Device Status</h2>
<table><thead><tr><th>Hostname</th><th>Status</th><th>OS</th><th>Privacy Mode</th><th>Compliant</th></tr></thead><tbody>${devRows}</tbody></table>

<h2>Recent Compliance Events</h2>
${evtRows ? `<table><thead><tr><th>Event</th><th>Severity</th><th>Device</th><th>Details</th></tr></thead><tbody>${evtRows}</tbody></table>` : '<p>No compliance events.</p>'}

<h2>Cost Trend (Last 7 Days)</h2>
<table><thead><tr><th>Date</th><th>Calls</th><th>Cost</th></tr></thead><tbody>${costRows}</tbody></table>

<div class="footer">Generated by IntentOS Console &middot; Confidential</div>
<script>window.print();<\/script>
</body></html>`;

  const w = window.open('','_blank');
  w.document.write(html);
  w.document.close();
};

// -- Security & Compliance Page --
function renderSecurity(app) {
  app.innerHTML = `
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:24px">
    <h1 class="page-title" style="margin-bottom:0">Security &amp; Compliance</h1>
    <button class="btn primary" onclick="alert('PDF export coming soon')">&#128196; Download PDF</button>
  </div>

  <div class="sec-section">
    <h2>1. Architecture Overview</h2>
    <p>IntentOS enforces a strict security perimeter between user devices, local inference, and optional cloud APIs. All file content and personally identifiable data stays on-device. Only inference prompts (with no file content) cross the network boundary when cloud routing is explicitly enabled.</p>
    <div class="arch-diagram">
  +------------------------------------------------------------------+
  |                      USER DEVICE (Trust Zone)                     |
  |                                                                    |
  |  +-----------+     +------------------+     +-----------------+    |
  |  |  IntentOS |---->|  Intent Kernel   |---->|  Agent Sandbox  |    |
  |  |  Desktop  |     |  (Parse + Route) |     |  (Isolated Exec)|    |
  |  +-----------+     +------------------+     +-----------------+    |
  |        |                    |                        |             |
  |        v                    v                        v             |
  |  +-----------+     +------------------+     +-----------------+    |
  |  | RAG Index |     |  Inference Router |     |  File System   |    |
  |  | (ChromaDB)|     |  (Score + Route)  |     |  (Granted Paths)|   |
  |  +-----------+     +------------------+     +-----------------+    |
  |                       |            |                               |
  +=======================|============|===============================+
      SECURITY BOUNDARY   |            |
                          v            v
               +------------+   +-------------+
               | Local Model|   | Cloud API   |
               | (Ollama)   |   | (Opt-in,    |
               | FREE, 100% |   |  TLS 1.3)   |
               | Private    |   | No file data|
               +------------+   +-------------+</div>
  </div>

  <div class="sec-section">
    <h2>2. Data Residency</h2>
    <p>IntentOS is designed so that sensitive data never leaves the device. The following table documents where each data type resides and its encryption status.</p>
    <table class="sec-table"><thead><tr><th>Data Type</th><th>Location</th><th>Encrypted?</th></tr></thead><tbody>
      <tr><td>File contents</td><td>Device only</td><td>N/A (OS-level)</td></tr>
      <tr><td>File paths</td><td>Device only</td><td>N/A (OS-level)</td></tr>
      <tr><td>RAG embeddings</td><td>Device only</td><td>AES-256</td></tr>
      <tr><td>Task history</td><td>Device only</td><td>SQLite (encrypted at rest)</td></tr>
      <tr><td>Inference prompts (local)</td><td>Device only</td><td>N/A (in-memory)</td></tr>
      <tr><td>Inference prompts (cloud)</td><td>Transmitted</td><td>TLS 1.3</td></tr>
      <tr><td>Usage metrics</td><td>Console</td><td>TLS 1.3 + AES</td></tr>
      <tr><td>API keys</td><td>OS Keychain</td><td>OS-managed</td></tr>
      <tr><td>Audit log</td><td>Device + Console</td><td>AES-256</td></tr>
    </tbody></table>
  </div>

  <div class="sec-section">
    <h2>3. Encryption Standards</h2>
    <p>All cryptographic operations use industry-standard algorithms with no custom or proprietary ciphers. Key management follows NIST SP 800-57 guidelines.</p>
    <table class="sec-table"><thead><tr><th>Component</th><th>Algorithm</th><th>Key Size</th></tr></thead><tbody>
      <tr><td>Credential store</td><td>AES-256-GCM</td><td>256-bit</td></tr>
      <tr><td>Policy signing</td><td>HMAC-SHA256</td><td>256-bit</td></tr>
      <tr><td>Console transport</td><td>TLS 1.3</td><td>256-bit</td></tr>
      <tr><td>Key derivation</td><td>HKDF-SHA256</td><td>256-bit</td></tr>
      <tr><td>OS keychain</td><td>Platform-native</td><td>Platform-managed</td></tr>
    </tbody></table>
  </div>

  <div class="sec-section">
    <h2>4. Access Control Model</h2>
    <p>IntentOS implements a <strong>two-user daemon model</strong> for privilege separation. The human user owns files and grants explicit path access. The IntentOS daemon (<code>_intentos</code>) runs with zero default filesystem access and executes agents only within granted boundaries.</p>
    <p>Each agent runs under one of three sandbox policies:</p>
    <table class="sec-table"><thead><tr><th>Policy</th><th>Filesystem</th><th>Network</th><th>Use Case</th></tr></thead><tbody>
      <tr><td><strong>ReadOnly</strong></td><td>/workspace read-only</td><td>Proxied (allowlist)</td><td>Analysis agents</td></tr>
      <tr><td><strong>WorkspaceWrite</strong></td><td>/workspace read/write</td><td>Proxied (allowlist)</td><td>Most agents</td></tr>
      <tr><td><strong>FullAccess</strong></td><td>Full host access</td><td>Unrestricted</td><td>System agent (double opt-in)</td></tr>
    </tbody></table>
    <p>All destructive actions (delete, overwrite, move outside workspace) require explicit user confirmation. The daemon enforces <code>NoNewPrivileges</code> on Linux and equivalent restrictions on macOS/Windows. Path grants are stored in <code>~/.intentos/grants.json</code> and enforced at the OS ACL level.</p>
  </div>

  <div class="sec-section">
    <h2>5. Credential Management</h2>
    <p>IntentOS never stores credentials in <code>.env</code> files or configuration files in production. All secrets are managed through the operating system's native keychain:</p>
    <table class="sec-table"><thead><tr><th>Platform</th><th>Keychain</th><th>Access Control</th></tr></thead><tbody>
      <tr><td>macOS</td><td>Keychain Services</td><td>Per-app ACL, biometric optional</td></tr>
      <tr><td>Windows</td><td>Credential Manager</td><td>User-session scoped</td></tr>
      <tr><td>Linux</td><td>GNOME Keyring / KWallet</td><td>Session-locked</td></tr>
    </tbody></table>
    <p>API keys are injected at the network proxy boundary and never appear in agent code. The output pipeline scans all agent responses for credential patterns (AWS keys, bearer tokens, PEM blocks) before they reach the LLM or user interface.</p>
  </div>

  <div class="sec-section">
    <h2>6. Audit &amp; Logging</h2>
    <p>Every agent action is logged to an append-only audit file at <code>~/.intentos/logs/audit.jsonl</code>. Each entry includes timestamp, task ID, agent name, action, paths accessed, result, initiating user, and duration. The inference ledger records every cloud API call with model, token count, and cost.</p>
    <p>Logs are compatible with major SIEM platforms:</p>
    <table class="sec-table"><thead><tr><th>Platform</th><th>Format</th><th>Integration</th></tr></thead><tbody>
      <tr><td>Splunk</td><td>CIM-compatible JSON</td><td>HEC (HTTP Event Collector)</td></tr>
      <tr><td>Azure Sentinel</td><td>CEF / JSON</td><td>Log Analytics agent</td></tr>
      <tr><td>Elastic / ELK</td><td>JSON</td><td>Filebeat / direct API</td></tr>
    </tbody></table>
    <p>Retention: device-local logs retained for 90 days by default (configurable via policy). Console-aggregated logs follow the organization's retention policy.</p>
  </div>

  <div class="sec-section">
    <h2>7. Policy Enforcement</h2>
    <p>Policies are <strong>HMAC-SHA256 signed</strong> by the Console before distribution. Each device verifies the signature before applying a policy update. Tampered policies are rejected and a compliance event is generated.</p>
    <p>Policy controls include: privacy mode locking (prevent users from switching to cloud), agent allowlists, spending caps (daily/monthly per device or org), model pinning (restrict which LLMs can be used), and OTA policy updates delivered via the heartbeat channel.</p>
  </div>

  <div class="sec-section">
    <h2>8. Leak Detection Pipeline</h2>
    <p>IntentOS runs a three-stage leak detection pipeline on every task execution:</p>
    <table class="sec-table"><thead><tr><th>Stage</th><th>Action</th><th>Purpose</th></tr></thead><tbody>
      <tr><td>1. Input Scan</td><td>Scan user input for injection patterns</td><td>Prompt injection defense</td></tr>
      <tr><td>2. Execution</td><td>Agents run in sandboxed environment</td><td>Contain blast radius</td></tr>
      <tr><td>3. Output Scan</td><td>Scan all output for credential patterns</td><td>Prevent credential leakage to LLM</td></tr>
    </tbody></table>
    <p>Detected patterns and severity:</p>
    <table class="sec-table"><thead><tr><th>Pattern</th><th>Severity</th><th>Action</th></tr></thead><tbody>
      <tr><td>AWS Access Key (AKIA...)</td><td>Critical</td><td>Block</td></tr>
      <tr><td>Private Key (PEM)</td><td>Critical</td><td>Block</td></tr>
      <tr><td>Bearer Token</td><td>High</td><td>Redact</td></tr>
      <tr><td>API Token (generic)</td><td>High</td><td>Redact</td></tr>
      <tr><td>Connection String</td><td>Medium</td><td>Warn</td></tr>
    </tbody></table>
  </div>

  <div class="sec-section">
    <h2>9. Compliance Mapping</h2>
    <p>IntentOS maps to major compliance frameworks out of the box:</p>
    <table class="sec-table"><thead><tr><th>Framework</th><th>Control</th><th>IntentOS Implementation</th></tr></thead><tbody>
      <tr><td>SOC2 CC6.1</td><td>Logical access</td><td>Policy engine + agent sandboxing</td></tr>
      <tr><td>SOC2 CC6.6</td><td>Encryption</td><td>AES-256-GCM + OS keychain</td></tr>
      <tr><td>SOC2 CC7.2</td><td>Monitoring</td><td>Inference ledger + audit log + Console</td></tr>
      <tr><td>HIPAA &sect;164.312(a)</td><td>Access control</td><td>Access control via policy engine</td></tr>
      <tr><td>HIPAA &sect;164.312(e)</td><td>Encryption</td><td>TLS 1.3 in transit, AES-256 at rest</td></tr>
      <tr><td>GDPR Art.25</td><td>Privacy by design</td><td>Local-first architecture</td></tr>
      <tr><td>GDPR Art.32</td><td>Security measures</td><td>Encryption + access controls + audit trail</td></tr>
      <tr><td>ISO 27001 A.8</td><td>Asset management</td><td>Fleet Console with device inventory</td></tr>
      <tr><td>ISO 27001 A.10</td><td>Cryptographic controls</td><td>AES-256, HMAC-SHA256, HKDF</td></tr>
    </tbody></table>
  </div>

  <div class="sec-section">
    <h2>10. Incident Response</h2>
    <p>When a policy violation or security event is detected, IntentOS follows this automated response flow:</p>
    <div class="arch-diagram" style="font-size:12px">
  Violation Detected
       |
       v
  Compliance Event Created (device-local audit log)
       |
       v
  Alert to Console (next heartbeat, &lt;60s)
       |
       v
  Webhook to Slack / SIEM (if configured)
       |
       v
  Audit Trail Preserved (append-only, tamper-evident)
       |
       v
  IT Admin Reviews in Console (Compliance Events page)</div>
  </div>

  <div class="sec-section">
    <h2>11. Deployment Security</h2>
    <p>IntentOS supports enterprise MDM deployment through Jamf (macOS) and Microsoft Intune (Windows). The installer is distributed as a signed <code>.pkg</code> (macOS) or <code>.msi</code> (Windows) with code signing certificates.</p>
    <table class="sec-table"><thead><tr><th>Feature</th><th>Details</th></tr></thead><tbody>
      <tr><td>Update channels</td><td>Stable (production) and Beta (early access)</td></tr>
      <tr><td>Offline operation</td><td>30-day license grace period without Console connectivity</td></tr>
      <tr><td>Auto-update</td><td>Disabled by default; requires IT admin approval via policy</td></tr>
      <tr><td>MDM integration</td><td>Jamf, Intune, Kandji, Mosyle</td></tr>
      <tr><td>Binary signing</td><td>Apple notarization (macOS), Authenticode (Windows)</td></tr>
    </tbody></table>
  </div>
  `;
}

// -- ROI Calculator --
function renderROI(app) {
  app.innerHTML = `
  <h1 class="page-title">ROI Calculator</h1>
  <p style="color:var(--dim);margin-bottom:24px">Estimate your savings by switching to IntentOS from current AI tools.</p>

  <div class="card" style="margin-bottom:24px">
    <div class="roi-inputs">
      <div class="form-group">
        <label>Number of seats</label>
        <input type="number" id="roi-seats" value="100" min="1" oninput="calcROI()">
      </div>
      <div class="form-group">
        <label>Current AI tool</label>
        <select id="roi-tool" onchange="roiToolChange();calcROI()">
          <option value="60">ChatGPT Enterprise ($60/seat)</option>
          <option value="30">Microsoft Copilot ($30/seat)</option>
          <option value="39">GitHub Copilot ($39/seat)</option>
          <option value="custom">Other (custom)</option>
        </select>
      </div>
      <div class="form-group">
        <label>Current monthly cost per seat ($)</label>
        <input type="number" id="roi-cost" value="60" min="0" step="1" oninput="calcROI()">
      </div>
      <div class="form-group">
        <label>Average tasks per user per day</label>
        <input type="number" id="roi-tasks" value="15" min="1" oninput="calcROI()">
      </div>
      <div class="form-group" style="grid-column:1/-1">
        <label>% tasks that can run locally: <span id="roi-local-val" style="color:var(--cyan)">70%</span></label>
        <input type="range" id="roi-local" min="0" max="100" value="70" oninput="document.getElementById('roi-local-val').textContent=this.value+'%';calcROI()">
      </div>
    </div>
  </div>

  <div class="roi-output" id="roi-output">
    <div class="card" style="text-align:center">
      <div class="label">Current Annual Cost</div>
      <div class="roi-big" style="color:var(--red)" id="roi-current">$72,000</div>
    </div>
    <div class="card" style="text-align:center">
      <div class="label">IntentOS Annual Cost</div>
      <div class="roi-big" style="color:var(--cyan)" id="roi-intentos">$42,000</div>
    </div>
    <div class="card" style="text-align:center">
      <div class="label">Annual Savings</div>
      <div class="roi-big" style="color:var(--green)" id="roi-savings">$30,000</div>
    </div>
  </div>

  <div class="grid2" style="margin-top:16px">
    <div class="card" style="text-align:center">
      <div class="label">Est. Cloud API Cost / Year</div>
      <div class="value cyan" id="roi-cloud">$4,931</div>
    </div>
    <div class="card" style="text-align:center">
      <div class="label">Effective Cost Per Seat / Month</div>
      <div class="value blue" id="roi-effective">$35.00</div>
    </div>
  </div>

  <div style="margin-top:24px">
    <h2 style="font-size:15px;color:var(--dim);text-transform:uppercase;letter-spacing:.06em;margin-bottom:14px">Comparison</h2>
    <div class="card" style="padding:24px">
      <svg width="100%" viewBox="0 0 500 120" id="roi-chart"></svg>
    </div>
  </div>

  <div class="roi-summary" id="roi-summary"></div>`;

  calcROI();
}

window.roiToolChange = () => {
  const sel = document.getElementById('roi-tool');
  const costInput = document.getElementById('roi-cost');
  if(sel.value !== 'custom') {
    costInput.value = sel.value;
  }
};

window.calcROI = () => {
  const seats = Math.max(1, parseInt(document.getElementById('roi-seats').value) || 100);
  const costPerSeat = Math.max(0, parseFloat(document.getElementById('roi-cost').value) || 0);
  const tasks = Math.max(1, parseInt(document.getElementById('roi-tasks').value) || 15);
  const localPct = (parseInt(document.getElementById('roi-local').value) || 70) / 100;
  const cloudPct = 1 - localPct;

  const currentAnnual = seats * costPerSeat * 12;
  const intentosLicense = seats * 35 * 12;
  const cloudApiCost = Math.round(seats * tasks * cloudPct * 0.003 * 365);
  const intentosTotal = intentosLicense + cloudApiCost;
  const savings = currentAnnual - intentosTotal;
  const effectivePerSeat = intentosTotal / seats / 12;

  const f = n => '$' + Math.abs(n).toLocaleString('en-US', {maximumFractionDigits:0});

  document.getElementById('roi-current').textContent = f(currentAnnual);
  document.getElementById('roi-intentos').textContent = f(intentosTotal);
  document.getElementById('roi-savings').textContent = (savings >= 0 ? '' : '-') + f(savings);
  document.getElementById('roi-savings').style.color = savings >= 0 ? 'var(--green)' : 'var(--red)';
  document.getElementById('roi-cloud').textContent = f(cloudApiCost);
  document.getElementById('roi-effective').textContent = '$' + effectivePerSeat.toFixed(2);

  // Bar chart
  const maxVal = Math.max(currentAnnual, intentosTotal, 1);
  const currentW = Math.max(10, (currentAnnual / maxVal) * 400);
  const intentosW = Math.max(10, (intentosTotal / maxVal) * 400);
  document.getElementById('roi-chart').innerHTML = `
    <text x="0" y="28" fill="#e2e8f0" font-family="Space Grotesk" font-size="13">Current</text>
    <rect x="80" y="14" width="${currentW}" height="24" rx="6" fill="#ef4444" opacity="0.7"/>
    <text x="${82+currentW}" y="31" fill="#e2e8f0" font-family="JetBrains Mono" font-size="12">${f(currentAnnual)}</text>
    <text x="0" y="78" fill="#e2e8f0" font-family="Space Grotesk" font-size="13">IntentOS</text>
    <rect x="80" y="64" width="${intentosW}" height="24" rx="6" fill="#06b6d4" opacity="0.7"/>
    <text x="${82+intentosW}" y="81" fill="#e2e8f0" font-family="JetBrains Mono" font-size="12">${f(intentosTotal)}</text>`;

  // Summary
  const toolSel = document.getElementById('roi-tool');
  const toolName = toolSel.options[toolSel.selectedIndex].text.split('(')[0].trim();
  const summaryEl = document.getElementById('roi-summary');
  if(savings > 0) {
    summaryEl.innerHTML = `<strong style="color:var(--green)">Switching ${seats} seats from ${toolName} to IntentOS saves ${f(savings)}/year</strong> while ensuring files never leave your devices. ${Math.round(localPct*100)}% of tasks run locally at zero inference cost.`;
  } else {
    summaryEl.innerHTML = `At the current pricing, IntentOS costs ${f(Math.abs(savings))}/year more than ${toolName} for ${seats} seats. However, IntentOS provides <strong>enterprise-grade security</strong> with local-first AI execution and full audit trails that ${toolName} cannot match.`;
  }
};

// -- Connectors --
async function renderConnectors(app) {
  const connectors = await api('/api/v1/connectors');

  const icons = {slack:'\u{1F4AC}', teams:'\u{1F465}', splunk:'\u{1F50D}', jira:'\u{1F4CB}', okta:'\u{1F510}', email:'\u{1F4E7}'};
  const descriptions = {
    slack:'Send real-time alerts to Slack channels when policy violations, spending alerts, or device events occur.',
    teams:'Push notifications to Microsoft Teams channels for security and compliance events.',
    splunk:'Stream audit logs and compliance events to Splunk for centralized SIEM monitoring.',
    jira:'Automatically create Jira tickets when policy violations are detected.',
    okta:'Enable SSO authentication for Console access via Okta.',
    email:'Send weekly digest emails summarizing fleet security status and compliance events.'
  };

  const cards = connectors.map(c => {
    const cfg = JSON.parse(c.config || '{}');
    const icon = icons[c.id] || '\u{1F517}';
    const desc = descriptions[c.id] || '';
    const statusClass = c.status === 'connected' ? 'connected' : 'not_configured';
    const statusLabel = c.status === 'connected' ? 'Connected' : 'Not Configured';
    const isOkta = c.id === 'okta';

    let configHTML = '';
    if(c.id === 'slack' || c.id === 'teams') {
      const evts = cfg.events || {};
      configHTML = `
        <div class="connector-config hidden" id="cfg-${c.id}">
          <div class="form-group"><label>Webhook URL</label>
            <input type="text" id="cfg-${c.id}-url" value="${cfg.webhook_url||''}"></div>
          <div style="margin-bottom:12px">
            <div class="label" style="margin-bottom:8px">Events to Notify</div>
            <label style="display:flex;align-items:center;gap:6px;font-size:13px;margin-bottom:4px;cursor:pointer">
              <input type="checkbox" ${evts.policy_violations?'checked':''} data-evt="policy_violations"> Policy Violations</label>
            <label style="display:flex;align-items:center;gap:6px;font-size:13px;margin-bottom:4px;cursor:pointer">
              <input type="checkbox" ${evts.spending_alerts?'checked':''} data-evt="spending_alerts"> Spending Alerts</label>
            <label style="display:flex;align-items:center;gap:6px;font-size:13px;margin-bottom:4px;cursor:pointer">
              <input type="checkbox" ${evts.device_offline?'checked':''} data-evt="device_offline"> Device Offline</label>
            <label style="display:flex;align-items:center;gap:6px;font-size:13px;margin-bottom:4px;cursor:pointer">
              <input type="checkbox" ${evts.new_device_registered?'checked':''} data-evt="new_device_registered"> New Device Registered</label>
          </div>
          <div class="form-actions">
            <button class="btn primary" onclick="saveConnector('${c.id}')">Save</button>
            <button class="btn" onclick="testConnector('${c.id}')">Test Connection</button>
            <button class="btn" onclick="document.getElementById('cfg-${c.id}').classList.add('hidden')">Cancel</button>
          </div>
        </div>`;
    } else if(c.id === 'splunk') {
      configHTML = `
        <div class="connector-config hidden" id="cfg-${c.id}">
          <div class="form-group"><label>HEC URL</label>
            <input type="text" id="cfg-${c.id}-hec-url" value="${cfg.hec_url||''}"></div>
          <div class="form-group"><label>HEC Token</label>
            <input type="password" id="cfg-${c.id}-hec-token" value="${cfg.hec_token||''}"></div>
          <div class="form-group"><label>Index</label>
            <input type="text" id="cfg-${c.id}-index" value="${cfg.index||'intentos'}"></div>
          <div class="form-group"><label>Source Type</label>
            <input type="text" id="cfg-${c.id}-sourcetype" value="${cfg.source_type||'intentos:audit'}"></div>
          <div style="margin-top:12px;margin-bottom:12px">
            <details>
              <summary style="font-size:12px;color:var(--blue);cursor:pointer">Export Format Preview</summary>
              <pre style="background:rgba(0,0,0,0.3);padding:12px;border-radius:8px;font-size:11px;margin-top:8px;color:var(--cyan);overflow-x:auto">{
  "time": 1712678400,
  "host": "alice-macbook",
  "source": "intentos",
  "sourcetype": "intentos:audit",
  "event": {
    "action": "file.list_files",
    "agent": "file_agent",
    "device_id": "abc-123",
    "result": "success",
    "cost_usd": 0.0
  }
}</pre>
            </details>
          </div>
          <div class="form-actions">
            <button class="btn primary" onclick="saveConnector('${c.id}')">Save</button>
            <button class="btn" onclick="testConnector('${c.id}')">Test Connection</button>
            <button class="btn" onclick="document.getElementById('cfg-${c.id}').classList.add('hidden')">Cancel</button>
          </div>
        </div>`;
    } else if(c.id === 'jira') {
      configHTML = `
        <div class="connector-config hidden" id="cfg-${c.id}">
          <div class="form-group"><label>Project Key</label>
            <input type="text" id="cfg-${c.id}-project" value="${cfg.project_key||''}" placeholder="e.g. SEC"></div>
          <div class="form-group"><label>API Token</label>
            <input type="password" id="cfg-${c.id}-token" value="${cfg.api_token||''}"></div>
          <div style="margin-bottom:12px;display:flex;align-items:center;gap:8px">
            <label class="toggle"><input type="checkbox" id="cfg-${c.id}-auto" ${cfg.create_on_violation?'checked':''}><span class="slider"></span></label>
            <span style="font-size:13px">Create ticket on policy violation</span>
          </div>
          <div class="form-actions">
            <button class="btn primary" onclick="saveConnector('${c.id}')">Save</button>
            <button class="btn" onclick="testConnector('${c.id}')">Test Connection</button>
            <button class="btn" onclick="document.getElementById('cfg-${c.id}').classList.add('hidden')">Cancel</button>
          </div>
        </div>`;
    } else if(c.id === 'okta') {
      configHTML = `
        <div class="connector-config hidden" id="cfg-${c.id}">
          <p style="font-size:12px;color:var(--amber);margin-bottom:12px">Coming in v2.1</p>
          <div class="form-group"><label>Okta Domain</label>
            <input type="text" id="cfg-${c.id}-domain" value="${cfg.domain||''}" placeholder="your-org.okta.com"></div>
          <div class="form-group"><label>Client ID</label>
            <input type="text" id="cfg-${c.id}-clientid" value="${cfg.client_id||''}"></div>
          <div class="form-group"><label>Client Secret</label>
            <input type="password" id="cfg-${c.id}-secret" value="${cfg.client_secret||''}"></div>
          <div class="form-actions">
            <button class="btn primary" onclick="saveConnector('${c.id}')">Save</button>
            <button class="btn" onclick="document.getElementById('cfg-${c.id}').classList.add('hidden')">Cancel</button>
          </div>
        </div>`;
    } else if(c.id === 'email') {
      const recipients = (cfg.recipients || []).join(', ');
      configHTML = `
        <div class="connector-config hidden" id="cfg-${c.id}">
          <div class="form-group"><label>Method</label>
            <select id="cfg-${c.id}-method"><option value="sendgrid" ${cfg.method==='sendgrid'?'selected':''}>SendGrid</option><option value="smtp" ${cfg.method==='smtp'?'selected':''}>Custom SMTP</option></select></div>
          <div class="form-group"><label>Recipients (comma-separated)</label>
            <input type="text" id="cfg-${c.id}-recipients" value="${recipients}"></div>
          <div class="form-group"><label>Schedule</label>
            <input type="text" id="cfg-${c.id}-schedule" value="${cfg.schedule||'Weekly on Monday 9:00 AM'}"></div>
          <div class="form-actions">
            <button class="btn primary" onclick="saveConnector('${c.id}')">Save</button>
            <button class="btn" onclick="testConnector('${c.id}')">Test Connection</button>
            <button class="btn" onclick="document.getElementById('cfg-${c.id}').classList.add('hidden')">Cancel</button>
          </div>
        </div>`;
    }

    return `<div class="connector-card">
      <div class="connector-header">
        <div style="display:flex;align-items:center;gap:10px">
          <span style="font-size:24px">${icon}</span>
          <div>
            <h3 style="font-size:16px">${c.name}</h3>
            ${isOkta ? '<span style="font-size:11px;color:var(--amber)">Coming in v2.1</span>' : ''}
          </div>
        </div>
        <span class="badge ${statusClass}">${statusLabel}</span>
      </div>
      <p style="font-size:13px;color:var(--dim);margin-bottom:12px">${desc}</p>
      ${c.last_tested ? `<p style="font-size:11px;color:var(--dim)">Last tested: ${ago(c.last_tested)}</p>` : ''}
      <button class="btn sm" onclick="document.getElementById('cfg-${c.id}').classList.toggle('hidden')" style="margin-top:8px">Configure</button>
      ${configHTML}
    </div>`;
  }).join('');

  app.innerHTML = `
  <h1 class="page-title">Connectors</h1>
  <p style="color:var(--dim);margin-bottom:24px">Manage integrations with external tools and services.</p>
  <div class="connector-grid">${cards}</div>`;
}

window.saveConnector = async (id) => {
  let config = {};
  if(id === 'slack' || id === 'teams') {
    const evts = {};
    document.querySelectorAll('#cfg-'+id+' input[data-evt]').forEach(cb => {
      evts[cb.dataset.evt] = cb.checked;
    });
    config = {webhook_url: document.getElementById('cfg-'+id+'-url').value, events: evts};
  } else if(id === 'splunk') {
    config = {
      hec_url: document.getElementById('cfg-splunk-hec-url').value,
      hec_token: document.getElementById('cfg-splunk-hec-token').value,
      index: document.getElementById('cfg-splunk-index').value,
      source_type: document.getElementById('cfg-splunk-sourcetype').value
    };
  } else if(id === 'jira') {
    config = {
      project_key: document.getElementById('cfg-jira-project').value,
      api_token: document.getElementById('cfg-jira-token').value,
      create_on_violation: document.getElementById('cfg-jira-auto').checked
    };
  } else if(id === 'okta') {
    config = {
      domain: document.getElementById('cfg-okta-domain').value,
      client_id: document.getElementById('cfg-okta-clientid').value,
      client_secret: document.getElementById('cfg-okta-secret').value
    };
  } else if(id === 'email') {
    config = {
      method: document.getElementById('cfg-email-method').value,
      recipients: document.getElementById('cfg-email-recipients').value.split(',').map(s=>s.trim()).filter(Boolean),
      schedule: document.getElementById('cfg-email-schedule').value
    };
  }
  await api('/api/v1/connectors/'+id, {method:'PUT', body:JSON.stringify({config, status:'connected'})});
  showToast('Connector saved');
  renderConnectors($('#app'));
};

window.testConnector = async (id) => {
  const result = await api('/api/v1/connectors/'+id+'/test', {method:'POST'});
  if(result.success) {
    showToast('\u2713 ' + result.message);
  } else {
    showToast('Test failed: ' + (result.message||'Unknown error'));
  }
};

// -- Policy Manager --
async function renderPolicies(app) {
  const policies = await api('/api/v1/policies');
  const policyCards = policies.map(p => {
    let pj = {};
    try { pj = JSON.parse(p.policy_json); } catch(e) {}
    return `<div class="card" style="margin-bottom:16px">
      <div style="display:flex;justify-content:space-between;align-items:start;margin-bottom:10px">
        <div>
          <h3 style="font-size:16px">${p.name} ${p.is_default ? '<span class="badge default">DEFAULT</span>' : ''}</h3>
          <p style="font-size:13px;color:var(--dim);margin-top:4px">${p.description || ''}</p>
        </div>
        <div style="display:flex;gap:6px">
          <button class="btn sm" onclick="editPolicy('${p.id}')">Edit</button>
          <button class="btn sm danger" onclick="deletePolicy('${p.id}','${p.name}')">Delete</button>
        </div>
      </div>
      <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;font-size:12px">
        <div><span style="color:var(--dim)">Privacy Mode:</span> <span class="mono">${pj.privacy_mode||'n/a'}</span></div>
        <div><span style="color:var(--dim)">Agents:</span> <span class="mono">${(pj.allowed_agents||[]).length} allowed</span></div>
        <div><span style="color:var(--dim)">Spend Limit:</span> <span class="mono">$${pj.max_daily_spend_usd||0}/day</span></div>
      </div>
      <div class="hidden" id="edit-${p.id}">
        <div style="margin-top:14px;border-top:1px solid var(--card-border);padding-top:14px">
          <div class="form-group"><label>Name</label><input type="text" id="edit-name-${p.id}" value="${p.name}"></div>
          <div class="form-group"><label>Description</label><input type="text" id="edit-desc-${p.id}" value="${p.description||''}"></div>
          <div class="form-group"><label>Policy JSON</label><textarea id="edit-json-${p.id}">${JSON.stringify(pj, null, 2)}</textarea></div>
          <div class="form-actions">
            <button class="btn primary" onclick="savePolicy('${p.id}')">Save Changes</button>
            <button class="btn" onclick="document.getElementById('edit-${p.id}').classList.add('hidden')">Cancel</button>
          </div>
        </div>
      </div>
    </div>`;
  }).join('');

  app.innerHTML = `
  <h1 class="page-title">Policy Manager</h1>
  <button class="btn primary" onclick="toggleCreatePolicy()" style="margin-bottom:20px">+ Create Policy</button>
  <div class="inline-form hidden" id="create-policy-form">
    <h3>New Policy Template</h3>
    <div class="form-group"><label>Name</label><input type="text" id="new-policy-name" placeholder="Policy name"></div>
    <div class="form-group"><label>Description</label><input type="text" id="new-policy-desc" placeholder="Brief description"></div>
    <div class="form-group"><label>Policy JSON</label>
      <textarea id="new-policy-json" placeholder='{"privacy_mode":"local_only","max_daily_spend_usd":10}'>${JSON.stringify({privacy_mode:"local_only",max_daily_spend_usd:10,allowed_agents:["file_agent","system_agent"],require_confirmation_destructive:true},null,2)}</textarea>
    </div>
    <div class="form-actions">
      <button class="btn primary" onclick="createPolicy()">Create</button>
      <button class="btn" onclick="toggleCreatePolicy()">Cancel</button>
    </div>
  </div>
  ${policyCards}`;
}

window.toggleCreatePolicy = () => {
  document.getElementById('create-policy-form').classList.toggle('hidden');
};
window.createPolicy = async () => {
  let pj;
  try { pj = JSON.parse($('#new-policy-json').value); } catch(e) { alert('Invalid JSON'); return; }
  await api('/api/v1/policies', {method:'POST', body:JSON.stringify({
    name: $('#new-policy-name').value, description: $('#new-policy-desc').value, policy_json: pj
  })});
  renderPolicies($('#app'));
};
window.editPolicy = (id) => {
  document.getElementById('edit-'+id).classList.toggle('hidden');
};
window.savePolicy = async (id) => {
  let pj;
  try { pj = JSON.parse(document.getElementById('edit-json-'+id).value); } catch(e) { alert('Invalid JSON'); return; }
  await api('/api/v1/policies/'+id, {method:'PUT', body:JSON.stringify({
    name: document.getElementById('edit-name-'+id).value,
    description: document.getElementById('edit-desc-'+id).value,
    policy_json: pj
  })});
  renderPolicies($('#app'));
};
window.deletePolicy = async (id, name) => {
  if(!confirm('Delete policy "'+name+'"?')) return;
  await api('/api/v1/policies/'+id, {method:'DELETE'});
  renderPolicies($('#app'));
};

// -- Devices --
async function renderDevices(app) {
  const hash = window.location.hash;
  const match = hash.match(/#devices\/(.+)/);
  if(match) return renderDeviceDetail(app, match[1]);

  const devices = await api('/api/v1/devices');
  const cards = devices.map(d => `
    <div class="card" style="cursor:pointer" onclick="window.location.hash='#devices/${d.id}'">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
        <h3 style="font-size:16px">${d.hostname}</h3>
        <span class="badge ${d.status}">${d.status==='online'?'&#9679; ':'&#9675; '}${d.status}</span>
      </div>
      <div style="display:grid;grid-template-columns:repeat(2,1fr);gap:8px;font-size:12px;color:var(--dim)">
        <div>OS: <span style="color:var(--text)">${d.os}</span></div>
        <div>Version: <span class="mono" style="color:var(--text)">${d.intentos_version}</span></div>
        <div>Privacy: <span class="mono" style="color:var(--text)">${d.privacy_mode}</span></div>
        <div>Heartbeat: <span style="color:var(--text)">${ago(d.last_heartbeat_at)}</span></div>
        <div>Cloud: <span style="color:${d.cloud_access?'var(--green)':'var(--dim)'}">
          ${d.cloud_access?'Enabled':'Disabled'}</span></div>
        <div>Compliant: ${d.policy_compliant?'<span class="check">&#10003;</span>':'<span class="cross">&#10007;</span>'}</div>
      </div>
    </div>`).join('');

  app.innerHTML = `<h1 class="page-title">Devices</h1><div class="grid3">${cards}</div>`;
}

async function renderDeviceDetail(app, deviceId) {
  const d = await api('/api/v1/devices/' + deviceId);
  if(!d || d.error) { app.innerHTML = '<p>Device not found</p>'; return; }
  const allKeys = await api('/api/v1/api-keys');
  const assignedKeyIds = (d.assigned_api_keys || '').split(',').filter(Boolean);

  const auditRows = (d.recent_audit || []).map(a => `<tr>
    <td style="font-size:12px;color:var(--dim)">${ago(a.created_at)}</td>
    <td>${a.action}</td><td>${a.agent}</td>
    <td>${a.cost_usd > 0 ? '$'+a.cost_usd.toFixed(4) : '-'}</td>
    <td style="font-size:12px;color:var(--dim)">${a.details||''}</td>
  </tr>`).join('');

  // Usage by model today
  const usageByModel = {};
  (d.usage_history||[]).forEach(u => {
    if(!usageByModel[u.model]) usageByModel[u.model] = 0;
    usageByModel[u.model] += u.total_calls;
  });
  const usageBars = Object.entries(usageByModel).map(([m,c]) =>
    `<div style="display:flex;align-items:center;gap:10px;margin-bottom:6px">
      <span class="mono" style="font-size:12px;width:160px;color:var(--dim)">${m}</span>
      <div style="flex:1;height:8px;background:rgba(255,255,255,0.06);border-radius:4px;overflow:hidden">
        <div style="height:100%;width:${Math.min(100,c/5)}%;background:linear-gradient(90deg,var(--cyan),var(--blue));border-radius:4px"></div>
      </div>
      <span class="mono" style="font-size:12px;width:50px;text-align:right">${c}</span>
    </div>`).join('');

  const keyCheckboxes = allKeys.map(k =>
    `<label style="display:flex;align-items:center;gap:8px;margin-bottom:6px;font-size:13px;cursor:pointer">
      <input type="checkbox" value="${k.id}" ${assignedKeyIds.includes(k.id)?'checked':''} onchange="updateDeviceKeys('${deviceId}')">
      ${k.name} <span class="badge ${k.provider}">${k.provider}</span> <span class="mono" style="font-size:11px;color:var(--dim)">${k.key_masked}</span>
    </label>`).join('');

  app.innerHTML = `
  <div class="detail-back" onclick="window.location.hash='#devices'">&larr; Back to Devices</div>
  <h1 class="page-title">${d.hostname}</h1>
  <div class="device-detail">
    <div class="card device-info-card">
      <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:16px;font-size:13px">
        <div><div class="label">Status</div><span class="badge ${d.status}">${d.status}</span></div>
        <div><div class="label">OS</div>${d.os}</div>
        <div><div class="label">Version</div><span class="mono">${d.intentos_version}</span></div>
        <div><div class="label">Privacy Mode</div><span class="mono">${d.privacy_mode}</span></div>
        <div><div class="label">Last Heartbeat</div>${ago(d.last_heartbeat_at)}</div>
        <div><div class="label">Compliant</div>${d.policy_compliant?'<span class="check">&#10003; Yes</span>':'<span class="cross">&#10007; No</span>'}</div>
        <div><div class="label">Cloud Access</div>
          <label class="toggle"><input type="checkbox" ${d.cloud_access?'checked':''} onchange="toggleCloudAccess('${deviceId}',this.checked)">
          <span class="slider"></span></label>
        </div>
        <div><div class="label">Created</div>${ago(d.created_at)}</div>
      </div>
    </div>

    <div class="card">
      <div class="label" style="margin-bottom:12px">Assigned API Keys</div>
      <div id="key-checkboxes">${keyCheckboxes || '<span style="color:var(--dim);font-size:13px">No API keys available</span>'}</div>
    </div>

    <div class="card">
      <div class="label" style="margin-bottom:12px">Usage by Model</div>
      ${usageBars || '<span style="color:var(--dim);font-size:13px">No usage data</span>'}
    </div>

    <div class="card" style="grid-column:1/-1">
      <div class="label" style="margin-bottom:12px">Recent Activity</div>
      ${(d.recent_audit||[]).length ? `<table><thead><tr><th>Time</th><th>Action</th><th>Agent</th><th>Cost</th><th>Details</th></tr></thead>
      <tbody>${auditRows}</tbody></table>` : '<span style="color:var(--dim);font-size:13px">No recent activity</span>'}
    </div>
  </div>`;
}

window.toggleCloudAccess = async (deviceId, enabled) => {
  await api('/api/v1/devices/'+deviceId+'/cloud-access', {method:'PUT', body:JSON.stringify({enabled})});
};
window.updateDeviceKeys = async (deviceId) => {
  const checked = [...document.querySelectorAll('#key-checkboxes input[type=checkbox]:checked')].map(c=>c.value);
  await api('/api/v1/devices/'+deviceId+'/api-keys', {method:'PUT', body:JSON.stringify({key_ids:checked})});
};

// -- Audit Log --
let auditPage = 0;
async function renderAudit(app) {
  const devices = await api('/api/v1/devices');
  const limit = 20;
  const offset = auditPage * limit;

  // Get filters from existing DOM or defaults
  let filterDevice = '', filterAgent = '';
  const existingDev = document.getElementById('audit-filter-device');
  const existingAgent = document.getElementById('audit-filter-agent');
  if(existingDev) filterDevice = existingDev.value;
  if(existingAgent) filterAgent = existingAgent.value;

  let qs = `?limit=${limit}&offset=${offset}`;
  if(filterDevice) qs += `&device_id=${filterDevice}`;
  if(filterAgent) qs += `&agent=${filterAgent}`;

  const data = await api('/api/v1/audit-log' + qs);
  const agents = [...new Set(data.entries.map(e=>e.agent).filter(Boolean))];

  const rows = data.entries.map(e => {
    let actionClass = '';
    if(e.action.startsWith('file.')) actionClass = 'color:var(--cyan)';
    else if(e.action.startsWith('document.')) actionClass = 'color:var(--purple)';
    else if(e.action.startsWith('system.')) actionClass = 'color:var(--green)';
    return `<tr>
      <td style="font-size:12px;color:var(--dim);white-space:nowrap">${ago(e.created_at)}</td>
      <td>${e.device_hostname || 'unknown'}</td>
      <td><span class="mono" style="${actionClass};font-size:12px">${e.action}</span></td>
      <td>${e.agent}</td>
      <td>${e.cost_usd > 0 ? '$'+e.cost_usd.toFixed(4) : '-'}</td>
      <td style="font-size:12px;color:var(--dim);max-width:250px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${e.details||''}</td>
    </tr>`;
  }).join('');

  const totalPages = Math.ceil(data.total / limit);
  const pageInfo = `Showing ${offset+1}-${Math.min(offset+limit, data.total)} of ${data.total}`;

  app.innerHTML = `
  <h1 class="page-title">Audit Log</h1>
  <div class="filter-bar">
    <select id="audit-filter-device" onchange="auditPage=0;renderAudit($('#app'))">
      <option value="">All Devices</option>
      ${devices.map(d=>`<option value="${d.id}" ${filterDevice===d.id?'selected':''}>${d.hostname}</option>`).join('')}
    </select>
    <select id="audit-filter-agent" onchange="auditPage=0;renderAudit($('#app'))">
      <option value="">All Agents</option>
      <option value="file_agent" ${filterAgent==='file_agent'?'selected':''}>file_agent</option>
      <option value="document_agent" ${filterAgent==='document_agent'?'selected':''}>document_agent</option>
      <option value="system_agent" ${filterAgent==='system_agent'?'selected':''}>system_agent</option>
    </select>
  </div>
  <table><thead><tr><th>Time</th><th>Device</th><th>Action</th><th>Agent</th><th>Cost</th><th>Details</th></tr></thead>
  <tbody>${rows}</tbody></table>
  <div class="pagination">
    <button class="btn sm" ${auditPage===0?'disabled':''} onclick="auditPage--;renderAudit($('#app'))">&#8592; Prev</button>
    <span class="info">${pageInfo}</span>
    <button class="btn sm" ${auditPage>=totalPages-1?'disabled':''} onclick="auditPage++;renderAudit($('#app'))">Next &#8594;</button>
  </div>`;
}

// -- API Keys --
async function renderApiKeys(app) {
  const keys = await api('/api/v1/api-keys');
  const devices = await api('/api/v1/devices');

  const keyCards = keys.map(k => {
    const assignedIds = (k.assigned_devices||'').split(',').filter(Boolean);
    const assignedNames = assignedIds.map(id => {
      const d = devices.find(dev => dev.id === id);
      return d ? d.hostname : id.slice(0,8);
    });
    const devCheckboxes = devices.map(d =>
      `<label style="display:flex;align-items:center;gap:6px;font-size:12px;cursor:pointer">
        <input type="checkbox" value="${d.id}" ${assignedIds.includes(d.id)?'checked':''}
          onchange="assignKeyToDevices('${k.id}')"> ${d.hostname}
      </label>`).join('');

    return `<div class="card" style="margin-bottom:16px">
      <div style="display:flex;justify-content:space-between;align-items:start">
        <div>
          <h3 style="font-size:16px;margin-bottom:4px">${k.name}</h3>
          <div style="display:flex;gap:10px;align-items:center;font-size:13px">
            <span class="badge ${k.provider}">${k.provider}</span>
            <span class="mono" style="font-size:12px;color:var(--dim)">${k.key_masked}</span>
          </div>
        </div>
        <div style="display:flex;gap:6px">
          <button class="btn sm" onclick="rotateKey('${k.id}')">&#8635; Rotate</button>
          <button class="btn sm danger" onclick="deleteKey('${k.id}','${k.name}')">Delete</button>
        </div>
      </div>
      <div style="margin-top:12px;display:grid;grid-template-columns:1fr 1fr;gap:12px;font-size:12px;color:var(--dim)">
        <div>Assigned: <span style="color:var(--text)">${assignedNames.length ? assignedNames.join(', ') : 'None'}</span></div>
        <div>Last Rotated: <span style="color:var(--text)">${ago(k.last_rotated)}</span></div>
      </div>
      <details style="margin-top:10px">
        <summary style="font-size:12px;color:var(--blue);cursor:pointer">Assign to Devices</summary>
        <div style="margin-top:8px;display:flex;gap:16px" id="key-assign-${k.id}">${devCheckboxes}</div>
      </details>
    </div>`;
  }).join('');

  app.innerHTML = `
  <h1 class="page-title">API Key Vault</h1>
  <button class="btn primary" onclick="toggleCreateKey()" style="margin-bottom:20px">+ Add API Key</button>
  <div class="inline-form hidden" id="create-key-form">
    <h3>Add New API Key</h3>
    <div class="form-group"><label>Name</label><input type="text" id="new-key-name" placeholder="e.g. Production Anthropic"></div>
    <div class="form-group"><label>Provider</label>
      <select id="new-key-provider"><option value="anthropic">Anthropic</option><option value="openai">OpenAI</option><option value="google">Google</option></select>
    </div>
    <div class="form-group"><label>API Key</label><input type="password" id="new-key-value" placeholder="sk-..."></div>
    <div class="form-actions">
      <button class="btn primary" onclick="createKey()">Add Key</button>
      <button class="btn" onclick="toggleCreateKey()">Cancel</button>
    </div>
  </div>
  ${keyCards}`;
}

window.toggleCreateKey = () => {
  document.getElementById('create-key-form').classList.toggle('hidden');
};
window.createKey = async () => {
  await api('/api/v1/api-keys', {method:'POST', body:JSON.stringify({
    name: $('#new-key-name').value,
    provider: $('#new-key-provider').value,
    key_value: $('#new-key-value').value
  })});
  renderApiKeys($('#app'));
};
window.rotateKey = async (id) => {
  if(!confirm('Rotate this API key? The old key will be invalidated.')) return;
  await api('/api/v1/api-keys/'+id+'/rotate', {method:'POST'});
  renderApiKeys($('#app'));
};
window.deleteKey = async (id, name) => {
  if(!confirm('Delete API key "'+name+'"?')) return;
  await api('/api/v1/api-keys/'+id, {method:'DELETE'});
  renderApiKeys($('#app'));
};
window.assignKeyToDevices = async (keyId) => {
  const checked = [...document.querySelectorAll('#key-assign-'+keyId+' input[type=checkbox]:checked')].map(c=>c.value);
  // Update each device's assigned keys -- simplified: update the api_key's assigned_devices
  await api('/api/v1/api-keys/'+keyId+'/assign', {method:'PUT', body:JSON.stringify({device_ids:checked})});
  renderApiKeys($('#app'));
};

// -- Licenses Page --
async function renderLicenses(app) {
  const licenses = await api('/api/v1/licenses');
  const current = licenses[0] || {};
  const maskedKey = current.license_key ? current.license_key.replace(/(.{10})(.*)(.{4})/, '$1-****-$3') : 'N/A';
  const usedPct = current.max_seats ? Math.round((current.used_seats / current.max_seats) * 100) : 0;
  const barW = 400;
  const usedW = Math.round(barW * usedPct / 100);

  const historyRows = licenses.map(l => `<tr>
    <td>${l.activated_at ? new Date(l.activated_at).toLocaleDateString() : 'N/A'}</td>
    <td><span class="mono" style="font-size:12px">${l.license_key}</span></td>
    <td>${l.tier}</td>
    <td>${l.max_seats} seats</td>
    <td><span class="badge ${l.status==='active'?'online':'offline'}">${l.status}</span></td>
  </tr>`).join('');

  app.innerHTML = `
  <h1 class="page-title">License Management</h1>

  <div class="card" style="margin-bottom:24px">
    <h3 style="font-size:16px;margin-bottom:16px">Current License</h3>
    <div style="display:grid;grid-template-columns:repeat(2,1fr);gap:16px;font-size:14px">
      <div><span style="color:var(--dim)">License Key:</span> <span class="mono">${maskedKey}</span></div>
      <div><span style="color:var(--dim)">Tier:</span> <span style="text-transform:capitalize">${current.tier||'N/A'}</span></div>
      <div><span style="color:var(--dim)">Seats:</span> ${current.used_seats||0} / ${current.max_seats||0} used</div>
      <div><span style="color:var(--dim)">Expires:</span> ${current.expires_at ? new Date(current.expires_at).toLocaleDateString() : 'N/A'}</div>
      <div><span style="color:var(--dim)">Status:</span> <span class="badge ${current.status==='active'?'online':'offline'}">${current.status||'N/A'}</span></div>
    </div>
  </div>

  <div class="card" style="margin-bottom:24px">
    <h3 style="font-size:16px;margin-bottom:16px">Seat Usage</h3>
    <svg width="${barW+80}" height="60" viewBox="0 0 ${barW+80} 60">
      <rect x="0" y="10" width="${barW}" height="30" rx="6" fill="rgba(255,255,255,0.06)"/>
      <rect x="0" y="10" width="${usedW}" height="30" rx="6" fill="url(#seatGrad)"/>
      <defs><linearGradient id="seatGrad" x1="0" y1="0" x2="1" y2="0">
        <stop offset="0%" stop-color="#06b6d4"/><stop offset="100%" stop-color="#2563eb"/></linearGradient></defs>
      <text x="${barW+10}" y="30" fill="#e2e8f0" font-family="JetBrains Mono" font-size="13">${usedPct}%</text>
      <text x="10" y="30" fill="#fff" font-family="JetBrains Mono" font-size="11">${current.used_seats||0} used</text>
    </svg>
  </div>

  <div class="inline-form" style="margin-bottom:24px">
    <h3>Activate License</h3>
    <div style="display:flex;gap:12px;align-items:end;margin-top:12px">
      <div class="form-group" style="flex:1;margin-bottom:0">
        <label>License Key</label>
        <input type="text" id="license-key-input" placeholder="INTENT-ENT-2026-XXXXXXXX">
      </div>
      <button class="btn primary" onclick="activateLicense()">Activate</button>
    </div>
    <div id="license-error" style="display:none;margin-top:8px;font-size:13px;color:var(--red)"></div>
  </div>

  <section>
    <h2>License History</h2>
    <table><thead><tr><th>Activated</th><th>License Key</th><th>Tier</th><th>Seats</th><th>Status</th></tr></thead>
    <tbody>${historyRows || '<tr><td colspan="5" style="text-align:center;color:var(--dim)">No license history</td></tr>'}</tbody></table>
  </section>`;
}

window.activateLicense = async () => {
  const key = document.getElementById('license-key-input').value.trim();
  const errEl = document.getElementById('license-error');
  errEl.style.display = 'none';
  const result = await api('/api/v1/licenses/activate', {method:'POST', body:JSON.stringify({license_key:key})});
  if(result.error) {
    errEl.textContent = result.error;
    errEl.style.display = 'block';
  } else {
    showToast('License activated');
    renderLicenses($('#app'));
  }
};

// -- Init --
if(localStorage.getItem('intentos_token')) {
  showApp();
} else {
  showLogin();
}
</script>
</body></html>"""

# ---------------------------------------------------------------------------
# HTTP Handler
# ---------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Device-Token, Authorization")

    def _json(self, code: int, data):
        body = json.dumps(data, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self._cors()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _html(self, html: str):
        body = html.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self._cors()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        return json.loads(self.rfile.read(length))

    def _path_parts(self) -> list:
        """Return URL path segments, stripping trailing slashes."""
        return urlparse(self.path).path.rstrip("/").split("/")

    def _query_params(self) -> dict:
        return parse_qs(urlparse(self.path).query)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def _check_auth(self, path: str, conn: sqlite3.Connection) -> bool:
        """Check auth for API routes. Returns True if authorized (or no auth needed)."""
        if not path.startswith("/api/v1/"):
            return True
        # Exempt endpoints
        if path == "/api/v1/auth/login" or path == "/api/v1/telemetry/heartbeat":
            return True
        hdrs = {k.lower(): v for k, v in self.headers.items()}
        user = verify_token(hdrs, conn)
        if not user:
            self._json(401, {"error": "Unauthorized — valid Bearer token required"})
            return False
        return True

    def do_GET(self):
        path = urlparse(self.path).path.rstrip("/")
        parts = self._path_parts()
        params = self._query_params()
        conn = get_db()
        try:
            if path == "" or path == "/":
                return self._html(DASHBOARD_HTML)
            if not self._check_auth(path, conn):
                return
            if path == "/api/v1/auth/me":
                hdrs = {k.lower(): v for k, v in self.headers.items()}
                user = verify_token(hdrs, conn)
                if not user:
                    return self._json(401, {"error": "Unauthorized"})
                return self._json(200, user)
            if path == "/api/v1/licenses":
                return self._json(200, api_licenses_list(conn))
            if path == "/api/v1/dashboard/fleet-overview":
                return self._json(200, api_fleet_overview(conn))
            if path == "/api/v1/dashboard/ai-usage":
                return self._json(200, api_ai_usage(conn))
            if path == "/api/v1/dashboard/cost-trend":
                return self._json(200, api_cost_trend(conn))
            if path == "/api/v1/dashboard/compliance":
                return self._json(200, api_compliance(conn))
            if path == "/api/v1/policies":
                return self._json(200, api_policies_list(conn))
            if path == "/api/v1/devices":
                return self._json(200, api_devices_list(conn))
            # GET /api/v1/devices/{id}
            if len(parts) == 5 and parts[1] == "api" and parts[3] == "devices":
                result = api_device_detail(parts[4], conn)
                if result is None:
                    return self._json(404, {"error": "device not found"})
                return self._json(200, result)
            if path == "/api/v1/audit-log":
                return self._json(200, api_audit_log(params, conn))
            if path == "/api/v1/api-keys":
                return self._json(200, api_keys_list(conn))
            if path == "/api/v1/connectors":
                return self._json(200, api_connectors_list(conn))
            self._json(404, {"error": "not found"})
        finally:
            conn.close()

    def do_POST(self):
        path = urlparse(self.path).path.rstrip("/")
        parts = self._path_parts()
        conn = get_db()
        try:
            body = self._read_body()
            hdrs = {k.lower(): v for k, v in self.headers.items()}
            if path == "/api/v1/auth/login":
                result = api_auth_login(body, conn)
                if result is None:
                    return self._json(401, {"error": "Invalid username or password"})
                return self._json(200, result)
            if not self._check_auth(path, conn):
                return
            if path == "/api/v1/telemetry/heartbeat":
                result = api_heartbeat(body, hdrs, conn)
                if result.get("status") == "error":
                    return self._json(403, result)
                return self._json(200, result)
            if path == "/api/v1/licenses/activate":
                result = api_licenses_activate(body, conn)
                if result.get("error"):
                    return self._json(400, result)
                return self._json(200, result)
            if path == "/api/v1/policies":
                return self._json(201, api_policies_create(body, conn))
            if path == "/api/v1/api-keys":
                return self._json(201, api_keys_create(body, conn))
            # POST /api/v1/api-keys/{id}/rotate
            if len(parts) == 6 and parts[3] == "api-keys" and parts[5] == "rotate":
                result = api_keys_rotate(parts[4], conn)
                if result is None:
                    return self._json(404, {"error": "api key not found"})
                return self._json(200, result)
            # POST /api/v1/connectors/{id}/test
            if len(parts) == 6 and parts[3] == "connectors" and parts[5] == "test":
                result = api_connectors_test(parts[4], conn)
                if result is None:
                    return self._json(404, {"error": "connector not found"})
                return self._json(200, result)
            self._json(404, {"error": "not found"})
        finally:
            conn.close()

    def do_PUT(self):
        path = urlparse(self.path).path.rstrip("/")
        parts = self._path_parts()
        conn = get_db()
        try:
            if not self._check_auth(path, conn):
                return
            body = self._read_body()
            # PUT /api/v1/policies/{id}
            if len(parts) == 5 and parts[3] == "policies":
                result = api_policies_update(parts[4], body, conn)
                if result is None:
                    return self._json(404, {"error": "policy not found"})
                return self._json(200, result)
            # PUT /api/v1/devices/{id}/cloud-access
            if len(parts) == 6 and parts[3] == "devices" and parts[5] == "cloud-access":
                result = api_device_cloud_access(parts[4], body, conn)
                if result is None:
                    return self._json(404, {"error": "device not found"})
                return self._json(200, result)
            # PUT /api/v1/devices/{id}/api-keys
            if len(parts) == 6 and parts[3] == "devices" and parts[5] == "api-keys":
                result = api_device_api_keys(parts[4], body, conn)
                if result is None:
                    return self._json(404, {"error": "device not found"})
                return self._json(200, result)
            # PUT /api/v1/api-keys/{id}/assign
            if len(parts) == 6 and parts[3] == "api-keys" and parts[5] == "assign":
                key_id = parts[4]
                device_ids = body.get("device_ids", [])
                existing = conn.execute("SELECT id FROM api_keys WHERE id=?", (key_id,)).fetchone()
                if not existing:
                    return self._json(404, {"error": "api key not found"})
                conn.execute("UPDATE api_keys SET assigned_devices=? WHERE id=?",
                             (",".join(device_ids), key_id))
                conn.commit()
                return self._json(200, {"id": key_id, "assigned_devices": device_ids})
            # PUT /api/v1/connectors/{id}
            if len(parts) == 5 and parts[3] == "connectors":
                result = api_connectors_update(parts[4], body, conn)
                if result is None:
                    return self._json(404, {"error": "connector not found"})
                return self._json(200, result)
            self._json(404, {"error": "not found"})
        finally:
            conn.close()

    def do_DELETE(self):
        path = urlparse(self.path).path.rstrip("/")
        parts = self._path_parts()
        conn = get_db()
        try:
            if not self._check_auth(path, conn):
                return
            # DELETE /api/v1/policies/{id}
            if len(parts) == 5 and parts[3] == "policies":
                result = api_policies_delete(parts[4], conn)
                if result is None:
                    return self._json(404, {"error": "policy not found"})
                return self._json(200, result)
            # DELETE /api/v1/api-keys/{id}
            if len(parts) == 5 and parts[3] == "api-keys":
                result = api_keys_delete(parts[4], conn)
                if result is None:
                    return self._json(404, {"error": "api key not found"})
                return self._json(200, result)
            self._json(404, {"error": "not found"})
        finally:
            conn.close()

    def log_message(self, format, *args):
        pass  # Silence default request logging


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    conn = get_db()
    init_db(conn)
    seed_data(conn)
    conn.close()

    port = int(os.environ.get("PORT", 8000))
    server = HTTPServer(("0.0.0.0", port), Handler)
    print(f"""
\033[1mIntentOS Console (Demo)\033[0m
=======================
Dashboard: http://localhost:{port}
API:       http://localhost:{port}/api/v1/

Database:  {DB_PATH}
Press Ctrl+C to stop.
""")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.server_close()


if __name__ == "__main__":
    main()

# IntentOS — CLAUDE.md
### Beast Mode Configuration

---

## Identity

**IntentOS** is an AI-powered execution layer where language is the interface. It routes natural language intent to specialized agents that execute tasks on the user's local machine — with files never leaving the device.

**This is not a chatbot. This is not a wrapper. This is an operating system substrate.**

We are building a **security-first, privacy-first, local-first AI execution platform** sold B2B on per-user licenses, with a free consumer tier as top-of-funnel.

---

## The Business

### Three-Tier Go-to-Market

| Tier | Buyer | Inference | Deployment | Price |
|------|-------|-----------|------------|-------|
| **Consumer** | Individual users | Local models (Ollama) | Self-install | Free / freemium |
| **SMB** | Small businesses | Local + cloud API (smart routing) | Self-serve + onboarding | Per-user/month |
| **Enterprise** | Large orgs (C-Suite focus) | On-prem data center (open-source models) | IT-managed fleet deployment | Per-user/month + deployment |

**The pitch:**
- **Enterprise:** "Your executives' devices are your biggest attack surface. IntentOS runs AI locally — files never leave the perimeter. Run models you own, in data centers you control. Per-user license, deployed by IT in one command."
- **SMB:** "Enterprise-grade AI security at SMB prices. Cloud APIs only when your local model can't handle it. You control the spend."
- **Consumer:** "Your AI assistant that respects your privacy. Works offline. Runs on your hardware. Free."

**One codebase. Three deployment wrappers. Same security promise at every tier.**

---

## Repository Structure

```
intentos/
├── CLAUDE.md                    ← YOU ARE HERE
├── core/
│   └── kernel.py                ← Intent Kernel (parse → plan → route)
├── capabilities/
│   ├── file_agent/              ← File system operations
│   ├── browser_agent/           ← Web search + page fetching
│   ├── document_agent/          ← Document creation/manipulation
│   ├── system_agent/            ← System information
│   ├── ARCHITECTURE.md          ← System design (9 layers)
│   ├── SECURITY.md              ← Two-user daemon security model
│   ├── RAG_SYSTEM.md            ← Semantic memory design
│   └── FIRST_LAUNCH.md          ← First-run UX flow
├── docs/
│   ├── SPEC.md                  ← Capability specification (ACP contract)
│   ├── VISION.md                ← Product vision
│   ├── file_agent.md            ← File agent spec
│   ├── featurespec.md           ← Complete feature specification
│   └── implementation.md        ← Technical implementation roadmap
├── tests/
│   └── test_phase2.py           ← Integration tests
├── requirements.txt
├── setup.sh
└── .env.example
```

---

## Core Architecture

### The ACP Contract (Agent Communication Protocol)

Every agent implements ONE function:

```python
def run(input: dict) -> dict:
    # input = {"action": str, "params": dict, "context": dict}
    # returns {"status": str, "result": any, "metadata": dict, ...}
```

**Status values:** `"success"` | `"error"` | `"confirmation_required"`

**Context (injected by scheduler):**
```python
context = {
    "user": str,
    "workspace": "~/.intentos/workspace",
    "granted_paths": list[str],
    "task_id": str,
    "dry_run": bool,
    "llm_client": object  # optional
}
```

### The Five Rules (Non-Negotiable)

1. **Never exceed granted paths.** Check `context["granted_paths"]` before every file operation. No exceptions.
2. **All writes go to workspace by default.** `context["workspace"] + "/outputs/"` unless modifying in-place.
3. **Destructive actions require confirmation.** Return `"confirmation_required"` status. Never auto-delete.
4. **Respect dry_run.** If `context["dry_run"]` is True, describe what would happen. Never execute.
5. **Never surface raw errors.** Translate all exceptions to plain language. No stack traces reach the user.

### Intent Flow

```
User speaks → Intent Kernel → Inference Router → LLM parses intent
    → Subtask decomposition → Agent Scheduler → Agents execute
    → Results returned → Plain language response
```

### Subtask References

Subtasks can reference previous results: `"{{1.result}}"` in params, resolved at runtime.

---

## Technical Inspirations (Encoded)

### From IronClaw — Security (Priority 1)

We adopt IronClaw's defense-in-depth model:

- **AES-256-GCM encryption** for all stored credentials with HKDF-SHA256 key derivation
- **OS keychain integration** — macOS Keychain, GNOME Keyring, Windows Credential Manager. No `.env` files in production.
- **Per-job isolation tokens** — cryptographically random, in-memory only, constant-time comparison
- **Leak detection pipeline** — scan ALL agent output for secrets (API keys, PEM files, Bearer tokens) before it reaches the LLM. Actions: Block (critical), Redact (high), Warn (medium).
- **Prompt injection defense** — content wrapping with zero-width space insertion, external content framing, three-stage output sanitization
- **Three-tier sandbox policies:**

| Policy | Filesystem | Network | Use Case |
|--------|-----------|---------|----------|
| ReadOnly | /workspace read-only | Proxied (allowlist) | Analysis agents |
| WorkspaceWrite | /workspace read/write | Proxied (allowlist) | Most agents |
| FullAccess | Full host access | Unrestricted | System agent (double opt-in) |

- **Network proxy with domain allowlisting** — credentials injected at proxy boundary, never in agent code
- **Credential injection architecture** — agents get results, never keys

### From MetaGPT — Agent Orchestration (Priority 2)

We adopt MetaGPT's SOP-driven multi-agent coordination:

- **Publish-subscribe message bus** — agents subscribe to action types via `cause_by` / `_watch` pattern. Decoupled, extensible.
- **Typed structured handoffs** — every agent-to-agent handoff produces a validated Pydantic model, not raw dicts.
- **React modes per task:**
  - `BY_ORDER` — sequential execution (simple tasks: rename, list, move)
  - `PLAN_AND_ACT` — create plan first, then execute (complex multi-agent tasks)
  - `REACT` — LLM dynamically selects next action (exploratory tasks)
- **Quality gates** — validation step before any agent output is passed downstream. LGTM/LBTM pattern.
- **Cost governance** — track token usage per task/user/org. Enforce spending limits. `CostManager` pattern.
- **State serialization** — serialize full execution state for recovery of interrupted tasks.
- **Experience retriever** — learn from past task executions to improve future routing.

### From Project NOMAD — Offline Deployment (Priority 3)

We adopt NOMAD's survival-kit deployment model:

- **One-command deployment** — single script installs Docker, detects GPU, pulls containers, configures everything
- **Hardware auto-detection** — GPU (NVIDIA/AMD), RAM, CPU → auto-select optimal local model
- **Tiered content collections** — Essential / Standard / Comprehensive bundles per industry vertical
- **Self-updating sidecar** — push updates through management layer without SSH
- **Docker-outside-of-Docker (DooD)** — Command Center orchestrates containerized services
- **Adaptive RAG context** — adjust retrieval depth based on model size (1-3B: 2 results, 4-8B: 4 results, 13B+: uncapped)
- **Offline knowledge bundles** — for underdeveloped markets with scarce internet. Curated AI + reference content in one deployable package.

---

## Development Workflow

### Mandatory Process (Superpowers-Enforced)

Every feature follows this chain. No shortcuts.

```
1. BRAINSTORM    → Socratic design session. One question at a time.
                   No implementation until design is approved.
                   Specs saved to docs/specs/

2. PLAN          → Bite-sized tasks (2-5 min each).
                   Every task has: exact file paths, code, test commands,
                   expected output. Plans saved to docs/plans/

3. EXECUTE       → Subagent per task. Fresh context per execution.
                   Two-stage review after each task:
                   Stage 1: Spec compliance
                   Stage 2: Code quality

4. VERIFY        → Run actual commands. Read actual output.
                   No completion claims without fresh verification evidence.

5. REVIEW        → Code review with categorized feedback:
                   Critical / Important / Minor
```

### Test-Driven Development (The Iron Law)

**NO PRODUCTION CODE WITHOUT A FAILING TEST FIRST.**

```
RED    → Write a test that fails (proves the gap exists)
GREEN  → Write minimum code to pass the test
REFACTOR → Clean up without changing behavior
```

- Every declared action has a happy-path test
- Every action has a dry_run test
- Every destructive action has a confirmation test
- All tests use sandboxed directories (`tmp_path` / `tempfile.mkdtemp()`)
- No test touches real user filesystem
- Test sensitive file detection (`.env`, `*.pem`, `credentials.*`)

### Systematic Debugging (No Random Fixes)

```
Phase 1: Root Cause Investigation (trace backward through call chain)
Phase 2: Pattern Analysis (is this a class of bug or isolated?)
Phase 3: Hypothesis Testing (form theory, test it, prove it)
Phase 4: Implementation (fix the root cause, not the symptom)
```

**If 3+ fixes fail, question the architecture.** Do not keep patching.

### Git Workflow

- Feature development in **git worktrees** (isolated branches)
- Commits are atomic and descriptive
- PRs follow: `capability: add your_agent` or `core: description`
- Never force push. Never skip hooks. Never commit secrets.

---

## Agent Development Rules

### Creating a New Agent

```
capabilities/your_agent/
├── agent.py           ← run(input: dict) -> dict
├── manifest.json      ← identity, permissions, actions
├── schemas.py         ← Pydantic models for typed handoffs
├── primitives.py      ← low-level operations
├── planner.py         ← LLM-based task decomposition (if needed)
├── audit.py           ← audit logging
├── tests/
│   └── test_agent.py  ← pytest suite
└── __init__.py
```

### Manifest Schema

```json
{
  "name": "your_agent",
  "version": "0.1.0",
  "description": "One sentence — what this agent does",
  "category": "files | browser | image | media | system | document | utility",
  "permissions": ["filesystem.read"],
  "optional_permissions": [],
  "actions": ["action_one", "action_two"],
  "sandbox_policy": "ReadOnly | WorkspaceWrite | FullAccess",
  "platforms": ["linux", "macos", "windows"]
}
```

### Permission Reference

| Permission | What It Allows |
|---|---|
| `filesystem.read` | Read file contents and metadata |
| `filesystem.write` | Create and modify files (workspace only by default) |
| `filesystem.move` | Move and rename files |
| `filesystem.delete` | Delete files (always triggers confirmation) |
| `network` | Make HTTP/S requests (proxied, allowlisted domains) |
| `system.processes` | List and manage processes |
| `system.hardware` | Read hardware info |
| `display` | Render output to screen |

**Golden rule:** If you can do it without a permission, don't declare it.

### Error Handling

```python
# WRONG — raw error
except FileNotFoundError as e:
    return {"status": "error", "error": {"message": str(e)}}

# RIGHT — plain language
except FileNotFoundError:
    return {"status": "error", "error": {
        "code": "FILE_NOT_FOUND",
        "message": "I couldn't find that file — it may have been moved or deleted"
    }}
```

### Sensitive File Protection

Block operations on files matching these patterns:
`.env`, `*.pem`, `*.key`, `*.p12`, `*.pfx`, `credentials.*`, `*secret*`, `*password*`, `*token*`, `id_rsa`, `id_ed25519`, `*.keystore`

Warn the user. Never proceed silently.

---

## Security Principles (Enterprise-Grade)

### The Two-User Daemon Model

```
HUMAN USER (john)              → owns files, controls permissions
    │ grants specific paths
    ▼
INTENTOS DAEMON (_intentos)    → executes agents, zero default access
    │ OS-level ACLs enforce boundaries
    ▼
HOST FILESYSTEM                → only granted paths accessible
```

- Daemon has `NoNewPrivileges` (Linux), no interactive login
- Platform-specific: `setfacl` (Linux), `chmod +a` (macOS), Windows ACLs
- `~/.intentos/grants.json` is the source of truth for path access

### Data That Never Leaves the Device

| Data | Local Only | Always |
|------|-----------|--------|
| File contents | ✓ | Even in cloud inference mode |
| File paths | ✓ | Full paths never transmitted |
| RAG index | ✓ | Embeddings stored locally |
| Task history | ✓ | Complete log local only |
| User profile | ✓ | Preferences never transmitted |
| API keys | ✓ | Used only for authorized calls |
| Audit log | ✓ | Append-only, never transmitted |

### Audit Logging

Every agent action logged to `~/.intentos/logs/audit.jsonl`:

```json
{
  "timestamp": "ISO8601",
  "task_id": "uuid",
  "agent": "file_agent",
  "action": "move_file",
  "paths_accessed": [],
  "result": "success",
  "initiated_by": "john",
  "duration_ms": 150
}
```

---

## Inference Router

The decision engine between local and cloud:

```
Task arrives → Complexity Score → Route

Score factors: token count, task type, ambiguity, context depth, agent count

LOW/MED  → Local SLM (instant, private, free)
HIGH     → Cloud API (opt-in, powerful, costs tokens)
```

### Privacy Modes (User-Controlled)

| Mode | Behavior |
|------|----------|
| **Local Only** | All tasks on local SLM. No data leaves machine. |
| **Smart Routing** | Simple → local, Complex → cloud (ask before sending) |
| **Performance** | Always cloud. Fastest and most capable. |

### Model Selection by Hardware

| RAM | GPU | Recommended Model |
|-----|-----|-------------------|
| 4GB | None | Phi-3 Mini (3.8B) |
| 8GB | None | Mistral 7B (4-bit) |
| 16GB | Any | Llama 3.1 8B |
| 32GB+ | NVIDIA | Llama 3.1 70B (4-bit) |
| Enterprise | Cluster | Llama 3.1 405B / Mixtral |

### Cost Governance

- Track tokens per task, per user, per org
- Enforce spending limits per tier
- Route simple tasks locally to minimize API spend
- Surface cost transparency: user sees what each task costs

---

## RAG System (Semantic Memory)

### Three Indexes

| Index | Purpose | Technology |
|-------|---------|------------|
| **File Index** | Semantic understanding of filesystem | ChromaDB + nomic-embed-text |
| **Task Index** | History of completed tasks | ChromaDB + embeddings |
| **User Profile** | Inferred preferences | Structured JSON |

### Context Assembler

On every task, queries all three indexes and injects relevant context into the Intent Kernel prompt:

```
User: "find the invoice from Ahmed"
    → File Index: top 3 matching files with paths
    → Task Index: last 2 similar tasks
    → User Profile: frequent_folders.invoices, contacts.Ahmed
    → Assembled context prepended to kernel prompt
    → Intent resolved with high confidence, no clarifying question
```

### Retrieval Strategy (Claude-Mem Inspired)

Three-layer progressive disclosure for token efficiency:
1. **Search** — compact index with IDs and metadata (~50-100 tokens/result)
2. **Timeline** — chronological context around an anchor point
3. **Get** — full details only for selected results (~500-1000 tokens each)

**~10x token savings** vs fetching everything.

### Granular Vector Indexing

Split documents into field-level chunks for precision:
- Separate embeddings for narrative, facts, metadata
- Session summaries split into: request, investigated, learned, completed, next_steps
- Enables field-level semantic search, not just whole-record matching

---

## Technology Decisions

### Current Stack (Phase 1 — Python Prototype)

| Component | Technology |
|-----------|-----------|
| Language | Python 3.9+ |
| LLM API | Anthropic Claude |
| Web search | DuckDuckGo |
| HTML parsing | BeautifulSoup4 |
| Documents | python-docx, pypdf |
| Environment | python-dotenv |

### Target Stack (Phase 2+ — Rust Core)

| Component | Technology |
|-----------|-----------|
| Daemon/Core | **Rust** (security boundary) |
| Agent SDK | Python (contributor-friendly) |
| Sandbox (lightweight) | WASM via Wasmtime |
| Sandbox (heavy) | Docker containers |
| Vector DB | ChromaDB (embedded) or Qdrant |
| Embeddings | nomic-embed-text via Ollama |
| Encryption | AES-256-GCM + HKDF-SHA256 |
| Keychain | OS-native (macOS/GNOME/Windows) |
| Local inference | Ollama |
| Filesystem watch | watchdog |

### Why Rust for Core

- Memory safety at compile time (no GC, no runtime errors)
- Single binary deployment (air-gap capable)
- Native WASM host via Wasmtime
- ~5-15MB binary vs ~50-100MB Python runtime
- Enterprise credibility in security reviews
- `NoNewPrivileges` and capability restrictions enforced natively

### Migration Strategy

```
Phase 1: Python for everything (validate product, move fast)
Phase 2: Rust daemon (scheduler, sandbox, credentials, proxy)
         Python agents called by Rust daemon
Phase 3: Core agents migrate to Rust
         Community agents run in WASM/Docker sandbox
         Python SDK remains for contributors
```

---

## Copy & UX Principles

### Language Rules

**Use:** your device, online, thinking, working, ready, connected, private
**Never use:** model, API, inference, token, parameter, LLM, SLM, weights, quantized

### Error Tone

- Assume the problem is fixable
- Assume the user is smart
- Never blame
- Always give a next step
- "I couldn't complete that — here's why" not "Error 503: Connection timeout"

### Interface Rules

- One decision per screen
- No technical vocabulary in user-facing surfaces
- Show progress, not waiting
- Every loading state has a plain-language explanation

---

## Build & Test Commands

```bash
# Setup
bash setup.sh
source .venv/bin/activate

# Run the kernel
python3 core/kernel.py

# Run tests
pytest tests/ -v

# Run specific agent tests
pytest capabilities/file_agent/tests/ -v

# Lint
ruff check .

# Type check
mypy core/ capabilities/
```

---

## Code Style

- **Python:** PEP 8, type hints on all public functions, Google-style docstrings only where logic isn't self-evident
- **Rust (future):** Standard rustfmt, clippy clean, no `unsafe` without security review
- **Naming:** snake_case for Python, snake_case for Rust, kebab-case for files
- **Imports:** stdlib → third-party → local, one blank line between groups
- **Line length:** 100 characters max
- **Error messages:** Always plain language. Never stack traces in user-facing output.

---

## What Claude Code Must Always Do

1. **Read before editing.** Never propose changes to code you haven't read.
2. **Follow the Five Rules.** Every agent interaction respects path grants, workspace writes, confirmation flow, dry_run, and plain-language errors.
3. **Test first.** Write the failing test before the implementation. Always.
4. **Verify before claiming done.** Run the actual command. Read the actual output. Then report.
5. **Think security.** Scan for secrets in output. Check path grants. Validate inputs at system boundaries.
6. **Respect the ACP contract.** `run(input: dict) -> dict`. Every agent. No exceptions.
7. **Plain language always.** No technical jargon in user-facing strings. Ever.
8. **Minimal permissions.** If an agent doesn't need a permission, don't declare it.
9. **No scope creep.** Do what was asked. Don't add features, refactor surrounding code, or "improve" things that weren't broken.
10. **Enterprise mindset.** Every line of code may run on a CFO's laptop with board documents. Act accordingly.

---

*IntentOS — Language is the interface. Security is the foundation. The file never leaves.*

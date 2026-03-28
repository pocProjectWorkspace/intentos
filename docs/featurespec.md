# IntentOS Feature Specification
### *Complete Capability Map — Original + Pivoted*

**Version:** 2.0.0
**Status:** Active
**Last Updated:** 2026-03-28

---

## Overview

This document captures every feature IntentOS will deliver, organized by:
- **Origin:** whether the feature was in the original vision or added during the enterprise pivot
- **Phase:** when it gets built
- **Tier:** which product tier it applies to (Consumer / SMB / Enterprise / All)
- **Inspiration:** which reference project informed the design

---

## Feature Index

| # | Feature | Phase | Tier | Origin | Inspiration |
|---|---------|-------|------|--------|-------------|
| 1 | Intent Kernel | 1 | All | Original | — |
| 2 | File Agent | 1 | All | Original | — |
| 3 | Browser Agent | 1 | All | Original | — |
| 4 | Document Agent | 1 | All | Original | — |
| 5 | System Agent | 1 | All | Original | — |
| 6 | CLI Task Interface | 1 | All | Original | — |
| 7 | Workspace Auto-Setup | 1 | All | Original | — |
| 8 | Dry-Run Preview | 1 | All | Original | — |
| 9 | Confirmation Flow | 1 | All | Original | — |
| 10 | Audit Logging | 1 | All | Original | — |
| 11 | Sensitive File Detection | 1 | All | Original | — |
| 12 | Credential Encryption | 2 | All | Pivot | IronClaw |
| 13 | OS Keychain Integration | 2 | All | Pivot | IronClaw |
| 14 | Leak Detection Pipeline | 2 | All | Pivot | IronClaw |
| 15 | Prompt Injection Defense | 2 | All | Pivot | IronClaw |
| 16 | Per-Job Isolation Tokens | 2 | Enterprise | Pivot | IronClaw |
| 17 | Sandbox Policies (3-tier) | 2 | All | Pivot | IronClaw |
| 18 | Network Proxy + Allowlisting | 2 | SMB/Enterprise | Pivot | IronClaw |
| 19 | Pub-Sub Message Bus | 2 | All | Pivot | MetaGPT |
| 20 | SOP-Driven Task Decomposition | 2 | All | Pivot | MetaGPT |
| 21 | Typed Agent Handoffs (Pydantic) | 2 | All | Pivot | MetaGPT |
| 22 | React Modes (BY_ORDER / PLAN_AND_ACT / REACT) | 2 | All | Pivot | MetaGPT |
| 23 | Quality Gates (LGTM/LBTM) | 2 | All | Pivot | MetaGPT |
| 24 | Cost Governance (CostManager) | 2 | SMB/Enterprise | Pivot | MetaGPT |
| 25 | State Serialization / Recovery | 2 | All | Pivot | MetaGPT |
| 26 | Inference Router | 2 | All | Original | — |
| 27 | Hardware Auto-Detection | 2 | All | Pivot | NOMAD |
| 28 | Adaptive Model Selection | 2 | All | Pivot | NOMAD |
| 29 | Image Agent | 2 | All | Original | — |
| 30 | Media Agent | 2 | All | Original | — |
| 31 | RAG: File Index | 2 | All | Original | — |
| 32 | Agent Scheduler with Isolation | 2 | All | Original | — |
| 33 | Two-User Daemon Model | 3 | All | Original | — |
| 34 | Rust Daemon Core | 3 | All | Pivot | IronClaw |
| 35 | WASM Sandbox (Wasmtime) | 3 | All | Pivot | IronClaw |
| 36 | Docker Container Sandbox | 3 | All | Pivot | IronClaw |
| 37 | RAG: Task Index | 3 | All | Original | — |
| 38 | Experience Retriever | 3 | All | Pivot | MetaGPT |
| 39 | Desktop GUI Task Interface | 3 | All | Original | UI/UX Pro Max |
| 40 | Capability Registry | 3 | All | Original | — |
| 41 | ACP Standardization | 3 | All | Original | — |
| 42 | SSO / SAML Integration | 3 | Enterprise | Pivot | — |
| 43 | Admin Console (Fleet Management) | 3 | Enterprise | Pivot | — |
| 44 | SIEM Integration | 3 | Enterprise | Pivot | — |
| 45 | Compliance Reporting | 3 | Enterprise | Pivot | — |
| 46 | Team Workspaces | 3 | SMB/Enterprise | Pivot | — |
| 47 | One-Command Fleet Deployment | 3 | Enterprise | Pivot | NOMAD |
| 48 | Self-Updating Sidecar | 3 | Enterprise | Pivot | NOMAD |
| 49 | RAG: User Profile Index | 4 | All | Original | — |
| 50 | Public Capability Registry (IntentHub) | 4 | All | Original | — |
| 51 | Contributor SDK | 4 | All | Original | — |
| 52 | Capability Signing | 4 | All | Original | — |
| 53 | Tiered Knowledge Bundles (Industry Verticals) | 4 | Enterprise | Pivot | NOMAD |
| 54 | Offline Knowledge Packages | 4 | Consumer | Pivot | NOMAD |
| 55 | Proactive Suggestions | 4 | All | Original | — |
| 56 | Memory Agent | 4 | All | Original | — |
| 57 | Secrets Manager | 4 | SMB/Enterprise | Pivot | IronClaw |
| 58 | Granular Vector Indexing | 4 | All | Pivot | Claude-Mem |
| 59 | Progressive Disclosure Retrieval | 4 | All | Pivot | Claude-Mem |
| 60 | Industry-Aware UI Reasoning | 4 | Enterprise | Pivot | UI/UX Pro Max |

---

## Phase 1 — Proof of Concept (Current)

### F1: Intent Kernel
**Status:** Built
**File:** `core/kernel.py`

The brain of IntentOS. Receives natural language, interprets intent via Claude API, decomposes into ordered subtasks, routes to agents.

**Capabilities:**
- Parse natural language into structured intent objects
- Decompose complex tasks into ordered subtasks with dependencies
- Route subtasks to appropriate agents
- Handle subtask result references (`{{1.result}}`)
- Return structured results to CLI
- Ask clarifying questions when intent is ambiguous (minimally)

**Intent Object:**
```json
{
  "raw_input": "user's exact instruction",
  "intent": "category.action",
  "subtasks": [
    {"id": "1", "agent": "agent_name", "action": "action", "params": {}}
  ]
}
```

---

### F2: File Agent
**Status:** Built
**File:** `capabilities/file_agent/`

Interface to the local file system. Handles reading, writing, finding, moving, organizing files.

**Actions:**
| Action | Description |
|--------|-------------|
| `list_files` | List files with human-readable metadata |
| `find_files` | Search by name, type, date, size |
| `read_file` | Read file contents |
| `rename_file` | Rename a single file |
| `move_file` | Move file to new location |
| `copy_file` | Copy file to new location |
| `create_folder` | Create new directory |
| `delete_file` | Delete file (confirmation required) |
| `get_metadata` | File metadata (size, dates, type) |
| `get_disk_usage` | Disk space analysis |

**Compound Actions (via LLM planner):**
- `organize_by_type` — sort files into folders by extension
- `bulk_rename` — rename multiple files using patterns
- Batches large operations (max 80 files per batch)

**Safety:**
- Sensitive file detection (`.env`, `*.pem`, `credentials.*`, etc.)
- Path grant enforcement before every operation
- Dry-run preview for batch operations
- Audit logging for all actions

---

### F3: Browser Agent
**Status:** Built
**File:** `capabilities/browser_agent/`

Web search and content extraction.

**Actions:**
| Action | Description |
|--------|-------------|
| `search_web` | DuckDuckGo search |
| `fetch_page` | Retrieve and parse web content |
| `extract_data` | LLM-powered data extraction from pages |

---

### F4: Document Agent
**Status:** Built
**File:** `capabilities/document_agent/`

Document creation and manipulation.

**Actions:**
| Action | Description |
|--------|-------------|
| `create_document` | Generate .docx with formatted content |
| `append_content` | Add content to existing .docx |
| `read_document` | Parse .docx/.pdf to plain text |
| `convert_document` | Format conversion (docx/txt/pdf) |
| `save_document` | Copy/save to new location |

---

### F5: System Agent
**Status:** Built
**File:** `capabilities/system_agent/`

**Actions:**
| Action | Description |
|--------|-------------|
| `get_current_date` | Current date in requested format |

*Planned expansions: disk cleanup, process management, network info*

---

### F6: CLI Task Interface
**Status:** Built

Terminal-based task input and result display. User types natural language, sees plan, confirms, gets results.

---

### F7-F11: Safety Features
**Status:** Built

- **F7: Workspace Auto-Setup** — `~/.intentos/workspace/` created on first run
- **F8: Dry-Run Preview** — preview what would happen before execution
- **F9: Confirmation Flow** — destructive actions require explicit confirmation
- **F10: Audit Logging** — append-only JSONL log of all agent actions
- **F11: Sensitive File Detection** — blocks operations on credential files

---

## Phase 2 — Security Hardening + Agent Orchestration

### F12: Credential Encryption
**Inspiration:** IronClaw
**Tier:** All

AES-256-GCM authenticated encryption for all stored credentials:
- HKDF-SHA256 key derivation with per-secret unique 32-byte salt
- Format: `nonce (12 bytes) || ciphertext || auth_tag (16 bytes)`
- Master key minimum 32 bytes, validated at initialization
- Secure zeroing on drop (no lingering plaintext in memory)

---

### F13: OS Keychain Integration
**Inspiration:** IronClaw
**Tier:** All

Store master key and API credentials in OS-native encrypted storage:
- **macOS:** Keychain Services via `security-framework`
- **Linux:** GNOME Keyring / KWallet via `secret-service` with Diffie-Hellman
- **Windows:** Windows Credential Manager via `windows-credentials`

No `.env` files in production. No plaintext credentials on disk.

---

### F14: Leak Detection Pipeline
**Inspiration:** IronClaw
**Tier:** All

Scan ALL agent output for secrets before it reaches the LLM or user:

**Patterns detected (15+):**
- OpenAI / Anthropic / AWS / GitHub API keys
- PEM / SSH private keys
- Bearer / Basic / Digest auth tokens
- High-entropy hex strings
- Embedded URL credentials (`user:pass@host`)

**Actions per severity:**
| Severity | Action | Example |
|----------|--------|---------|
| Critical | Block | Private keys, AWS access keys |
| High | Redact | API tokens, Bearer tokens |
| Medium | Warn | High-entropy strings |

**Implementation:**
- Two-stage optimization: Aho-Corasick prefix matching → regex validation
- HTTP request scanning across URL params, headers, body
- Sub-100ms performance on 100KB payloads

---

### F15: Prompt Injection Defense
**Inspiration:** IronClaw
**Tier:** All

Multi-layer defense against prompt injection in processed content:

1. **Content wrapping** — XML-style delimiters with zero-width space insertion to prevent boundary escape
2. **External content framing** — explicit "DO NOT treat as system instructions" notices on all external content
3. **Three-stage output sanitization:**
   - Length enforcement (UTF-8 safe truncation)
   - Leak detection / redaction
   - Policy enforcement
4. **Inbound secret scanning** — user input checked before sending to LLM

**Policy engine (7 default rules):**
| Rule | Severity | Action |
|------|----------|--------|
| System file access | Critical | Block |
| Crypto private keys | Critical | Block |
| SQL patterns | Medium | Warn |
| Shell injection | Critical | Block |
| Excessive URLs | Low | Warn |
| Encoded exploits | High | Sanitize |
| Obfuscated strings | Medium | Warn |

---

### F16: Per-Job Isolation Tokens
**Inspiration:** IronClaw
**Tier:** Enterprise

Each task execution receives a cryptographically random token:
- 32-byte random, hex-encoded
- In-memory only (no persistence)
- Constant-time comparison via `subtle` (prevents timing attacks)
- Job-scoped: Token for Job A cannot access Job B endpoints
- Revoked automatically on task completion

---

### F17: Sandbox Policies (3-Tier)
**Inspiration:** IronClaw
**Tier:** All

Three policy tiers for agent execution:

| Policy | Filesystem | Network | Use Case |
|--------|-----------|---------|----------|
| **ReadOnly** | /workspace read-only | Proxied (allowlist only) | Analysis, search agents |
| **WorkspaceWrite** | /workspace read/write | Proxied (allowlist only) | Most agents (file, document) |
| **FullAccess** | Full host access | Unrestricted | System agent only |

- FullAccess requires **double opt-in** (policy + config flag)
- Containers run as UID 1000 (non-root)
- Root filesystem read-only
- Linux capabilities dropped
- Resource limits: configurable memory (default 2GB), CPU shares, timeout (default 120s), output truncation at 64KB

---

### F18: Network Proxy + Allowlisting
**Inspiration:** IronClaw
**Tier:** SMB / Enterprise

When agents need network access:
- All requests routed through a local proxy
- Domain allowlist (default: package registries, GitHub, approved API providers)
- Credentials injected at the proxy boundary (never in agent code)
- Request logging and monitoring
- Enterprise: custom allowlists per org policy

---

### F19: Pub-Sub Message Bus
**Inspiration:** MetaGPT
**Tier:** All

Replace direct agent-to-agent calls with an event-driven message bus:

```python
class Message:
    content: str
    cause_by: type[Action]     # which action produced this
    sent_from: str             # source agent
    send_to: str               # target agent
    instruct_content: BaseModel  # typed Pydantic payload
```

- Agents **publish** messages after acting
- Environment **routes** messages to agents whose subscriptions match
- Agents **observe** by filtering for `cause_by` matching their `_watch` list
- Decoupled, extensible, debuggable
- Full message history stored for audit and replay

---

### F20: SOP-Driven Task Decomposition
**Inspiration:** MetaGPT
**Tier:** All

The Intent Kernel decomposes tasks following Standard Operating Procedures:

```
1. PARSE     → Extract intent from natural language
2. PLAN      → Decompose into ordered subtasks with dependencies
3. VALIDATE  → Check all required agents exist and have permissions
4. PREVIEW   → Dry-run for batch/destructive operations
5. EXECUTE   → Run subtasks in dependency order
6. VERIFY    → Confirm results match intent
7. REPORT    → Return plain-language summary
```

Each step produces typed output consumed by the next. No free-form agent chat.

---

### F21: Typed Agent Handoffs
**Inspiration:** MetaGPT
**Tier:** All

Every agent-to-agent handoff produces a validated Pydantic model:

```python
class FileListResult(BaseModel):
    files: list[FileInfo]
    total_count: int
    total_size_bytes: int

class FileInfo(BaseModel):
    path: str
    name: str
    size_bytes: int
    modified: datetime
    file_type: str
```

No raw dicts between agents. Type validation catches errors at handoff boundaries.

---

### F22: React Modes
**Inspiration:** MetaGPT
**Tier:** All

Different tasks need different orchestration strategies:

| Mode | When | Behavior |
|------|------|----------|
| `BY_ORDER` | Simple tasks (rename, list, move) | Sequential action execution |
| `PLAN_AND_ACT` | Complex multi-agent tasks | Create plan first, then execute |
| `REACT` | Exploratory tasks (research, debug) | LLM dynamically selects next action |

The Intent Kernel selects the mode based on task complexity scoring.

---

### F23: Quality Gates
**Inspiration:** MetaGPT
**Tier:** All

Before any agent's output is passed downstream:

1. **Schema validation** — output matches expected Pydantic model
2. **Content validation** — results make sense (e.g., file count > 0 if files expected)
3. **Security scan** — output checked for leaked secrets
4. **LGTM/LBTM decision** — pass downstream or retry with feedback

Especially critical for destructive actions: double-validate before executing.

---

### F24: Cost Governance
**Inspiration:** MetaGPT
**Tier:** SMB / Enterprise

```python
class CostManager:
    total_budget: float
    spent: float
    tokens_used: dict[str, int]  # per model

    def check_budget(self, estimated_cost: float) -> bool: ...
    def record_usage(self, model: str, tokens: int, cost: float): ...
    def get_report(self) -> CostReport: ...
```

- Track token usage per task, per user, per org
- Enforce spending limits (raise `BudgetExceededException`)
- Route simple tasks locally to minimize API spend
- Surface cost transparency per task in results metadata

---

### F25: State Serialization / Recovery
**Inspiration:** MetaGPT
**Tier:** All

Serialize full execution state for interrupted task recovery:

```python
class TaskState:
    task_id: str
    intent: IntentObject
    subtasks: list[SubtaskState]
    completed: list[str]
    pending: list[str]
    context: dict
    messages: list[Message]
    timestamp: datetime
```

- Save state on every subtask completion
- Resume from last checkpoint on interruption
- Critical for enterprise reliability (long-running batch operations)

---

### F26: Inference Router
**Tier:** All
**Origin:** Original design, enhanced with NOMAD patterns

Routes tasks to optimal inference backend:

```
Complexity Score:
  token_count × task_type × ambiguity × context_depth × agent_count
    → LOW/MED → Local SLM (Ollama)
    → HIGH → Cloud API (with user consent)
```

**Privacy modes:** Local Only / Smart Routing / Performance

---

### F27-F28: Hardware Auto-Detection + Adaptive Model Selection
**Inspiration:** NOMAD
**Tier:** All

On first launch and periodically:
1. Detect GPU (NVIDIA via nvidia-smi, AMD via ROCm, Apple Silicon via sysctl)
2. Detect available RAM
3. Detect CPU capabilities
4. Select optimal local model automatically
5. Configure Ollama runtime (GPU layers, context window, batch size)

No user configuration required. "It just works."

---

### F29: Image Agent
**Tier:** All
**Origin:** Original

**Planned Actions:**
| Action | Description |
|--------|-------------|
| `remove_background` | Background removal from images |
| `resize` | Resize images maintaining aspect ratio |
| `crop` | Crop images to dimensions |
| `convert_format` | Convert between image formats |
| `compress` | Optimize image file size |
| `get_info` | Image metadata (EXIF, dimensions) |

---

### F30: Media Agent
**Tier:** All
**Origin:** Original

**Planned Actions:**
| Action | Description |
|--------|-------------|
| `convert` | Audio/video format conversion |
| `trim` | Cut audio/video to time range |
| `extract_audio` | Extract audio from video |
| `get_info` | Media metadata (duration, codec, bitrate) |
| `compress` | Reduce media file size |

---

### F31: RAG File Index
**Tier:** All
**Origin:** Original

Semantic understanding of the user's filesystem:
- Index Desktop, Documents, Downloads immediately
- Background index home folder over 24 hours
- Idle-time index everything else
- Live updates via filesystem watcher (watchdog)
- Never index: system dirs, `.git`, `.ssh`, `node_modules`, build artifacts

**Index entry:** path, filename, type, size, dates, content_chunks, semantic_tags, embedding

---

### F32: Agent Scheduler with Isolation
**Tier:** All
**Origin:** Original

Process manager for agents:
- Spawn agent processes on demand
- Manage concurrency (parallel independent subtasks)
- Enforce resource limits per agent
- Sandbox enforcement (permissions from manifest vs. declared actions)
- Handle agent failures gracefully
- Report back to Intent Kernel

---

## Phase 3 — Enterprise Ready + Desktop UI

### F33: Two-User Daemon Model
**Origin:** Original

Production deployment of the security model:
- `intentos-daemon` runs as system service user
- Platform-specific: `intentos` (Linux), `_intentos` (macOS), `INTENTOS_SVC` (Windows)
- OS-level ACLs enforce path boundaries
- `NoNewPrivileges=true` (Linux systemd)
- `grants.json` as source of truth
- Complete multi-user isolation on shared machines

---

### F34: Rust Daemon Core
**Inspiration:** IronClaw
**Tier:** All

Rewrite the core execution layer in Rust:
- Scheduler, sandbox manager, credential store, network proxy
- Single binary deployment (~5-15MB)
- Air-gap capable (no runtime dependencies)
- Native WASM host via Wasmtime
- Memory safety at compile time
- Python agents called via subprocess/IPC

---

### F35-F36: WASM + Docker Sandboxing
**Inspiration:** IronClaw
**Tier:** All

**WASM (lightweight agents):**
- Contributors write Python/JS/Rust → compile to WASM via build toolchain
- Wasmtime runtime with fuel metering (CPU limits)
- Memory isolation per module
- Capability-based permissions from manifest
- Epoch interruption for deadline enforcement

**Docker (heavy agents):**
- Media processing (ffmpeg), OCR (Tesseract), ML inference
- Three-tier policies (ReadOnly/WorkspaceWrite/FullAccess)
- Auto-cleanup via reaper process
- Resource limits (memory, CPU, timeout)

---

### F37: RAG Task Index
**Origin:** Original

Every completed task stored with full context:
- Original instruction, resolved intent, agents used, files affected
- Parameters used, result, duration
- Embedding for semantic search

**Enables:** Replay ("do that again"), pattern learning, disambiguation, history queries

---

### F38: Experience Retriever
**Inspiration:** MetaGPT
**Tier:** All

Learn from past task executions to improve future routing:
- If user always renames photos by date → apply automatically
- If user always saves invoices to specific folder → suggest it
- Confidence scoring on learned patterns
- Feeds User Profile Index (Phase 4)

---

### F39: Desktop GUI Task Interface
**Origin:** Original
**Inspiration:** UI/UX Pro Max

Single-surface desktop UI:
- Text input field
- Task history panel
- Result area
- No menus, no file managers, no settings panels visible by default
- Built with Tauri (Rust backend + web frontend)

**Design system generated with UI/UX Pro Max:**
- Industry-aware reasoning for enterprise admin vs consumer shell
- Accessibility-first (WCAG compliance)
- Master + Page Overrides for design consistency
- Anti-pattern enforcement via pre-delivery checklist

---

### F40-F41: Capability Registry + ACP Standardization
**Origin:** Original

Package manager for IntentOS capabilities:
- Local and remote catalog
- Version and dependency management
- Auto-install missing capabilities when a task requires them
- Standardized ACP contract enforced on all agents

---

### F42-F46: Enterprise Features
**Tier:** Enterprise

| Feature | Description |
|---------|-------------|
| **F42: SSO/SAML** | Enterprise identity integration (Okta, Azure AD, etc.) |
| **F43: Admin Console** | Fleet management UI — user provisioning, policy management, usage dashboards |
| **F44: SIEM Integration** | Export audit logs to Splunk, Datadog, Elastic, etc. |
| **F45: Compliance Reporting** | SOC 2, GDPR, HIPAA-aligned reports from audit data |
| **F46: Team Workspaces** | Shared capabilities, shared context, role-based access |

---

### F47-F48: Enterprise Deployment
**Inspiration:** NOMAD
**Tier:** Enterprise

| Feature | Description |
|---------|-------------|
| **F47: One-Command Fleet Deployment** | Single script: install Docker, detect GPU, pull containers, configure everything. Deployable via MDM (Jamf, Intune) or GPO. |
| **F48: Self-Updating Sidecar** | Push updates through management layer. No SSH required. Updater has Docker socket access, pulls new images, recreates containers from admin UI. |

---

## Phase 4 — Platform + Ecosystem

### F49: RAG User Profile Index
**Origin:** Original

Passively-built preference profile:
- Date format, export format, image format, language, timezone
- Frequent folders, frequent contacts
- Task patterns with frequency and preferred parameters
- Avoided actions

Injected into Intent Kernel context on every task.

---

### F50-F52: IntentHub + Contributor Ecosystem
**Origin:** Original

| Feature | Description |
|---------|-------------|
| **F50: IntentHub** | Public capability registry. Anyone can contribute agents. |
| **F51: Contributor SDK** | Python SDK for building capabilities. Handles ACP compliance, testing harness, WASM compilation. |
| **F52: Capability Signing** | Cryptographic signing of published capabilities. Verified before execution. Prevents supply chain attacks. |

---

### F53-F54: Knowledge Packages
**Inspiration:** NOMAD

| Feature | Tier | Description |
|---------|------|-------------|
| **F53: Industry Vertical Bundles** | Enterprise | Curated knowledge + capabilities per industry (legal, medical, financial, manufacturing). Tiered: Essential / Standard / Comprehensive. |
| **F54: Offline Knowledge Packages** | Consumer | NOMAD-style survival kits for underdeveloped markets. Bundled AI + reference content. Works without internet. |

---

### F55-F60: Intelligence Features

| Feature | Description |
|---------|-------------|
| **F55: Proactive Suggestions** | After completing a task, surface related files/actions |
| **F56: Memory Agent** | Persistent user context and preferences across sessions |
| **F57: Secrets Manager** | Enterprise credential management with rotation, expiration, access tracking |
| **F58: Granular Vector Indexing** | Field-level document chunking for precision search (Claude-Mem inspired) |
| **F59: Progressive Disclosure Retrieval** | 3-layer token-efficient retrieval: Search → Timeline → Get (Claude-Mem inspired) |
| **F60: Industry-Aware UI Reasoning** | 161 reasoning rules mapping product types to UI patterns (UI/UX Pro Max inspired) |

---

## Feature Count Summary

| Phase | Features | Status |
|-------|----------|--------|
| Phase 1 | 11 | Built (PoC) |
| Phase 2 | 21 | Next |
| Phase 3 | 16 | Enterprise Ready |
| Phase 4 | 12 | Platform |
| **Total** | **60** | |

| Origin | Count |
|--------|-------|
| Original vision | 28 |
| Enterprise pivot | 32 |

| Tier | Count |
|------|-------|
| All tiers | 43 |
| SMB + Enterprise | 5 |
| Enterprise only | 8 |
| Consumer specific | 1 |
| SMB specific | 0 |

---

*IntentOS Feature Specification v2.0.0 — 60 features, 4 phases, 3 tiers, one product.*

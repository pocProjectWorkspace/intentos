# IntentOS Implementation Roadmap
### *How We Build This — Phase by Phase, Decision by Decision*

**Version:** 2.0.0
**Status:** Active
**Last Updated:** 2026-03-28

---

## Guiding Principles

1. **Ship early, harden continuously.** Phase 1 Python validates the product. Rust hardens it for enterprise.
2. **Security is not a feature — it's the foundation.** Every phase includes security work.
3. **One codebase, three tiers.** Consumer, SMB, Enterprise differ in deployment and config, never in core code.
4. **Local-first, cloud-optional.** Everything works offline. Cloud enhances, never gates.
5. **Test-driven, always.** No production code without a failing test first.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     TASK INTERFACE                            │
│              (CLI → Desktop GUI → Web)                       │
├─────────────────────────────────────────────────────────────┤
│                   USER IDENTITY LAYER                        │
│        (~/.intentos/profile · grants.json)                   │
├─────────────────────────────────────────────────────────────┤
│                    INTENT KERNEL                             │
│          (parse → SOP decompose → route)                     │
├─────────────────────────────────────────────────────────────┤
│                  INFERENCE ROUTER                            │
│        (complexity score → local SLM or cloud API)           │
├──────────────────────┬──────────────────────────────────────┤
│   LOCAL INFERENCE    │      CLOUD INFERENCE                  │
│  (Ollama: Phi-3,     │   (Claude, GPT, Gemini)              │
│   Mistral, Llama)    │   (only with user consent)            │
├──────────────────────┴──────────────────────────────────────┤
│                  SECURITY LAYER                              │
│   (leak detection · prompt defense · credential encryption)  │
├─────────────────────────────────────────────────────────────┤
│              AGENT SCHEDULER + MESSAGE BUS                   │
│    (spawn · isolate · route messages · enforce sandbox)      │
├──────────┬──────────┬──────────┬──────────┬─────────────────┤
│  FILE    │ BROWSER  │ DOCUMENT │  IMAGE   │  MEDIA   │ ...  │
│  AGENT   │ AGENT    │ AGENT    │  AGENT   │  AGENT   │      │
├──────────┴──────────┴──────────┴──────────┴─────────────────┤
│                 CAPABILITY REGISTRY                          │
├─────────────────────────────────────────────────────────────┤
│              SEMANTIC MEMORY (RAG)                           │
│     (File Index · Task Index · User Profile)                 │
├─────────────────────────────────────────────────────────────┤
│                        ACP                                   │
│          (Agent Communication Protocol)                      │
├─────────────────────────────────────────────────────────────┤
│            DAEMON (intentos-daemon)                           │
│    (Rust core · WASM sandbox · Docker sandbox)               │
└─────────────────────────────────────────────────────────────┘
```

---

## Phase 1: Proof of Concept (CURRENT — Complete)

### What's Built

| Component | Status | Notes |
|-----------|--------|-------|
| Intent Kernel (CLI) | Done | `core/kernel.py`, Claude API |
| File Agent | Done | Full CRUD + compound actions |
| Browser Agent | Done | DuckDuckGo + page fetch + extraction |
| Document Agent | Done | .docx/.pdf create/read/convert |
| System Agent | Done | Date only (minimal) |
| CLI Task Interface | Done | Terminal input/output |
| Workspace setup | Done | `~/.intentos/workspace/` auto-created |
| Dry-run + confirmation | Done | Preview + confirm for destructive ops |
| Audit logging | Done | Append-only JSONL |
| Sensitive file detection | Done | Pattern-based blocking |

### What We Learned

- The ACP contract (`run(input) -> dict`) works. Agents are clean and composable.
- Claude API handles intent parsing reliably for most single and multi-step tasks.
- The subtask reference system (`{{1.result}}`) enables powerful agent chaining.
- Dry-run previews significantly improve user trust.
- The current architecture has no formal security boundary — everything runs as the user.

### What Phase 1 Doesn't Have

- No encryption, no sandboxing, no privilege separation
- No local inference (cloud-only)
- No message bus (direct agent calls)
- No typed handoffs (raw dicts)
- No cost tracking
- No recovery from interrupted tasks

---

## Phase 2: Security Hardening + Agent Orchestration

**Goal:** Make IntentOS enterprise-defensible and architecturally sound.

**Timeline:** This is the critical phase. Nothing else matters until security is solid.

### Track A: Security Hardening (IronClaw-Inspired)

#### Step 2A.1: Credential Encryption Module

**Build:** `core/security/encryption.py`

```python
class CredentialStore:
    """AES-256-GCM encrypted credential storage."""

    def __init__(self, master_key: bytes):
        assert len(master_key) >= 32
        self._master_key = master_key

    def encrypt(self, plaintext: str, context: str) -> EncryptedBlob:
        """Encrypt with unique salt and nonce per secret."""
        salt = os.urandom(32)
        key = HKDF(self._master_key, salt)
        nonce = os.urandom(12)
        ciphertext, tag = AES_GCM_encrypt(key, nonce, plaintext.encode())
        return EncryptedBlob(nonce=nonce, ciphertext=ciphertext, tag=tag, salt=salt)

    def decrypt(self, blob: EncryptedBlob, context: str) -> str:
        """Decrypt and return plaintext. Raises on tamper."""
        key = HKDF(self._master_key, blob.salt)
        plaintext = AES_GCM_decrypt(key, blob.nonce, blob.ciphertext, blob.tag)
        return plaintext.decode()
```

**Dependencies:** `cryptography` (Python), later native Rust
**Tests:** Roundtrip, salt uniqueness, cross-key isolation, truncation attacks, tampered ciphertext rejection

---

#### Step 2A.2: OS Keychain Integration

**Build:** `core/security/keychain.py`

```python
class KeychainManager:
    """OS-native keychain for master key storage."""

    def store_master_key(self, key: bytes) -> None: ...
    def retrieve_master_key(self) -> bytes: ...
    def delete_master_key(self) -> None: ...
```

**Platform implementations:**
| Platform | Library | Backend |
|----------|---------|---------|
| macOS | `keyring` + `security` CLI | Keychain Services |
| Linux | `keyring` + `secretstorage` | GNOME Keyring / KWallet |
| Windows | `keyring` + `win32cred` | Windows Credential Manager |

**Tests:** Store/retrieve roundtrip, missing key handling, platform detection

---

#### Step 2A.3: Leak Detection Pipeline

**Build:** `core/security/leak_detector.py`

```python
class LeakDetector:
    """Scan text for leaked credentials."""

    PATTERNS: list[CredentialPattern]  # 15+ patterns
    # Each pattern: regex, severity (Critical/High/Medium), action (Block/Redact/Warn)

    def scan(self, text: str) -> list[LeakDetection]:
        """Two-stage: Aho-Corasick prefix match → regex validation."""
        ...

    def scan_agent_output(self, output: dict) -> SanitizedOutput:
        """Recursively scan all string values in agent output dict."""
        ...
```

**Integration point:** Called after every agent `run()` return, before result is passed downstream or logged.

**Tests:** Each pattern type, false positive prevention, performance on 100KB payloads, nested dict scanning

---

#### Step 2A.4: Prompt Injection Defense

**Build:** `core/security/sanitizer.py`

```python
class ContentSanitizer:
    """Multi-layer prompt injection defense."""

    def wrap_external_content(self, content: str, source: str) -> str:
        """Wrap untrusted content with injection-resistant delimiters."""
        ...

    def sanitize_output(self, text: str) -> str:
        """Three-stage: length → leak detection → policy enforcement."""
        ...

    def scan_input(self, user_input: str) -> InputScanResult:
        """Check user input for embedded secrets before LLM send."""
        ...
```

**Tests:** Boundary escape attempts, Unicode edge cases (ZWSP, RTL overrides, BOM), nested injection

---

#### Step 2A.5: Sandbox Policies

**Build:** `core/security/sandbox.py`

```python
class SandboxPolicy(Enum):
    READ_ONLY = "ReadOnly"
    WORKSPACE_WRITE = "WorkspaceWrite"
    FULL_ACCESS = "FullAccess"

class SandboxManager:
    def create_sandbox(self, agent_name: str, policy: SandboxPolicy) -> Sandbox:
        """Create isolated execution environment for an agent."""
        ...

    def enforce_policy(self, sandbox: Sandbox, operation: FileOp) -> bool:
        """Check if operation is allowed under the sandbox policy."""
        ...
```

**Phase 2 implementation:** Process-level isolation with filesystem guards
**Phase 3 upgrade:** WASM (Wasmtime) and Docker containers

**Tests:** Path traversal attempts, symlink escape, policy tier enforcement, double opt-in for FullAccess

---

### Track B: Agent Orchestration (MetaGPT-Inspired)

#### Step 2B.1: Message Bus

**Build:** `core/orchestration/message_bus.py`

```python
class Message(BaseModel):
    id: str
    content: str
    cause_by: str              # action class name that produced this
    sent_from: str             # source agent
    send_to: str | None        # target agent (None = broadcast)
    payload: BaseModel | None  # typed data
    timestamp: datetime

class MessageBus:
    _subscribers: dict[str, list[str]]  # cause_by → list of agent names
    _history: list[Message]

    def publish(self, message: Message) -> None: ...
    def subscribe(self, agent_name: str, watch: list[str]) -> None: ...
    def get_messages_for(self, agent_name: str) -> list[Message]: ...
```

**Tests:** Pub/sub routing, subscription filtering, history recording, concurrent publish

---

#### Step 2B.2: Typed Handoff Schemas

**Build:** `core/orchestration/schemas.py`

Define Pydantic models for all existing agent outputs:

```python
class FileListResult(BaseModel):
    files: list[FileInfo]
    total_count: int
    total_size_bytes: int

class SearchResult(BaseModel):
    query: str
    results: list[WebResult]
    total_results: int

class DocumentResult(BaseModel):
    path: str
    format: str
    content: str | None
    page_count: int | None
```

**Migration:** Wrap existing `run()` returns in schema validation. Fail fast on schema mismatch.

---

#### Step 2B.3: SOP Engine

**Build:** `core/orchestration/sop.py`

```python
class SOPEngine:
    """Standard Operating Procedure execution engine."""

    PHASES = ["PARSE", "PLAN", "VALIDATE", "PREVIEW", "EXECUTE", "VERIFY", "REPORT"]

    def execute_task(self, raw_input: str, context: ExecutionContext) -> TaskResult:
        intent = self.parse(raw_input)
        plan = self.plan(intent)
        self.validate(plan)
        if plan.needs_preview:
            preview = self.preview(plan)
            if not self.get_confirmation(preview):
                return TaskResult(status="cancelled")
        results = self.execute(plan)
        self.verify(results, intent)
        return self.report(results)
```

---

#### Step 2B.4: React Mode Router

**Build:** `core/orchestration/mode_router.py`

```python
class ReactMode(Enum):
    BY_ORDER = "by_order"           # sequential, deterministic
    PLAN_AND_ACT = "plan_and_act"   # plan first, then execute
    REACT = "react"                  # dynamic action selection

class ModeRouter:
    def select_mode(self, intent: IntentObject) -> ReactMode:
        """Score task complexity and select execution mode."""
        if intent.subtask_count == 1:
            return ReactMode.BY_ORDER
        if intent.requires_research or intent.is_ambiguous:
            return ReactMode.REACT
        return ReactMode.PLAN_AND_ACT
```

---

#### Step 2B.5: Cost Manager

**Build:** `core/orchestration/cost_manager.py`

```python
class CostManager:
    def __init__(self, budget: float | None = None):
        self.budget = budget
        self.spent = 0.0
        self.usage: dict[str, TokenUsage] = {}

    def check_budget(self, estimated_cost: float) -> bool:
        if self.budget is None:
            return True
        return (self.spent + estimated_cost) <= self.budget

    def record_usage(self, model: str, input_tokens: int, output_tokens: int, cost: float):
        self.spent += cost
        self.usage.setdefault(model, TokenUsage()).add(input_tokens, output_tokens, cost)

    def get_report(self) -> CostReport:
        return CostReport(total_spent=self.spent, by_model=self.usage)
```

---

### Track C: Inference + New Agents

#### Step 2C.1: Inference Router

**Build:** `core/inference/router.py`

```python
class InferenceRouter:
    def __init__(self, mode: PrivacyMode, ollama_client, cloud_client=None):
        self.mode = mode
        self.ollama = ollama_client
        self.cloud = cloud_client

    def route(self, prompt: str, task_type: str) -> InferenceResult:
        score = self.score_complexity(prompt, task_type)

        if self.mode == PrivacyMode.LOCAL_ONLY:
            return self.ollama.generate(prompt)

        if self.mode == PrivacyMode.PERFORMANCE:
            return self.cloud.generate(prompt)

        # Smart Routing
        if score <= self.LOCAL_THRESHOLD:
            return self.ollama.generate(prompt)
        else:
            if self.get_cloud_consent(prompt):
                return self.cloud.generate(prompt)
            return self.ollama.generate(prompt)  # fallback

    def score_complexity(self, prompt: str, task_type: str) -> float:
        """Score based on token count, task type, ambiguity, context depth."""
        ...
```

**Dependencies:** Ollama Python SDK, Anthropic SDK (existing)
**Tests:** Routing decisions per mode, consent flow, fallback behavior

---

#### Step 2C.2: Hardware Detection

**Build:** `core/inference/hardware.py`

```python
class HardwareProfile:
    gpu: GPUInfo | None      # vendor, model, vram_gb
    ram_gb: float
    cpu_cores: int
    cpu_model: str
    platform: str            # linux, macos, windows
    arch: str                # x86_64, arm64

class HardwareDetector:
    def detect(self) -> HardwareProfile: ...
    def recommend_model(self, profile: HardwareProfile) -> ModelRecommendation: ...
```

**Detection methods:**
| Component | Linux | macOS | Windows |
|-----------|-------|-------|---------|
| GPU | `nvidia-smi`, `rocm-smi` | `system_profiler`, `sysctl` | `wmic`, `nvidia-smi` |
| RAM | `/proc/meminfo` | `sysctl hw.memsize` | `wmic` |
| CPU | `/proc/cpuinfo` | `sysctl machdep.cpu` | `wmic` |

---

#### Step 2C.3: Image Agent

**Build:** `capabilities/image_agent/`

**Dependencies:** Pillow, rembg (background removal)
**Sandbox policy:** WorkspaceWrite
**Actions:** remove_background, resize, crop, convert_format, compress, get_info

---

#### Step 2C.4: Media Agent

**Build:** `capabilities/media_agent/`

**Dependencies:** ffmpeg (system binary), pydub
**Sandbox policy:** WorkspaceWrite (Docker for ffmpeg)
**Actions:** convert, trim, extract_audio, get_info, compress

---

#### Step 2C.5: RAG File Index

**Build:** `core/rag/file_index.py`

**Dependencies:** ChromaDB, nomic-embed-text via Ollama, watchdog
**Indexing strategy:** Priority-based (Desktop/Documents/Downloads first)
**Update mechanism:** watchdog filesystem watcher for live updates
**Chunking:** Semantic (paragraphs for prose, sections for structured docs, 200-500 tokens/chunk, 50-token overlap)

---

#### Step 2C.6: Agent Scheduler

**Build:** `core/orchestration/scheduler.py`

```python
class AgentScheduler:
    def spawn(self, agent_name: str, input: dict, sandbox: SandboxPolicy) -> AgentProcess: ...
    def execute_parallel(self, tasks: list[SubTask]) -> list[SubTaskResult]: ...
    def execute_sequential(self, tasks: list[SubTask]) -> list[SubTaskResult]: ...
    def enforce_permissions(self, agent_name: str, manifest: Manifest, operation: str) -> bool: ...
    def handle_failure(self, agent: str, error: AgentError) -> FailureAction: ...
```

---

### Phase 2 Build Order

```
Week 1-2:   2A.1 Credential Encryption
            2A.2 OS Keychain Integration
            2B.1 Message Bus
            2B.2 Typed Handoff Schemas

Week 3-4:   2A.3 Leak Detection Pipeline
            2A.4 Prompt Injection Defense
            2B.3 SOP Engine
            2B.4 React Mode Router

Week 5-6:   2A.5 Sandbox Policies
            2B.5 Cost Manager
            2C.1 Inference Router
            2C.2 Hardware Detection

Week 7-8:   2C.3 Image Agent
            2C.4 Media Agent
            2C.5 RAG File Index
            2C.6 Agent Scheduler

Week 9-10:  Integration testing
            Security audit (internal)
            Performance benchmarks
            Documentation update
```

---

## Phase 3: Enterprise Ready + Desktop UI

### Track A: Rust Daemon (Parallel Workstream)

**Start:** During Phase 2, once Python prototype is validated with early customers.

#### Step 3A.1: Rust Project Scaffold

```
intentos-daemon/
├── Cargo.toml
├── src/
│   ├── main.rs                  ← daemon entry point
│   ├── scheduler/
│   │   ├── mod.rs
│   │   ├── process.rs           ← agent process management
│   │   └── pool.rs              ← worker pool
│   ├── sandbox/
│   │   ├── mod.rs
│   │   ├── wasm.rs              ← Wasmtime WASM host
│   │   ├── docker.rs            ← Docker container management
│   │   └── policy.rs            ← 3-tier policy enforcement
│   ├── security/
│   │   ├── mod.rs
│   │   ├── encryption.rs        ← AES-256-GCM
│   │   ├── keychain.rs          ← OS keychain integration
│   │   ├── leak_detector.rs     ← credential scanning
│   │   ├── sanitizer.rs         ← prompt injection defense
│   │   └── tokens.rs            ← per-job isolation tokens
│   ├── proxy/
│   │   ├── mod.rs
│   │   └── allowlist.rs         ← domain allowlisting
│   ├── ipc/
│   │   ├── mod.rs
│   │   └── agent_bridge.rs      ← Python agent IPC
│   └── observability/
│       ├── mod.rs
│       ├── audit.rs             ← audit log writer
│       └── metrics.rs           ← performance metrics
├── tests/
└── benches/
```

**Key crates:**
| Crate | Purpose |
|-------|---------|
| `wasmtime` | WASM runtime |
| `bollard` | Docker API client |
| `ring` / `aes-gcm` | Cryptography |
| `security-framework` | macOS keychain |
| `secret-service` | Linux keyring |
| `hyper` | HTTP proxy |
| `tokio` | Async runtime |
| `tracing` | Structured logging |

---

#### Step 3A.2: WASM Sandbox Implementation

```rust
pub struct WasmSandbox {
    engine: Engine,
    linker: Linker<SandboxState>,
}

impl WasmSandbox {
    pub fn execute(
        &self,
        module: &[u8],         // compiled WASM bytes
        input: &str,           // JSON input
        policy: SandboxPolicy,
        fuel: u64,             // CPU limit
        memory_limit: usize,   // bytes
        timeout: Duration,
    ) -> Result<String, SandboxError> {
        // 1. Compile module (cached)
        // 2. Create fresh instance with fuel metering
        // 3. Inject capabilities based on policy
        // 4. Execute with timeout via epoch interruption
        // 5. Collect output, enforce output size limit
        // 6. Scan output for leaks before returning
    }
}
```

**Agent build toolchain:**
```bash
# Contributor writes Python agent
$ intentos build my_agent

# Under the hood:
# 1. componentize-py compiles agent.py → my_agent.wasm
# 2. Manifest validated
# 3. Bundle created: my_agent.wasm + manifest.json
# 4. Ready for local install or IntentHub publish
```

---

#### Step 3A.3: Python Agent Bridge

The Rust daemon calls Python agents via IPC:

```
Rust Daemon                    Python Agent
    │                              │
    ├─── spawn subprocess ────────►│
    │    (with sandbox policy)     │
    │                              │
    ├─── send JSON input ─────────►│
    │    (via stdin)               │
    │                              │
    │◄── receive JSON output ──────┤
    │    (via stdout)              │
    │                              │
    ├─── scan for leaks            │
    ├─── validate schema           │
    ├─── log to audit              │
    │                              │
    ├─── kill on timeout ─────────►│
    └─── cleanup ─────────────────►│
```

---

### Track B: Enterprise Features

#### Step 3B.1: SSO/SAML Integration

**Build:** `core/enterprise/auth.py` (Python) → `src/auth/` (Rust)

| Provider | Protocol | Library |
|----------|----------|---------|
| Okta | SAML 2.0 / OIDC | `python-saml` / `openidconnect` |
| Azure AD | SAML 2.0 / OIDC | `msal` |
| Google Workspace | OIDC | `google-auth` |
| Custom | SAML 2.0 | `python-saml` |

Maps SSO identity to IntentOS user profile. Admin provisions users via directory sync.

---

#### Step 3B.2: Admin Console

**Build:** Web-based admin UI (Tauri or standalone web app)

**Screens:**
| Screen | Purpose |
|--------|---------|
| Dashboard | Active users, task volume, cost, security events |
| Users | Provisioning, role assignment, license management |
| Policies | Sandbox policies, network allowlists, model routing rules |
| Audit | Searchable audit log with export |
| Compliance | SOC 2 / GDPR / HIPAA report generation |
| Models | On-prem model management, Ollama fleet config |
| Updates | Fleet-wide update management |

---

#### Step 3B.3: SIEM Integration

**Build:** `core/enterprise/siem.py`

Export audit events in standard formats:
| Format | Target |
|--------|--------|
| Syslog (RFC 5424) | Splunk, rsyslog |
| JSON over HTTPS | Datadog, Elastic, custom SIEM |
| CEF | ArcSight, QRadar |

Real-time streaming via webhook or batch export via scheduled job.

---

#### Step 3B.4: Compliance Reporting

**Build:** `core/enterprise/compliance.py`

Auto-generate compliance reports from audit data:
- **SOC 2:** Access control evidence, encryption-at-rest proof, audit trail completeness
- **GDPR:** Data processing records, right-to-erasure execution log, data locality proof
- **HIPAA:** PHI access log, minimum necessary enforcement, encryption verification

Reports are PDF or HTML, exportable on demand or scheduled.

---

### Track C: Desktop GUI

#### Step 3C.1: Task Interface (Tauri)

**Build:** `ui/` directory

```
ui/
├── src-tauri/          ← Rust backend (Tauri)
│   ├── src/
│   │   ├── main.rs
│   │   └── commands.rs  ← IPC commands to kernel
│   └── Cargo.toml
├── src/                ← Web frontend
│   ├── App.tsx
│   ├── components/
│   │   ├── TaskInput.tsx
│   │   ├── TaskHistory.tsx
│   │   ├── ResultPane.tsx
│   │   └── Settings.tsx
│   └── styles/
├── package.json
└── vite.config.ts
```

**Why Tauri:**
- Rust backend (aligns with daemon core)
- ~5MB binary vs ~100MB Electron
- Native OS integration (system tray, notifications)
- WebView (no bundled Chromium)
- macOS, Windows, Linux from one codebase

**Design system:** Generated using UI/UX Pro Max skill with IntentOS-specific reasoning rules:
- Product type: "Security SaaS / AI Tool"
- Style: Clean, trust-focused, minimal
- Color mood: Professional blue + green accents (trust + action)
- Typography: Inter (headings) + JetBrains Mono (code/results)
- Accessibility: WCAG AA minimum

---

### Track D: RAG Expansion

#### Step 3D.1: Task Index

Same architecture as File Index but for completed tasks:
- Store: original instruction, resolved intent, agents used, files affected, parameters, result, duration
- Embed with nomic-embed-text
- Enable: replay, pattern detection, disambiguation, history queries

#### Step 3D.2: Experience Retriever

Query Task Index for patterns:
- "User renamed photos by date 8 times" → auto-suggest date-based rename
- "User always saves invoices to Finance/Invoices/" → route new invoices there
- Confidence scoring: frequency × recency × consistency

---

### Phase 3 Build Order

```
Months 1-2:  3A.1 Rust scaffold + 3A.2 WASM sandbox (parallel track)
             3B.1 SSO/SAML
             3C.1 Tauri UI scaffold

Months 3-4:  3A.3 Python agent bridge
             3B.2 Admin console (MVP)
             3C.1 Task Interface (functional)
             3D.1 Task Index

Months 5-6:  3B.3 SIEM integration
             3B.4 Compliance reporting
             3D.2 Experience Retriever
             Integration testing (full stack)
             Security audit (external, third-party)
             Enterprise pilot deployments
```

---

## Phase 4: Platform + Ecosystem

### 4.1: IntentHub (Public Registry)

**Architecture:**
```
intenthub.io/
├── Registry API          ← capability discovery, versioning, download
├── Build Service         ← compile Python agents to WASM on upload
├── Signing Service       ← cryptographic signing of published capabilities
├── Review Pipeline       ← automated checks + manual review queue
└── Dashboard             ← contributor analytics, install counts
```

**Submission flow:**
1. Contributor pushes capability to GitHub
2. CI runs: manifest validation, test suite, security scan, WASM compilation
3. Automated review: permissions audit, code quality, test coverage
4. Manual review queue for first-time contributors
5. Signed and published to IntentHub
6. Available to all IntentOS users on next registry sync

---

### 4.2: Contributor SDK

```bash
pip install intentos-sdk

# Scaffold a new capability
intentos new my_agent

# Run tests in sandbox
intentos test my_agent

# Build WASM bundle
intentos build my_agent

# Publish to IntentHub
intentos publish my_agent
```

The SDK handles:
- ACP compliance scaffolding
- Test harness with sandboxed directories
- Manifest generation and validation
- WASM compilation (componentize-py)
- IntentHub authentication and upload

---

### 4.3: Industry Vertical Bundles

| Vertical | Agents | Knowledge | Target |
|----------|--------|-----------|--------|
| **Legal** | contract_agent, case_agent | Legal databases, statute references | Law firms |
| **Medical** | patient_agent, reference_agent | Medical references (offline), drug databases | Hospitals, clinics |
| **Financial** | invoice_agent, report_agent | Financial regulations, tax codes | Accounting firms |
| **Manufacturing** | inventory_agent, quality_agent | Safety standards, maintenance guides | Factories |
| **Education** | course_agent, assessment_agent | Khan Academy (offline), textbook references | Schools |

Each bundle is a curated collection:
- **Essential:** Core agents + minimal knowledge (< 5GB)
- **Standard:** Full agents + moderate knowledge (< 20GB)
- **Comprehensive:** Everything + full reference library (< 100GB)

---

### 4.4: Offline Knowledge Packages (NOMAD-Inspired)

For underdeveloped markets and air-gapped environments:

```
IntentOS Offline Kit:
├── IntentOS core binary (Rust, ~15MB)
├── Ollama + Phi-3 Mini (~2.5GB)
├── nomic-embed-text (~270MB)
├── Curated content (user-selected):
│   ├── Wikipedia Quick Reference (313MB)
│   ├── Medical Essential (1GB)
│   ├── Survival + Agriculture (500MB)
│   └── Education (Khan Academy, 2GB)
├── Offline maps (regional, ~500MB)
└── Total: ~7GB on a USB drive
```

One device becomes a knowledge hub for an entire community.

---

### 4.5: User Profile Index + Proactive Suggestions

```json
{
  "preferences": {
    "date_format": "YYYY-MM-DD",
    "default_export_format": "pdf",
    "preferred_image_format": "jpg",
    "language": "en",
    "timezone": "Asia/Dubai"
  },
  "frequent_folders": {
    "invoices": "/home/user/Documents/Finance/Invoices"
  },
  "task_patterns": [
    {
      "pattern": "photo_rename",
      "frequency": 8,
      "preferred_params": {"rename_pattern": "YYYY-MM-DD"}
    }
  ]
}
```

After completing a task, proactively suggest:
- Related files ("I found 3 other invoices from Ahmed")
- Similar past actions ("Last time you also compressed these")
- Optimization opportunities ("These 50 files are duplicates")

---

## Technology Decision Records

### TDR-001: Rust for Daemon Core

**Decision:** Rewrite the core execution layer (scheduler, sandbox, credentials, proxy) in Rust.

**Why:**
- Memory safety at compile time (no GC, no runtime errors)
- Single binary deployment (air-gap capable, ~5-15MB)
- Native WASM host via Wasmtime crate
- Enterprise security credibility
- Performance for file operations and agent orchestration

**Trade-off:** Slower initial development vs. long-term security and deployment advantages.

**Migration:** Python prototype validates product first. Rust core built as parallel track. Python agents called by Rust daemon via IPC.

---

### TDR-002: WASM for Third-Party Agent Sandboxing

**Decision:** Third-party capabilities run in WASM sandboxes (Wasmtime), not as raw Python processes.

**Why:**
- Memory isolation per module (no shared state)
- Fuel metering for CPU limits
- Capability-based permissions (only what manifest declares)
- Contributors write normal Python → build toolchain compiles to WASM
- Solves the "malicious capability" threat from Phase 4 IntentHub

**Trade-off:** Build toolchain complexity vs. zero-trust agent execution.

**Alternative for heavy agents:** Docker containers with tiered policies (for agents needing ffmpeg, Tesseract, etc.)

---

### TDR-003: Tauri for Desktop GUI

**Decision:** Desktop GUI built with Tauri (Rust backend + web frontend), not Electron.

**Why:**
- Rust backend aligns with daemon core
- ~5MB binary vs ~100MB Electron
- No bundled Chromium (uses system WebView)
- Native OS integration
- Cross-platform from one codebase

**Trade-off:** Smaller ecosystem vs. lighter footprint and Rust alignment.

---

### TDR-004: ChromaDB for RAG (Embedded, No Server)

**Decision:** ChromaDB as the default vector database, running embedded.

**Why:**
- No separate database process to manage
- Python-native integration
- Handles 500K+ files comfortably
- Sub-100ms similarity search
- Local-only (aligns with privacy model)

**Upgrade path:** Qdrant for enterprise deployments needing higher throughput or distributed search.

---

### TDR-005: Per-User Licensing Model

**Decision:** Revenue via per-user license, not usage-based or token-based.

**Why:**
- Predictable revenue for us
- Predictable cost for buyer
- Aligns incentives (we want users to use it more, not less)
- Enterprise procurement prefers per-seat
- Usage-based creates adversarial dynamics (user avoids using product to save money)

**Tiers:**
| Tier | Model |
|------|-------|
| Consumer | Free (with upgrade to Pro) |
| SMB | $X/user/month |
| Enterprise | $Y/user/month + deployment fee |

---

### TDR-006: Superpowers Workflow for Development

**Decision:** All IntentOS development follows the Superpowers workflow (brainstorm → plan → execute with subagents → TDD → verify → review).

**Why:**
- Enforces discipline in security-critical codebase
- TDD prevents regression in agent safety features
- Two-stage review catches spec violations before merge
- Subagent isolation prevents context pollution on complex tasks
- Rationalization resistance prevents Claude from cutting corners

---

## Risk Register

| Risk | Severity | Mitigation |
|------|----------|------------|
| Rust rewrite delays product | High | Keep Python prototype running. Rust is parallel track, not blocking. |
| WASM compilation breaks contributor flow | Medium | Invest in `intentos build` toolchain. Make it one command. |
| Local models too weak for complex tasks | Medium | Smart routing to cloud. Improve as open-source models evolve. |
| Enterprise sales cycle too long | High | Consumer + SMB validate product while enterprise pipeline builds. |
| Prompt injection bypasses defenses | Critical | Multi-layer defense (IronClaw-inspired). External security audit in Phase 3. |
| API key exposure in agent output | Critical | Leak detection pipeline scans ALL output. Block/Redact/Warn. |
| Competitor ships similar product | Medium | Speed. Our security model + offline capability is the moat. |
| Community agents are malicious | High | WASM sandbox + capability signing + review pipeline. Phase 4. |

---

## Success Metrics

### Phase 2 Exit Criteria
- [ ] All 15+ credential patterns detected by leak scanner
- [ ] Prompt injection defense passes adversarial test suite
- [ ] Agent output scanning catches 100% of test credential leaks
- [ ] Inference Router correctly routes tasks in all three privacy modes
- [ ] Image and Media agents pass all action tests
- [ ] File Index indexes 10K files in < 5 minutes
- [ ] Cost Manager accurately tracks token usage within 1% margin
- [ ] State serialization enables full recovery from interrupted tasks

### Phase 3 Exit Criteria
- [ ] Rust daemon runs all existing Python agents via IPC
- [ ] WASM sandbox executes test agents with fuel metering
- [ ] Docker sandbox enforces all three policy tiers
- [ ] SSO integration works with Okta and Azure AD
- [ ] Admin console displays real-time fleet status
- [ ] SIEM export validated with Splunk and Datadog
- [ ] Desktop GUI passes accessibility audit (WCAG AA)
- [ ] External security audit completed with no Critical findings
- [ ] 3+ enterprise pilot customers deployed

### Phase 4 Exit Criteria
- [ ] IntentHub accepts, signs, and distributes community capabilities
- [ ] Contributor SDK enables new agent creation in < 30 minutes
- [ ] 2+ industry vertical bundles available
- [ ] Offline knowledge package tested in low-connectivity environment
- [ ] User Profile Index correctly predicts preferences with > 80% accuracy

---

*IntentOS Implementation Roadmap v2.0.0 — from Python prototype to enterprise-grade Rust platform.*

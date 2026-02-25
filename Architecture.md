# IntentOS Architecture
### *How Language Becomes Action*

---

## Overview

IntentOS is structured as a layered agent-native operating system. Unlike traditional OSes that expose hardware to applications, IntentOS exposes **intent to agents**. Each layer has a single responsibility. Together, they turn a natural language sentence into a completed task.

```
┌─────────────────────────────────────────────────────┐
│                   TASK INTERFACE                     │
│         (single text input + result pane)            │
├─────────────────────────────────────────────────────┤
│                  INTENT KERNEL                       │
│       (parse intent → plan → route to agents)        │
├─────────────────────────────────────────────────────┤
│              INFERENCE ROUTER                        │
│   (local SLM  ←─ complexity score ─→  cloud API)    │
├──────────────────────┬──────────────────────────────┤
│   LOCAL INFERENCE    │      CLOUD INFERENCE          │
│  (Phi-3 / Mistral)   │   (Claude / GPT / Gemini)    │
├──────────────────────┴──────────────────────────────┤
│                 AGENT SCHEDULER                      │
│      (spawn, manage, isolate, dissolve agents)       │
├──────────────┬──────────────┬───────────────────────┤
│  FILE AGENT  │ BROWSER AGENT│  MEDIA AGENT  │  ...  │
│              │              │               │       │
├──────────────┴──────────────┴───────────────────────┤
│              CAPABILITY REGISTRY                     │
│         (discover, load, version capabilities)       │
├─────────────────────────────────────────────────────┤
│            SEMANTIC MEMORY LAYER                     │
│    (user context, file index, task history)          │
├─────────────────────────────────────────────────────┤
│         AGENT COMMUNICATION PROTOCOL (ACP)           │
│        (standard contract between all agents)        │
└─────────────────────────────────────────────────────┘
```

---

## Layer by Layer

### 1. Task Interface
The only surface the user ever sees. A text input field, a task history panel, and a result area. There are no menus, no file managers, no settings panels visible by default. Everything the user needs is reachable through language.

**Responsibilities:**
- Accept natural language input
- Display task progress and results
- Show task history with the ability to replay or modify past tasks
- Surface errors in plain language, never in stack traces

**Technology:** Lightweight desktop UI built with a web renderer (Tauri/Electron) or terminal-first for early versions.

---

### 2. Intent Kernel
The brain of IntentOS. Receives raw natural language, interprets the user's goal, decomposes it into sub-tasks, and routes each sub-task to the appropriate agent. This is the component that makes IntentOS feel intelligent.

**Responsibilities:**
- Parse natural language into structured intent objects
- Decompose complex tasks into ordered sub-tasks
- Route sub-tasks to the right capabilities via the Agent Scheduler
- Handle ambiguity by asking clarifying questions (minimally)
- Return structured results to the Task Interface

**Technology:** LLM-powered. The kernel does not call a model directly — it passes every task through the **Inference Router**, which decides whether a local SLM or cloud API handles it. The kernel prompt is the most critical piece of engineering in the entire OS. It must be precise, auditable, and versioned.

**Intent Object (example):**
```json
{
  "raw_input": "remove the background from all images in my Downloads folder",
  "intent": "image.background_remove",
  "scope": "batch",
  "target": "~/Downloads/*.{jpg,png,jpeg}",
  "output": "same_folder",
  "subtasks": [
    { "id": "1", "agent": "file_agent", "action": "list_files", "params": { "path": "~/Downloads", "types": ["jpg","png","jpeg"] } },
    { "id": "2", "agent": "image_agent", "action": "remove_background", "params": { "files": "{{1.result}}" } }
  ]
}
```

---

### 3. Inference Router
The decision layer between the Intent Kernel and any language model. Every task passes through here. The Inference Router scores the complexity of each task and routes it to the right inference backend — a local SLM running on the user's machine, or a cloud API for tasks that need more power.

This is what makes IntentOS private by default, fast for simple tasks, and capable for complex ones — without the user ever having to think about it.

**Routing Logic:**

```
Task arrives from Intent Kernel
        │
        ▼
┌───────────────────┐
│  Complexity Score  │  ← token count, task type, ambiguity level, context depth
└───────────────────┘
        │
   ┌────┴────┐
 score       score
 LOW/MED     HIGH
   │           │
   ▼           ▼
Local SLM   Cloud API
(instant,   (opt-in,
 private,    powerful,
 free)       costs tokens)
```

**Complexity scoring factors:**

| Factor | Low complexity | High complexity |
|---|---|---|
| Task type | Route, rename, list, play | Summarize, reason, multi-step web |
| Input length | Short instruction | Long document or context |
| Ambiguity | Clear intent | Vague or multi-intent |
| Memory required | Stateless | Requires deep context |
| Agent count | Single agent | 3+ agents composing |

**Privacy modes (user-controlled):**

```
● Local Only     — all tasks run on local SLM, no data leaves the machine
                   (slower on complex tasks, may degrade gracefully)

● Smart Routing  — default. Simple tasks stay local, complex tasks
                   ask before sending to cloud

● Performance    — always use cloud API for best results
                   (fastest and most capable, costs tokens)
```

**The user sees this as a single toggle in settings.** They never think about models, APIs, or routing. They just choose how private they want to be.

**Local SLM options (bundled or user-installed via Ollama):**

| Model | Size | RAM needed | Best for |
|---|---|---|---|
| Phi-3 Mini | 3.8B | 4GB | Intent parsing, simple routing |
| Mistral 7B (4-bit) | ~4GB | 8GB | More complex instructions |
| Qwen2.5 3B | 3B | 4GB | Multilingual tasks |

**Cloud API options (user provides key, IntentOS never stores it):**

- Anthropic Claude (default recommendation)
- OpenAI GPT-4o
- Google Gemini
- Any OpenAI-compatible endpoint (local or remote)

**Why this matters for the vision:**

An OS that requires a cloud subscription to function is not really an OS — it's a SaaS product with a nice interface. The Inference Router means IntentOS works on a plane, in a country with restricted APIs, on a machine with no internet, and for users who simply don't want their instructions leaving their computer. Local-first is a feature, not a compromise.

---

### 4. Agent Scheduler
The process manager of IntentOS. Spawns agents when tasks need them, allocates resources, isolates agent execution, and dissolves agents when tasks are complete. Users never interact with this layer directly.

**Responsibilities:**
- Spawn agent processes on demand
- Manage concurrency (run independent sub-tasks in parallel)
- Enforce resource limits per agent
- Sandbox agents so a file agent cannot make network calls, a browser agent cannot write to disk without permission, etc.
- Handle agent failures gracefully and report back to the Intent Kernel

**Technology:** Python subprocess management initially. Containerized agents (Docker/podman) for production isolation.

---

### 5. Capabilities (Agents)
The "packages" of IntentOS. Each capability is a self-contained agent with a defined interface. Anyone can build and contribute a capability. The OS routes tasks to capabilities automatically based on intent — the user never selects them.

**Core capabilities (v1 target):**

| Capability | What it does |
|---|---|
| `file_agent` | Read, write, move, rename, archive, search files |
| `browser_agent` | Navigate web, extract data, fill forms, book things |
| `image_agent` | Resize, crop, filter, remove background, convert format |
| `media_agent` | Play, convert, trim, extract audio, add subtitles |
| `system_agent` | Disk cleanup, process management, network info |
| `document_agent` | Read PDFs, merge docs, extract tables, summarize |
| `memory_agent` | Store and retrieve user context and preferences |

Each capability follows the **Capability Specification** (see `/capabilities/SPEC.md`).

---

### 6. Capability Registry
The package manager of IntentOS. Maintains a catalog of available capabilities, their versions, their interfaces, and their permissions. When the Intent Kernel needs a capability that isn't loaded, the registry fetches and installs it automatically.

**Responsibilities:**
- Maintain a local and remote catalog of capabilities
- Version and dependency management
- Capability permission declarations (what can this agent access?)
- Auto-install missing capabilities when a task requires them

**Inspired by:** apt, npm, and OpenClaw's ClawHub.

---

### 7. Semantic Memory Layer
The file system equivalent for IntentOS — but instead of a hierarchy of bytes, it's a queryable store of context. The OS remembers what files you have, what tasks you've run, what your preferences are, and uses that context to make future tasks smarter.

**Responsibilities:**
- Index user files with semantic metadata
- Store task history with inputs, outputs, and agent traces
- Maintain user preference profile (updated passively from task patterns)
- Provide context injection to the Intent Kernel on every task

**Technology:** Local vector store (ChromaDB or similar) + structured JSON for preferences.

---

### 8. Agent Communication Protocol (ACP)
The POSIX of IntentOS. The standard contract that every agent must implement to communicate with the scheduler and with other agents. Inherited and extended from OpenClaw's ACP.

**Every agent exposes:**
```json
{
  "name": "file_agent",
  "version": "0.1.0",
  "capabilities": ["read", "write", "list", "move", "search"],
  "permissions": ["filesystem"],
  "input_schema": { ... },
  "output_schema": { ... }
}
```

**Technology:** JSON over local IPC (initially). gRPC or message queue for distributed deployments.

---

## Design Principles for Contributors

**1. Every layer is replaceable.** The Intent Kernel could run on a different LLM. The Task Interface could be a voice input. The Scheduler could be Kubernetes. Design for replaceability.

**2. Agents are stateless.** Each agent execution is independent. State lives in the Semantic Memory Layer, not inside agents.

**3. Permissions are explicit and minimal.** Every capability declares exactly what it can access. The Scheduler enforces these declarations. A capability cannot exceed its declared permissions.

**4. Failures are first-class.** Every agent must handle failure gracefully and return a structured error. The Intent Kernel translates errors into plain language for the user.

**5. The user never sees agents.** No agent names, no technical jargon, no stack traces in the Task Interface. If something goes wrong, the user sees "I couldn't complete that — here's why" in plain language.

---

## Build Sequence (Roadmap)

```
Phase 1 — Proof of Concept
  ✦ Intent Kernel (CLI only, Claude API)
  ✦ File Agent (basic read/write/list/move)
  ✦ Task Interface v0 (terminal input/output)

Phase 2 — Core Capabilities
  ✦ Agent Scheduler with basic isolation
  ✦ Browser Agent (headless, Playwright)
  ✦ Image Agent (background removal, resize, convert)
  ✦ Media Agent (convert, trim, extract audio)
  ✦ Semantic Memory Layer v1

Phase 3 — OS Experience
  ✦ Task Interface v1 (desktop GUI)
  ✦ Capability Registry + auto-install
  ✦ System Agent
  ✦ Document Agent
  ✦ ACP standardization

Phase 4 — Platform
  ✦ Public capability registry (IntentHub)
  ✦ Contributor SDK
  ✦ IntentOS distributable image
```

---

*IntentOS — Built on OpenClaw. Language is the interface.*

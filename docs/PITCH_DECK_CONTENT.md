# IntentOS Pitch Deck Content
### Source Material for 10-12 Slide Investor/Client Presentation

---

## SLIDE 1: Title Slide

**Product Name:** IntentOS

**Tagline:** Your Computer, Finally On Your Side

**Subtitle:** AI that runs on your device. Files never leave. Enterprise-grade security.

**One-line description:** IntentOS is an AI execution layer that turns natural language into action on the user's own machine, with complete IT visibility and zero data leakage.

**Visual suggestion:** Full-bleed dark background with the IntentOS logo centered. The tagline in large, clean sans-serif type. Below it, a subtle glow effect around a laptop silhouette with a shield icon, reinforcing the "local + secure" message. No screenshots on this slide. Keep it cinematic.

**Speaker note:** "Every company is racing to deploy AI. But the tools available today force a choice: power or privacy. IntentOS eliminates that trade-off."

---

## SLIDE 2: The Problem

### The Enterprise AI Dilemma

Every enterprise wants AI productivity. None of them want the risk that comes with it.

**The reality today:**

- **Data leakage is the default.** ChatGPT, Copilot, and every major AI tool requires uploading documents to third-party cloud infrastructure. Every prompt, every file, every question becomes training data or sits on someone else's server.

- **IT is flying blind.** There is no centralized dashboard showing what employees are sending to AI. No audit trail. No policy enforcement. The CISO finds out about misuse after the breach, not before.

- **Cost is a black box.** Enterprise AI subscriptions charge flat per-seat fees with no visibility into actual usage. A user who runs one query a month costs the same as a power user running 200. There is no per-task cost tracking and no way to optimize spend.

- **Shadow AI is already happening.** Employees who are blocked from official AI tools use personal accounts, browser extensions, or unofficial APIs. The problem does not go away by banning it. It goes underground.

**The numbers:**

| Data Point | Source |
|---|---|
| 65% of enterprises have banned or restricted ChatGPT use | Reuters, 2024 survey of Fortune 500 |
| 55% of organizations cite data privacy as the #1 concern with generative AI | Gartner, 2024 |
| Samsung, JPMorgan, Apple, Deutsche Bank have all restricted AI tool access | Public reports, 2023-2024 |
| 82% of employees say they use AI tools that IT has not approved | Salesforce Generative AI Snapshot, 2024 |
| Average cost of a data breach in 2024: $4.88 million | IBM Cost of a Data Breach Report |

**The CISO's nightmare scenario:** Your CFO just uploaded the board deck to ChatGPT to "clean up the formatting." The M&A term sheet went to Claude for "a quick summary." The HR director pasted salary data into Copilot to "make a chart." None of this was logged. None of it can be recalled.

**Visual suggestion:** Split the slide into two halves. Left side: a chaotic collage of news headlines about AI bans, data leaks, and shadow IT. Right side: clean, large text with the key stat: "65% of enterprises have restricted AI access. The other 35% just don't know what's happening." Use red/orange tones to convey urgency.

**Speaker note:** "This is not a hypothetical. This is happening inside every enterprise right now. The question is not whether to deploy AI. It's whether you can afford to deploy it without control."

---

## SLIDE 3: The Solution -- IntentOS

### One sentence: An AI execution layer that runs on the user's device, controlled by IT.

IntentOS is not another chatbot. It is not an API wrapper. It is an execution platform that turns natural language into real actions on the user's own machine, while giving IT complete visibility and policy control.

**Three pillars:**

**1. Local-First AI**
70% of tasks run entirely on-device using open-source models via Ollama. No internet required. No API calls. No cost. The user's files are processed by a model running on their own hardware. For simple tasks (file operations, system queries, local search), the response is instant and free. Cloud AI is only invoked for genuinely complex tasks, and only with user consent.

**2. Zero Data Leakage**
Even when a task does route to cloud AI (Anthropic Claude, OpenAI, Google Gemini), IntentOS never sends file contents. The inference interceptor extracts the semantic query from the file locally, sends only the prompt to the cloud, and applies the response locally. File contents, file paths, embeddings, and task history never leave the device. This is not a policy. It is an architectural constraint.

**3. IT Fleet Control**
The IntentOS Console is a centralized dashboard where IT manages every IntentOS installation across the organization. Deploy signed policies that lock privacy modes, block specific agents, cap spending per user, and enforce compliance. Every action across the fleet is logged to a searchable, exportable audit trail. API keys are managed centrally and rotated from the Console, never stored in config files on endpoints.

**Visual suggestion:** Three columns or a triangle layout. Each pillar gets an icon: a CPU chip for Local-First, a shield with a lock for Zero Data Leakage, a dashboard/monitor for IT Fleet Control. Below each icon, 2-3 lines of text. Use brand colors (dark background, accent blue or green). At the bottom, a single line: "One codebase. Three deployment tiers. Same security promise at every level."

**Speaker note:** "Most AI products are built cloud-first and then try to bolt on privacy. We built privacy-first and then added cloud as an option. That architectural decision cannot be replicated by competitors without a full rebuild."

---

## SLIDE 4: How It Works (Architecture)

### The Intent Execution Flow

IntentOS converts natural language into executed actions through a five-stage pipeline:

```
User speaks or types
       |
       v
[Intent Kernel] -- parses natural language into structured intent
       |
       v
[Inference Router] -- scores task complexity, routes to local or cloud AI
       |
       v
[Agent Scheduler] -- decomposes into subtasks, assigns to specialized agents
       |
       v
[Agent Execution] -- agents operate within sandboxed permissions
       |
       v
[Result Assembly] -- plain-language response returned to user
```

**Key architectural components:**

| Component | Role |
|---|---|
| **Intent Kernel** | Parses natural language input, resolves ambiguity using RAG context, produces a structured execution plan |
| **Inference Router** | Evaluates task complexity (token count, ambiguity, agent count) and routes to local model or cloud API. User controls the routing policy. |
| **Agent Scheduler** | Orchestrates multi-step tasks. Agents can reference previous results. Supports sequential, plan-and-act, and dynamic execution modes. |
| **Security Pipeline** | Every input and output passes through a three-stage leak detection pipeline. Credentials are injected at runtime, never stored in agent code. |
| **RAG Context** | Three local vector indexes (files, tasks, user profile) provide semantic memory. The system learns the user's patterns without sending data anywhere. |

**The privacy boundary:**

Everything inside the dotted line runs on the user's machine: all file processing, all agent execution, all embeddings, all task history. The only data that crosses to the IntentOS Console is usage telemetry: action counts, cost totals, compliance status, device health. Never prompt content. Never file contents. Never paths.

**Six capability agents shipping today:**

1. **File Agent** -- search, organize, move, rename, analyze files
2. **Browser Agent** -- web search, page fetching, content extraction
3. **Document Agent** -- create, edit, summarize PDFs and documents
4. **System Agent** -- hardware info, disk usage, process management
5. **Image Agent** -- image analysis, metadata extraction
6. **Media Agent** -- audio/video processing, transcription

**Visual suggestion:** A horizontal flow diagram showing the five stages as connected nodes, left to right. Below it, a dashed rectangle labeled "Device Boundary" enclosing all components except the Console. A small arrow from the device boundary to a "Console" icon labeled "usage stats only." The six agents shown as small icons below the scheduler. Use clean, technical illustration style. No gradients, no 3D effects.

**Speaker note:** "The key insight here is the privacy boundary. Everything that touches user data happens inside the device. The Console only sees metadata. This is how we satisfy CISO requirements without sacrificing functionality."

---

## SLIDE 5: The Desktop Experience (User Persona)

### What the user sees

IntentOS is a native macOS application (120 MB, launches from /Applications). It looks and feels like a modern chat interface, but behind the conversation is a full execution engine.

**Interface elements:**

- **Chat window:** Clean dark theme with markdown rendering, code highlighting, and inline results. Responses stream in real-time via SSE.
- **Input bar:** "Tell IntentOS what to do..." with a mic button for voice input (Whisper STT, runs locally) and a paperclip for file attachments.
- **Session sidebar:** Full conversation history with search. Sessions persist across app restarts.
- **Status bar:** Shows the active model name, current privacy mode (Local Only / Smart Routing / Performance), and token usage for the session.
- **Follow-up chips:** After each response, suggested next actions appear as clickable chips below the result.
- **Settings panel:** Privacy mode selector, voice toggle, model preferences, theme -- all user-controllable within the boundaries set by IT policy.

**Example interactions that demonstrate the value:**

| User says | What happens | Cost |
|---|---|---|
| "What's my disk usage?" | System agent queries locally. Instant response. | $0.00 |
| "Summarize this contract PDF" | Document agent processes the file on-device using local model. File never uploaded. | $0.00 |
| "Find all invoices from Q3 in my Downloads folder" | File agent searches locally using RAG index. Returns file list with previews. | $0.00 |
| "Search the web for Tesla Q3 earnings and summarize" | Browser agent fetches web content, cloud AI summarizes. Logged in Console. | ~$0.01 |
| "Draft an email to the team about the project delay" | Cloud AI composes text. No local files involved. Cost tracked per-token. | ~$0.02 |
| "Rename all screenshots on my desktop to include the date" | File agent executes locally. Asks for confirmation before bulk rename. | $0.00 |

**Voice I/O:** Both speech-to-text (Whisper) and text-to-speech (Piper) run entirely on-device. The user can speak commands and hear responses without any audio data leaving their machine. This matters for executives who dictate rather than type.

**Key message for this slide:** "It works like ChatGPT, but your files never leave. And 70% of tasks cost nothing."

**Visual suggestion:** A centered screenshot (or high-fidelity mockup) of the IntentOS desktop app showing a conversation in progress. Callout annotations pointing to key UI elements: voice input, session history, status bar, follow-up chips. On the right side, a small cost comparison: three example tasks with $0.00 next to each one, contrasted with "Same tasks on ChatGPT: $0.08" or similar. Keep the mockup large and the annotations minimal.

**Speaker note:** "Notice the status bar. The user always knows what mode they're in and what it's costing. There are no surprises. And when IT has locked the privacy mode to Local Only, the user sees that too. Transparency at every level."

---

## SLIDE 6: The IT Admin Experience (IT Persona)

### IntentOS Console -- Fleet Command for AI

The Console is a web-based dashboard (React + FastAPI) where IT administrators manage every IntentOS installation across the organization. It provides the visibility, control, and compliance tooling that enterprise IT teams require before approving any AI deployment.

**Eight pages, each solving a specific IT need:**

**1. Dashboard (Fleet Overview)**
Real-time fleet health at a glance. Total active devices, tasks executed today, total cost this billing period, top users by activity, model usage breakdown (local vs. cloud), and a 30-day cost trend line. One screen tells the CISO everything they need for the weekly security meeting.

**2. Policy Manager**
Create, sign, and deploy policies across the fleet. Policies are JSON documents signed with HMAC-SHA256 -- they cannot be tampered with on the endpoint. Policy controls include:
- Lock privacy mode (e.g., force "Local Only" for finance department)
- Block specific agents (e.g., disable Browser Agent for regulated users)
- Cap cloud spending per user per month
- Restrict which cloud AI providers are permitted
- Enforce model allowlists (only approved models)

**3. Device Manager**
Per-device inventory with status indicators. Toggle cloud access per device, assign API keys, push policy updates, view last heartbeat time. Group devices by department, location, or custom tags. Remote-wipe API keys if a device is lost or compromised.

**4. Audit Log**
Every action across every device, in one searchable timeline. Filter by user, device, agent, action type, date range. Export to CSV or push to SIEM (Splunk integration built-in). The audit log captures: timestamp, user, device ID, agent, action, paths accessed, result status, duration, and cost. It does not capture prompt content or file contents.

**5. API Key Vault**
Centralized management of cloud AI credentials. IT stores API keys for Anthropic, OpenAI, Google, and other providers in the Vault. Keys are encrypted at rest (AES-256-GCM), distributed to devices via secure channel, and can be rotated or revoked instantly from the Console. No user ever sees or handles an API key.

**6. Connectors**
Pre-built integrations with enterprise tools:
- **Slack/Teams:** Push alerts when policy violations are detected or spending thresholds are hit
- **Splunk:** Stream audit logs to existing SIEM infrastructure
- **Jira:** Auto-create tickets for security events
- **Okta:** SSO/SAML integration for user provisioning (roadmap Q3 2026)

**7. Security & Compliance**
Compliance mapping dashboard showing the organization's posture against major frameworks:
- SOC 2 Type II (CC6.1, CC6.6, CC7.2)
- HIPAA (Section 164.312)
- GDPR (Article 25 Data Protection by Design, Article 32 Security of Processing)
- ISO 27001 (Annex A.8 Asset Management, A.10 Cryptography)

Each control is mapped to IntentOS features with evidence links and compliance status.

**8. ROI Calculator**
Interactive calculator where IT and procurement can model cost savings. Input: number of seats, current AI tool spend, estimated task distribution. Output: projected annual savings, cost-per-task comparison, and break-even analysis vs. ChatGPT Enterprise and Microsoft Copilot.

**Key message:** "Complete visibility and control from a single dashboard. Every AI action across your fleet, logged, searchable, and exportable."

**Visual suggestion:** A 2x4 grid showing a thumbnail/icon for each of the eight Console pages, with a one-line description below each. Alternatively, show the Dashboard page as a large screenshot with smaller thumbnails of Policy Manager and Audit Log flanking it. Use a blue/dark enterprise aesthetic. The grid should feel comprehensive but not overwhelming.

**Speaker note:** "This is the slide that closes the deal with IT. The Console gives them everything they already have for endpoint security, but for AI. Policy enforcement, audit trails, cost control, compliance mapping. This is what makes IntentOS deployable in a regulated enterprise."

---

## SLIDE 7: Security & Compliance (CISO Persona)

### Enterprise-Grade Security Is the Default, Not an Upgrade

IntentOS was designed for environments where a data breach costs millions and a compliance failure costs the contract. Security is not a feature toggle. It is the architecture.

**Data Residency -- What stays where:**

| Data | Location | Transmitted? |
|---|---|---|
| File contents | Device only | Never. Under any mode. |
| File paths | Device only | Never. Not even hashed. |
| RAG embeddings | Device only | Stored in local ChromaDB. |
| Task history | Device only | Complete execution log. |
| User preferences | Device only | Profile stays on-device. |
| API keys | Device only (OS keychain) | Keys never in config files. |
| Audit log | Device only | Append-only, tamper-evident. |
| Usage statistics | Transmitted to Console | Action counts, costs, compliance -- never content. |

**Encryption and key management:**

| Layer | Standard | Implementation |
|---|---|---|
| Credentials at rest | AES-256-GCM | HKDF-SHA256 key derivation, OS keychain storage |
| Policy signing | HMAC-SHA256 | Policies signed by Console, verified on endpoint |
| Transport | TLS 1.3 | All Console communication encrypted in transit |
| Token comparison | Constant-time | Per-job isolation tokens, prevents timing attacks |

**Access control model:**

- **Per-agent sandboxing:** Each agent declares required permissions. File Agent gets filesystem.read. Browser Agent gets network. No agent gets more than it needs.
- **Three sandbox tiers:** ReadOnly (analysis), WorkspaceWrite (most agents), FullAccess (system agent with double opt-in)
- **Path grants:** The user explicitly grants access to specific directories. The IntentOS daemon has zero default filesystem access.
- **Destructive action confirmation:** Any delete, overwrite, or bulk rename requires explicit user confirmation. No silent destructive operations.

**Leak detection pipeline (three stages):**

1. **Input scanning:** Every user input is scanned for accidental credential pasting before it reaches the LLM
2. **Output scanning:** Every LLM response is scanned for leaked secrets (API keys, PEM content, bearer tokens) before display
3. **Agent output scanning:** Every agent result is scanned before it enters the execution pipeline

**Compliance framework mapping:**

| Framework | Relevant Controls | IntentOS Coverage |
|---|---|---|
| SOC 2 Type II | CC6.1 (Logical Access), CC6.6 (Boundary Protection), CC7.2 (System Monitoring) | Policy engine, device boundary, audit logging |
| HIPAA | Section 164.312 (Technical Safeguards) | Encryption at rest, access controls, audit trail |
| GDPR | Article 25 (Data Protection by Design), Article 32 (Security of Processing) | Local-first architecture, encryption, consent controls |
| ISO 27001 | A.8 (Asset Management), A.10 (Cryptography) | Device inventory, AES-256-GCM, key management |

**Key message:** "Your data stays on the device. Period. We do not ask you to trust us with your files. We architected it so we never have access to them in the first place."

**Visual suggestion:** A two-column layout. Left column: the data residency table with green checkmarks for "Device Only" items and a clear dividing line showing the one category that is transmitted (usage stats). Right column: compliance badges (SOC 2, HIPAA, GDPR, ISO 27001) arranged in a 2x2 grid. At the bottom, a bold pull quote: "Zero trust is not a policy. It's the architecture."

**Speaker note:** "When we say files never leave, we mean it structurally. There is no config flag that overrides this. There is no admin setting that changes it. The architecture does not support sending file contents to any external service. This is what makes the compliance conversation straightforward."

---

## SLIDE 8: Smart Cost Management (CFO Persona)

### 70% of Tasks Run Free. The Rest Cost Pennies.

IntentOS's inference router is a cost optimization engine disguised as a privacy feature. By running simple tasks locally and only routing complex tasks to cloud AI, enterprises save 25-40% compared to flat-rate competitors while getting better security.

**How inference routing works:**

Every incoming task receives a complexity score based on: token count, task type, ambiguity level, context depth, and number of agents required.

| Complexity | Route | Examples | Cost |
|---|---|---|---|
| Low | Local model (Ollama) | List files, rename, disk usage, date queries, simple search | $0.00 |
| Medium | Local model (Ollama) | File organization, local document summarization, metadata extraction | $0.00 |
| High | Cloud API (user consents) | Complex analysis, multi-source research, long-form composition | $0.003 - $0.05 per task |

**Result:** In typical enterprise usage, 70% of tasks are low or medium complexity and run entirely on the user's hardware at zero marginal cost. The remaining 30% route to cloud AI at per-token pricing, fully logged and tracked.

**Head-to-head cost comparison (annual, per 500 seats):**

| Solution | Per-Seat Price | Inference Model | Annual Cost (500 seats) |
|---|---|---|---|
| ChatGPT Enterprise | $60/seat/month | 100% cloud | $360,000 |
| Microsoft Copilot | $30/seat/month | 100% cloud | $180,000 |
| Google Gemini Business | $20/seat/month | 100% cloud | $120,000 |
| **IntentOS Enterprise** | **$35-45/seat/month** | **70% local + 30% cloud** | **$210,000-$270,000 license + ~$48,000 cloud API** |

**The IntentOS math for 500 enterprise seats at $42/seat:**

- License cost: $42 x 500 x 12 = $252,000/year
- Estimated cloud API cost (30% of tasks): ~$48,000/year
- **Total: $300,000/year**
- vs. ChatGPT Enterprise: $360,000/year
- **Savings: $60,000/year (17%) PLUS files-never-leave security and IT fleet control**

At the SMB tier ($15/seat/month), the savings are even more dramatic:
- 100 SMB seats: $18,000/year + ~$6,000 cloud = $24,000/year
- vs. ChatGPT Team at $25/seat: $30,000/year
- **Savings: $6,000/year (20%) with dramatically better privacy**

**Cost governance features in Console:**

- Per-user monthly spending caps (enforced by policy)
- Per-task cost logging with provider breakdown
- Department-level cost allocation
- Trend analysis and anomaly detection
- Budget alerts via Slack/Teams integration

**Key message:** "Save money AND get better security. It is not a trade-off."

**Visual suggestion:** A bar chart comparing annual costs for 500 seats across four competitors. IntentOS's bar is split into two colors: license (blue) and cloud API (lighter blue), showing the combined total is lower than ChatGPT Enterprise. Below the chart, three large numbers: "70% free" (local tasks), "$0.003" (average cloud task cost), "25-40%" (savings vs. flat-rate competitors). Keep the chart clean, no gridlines, no 3D effects.

**Speaker note:** "The CFO sees two things on this slide: the bill goes down, and the security goes up. That is a rare combination in enterprise software. The inference router is doing double duty -- it saves money and it keeps data local. Every task that runs on the local model is a task that never touches the cloud."

---

## SLIDE 9: Three-Tier Go-to-Market

### One Codebase. Three Markets. Same Security Promise.

IntentOS serves three distinct buyer personas from a single codebase with three deployment wrappers. The consumer tier feeds the enterprise funnel.

| | Consumer | SMB | Enterprise |
|---|---|---|---|
| **Buyer** | Individual user | Small business owner / IT generalist | CIO, CISO, IT Director |
| **AI Inference** | Local only (Ollama) | Local + cloud (smart routing) | On-prem models + cloud (policy-controlled) |
| **Deployment** | Self-install from intentos.dev | Self-serve + onboarding | IT-managed fleet via MDM |
| **Console** | None | Basic dashboard | Full Console (8 pages, policy engine, audit) |
| **Price** | Free | $15/seat/month | $35-45/seat/month |
| **Support** | Community / docs | Email + chat | Dedicated CSM + SLA |
| **Security** | Local-first by default | Local-first + cloud logging | Full policy engine + HMAC signing + compliance |

**The funnel logic:**

1. **Consumer (Free):** Individual users discover IntentOS, install it, use it daily. It becomes part of their workflow. When they use it at work, they become internal advocates. "I use this at home. Why can't we have this at the office?"

2. **SMB ($15/seat):** Small businesses adopt when a team lead or IT generalist signs up after trying the free tier. Self-serve onboarding, credit card billing, basic Console for cost tracking. Low friction, high conversion.

3. **Enterprise ($35-45/seat):** Large organizations adopt when the CISO or CIO evaluates IntentOS against Copilot and ChatGPT Enterprise. The IT Console, policy engine, and compliance mapping close the deal. Annual contract, dedicated CSM, SLA.

**The enterprise pitch (one sentence per persona):**

- **To the CISO:** "Your executives' devices are your biggest attack surface. IntentOS runs AI locally, and files never leave the perimeter."
- **To the CIO:** "Deploy AI to 5,000 seats in a week via MDM, with full policy control and audit trail from day one."
- **To the CFO:** "Spend less than Copilot, get better security than ChatGPT Enterprise, and track every dollar to the task level."
- **To the end user:** "It works like ChatGPT, but it's faster for simple tasks and your IT team actually approves it."

**Visual suggestion:** A funnel diagram flowing from top (Consumer - widest, labeled "Free, millions of users") through middle (SMB - medium, labeled "$15/seat, thousands of teams") to bottom (Enterprise - narrowest, labeled "$35-45/seat, large organizations"). Arrows showing the bottom-up adoption path. On the right side, the pricing table. Use green for Consumer, blue for SMB, dark blue/purple for Enterprise.

**Speaker note:** "This is the Slack playbook. Free users become advocates. Advocates bring it into the workplace. The workplace becomes an enterprise deal. But unlike Slack, we have a genuine security story that makes the enterprise sale easier, not harder."

---

## SLIDE 10: Implementation & Deployment

### From Pilot to Fleet in 30 Days

IntentOS is designed for the way enterprise IT actually deploys software: MDM push, staged rollout, policy-first.

**Deployment timeline:**

| Day | Activity | Outcome |
|---|---|---|
| Day 1 | IT receives .pkg (macOS) / .msi (Windows) + policy template JSON | Package ready for MDM |
| Day 1-2 | MDM push to pilot group (10 devices). Console configured with initial policy. | Pilot devices active, reporting to Console |
| Day 3-5 | Pilot users begin using IntentOS. Console fills with usage data, cost tracking, audit entries. | IT has real data to evaluate |
| Week 2 | IT reviews audit log, adjusts policies (tighten or relax agent access, set spending caps). Console proves compliance posture. | Policies tuned to org needs |
| Week 3 | Expand to department-level rollout (50-100 devices). Onboard department leads. | Broader adoption, departmental policies |
| Week 4 | Full fleet deployment. Sign enterprise agreement. Enable Slack/Teams/Splunk integrations. | Production deployment complete |

**Technical requirements (minimal):**

| Requirement | Specification |
|---|---|
| Operating System | macOS 12+ or Windows 10+ (64-bit) |
| RAM (minimum) | 8 GB (runs cloud-only mode for AI tasks) |
| RAM (recommended) | 16 GB (enables local AI via Ollama) |
| Disk space | 500 MB for app + 4-8 GB for local model |
| Network | Optional. Fully functional offline in Local Only mode. |
| Server infrastructure | None. Console is SaaS-hosted. On-prem Console available for air-gapped environments. |

**Integration with existing enterprise stack:**

- **MDM:** Deploy via Jamf, Intune, Mosyle, Kandji, or any MDM that supports .pkg/.msi
- **SSO/SAML:** Okta, Azure AD, OneLogin integration (Q3 2026 roadmap)
- **SIEM:** Splunk connector ships today. Elastic/Datadog on roadmap.
- **Messaging:** Slack and Teams alerts for policy violations, spend thresholds, security events
- **Ticketing:** Jira connector for auto-creating tickets on security events

**No server infrastructure required.** IntentOS Console is a hosted SaaS application. For organizations that require on-premise hosting (air-gapped environments, defense sector, regulated industries), an on-prem Console deployment is on the 2027 roadmap.

**Key message:** "Pilot in a day. Fleet in a month. No servers to stand up."

**Visual suggestion:** A horizontal timeline showing the 30-day deployment journey, from "Day 1: Package delivery" to "Week 4: Full fleet." Below the timeline, three icons representing the integration points: MDM logo, SIEM logo, messaging logos. Keep it clean and linear. The message is simplicity.

**Speaker note:** "Enterprise buyers always ask: how long until we're live? The answer is one day for the pilot. The .pkg goes through MDM like any other app. The policy template is a JSON file. There is no server to provision, no database to configure, no VPN to set up. The Console is SaaS. The app is native. The deployment is the same workflow IT already uses for every other tool."

---

## SLIDE 11: Traction & Roadmap

### What's Built Today. What's Coming Next.

IntentOS is not a pitch deck. It is a working product with a native app, an enterprise console, and over 1,500 automated tests.

**Shipped and working today:**

- Native macOS desktop app (Tauri framework, 120 MB, installs to /Applications)
- Local AI via Ollama (Gemma 4) with cloud routing to Anthropic Claude, OpenAI, and Google Gemini
- 6 capability agents: File, Browser, Document, System, Image, Media
- Voice input (Whisper STT) and voice output (Piper TTS), both running entirely on-device
- Chat-style UI with session persistence, markdown rendering, SSE streaming
- Enterprise policy engine with HMAC-signed policies
- Inference interceptor logging every cloud API call (provider, tokens, cost -- never prompt content)
- Telemetry reporter sending heartbeats to Console every 5 minutes
- IT Admin Console with 8 functional pages
- 1,504 automated tests passing, zero new dependencies added for enterprise features
- Landing page at intentos.dev, GitHub releases, macOS DMG distribution

**Roadmap:**

| Quarter | Milestone | Impact |
|---|---|---|
| **Q2 2026** | Windows app + code signing. First 3 enterprise pilots. Apple notarization. | Cross-platform. First revenue. App Store readiness. |
| **Q3 2026** | SSO/SAML (Okta, Azure AD). SIEM integration (Elastic, Datadog). Agent marketplace for third-party agents. | Enterprise access management. Broader SIEM coverage. Ecosystem growth. |
| **Q4 2026** | Rust core migration begins. WASM sandboxing for third-party agents. Mobile companion app (iOS/Android, view-only). | Performance and security hardened. Mobile access for executives. |
| **2027 H1** | On-prem Console for air-gapped environments. Industry-specific agent bundles (legal, finance, healthcare). | Defense/government market. Vertical expansion. |
| **2027 H2** | Agent SDK public release. Developer ecosystem. Multi-language agent support. | Platform play. Network effects. |

**Technical moat:**

The security-first, local-first architecture is not a feature that can be bolted on. Competitors who built cloud-first (ChatGPT, Copilot, Glean) would need to fundamentally redesign their inference pipeline, their data handling, and their deployment model to match IntentOS's privacy guarantees. This is a 12-18 month rebuild for an established team. The architecture is the moat.

**Visual suggestion:** Left half of the slide shows "Today" with a summary of what's shipped (app screenshot thumbnail, test count, agent count). Right half shows the roadmap as a timeline with quarterly milestones. Use a "building blocks" visual metaphor -- each quarter adds a layer. At the bottom, the moat statement in bold.

**Speaker note:** "We are not asking you to invest in an idea. The product is built. The tests pass. The app installs. What we are asking for is the capital to take this to market. Windows, code signing, and the first ten enterprise pilots."

---

## SLIDE 12: The Ask / Call to Action

### For Investors

"We are raising to accelerate enterprise go-to-market and achieve cross-platform readiness."

**Use of funds:**

| Allocation | Purpose | Timeline |
|---|---|---|
| Windows app + code signing | Cross-platform coverage, enterprise requirement | Q2 2026 |
| Enterprise sales (2 AEs + 1 SE) | Close first 10 enterprise pilots | Q2-Q3 2026 |
| Apple notarization + App Store | Distribution credibility | Q2 2026 |
| SOC 2 Type II certification | Compliance requirement for enterprise sales | Q3 2026 |
| SSO/SAML integration | Enterprise access management requirement | Q3 2026 |

**Milestones:**

- 50 enterprise seats deployed in 6 months
- 500 enterprise seats deployed in 12 months
- 3 signed enterprise contracts in 9 months
- 10,000+ consumer downloads in 12 months (funnel)

### For Enterprise Clients

**Start a free 30-day pilot with 10 seats.**

- We configure the Console and policy template for your organization
- You push the .pkg to 10 devices via your existing MDM
- In 30 days, you have real usage data, audit trail, and cost analysis
- No commitment. No credit card. No server setup.

**See the ROI for your organization:** intentos.dev/roi

### Contact

- Web: intentos.dev
- Email: hello@intentos.dev
- GitHub: github.com/pocProjectWorkspace/intentos

### Closing Line

**"Language is the interface. Security is the foundation. The file never leaves."**

**Visual suggestion:** Clean, minimal slide. The ask (for investors or clients, depending on audience) in large text at the top. Below it, the milestone targets or pilot offer. At the bottom, contact information and the closing line. No clutter. This slide should feel like a handshake.

**Speaker note:** "We built this because we believe AI should make people more productive without making them less secure. The technology exists to run powerful models on consumer hardware. The architecture exists to keep files local. The Console exists to give IT the control they need. What's missing is the go-to-market engine. That's what we're here to build together."

---

## APPENDIX A: Technical Architecture Deep Dive

### For technical due diligence conversations

**Full 9-layer architecture:**

| Layer | Name | Responsibility |
|---|---|---|
| 1 | Input Layer | Voice (Whisper STT), text, file attachments |
| 2 | Intent Kernel | NLP parsing, intent classification, ambiguity resolution |
| 3 | RAG Context | Three-index semantic memory (files, tasks, user profile) |
| 4 | Inference Router | Complexity scoring, local/cloud routing, cost optimization |
| 5 | Agent Scheduler | Subtask decomposition, dependency resolution, execution orchestration |
| 6 | Agent Layer | Six specialized agents with ACP contract compliance |
| 7 | Security Pipeline | Leak detection, path grant enforcement, sandbox policies |
| 8 | Output Layer | Response assembly, markdown rendering, voice output (Piper TTS) |
| 9 | Telemetry Layer | Usage tracking, Console reporting, audit logging |

**Agent Communication Protocol (ACP):**

Every agent implements one function:

```python
def run(input: dict) -> dict:
    # input = {"action": str, "params": dict, "context": dict}
    # returns {"status": "success"|"error"|"confirmation_required",
    #          "result": any, "metadata": dict}
```

Context injected by scheduler includes: user identity, workspace path, granted paths, task ID, dry-run flag, and optional LLM client.

**Inference router decision tree:**

```
Task arrives
    |
    v
Complexity Score = f(token_count, task_type, ambiguity, context_depth, agent_count)
    |
    +-- Score LOW/MEDIUM --> Local model (Ollama, Gemma 4) --> $0.00
    |
    +-- Score HIGH --> Check privacy mode
                        |
                        +-- "Local Only" --> Local model (may be slower/less accurate)
                        |
                        +-- "Smart Routing" --> Ask user --> Cloud API if consented
                        |
                        +-- "Performance" --> Cloud API directly --> logged + costed
```

**RAG system (three indexes):**

| Index | Technology | Content | Query Strategy |
|---|---|---|---|
| File Index | ChromaDB + nomic-embed-text | Semantic embeddings of user's filesystem | Top-3 relevant files per query |
| Task Index | ChromaDB + embeddings | History of completed tasks with outcomes | Last 2 similar tasks for context |
| User Profile | Structured JSON | Inferred preferences, frequent folders, contacts | Always injected, low token cost |

**Token efficiency:** Three-layer progressive disclosure (Search -> Timeline -> Get) achieves approximately 10x token savings vs. fetching full context for every query.

---

## APPENDIX B: Competitive Landscape

### Feature Comparison Matrix

| Feature | IntentOS | ChatGPT Enterprise | Microsoft Copilot | Glean | Google Gemini Business |
|---|---|---|---|---|---|
| **Local AI (on-device)** | Yes (70% of tasks) | No | No | No | No |
| **Files never leave device** | Yes (architectural) | No | No | No | No |
| **IT Admin Console** | Yes (8 pages) | Basic admin | Microsoft Admin Center | Yes | Google Admin |
| **Signed Policy Engine** | Yes (HMAC-SHA256) | No | Intune policies | No | Google Workspace policies |
| **Per-task Audit Trail** | Yes (device-level) | Basic logs | Microsoft Purview | Yes | Google Vault |
| **Cost per Seat** | $35-45/month | $60/month | $30/month | $10-25/month | $20/month |
| **Offline Mode** | Full functionality | No | No | No | No |
| **Voice I/O (local)** | Yes (Whisper + Piper) | Voice input only (cloud) | Voice input only (cloud) | No | Voice input only (cloud) |
| **Agent Execution System** | Yes (6 agents) | Plugins/GPTs | Copilot agents | Connectors | Extensions |
| **Open-source Models** | Yes (Ollama) | No (OpenAI only) | No (Azure OpenAI) | No | No (Google only) |
| **Per-task Cost Tracking** | Yes | No | No | No | No |
| **Credential Leak Detection** | Yes (3-stage pipeline) | No | No | No | No |

**Where IntentOS wins decisively:** Privacy (files never leave), cost efficiency (70% free local inference), offline capability, policy granularity (per-agent, per-model, per-spend), and audit depth (per-action on-device logging).

**Where competitors have advantages today:** Ecosystem integration depth (Microsoft 365, Google Workspace), brand recognition, existing enterprise relationships, broader model selection.

**The argument:** Competitors cannot retrofit local-first architecture. IntentOS can add integrations. The harder problem is already solved.

---

## APPENDIX C: Security Architecture Detail

### For CISO technical review

**Two-user daemon model:**

```
HUMAN USER (e.g., john)           --> owns files, controls permission grants
    |
    | grants specific directory paths via ~/.intentos/grants.json
    |
    v
INTENTOS DAEMON (_intentos)       --> executes agents, has ZERO default filesystem access
    |
    | OS-level ACLs enforce boundaries (setfacl on Linux, chmod +a on macOS)
    |
    v
HOST FILESYSTEM                   --> only explicitly granted paths are accessible
```

- Daemon runs with `NoNewPrivileges` flag (Linux) or equivalent macOS restrictions
- No interactive login shell for daemon user
- Grants are stored in `~/.intentos/grants.json`, editable only by the human user
- Every file operation checks granted paths before execution -- no exceptions

**Three-tier sandbox policies:**

| Policy | Filesystem Access | Network Access | Use Case | Agents |
|---|---|---|---|---|
| ReadOnly | /workspace read-only | Proxied (domain allowlist) | Analysis, reading, search | File Agent (read), System Agent |
| WorkspaceWrite | /workspace read/write | Proxied (domain allowlist) | Most creation tasks | Document Agent, Image Agent, Media Agent |
| FullAccess | Full host access | Unrestricted | System operations | System Agent (requires double opt-in) |

**Credential injection architecture:**

Agents never receive API keys directly. The security pipeline injects credentials at the proxy boundary:

```
Agent requests cloud AI call
    |
    v
Security Pipeline intercepts
    |
    v
Retrieves API key from OS keychain (macOS Keychain, GNOME Keyring, Windows Credential Manager)
    |
    v
Injects credential into HTTPS request at proxy layer
    |
    v
Agent receives response -- never sees the key
```

**Leak detection pipeline (detailed):**

| Stage | Trigger | Patterns Detected | Action on Match |
|---|---|---|---|
| Stage 1: Input | Before any processing | API keys, PEM content, bearer tokens, passwords in plain text | Block (critical) or Warn (medium) |
| Stage 2: LLM Output | After cloud AI response | Hallucinated credentials, leaked training data, injection attempts | Redact (high) or Block (critical) |
| Stage 3: Agent Output | Before result display | File contents matching secret patterns, environment variables, key files | Block (critical) with user notification |

**Sensitive file protection (always enforced):**

Operations are blocked on files matching: `.env`, `*.pem`, `*.key`, `*.p12`, `*.pfx`, `credentials.*`, `*secret*`, `*password*`, `*token*`, `id_rsa`, `id_ed25519`, `*.keystore`

The user is warned. The operation does not proceed silently. This cannot be overridden by policy.

---

*Document prepared for IntentOS pitch deck generation. Each slide section contains sufficient detail for visual design and speaker notes. Last updated: April 2026.*

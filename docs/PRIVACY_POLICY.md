# IntentOS Privacy Policy

**Effective: April 2026**

---

## 1. Introduction

IntentOS is a local-first AI execution platform. Your files, your prompts, your data — they stay on your device by default. This policy explains what we collect, what we never collect, and how your information is handled across our Consumer, SMB, and Enterprise tiers.

We believe privacy is not a feature — it is a right. IntentOS was built from the ground up to process your data locally, on hardware you control.

---

## 2. Data We Never Collect

The following categories of data **never leave your device**, regardless of your subscription tier or configuration:

- **File contents** — Documents, images, spreadsheets, code, and any other files processed by IntentOS remain entirely on your local machine.
- **File paths** — The full paths to your files are never transmitted to any external service.
- **Document text** — Text extracted from documents for analysis is processed locally and never sent externally.
- **User prompts** (when using local models) — When IntentOS routes your task to a local AI model, your instructions never leave your device.
- **Personal files** — IntentOS does not scan, index, or transmit personal files beyond what you explicitly ask it to process.
- **Browsing history** — IntentOS does not monitor or collect your web browsing activity.
- **RAG index data** — The semantic search indexes that help IntentOS understand your files are stored locally in `~/.intentos/` and never transmitted.

---

## 3. Data Collected by IntentOS Desktop (Consumer & SMB)

**By default, IntentOS Desktop collects no telemetry data.**

When telemetry is explicitly enabled (opt-in for Consumer/SMB, policy-managed for Enterprise), the following **aggregated, non-personal metrics** may be collected:

- **Usage counts** — Number of tasks processed per day (not the content of those tasks).
- **AI model usage** — Which models were used, approximate token counts, and associated costs. This helps optimize routing and cost management.
- **Application health** — Crash reports, startup time, and performance metrics.
- **Feature usage** — Which IntentOS features are used (e.g., voice input, file search) to guide product development.

**We never collect:** file contents, prompts, file paths, document text, personal information, or any data that could identify the specific work you are doing.

---

## 4. Data Collected by IntentOS Console (Enterprise)

Organizations using IntentOS Console for fleet management may collect the following from managed devices:

- **Device registration** — Hostname, operating system, IntentOS version, and device identifier.
- **Aggregated usage metrics** — Task counts, model usage statistics, and cost data.
- **Policy compliance events** — Whether devices comply with organizational AI policies (e.g., privacy mode settings, approved model lists).
- **Security events** — Policy violations, blocked operations, and security pipeline statistics.

**Important:** Console telemetry is sent to **your organization's Console instance** — either self-hosted on your infrastructure or hosted by IntentOS on your behalf. IntentOS Inc. does not have access to Enterprise telemetry data stored in self-hosted Console instances.

---

## 5. Cloud AI Providers

When IntentOS is configured for "Smart Routing" or "Performance" mode, certain tasks may be sent to cloud AI providers (such as Anthropic, OpenAI, or Google). In these cases:

- **The prompt text** is sent to the cloud provider to generate a response.
- **File contents are processed locally** — only summaries, queries, or extracted metadata may be included in the prompt. Raw file contents are never transmitted.
- **You are informed before each cloud call** — IntentOS will indicate when a task is being routed to a cloud provider.
- **You can prevent all cloud calls** — Setting your privacy mode to "Local Only" ensures no data is ever sent to external AI providers.

Each cloud AI provider has its own privacy policy and data handling practices. We encourage you to review:

- Anthropic: https://www.anthropic.com/privacy
- OpenAI: https://openai.com/privacy
- Google AI: https://ai.google/responsibility/privacy/

---

## 6. Data Storage and Encryption

### Local Storage

- All IntentOS data is stored in `~/.intentos/` on your device.
- Stored credentials are encrypted with **AES-256-GCM** using keys derived via **HKDF-SHA256**.
- Where available, encryption keys are stored in your operating system's native keychain (macOS Keychain, GNOME Keyring, Windows Credential Manager).
- No credentials or API keys are stored in plain text files.

### Data in Transit

- All network communications use **TLS 1.3** encryption.
- Console telemetry is transmitted over HTTPS with device-token authentication.

### Console Storage (Enterprise)

- Console data is stored in PostgreSQL with encryption at rest.
- Access is controlled through organizational authentication and role-based permissions.

---

## 7. Your Rights

You have the right to:

- **Access your data** — All local data is stored in `~/.intentos/` and can be inspected at any time.
- **Delete your data** — Delete the `~/.intentos/` directory to remove all IntentOS data from your device. For Enterprise Console data, contact your organization's IT administrator.
- **Export your data** — Use IntentOS backup features to export your data at any time.
- **Control telemetry** — Enable or disable telemetry collection through IntentOS settings.
- **Choose your privacy mode** — Select "Local Only" to ensure no data ever leaves your device.

---

## 8. Third Parties

- **We do not sell your data.** IntentOS Inc. does not sell, rent, or trade personal information or usage data to third parties.
- **Cloud AI providers** process prompt data according to their own privacy policies when you opt into cloud routing.
- **Console telemetry** is sent only to your organization's Console instance, not to IntentOS Inc. or any third party.
- **No advertising.** IntentOS does not display ads or share data with advertising networks.

---

## 9. Children

IntentOS is not designed for or directed at children under the age of 13. We do not knowingly collect personal information from children. If you believe a child has provided us with personal information, please contact us at the address below.

---

## 10. Changes to This Policy

We may update this privacy policy from time to time. When we make material changes:

- We will update the "Effective" date at the top of this document.
- We will notify users through the IntentOS application.
- For Enterprise customers, changes will be communicated through Console and your account representative.

---

## 11. Contact

If you have questions about this privacy policy or IntentOS data practices:

- **Email:** contact@intentos.dev
- **Website:** https://intentos.dev/privacy

---

*IntentOS — Your data stays on your device. That is not a feature. It is the architecture.*

# IntentOS First Launch Experience
### *What the user sees, hears, and feels from download to first task*

---

## Design Philosophy

The first launch experience has one job: get the user to their first completed task as fast as possible, with as few decisions as possible, feeling like they made the right choice downloading this.

Every screen in this flow is governed by three rules:
1. **One decision per screen.** Never ask two things at once.
2. **No technical vocabulary.** If a sentence contains the words "model", "API", "inference", "token", or "parameter" — rewrite it.
3. **Show progress, not waiting.** Every loading state has a plain-language explanation of what's happening and why.

---

## Screen by Screen

---

### Screen 1 — Welcome

```
┌─────────────────────────────────────────────────────┐
│                                                      │
│                                                      │
│                    IntentOS                          │
│                                                      │
│         Your computer, finally on your side.         │
│                                                      │
│                                                      │
│   ┌─────────────────────────────────────────────┐   │
│   │           Get started  →                    │   │
│   └─────────────────────────────────────────────┘   │
│                                                      │
│                                                      │
└─────────────────────────────────────────────────────┘
```

No feature list. No bullet points. No version numbers. Just the name, one line of copy, one button.

---

### Screen 2 — The One Choice

This is the only real decision in the entire setup flow. Everything else is automatic.

```
┌─────────────────────────────────────────────────────┐
│                                                      │
│   How would you like IntentOS to think?              │
│                                                      │
│   ┌─────────────────────────────────────────────┐   │
│   │  ●  Private                                  │   │
│   │                                              │   │
│   │     Runs entirely on your device.            │   │
│   │     Works offline. Nothing leaves            │   │
│   │     your computer. Ever.                     │   │
│   │                                              │   │
│   │     One-time setup: ~2GB download            │   │
│   └─────────────────────────────────────────────┘   │
│                                                      │
│   ┌─────────────────────────────────────────────┐   │
│   │  ○  Connected                                │   │
│   │                                              │   │
│   │     Uses your AI account for everything.     │   │
│   │     No download needed. Requires internet.   │   │
│   │                                              │   │
│   │     You'll need an API key to continue       │   │
│   └─────────────────────────────────────────────┘   │
│                                                      │
│                  Continue  →                         │
│                                                      │
└─────────────────────────────────────────────────────┘
```

**"Private" is selected by default.** Most users should be here. The 2GB disclosure is shown upfront so there's no surprise. The word "API key" appears on the Connected option so technical users self-select.

---

### Screen 3A — Private Mode Setup (downloading)

```
┌─────────────────────────────────────────────────────┐
│                                                      │
│   Setting up your thinking engine                    │
│                                                      │
│   This happens once and takes a few minutes.         │
│   After this, IntentOS works instantly — even        │
│   without an internet connection.                    │
│                                                      │
│   ████████████████████░░░░░░░░░░  64%               │
│                                                      │
│   Downloading your local AI...                       │
│                                                      │
│                                                      │
│   ─────────────────────────────────────────────     │
│   While you wait:                                    │
│                                                      │
│   IntentOS will handle things like:                  │
│   "Rename all my photos by date"                     │
│   "Find the invoice from last month"                 │
│   "Clean up my Downloads folder"                     │
│   ...right here on your device, instantly.           │
│                                                      │
└─────────────────────────────────────────────────────┘
```

The loading screen teaches the user what IntentOS does while they wait — so by the time setup is done, they already have their first task in mind. No spinner with nothing to read. No technical progress details.

**Progress label copy (cycles through during download):**
- "Downloading your local AI..."
- "Almost there — unpacking..."
- "Running a quick test..."
- "Ready in a moment..."

---

### Screen 3B — Connected Mode Setup (API key entry)

```
┌─────────────────────────────────────────────────────┐
│                                                      │
│   Connect your AI account                            │
│                                                      │
│   IntentOS works with the AI service of              │
│   your choice. Paste your API key below.             │
│                                                      │
│   ┌─────────────────────────────────────────────┐   │
│   │  sk-...                                      │   │
│   └─────────────────────────────────────────────┘   │
│                                                      │
│   Supported: Anthropic · OpenAI · Gemini             │
│   or any compatible service                          │
│                                                      │
│   Your key is stored only on this device.            │
│   IntentOS never transmits it anywhere else.         │
│                                                      │
│                  Connect  →                          │
│                                                      │
│   Don't have a key?  Get one here                    │
│                                                      │
└─────────────────────────────────────────────────────┘
```

The trust line ("stored only on this device") is non-negotiable copy. It must appear on this screen, in plain sight, not in a terms doc nobody reads.

---

### Screen 4 — Ready

```
┌─────────────────────────────────────────────────────┐
│                                                      │
│                                                      │
│                  You're ready.                       │
│                                                      │
│          Just tell IntentOS what to do.              │
│                                                      │
│                                                      │
│   ┌─────────────────────────────────────────────┐   │
│   │  Try: "Show me my largest files"         →  │   │
│   └─────────────────────────────────────────────┘   │
│                                                      │
│                                                      │
└─────────────────────────────────────────────────────┘
```

No tutorial. No feature tour. No "here are 6 things you can do" carousel. Just the task shell, pre-filled with a suggested first task that works on any machine, shows immediate value, and completes in under 5 seconds.

The user hits enter. They see a result. Setup is done. They're a user.

---

## First Task Design

The suggested first task — *"Show me my largest files"* — is chosen deliberately:

It requires only `file_agent` which is always available. It returns a result in under 3 seconds on any machine. It surfaces something genuinely useful (most people have junk taking up space they don't know about). It requires no typing from the user if they just hit enter. And it proves the core promise — no app, no menu, just a sentence.

**Other acceptable first task suggestions by user context:**
- If many photos detected in home folder: *"Show me my photos from this year"*
- If many documents detected: *"What documents have I edited recently?"*
- Default fallback: *"Show me my largest files"*

IntentOS should detect the user's file landscape during the setup download and choose the most relevant first task suggestion automatically.

---

## Error States

### If model download fails mid-way

```
   The download stopped — probably a network hiccup.

   ┌──────────────────────┐  ┌──────────────────────┐
   │    Try again         │  │    Use cloud instead  │
   └──────────────────────┘  └──────────────────────┘
```

Never say: "Error 503", "Connection timeout", "Failed to pull manifest". Always give two paths forward.

### If API key is invalid

```
   That key didn't work. Double-check it was copied
   in full — they're easy to accidentally trim.

   [  Re-enter key  ]     [  Get a new key  ]
```

Assume user error is accidental, never intentional. Tone is helpful, not accusatory.

### If first task fails

```
   I couldn't do that one — something went wrong
   on my end, not yours.

   [  Try a different task  ]    [  See what happened  ]
```

"See what happened" opens a plain-language log, not a stack trace.

---

## Settings Accessible After First Launch

Users can change their thinking mode at any time from settings. The transition is smooth — switching from Connected to Private triggers the model download flow inline, not a full re-setup.

```
Settings → Thinking Engine

How IntentOS thinks:

● Private        Running on your device  [Change]
  Model: Phi-3 Mini

  Upgrade local model:
  ○ Mistral 7B (better reasoning)   [Install — needs 8GB RAM]
  ○ Qwen2.5 3B (multilingual)       [Install]
  ○ Custom                          [Add model name]

──────────────────────────────────────────

Switch to Connected mode            [Switch]
Uses your AI account. Requires internet.
```

---

## Copy Principles for the Entire Flow

These apply to every word a user reads during first launch and beyond.

**Use:** your device, online, thinking, working, ready, connected, private
**Never use:** model, API, inference, token, parameter, LLM, SLM, weights, quantized

**Tone:** calm, direct, confident. Like a knowledgeable friend setting up your new computer for you. Not corporate. Not over-explained. Not apologetic.

**Error tone:** always assume the problem is fixable and the user is smart. Never blame. Always give a next step.

---

*IntentOS First Launch — designed for the person who just wants to get things done.*

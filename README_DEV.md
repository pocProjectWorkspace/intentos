# IntentOS — Local Development Setup

## Prerequisites

- **Python 3.9+** (`python3 --version` to check)
- **Git**
- An **Anthropic API key** — get one at https://console.anthropic.com/settings/keys

## Getting started

### 1. Clone the repo

```bash
git clone https://github.com/your-org/intentos.git
cd intentos
```

### 2. Run the setup script

```bash
bash setup.sh
```

This will:
- Create a Python virtual environment at `.venv/`
- Activate it and install all dependencies from `requirements.txt`
- Copy `.env.example` to `.env` if `.env` doesn't exist yet

### 3. Add your API key

Open `.env` and replace the placeholder:

```
ANTHROPIC_API_KEY=sk-ant-...your-real-key...
```

### 4. Run the Intent Kernel

```bash
source .venv/bin/activate
python3 core/kernel.py
```

You'll see a prompt:

```
IntentOS Kernel v0.1.0
Type a task in natural language. Type 'exit' or 'quit' to stop.

intentos>
```

Type any instruction in plain English. The kernel will return a structured intent object showing how IntentOS would decompose it.

### Example

```
intentos> rename all .jpeg files in my Downloads folder to use today's date as a prefix
```

Returns a JSON intent object with `raw_input`, `intent`, and an ordered `subtasks` array.

## Project structure

```
intentos/
├── core/
│   └── kernel.py          ← Intent Kernel CLI (Phase 1 entry point)
├── capabilities/          ← Agent specs and architecture docs
├── docs/                  ← Vision, spec, and design docs
├── requirements.txt       ← Python dependencies
├── .env.example           ← Environment variable template
├── .gitignore
├── setup.sh               ← One-command local setup
└── README_DEV.md          ← This file
```

## Notes

- **Never commit `.env`** — it is excluded in `.gitignore`.
- The kernel currently uses `claude-sonnet-4-20250514` by default. Override by uncommenting `ANTHROPIC_MODEL` in `.env`.
- This is Phase 1 (CLI only). See `capabilities/ARCHITECTURE.md` for the full roadmap.

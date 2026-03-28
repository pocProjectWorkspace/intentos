# Installing IntentOS

## Quick Install (recommended)

```bash
curl -sSL https://raw.githubusercontent.com/pocProjectWorkspace/intentos/main/distribution/install.sh | bash
```

## Manual Install

### Prerequisites
- Python 3.9+
- git

### Steps
1. Clone: `git clone https://github.com/pocProjectWorkspace/intentos.git`
2. Setup: `cd intentos && bash setup.sh`
3. Start: `source .venv/bin/activate && intentos`

## Docker

```bash
cd distribution/docker
docker-compose up
```

## Homebrew (macOS)

```bash
brew tap pocProjectWorkspace/intentos
brew install intentos
```

## What happens on first run

1. IntentOS detects your hardware
2. You choose an AI provider (Anthropic/OpenAI/Gemini/Local)
3. You paste your API key (stored encrypted, never in plaintext)
4. You choose a privacy mode
5. You're ready — just type what you want to do

## Optional: Local AI (no cloud needed)

```bash
# Install Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# Pull a model
ollama pull llama3.1:8b

# Start IntentOS in Private mode
intentos
# Choose [1] Private when asked
```

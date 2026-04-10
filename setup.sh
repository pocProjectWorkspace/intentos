#!/usr/bin/env bash
# IntentOS — Setup Script
# Usage: bash setup.sh
#        bash setup.sh --silent              (non-interactive, skip Ollama)
#        bash setup.sh --silent --with-ollama (non-interactive, install Ollama)
#
# This script sets up IntentOS for local development or first-time use.
# It creates a virtual environment, installs dependencies, and optionally
# sets up Ollama for local AI inference.

set -e

VENV_DIR=".venv"
ENV_FILE=".env"
ENV_EXAMPLE=".env.example"

# Parse flags
SILENT=false
WITH_OLLAMA=false
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --silent|--non-interactive) SILENT=true ;;
        --with-ollama) WITH_OLLAMA=true ;;
    esac
    shift
done

echo ""
echo "  ╔══════════════════════════════════════════╗"
echo "  ║            IntentOS Setup                ║"
echo "  ║    Your computer, finally on your side.  ║"
echo "  ╚══════════════════════════════════════════╝"
echo ""

# 1. Check Python version
if ! command -v python3 &>/dev/null; then
    echo "  [!!] Python 3 is required. Install from https://python.org"
    exit 1
fi

PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "  [ok] Python ${PYTHON_VERSION} detected"

# 2. Create virtual environment
if [ -d "$VENV_DIR" ]; then
    echo "  [ok] Virtual environment already exists at $VENV_DIR"
else
    echo "  [..] Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
    echo "  [ok] Virtual environment created at $VENV_DIR"
fi

# 3. Activate it
echo "  [..] Activating virtual environment..."
source "$VENV_DIR/bin/activate"
echo "  [ok] Activated ($VENV_DIR/bin/python)"

# 4. Install core dependencies
echo "  [..] Installing core dependencies..."
pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet
echo "  [ok] Core dependencies installed"

# 5. Optional extras
if [ "$SILENT" = false ]; then
    echo ""
    echo "  Optional capabilities:"
    echo "    [1] OpenAI support      (openai)"
    echo "    [2] Gemini support      (google-generativeai)"
    echo "    [3] Voice input         (SpeechRecognition)"
    echo "    [4] All of the above"
    echo "    [5] Skip (install later with: pip install -e '.[all]')"
    echo ""
    read -p "  Install optional extras? [1-5, default=5]: " -r EXTRAS_CHOICE
    echo ""

    case "${EXTRAS_CHOICE:-5}" in
        1) pip install --quiet "openai>=1.0.0" && echo "  [ok] OpenAI support installed" ;;
        2) pip install --quiet "google-generativeai>=0.3.0" && echo "  [ok] Gemini support installed" ;;
        3) pip install --quiet "SpeechRecognition>=3.10.0" && echo "  [ok] Voice input installed" ;;
        4) pip install --quiet "openai>=1.0.0" "google-generativeai>=0.3.0" "SpeechRecognition>=3.10.0" && echo "  [ok] All extras installed" ;;
        5|*) echo "  [ok] Skipped optional extras" ;;
    esac
else
    echo "  [ok] Skipped optional extras (silent mode)"
fi

# 6. Ollama — local AI engine
OLLAMA_SETUP=false
if [ "$SILENT" = false ]; then
    echo ""
    echo "  Local AI Engine (Ollama):"
    echo "    IntentOS can run AI entirely on your device."
    echo "    This requires Ollama and a one-time download (~2-4 GB)."
    echo ""
    read -p "  Set up local AI? [y/N]: " -r OLLAMA_CHOICE
    echo ""
    if [[ "${OLLAMA_CHOICE:-n}" =~ ^[Yy] ]]; then
        OLLAMA_SETUP=true
    fi
elif [ "$WITH_OLLAMA" = true ]; then
    OLLAMA_SETUP=true
fi

if [ "$OLLAMA_SETUP" = true ]; then
    # Detect or install Ollama
    if command -v ollama &>/dev/null; then
        echo "  [ok] Ollama already installed ($(ollama --version 2>/dev/null || echo 'unknown version'))"
    else
        echo "  [..] Installing Ollama..."
        if command -v brew &>/dev/null; then
            brew install ollama --quiet 2>/dev/null && echo "  [ok] Ollama installed via Homebrew" || {
                echo "  [..] Trying alternative installer..."
                curl -fsSL https://ollama.com/install.sh | sh && echo "  [ok] Ollama installed" || {
                    echo "  [!!] Could not install Ollama. Install manually: https://ollama.com/download"
                }
            }
        else
            curl -fsSL https://ollama.com/install.sh | sh && echo "  [ok] Ollama installed" || {
                echo "  [!!] Could not install Ollama. Install manually: https://ollama.com/download"
            }
        fi
    fi

    # Pull models via the OllamaManager module
    if command -v ollama &>/dev/null; then
        echo "  [..] Preparing local AI..."
        python3 -m core.inference.ollama_manager --setup auto || {
            echo "  [!!] Model setup had issues — you can retry later with:"
            echo "       python3 -m core.inference.ollama_manager --setup auto"
        }
        echo ""
    fi
fi

# 7. Ensure .env exists
if [ -f "$ENV_FILE" ]; then
    echo "  [ok] .env file found"
else
    if [ -f "$ENV_EXAMPLE" ]; then
        cp "$ENV_EXAMPLE" "$ENV_FILE"
        echo ""
        echo "  ============================================="
        echo "  ACTION REQUIRED"
        echo "  .env was created from .env.example."
        echo "  Open .env and set your API key, or"
        echo "  IntentOS will prompt you on first run."
        echo "  ============================================="
        echo ""
    else
        echo "  [!!] .env.example not found — .env will be created on first run"
    fi
fi

# 8. Install as editable package (enables 'intentos' command)
echo "  [..] Installing IntentOS as package..."
pip install --quiet -e . 2>/dev/null || echo "  [!!] Editable install skipped (pyproject.toml may be missing)"

echo ""
echo "  Setup complete!"
echo ""
echo "  To start IntentOS:"
echo "    source $VENV_DIR/bin/activate"
echo "    intentos"
echo ""
echo "  Or run directly:"
echo "    python3 core/kernel_v2.py"
echo ""

#!/usr/bin/env bash
# IntentOS — Local development setup
# Usage: bash setup.sh

set -e

VENV_DIR=".venv"
ENV_FILE=".env"
ENV_EXAMPLE=".env.example"

echo "=== IntentOS Setup ==="
echo ""

# 1. Create virtual environment
if [ -d "$VENV_DIR" ]; then
    echo "[ok] Virtual environment already exists at $VENV_DIR"
else
    echo "[..] Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
    echo "[ok] Virtual environment created at $VENV_DIR"
fi

# 2. Activate it
echo "[..] Activating virtual environment..."
source "$VENV_DIR/bin/activate"
echo "[ok] Activated ($VENV_DIR/bin/python)"

# 3. Install dependencies
echo "[..] Installing dependencies from requirements.txt..."
pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet
echo "[ok] Dependencies installed"

# 4. Ensure .env exists
if [ -f "$ENV_FILE" ]; then
    echo "[ok] .env file found"
else
    if [ -f "$ENV_EXAMPLE" ]; then
        cp "$ENV_EXAMPLE" "$ENV_FILE"
        echo ""
        echo "============================================="
        echo "  ACTION REQUIRED"
        echo "  .env was created from .env.example."
        echo "  Open .env and set your ANTHROPIC_API_KEY."
        echo "============================================="
        echo ""
    else
        echo "[!!] .env.example not found — cannot create .env"
        exit 1
    fi
fi

echo ""
echo "Setup complete. To start:"
echo "  source $VENV_DIR/bin/activate"
echo "  python3 core/kernel.py"
echo ""

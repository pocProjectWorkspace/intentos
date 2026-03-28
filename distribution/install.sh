#!/usr/bin/env bash
set -euo pipefail

# IntentOS Installer
# Usage: curl -sSL https://get.intentos.dev/install.sh | bash

INTENTOS_VERSION="2.0.0"
INSTALL_DIR="${INTENTOS_HOME:-$HOME/.intentos-app}"
REPO_URL="https://github.com/pocProjectWorkspace/intentos.git"

echo ""
echo "  ╔══════════════════════════════════════════╗"
echo "  ║         IntentOS Installer v${INTENTOS_VERSION}        ║"
echo "  ║    Your computer, finally on your side.   ║"
echo "  ╚══════════════════════════════════════════╝"
echo ""

# Check Python
if ! command -v python3 &>/dev/null; then
    echo "  ❌ Python 3 is required but not found."
    echo "     Install from: https://python.org"
    exit 1
fi

PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "  ✓ Python ${PYTHON_VERSION} found"

# Check git
if ! command -v git &>/dev/null; then
    echo "  ❌ git is required but not found."
    exit 1
fi
echo "  ✓ git found"

# Clone or update
if [ -d "$INSTALL_DIR" ]; then
    echo "  Updating existing installation..."
    cd "$INSTALL_DIR" && git pull --quiet
else
    echo "  Downloading IntentOS..."
    git clone --quiet --depth 1 "$REPO_URL" "$INSTALL_DIR"
fi

cd "$INSTALL_DIR"

# Create venv
echo "  Setting up environment..."
python3 -m venv .venv
source .venv/bin/activate

# Install
pip install --quiet --upgrade pip
pip install --quiet -e ".[all]"

echo ""
echo "  ✅ IntentOS installed successfully!"
echo ""
echo "  To start:"
echo "    cd $INSTALL_DIR"
echo "    source .venv/bin/activate"
echo "    intentos"
echo ""
echo "  Or add to your PATH:"
echo "    echo 'alias intentos=\"$INSTALL_DIR/.venv/bin/intentos\"' >> ~/.zshrc"
echo "    source ~/.zshrc"
echo "    intentos"
echo ""

# Offer to run first-time setup now
read -p "  Start IntentOS now? [Y/n] " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]] || [[ -z $REPLY ]]; then
    intentos
fi

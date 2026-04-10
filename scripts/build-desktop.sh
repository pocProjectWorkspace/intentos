#!/usr/bin/env bash
# Build the IntentOS desktop app for macOS.
#
# Prerequisites:
#   - Rust toolchain (rustup.rs)
#   - Node.js 18+
#   - Python 3.9+ with pyinstaller
#   - Xcode Command Line Tools (macOS)
#
# Usage:
#   bash scripts/build-desktop.sh          # lite installer
#   bash scripts/build-desktop.sh --full   # full installer (bundles Ollama)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DESKTOP_DIR="$PROJECT_ROOT/ui/desktop"
FULL_BUILD=false

if [[ "${1:-}" == "--full" ]]; then
    FULL_BUILD=true
fi

echo ""
echo "  IntentOS Desktop Build"
echo "  ======================"
echo ""

# 1. Check prerequisites
echo "  [..] Checking prerequisites..."
command -v cargo &>/dev/null || { echo "  [!!] Rust not found. Install: https://rustup.rs"; exit 1; }
command -v node &>/dev/null || { echo "  [!!] Node.js not found. Install: https://nodejs.org"; exit 1; }
command -v python3 &>/dev/null || { echo "  [!!] Python 3 not found."; exit 1; }
echo "  [ok] All prerequisites found"

# 2. Build Python sidecar
echo "  [..] Building Python sidecar..."
pip install pyinstaller --quiet 2>/dev/null
python3 "$SCRIPT_DIR/build-sidecar.py"
echo ""

# 3. Install frontend dependencies
echo "  [..] Installing frontend dependencies..."
cd "$DESKTOP_DIR"
npm install --silent 2>/dev/null
echo "  [ok] Frontend deps installed"

# 4. Build Tauri app
echo "  [..] Building Tauri desktop app..."
if [ "$FULL_BUILD" = true ]; then
    # Download Ollama for bundling
    echo "  [..] Downloading Ollama for bundling..."
    OLLAMA_DIR="$DESKTOP_DIR/src-tauri/resources"
    mkdir -p "$OLLAMA_DIR"
    # macOS: download Ollama binary
    curl -fsSL "https://ollama.com/download/ollama-darwin" -o "$OLLAMA_DIR/ollama" 2>/dev/null || {
        echo "  [!!] Could not download Ollama binary. Building lite variant instead."
        FULL_BUILD=false
    }
    if [ "$FULL_BUILD" = true ]; then
        chmod +x "$OLLAMA_DIR/ollama"
        echo "  [ok] Ollama bundled"
        npm run tauri build -- --config src-tauri/tauri.full.conf.json
    else
        npm run tauri build
    fi
else
    npm run tauri build
fi

echo ""
echo "  Build complete!"
echo ""

# Find and display output
DMG=$(find "$DESKTOP_DIR/src-tauri/target/release/bundle/dmg" -name "*.dmg" 2>/dev/null | head -1)
if [ -n "$DMG" ]; then
    SIZE=$(du -h "$DMG" | cut -f1)
    echo "  Installer: $DMG ($SIZE)"
else
    echo "  Output: $DESKTOP_DIR/src-tauri/target/release/bundle/"
fi
echo ""

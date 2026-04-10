#!/usr/bin/env bash
# Build a macOS .pkg installer for IntentOS.
#
# Produces a component .pkg with selectable components:
#   - IntentOS Desktop (GUI app)
#   - IntentOS CLI (command-line tool)
#   - Local AI Engine (Ollama + recommended model)
#
# Prerequisites:
#   - macOS with Xcode Command Line Tools
#   - Tauri app already built (run build-desktop.sh first)
#   - PyInstaller CLI binary built (run build-sidecar.py with --cli flag)
#
# Usage:
#   bash scripts/build-pkg.sh           # lite (no Ollama bundled)
#   bash scripts/build-pkg.sh --full    # full (Ollama bundled)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BUILD_DIR="$PROJECT_ROOT/build/pkg"
VERSION="2.0.0"
IDENTIFIER="dev.intentos"
FULL_BUILD=false

if [[ "${1:-}" == "--full" ]]; then
    FULL_BUILD=true
fi

echo ""
echo "  IntentOS macOS Package Builder"
echo "  =============================="
echo ""

# Clean
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"/{gui,cli,scripts,resources}

# ---------------------------------------------------------------------------
# Component 1: GUI App (.app bundle from Tauri)
# ---------------------------------------------------------------------------

GUI_APP="$PROJECT_ROOT/ui/desktop/src-tauri/target/release/bundle/macos/IntentOS.app"

if [ -d "$GUI_APP" ]; then
    echo "  [ok] Found GUI app: $GUI_APP"
    cp -R "$GUI_APP" "$BUILD_DIR/gui/IntentOS.app"
else
    echo "  [..] GUI app not found — building Tauri app..."
    bash "$SCRIPT_DIR/build-desktop.sh"
    if [ -d "$GUI_APP" ]; then
        cp -R "$GUI_APP" "$BUILD_DIR/gui/IntentOS.app"
    else
        echo "  [!!] Tauri build did not produce an .app bundle"
        echo "       Falling back to .dmg path..."
        # Try to find any .app in the bundle output
        APP_FOUND=$(find "$PROJECT_ROOT/ui/desktop/src-tauri/target/release/bundle" -name "*.app" -maxdepth 3 | head -1)
        if [ -n "$APP_FOUND" ]; then
            cp -R "$APP_FOUND" "$BUILD_DIR/gui/IntentOS.app"
        else
            echo "  [!!] No .app found. Build the Tauri app first."
            exit 1
        fi
    fi
fi

# Build GUI component package
pkgbuild \
    --root "$BUILD_DIR/gui" \
    --install-location "/Applications" \
    --identifier "$IDENTIFIER.gui" \
    --version "$VERSION" \
    "$BUILD_DIR/intentos-gui.pkg"
echo "  [ok] GUI component package built"

# ---------------------------------------------------------------------------
# Component 2: CLI Tool (PyInstaller binary)
# ---------------------------------------------------------------------------

CLI_BINARY="$PROJECT_ROOT/build/sidecar-dist/intentos-backend"

if [ ! -f "$CLI_BINARY" ]; then
    echo "  [..] CLI binary not found — building..."
    pip install pyinstaller --quiet 2>/dev/null
    python3 "$SCRIPT_DIR/build-sidecar.py"
fi

if [ -f "$CLI_BINARY" ]; then
    mkdir -p "$BUILD_DIR/cli/usr/local/bin"
    cp "$CLI_BINARY" "$BUILD_DIR/cli/usr/local/bin/intentos"
    chmod +x "$BUILD_DIR/cli/usr/local/bin/intentos"

    pkgbuild \
        --root "$BUILD_DIR/cli" \
        --install-location "/" \
        --identifier "$IDENTIFIER.cli" \
        --version "$VERSION" \
        "$BUILD_DIR/intentos-cli.pkg"
    echo "  [ok] CLI component package built"
else
    echo "  [!!] CLI binary not available — skipping CLI component"
fi

# ---------------------------------------------------------------------------
# Component 3: Local AI Engine (Ollama) — full variant only
# ---------------------------------------------------------------------------

if [ "$FULL_BUILD" = true ]; then
    echo "  [..] Downloading Ollama for bundling..."
    mkdir -p "$BUILD_DIR/ollama/usr/local/bin"
    curl -fsSL "https://ollama.com/download/ollama-darwin" \
        -o "$BUILD_DIR/ollama/usr/local/bin/ollama" 2>/dev/null && {
        chmod +x "$BUILD_DIR/ollama/usr/local/bin/ollama"
        pkgbuild \
            --root "$BUILD_DIR/ollama" \
            --install-location "/" \
            --identifier "$IDENTIFIER.ollama" \
            --version "$VERSION" \
            "$BUILD_DIR/intentos-ollama.pkg"
        echo "  [ok] Ollama component package built"
    } || {
        echo "  [!!] Could not download Ollama binary — skipping"
        FULL_BUILD=false
    }
fi

# ---------------------------------------------------------------------------
# Post-install script
# ---------------------------------------------------------------------------

cat > "$BUILD_DIR/scripts/postinstall" << 'POSTINSTALL'
#!/bin/bash
# IntentOS post-install: start Ollama and pull recommended model if available

if command -v ollama &>/dev/null; then
    # Start Ollama daemon if not running
    if ! curl -s http://localhost:11434/api/tags &>/dev/null; then
        nohup ollama serve &>/dev/null &
        sleep 3
    fi

    # Check if models are needed (first install)
    MODELS=$(curl -s http://localhost:11434/api/tags 2>/dev/null | grep -c "name" || echo "0")
    if [ "$MODELS" -lt 2 ]; then
        # Pull in background — don't block installer
        nohup bash -c '
            ollama pull llama3.1:8b 2>/dev/null
            ollama pull nomic-embed-text 2>/dev/null
        ' &>/dev/null &
    fi
fi

exit 0
POSTINSTALL
chmod +x "$BUILD_DIR/scripts/postinstall"

# ---------------------------------------------------------------------------
# Distribution XML (defines component selection UI)
# ---------------------------------------------------------------------------

OLLAMA_CHOICE=""
if [ "$FULL_BUILD" = true ]; then
    OLLAMA_CHOICE='
    <choice id="ollama" title="Local AI Engine"
            description="Ollama — runs AI entirely on your device. Works offline after setup."
            start_selected="true">
        <pkg-ref id="dev.intentos.ollama"/>
    </choice>
    <pkg-ref id="dev.intentos.ollama" version="'"$VERSION"'">intentos-ollama.pkg</pkg-ref>'
fi

cat > "$BUILD_DIR/distribution.xml" << DISTXML
<?xml version="1.0" encoding="utf-8"?>
<installer-gui-script minSpecVersion="2">
    <title>IntentOS</title>
    <welcome file="welcome.html"/>
    <options customize="always" require-scripts="false" hostArchitectures="arm64,x86_64"/>

    <choices-outline>
        <line choice="gui"/>
        <line choice="cli"/>
        $([ "$FULL_BUILD" = true ] && echo '<line choice="ollama"/>')
    </choices-outline>

    <choice id="gui" title="Desktop App"
            description="The IntentOS desktop application. Drag-free install to Applications."
            start_selected="true">
        <pkg-ref id="dev.intentos.gui"/>
    </choice>

    <choice id="cli" title="Command Line Tool"
            description="The 'intentos' command for Terminal. Installed to /usr/local/bin."
            start_selected="true">
        <pkg-ref id="dev.intentos.cli"/>
    </choice>

    $OLLAMA_CHOICE

    <pkg-ref id="dev.intentos.gui" version="$VERSION">intentos-gui.pkg</pkg-ref>
    <pkg-ref id="dev.intentos.cli" version="$VERSION">intentos-cli.pkg</pkg-ref>
</installer-gui-script>
DISTXML

# ---------------------------------------------------------------------------
# Welcome HTML
# ---------------------------------------------------------------------------

cat > "$BUILD_DIR/resources/welcome.html" << 'WELCOME'
<!DOCTYPE html>
<html>
<head><style>
    body { font-family: -apple-system, sans-serif; padding: 20px; color: #1a1a1a; }
    h1 { font-size: 24px; margin-bottom: 8px; }
    .subtitle { color: #6b7280; font-size: 14px; margin-bottom: 24px; }
    .features { list-style: none; padding: 0; }
    .features li { padding: 6px 0; font-size: 14px; }
    .features li::before { content: "✓ "; color: #2563eb; font-weight: bold; }
    .note { margin-top: 20px; font-size: 12px; color: #9ca3af; }
</style></head>
<body>
    <h1>IntentOS</h1>
    <p class="subtitle">Your computer, finally on your side.</p>
    <ul class="features">
        <li>AI that runs on your device — files never leave</li>
        <li>Works offline after initial setup</li>
        <li>Desktop app and command line included</li>
        <li>Enterprise-grade security built in</li>
    </ul>
    <p class="note">
        On the next screen, choose which components to install.
        You can add or remove components later.
    </p>
</body>
</html>
WELCOME

# ---------------------------------------------------------------------------
# Build the final product archive (.pkg)
# ---------------------------------------------------------------------------

VARIANT="lite"
if [ "$FULL_BUILD" = true ]; then
    VARIANT="full"
fi

OUTPUT="$PROJECT_ROOT/build/IntentOS-${VERSION}-mac-${VARIANT}.pkg"

# Collect component packages
PKGS=("$BUILD_DIR/intentos-gui.pkg")
[ -f "$BUILD_DIR/intentos-cli.pkg" ] && PKGS+=("$BUILD_DIR/intentos-cli.pkg")
[ -f "$BUILD_DIR/intentos-ollama.pkg" ] && PKGS+=("$BUILD_DIR/intentos-ollama.pkg")

productbuild \
    --distribution "$BUILD_DIR/distribution.xml" \
    --resources "$BUILD_DIR/resources" \
    --scripts "$BUILD_DIR/scripts" \
    --package-path "$BUILD_DIR" \
    "$OUTPUT"

SIZE=$(du -h "$OUTPUT" | cut -f1)
echo ""
echo "  Package built: $OUTPUT ($SIZE)"
echo ""
echo "  To install: open $OUTPUT"
echo "  To install via CLI: sudo installer -pkg $OUTPUT -target /"
echo ""

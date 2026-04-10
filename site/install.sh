#!/bin/bash
# IntentOS CLI Installer
# Usage: curl -fsSL https://intentos.dev/install.sh | sh

set -e

REPO="pocProjectWorkspace/intentos"
LATEST_URL="https://api.github.com/repos/$REPO/releases/latest"

echo ""
echo "  IntentOS — Installing CLI"
echo ""

# Detect platform
OS=$(uname -s | tr '[:upper:]' '[:lower:]')
ARCH=$(uname -m)

case "$OS" in
  darwin) PLATFORM="mac" ;;
  linux)  PLATFORM="linux" ;;
  *)      echo "  Unsupported platform: $OS"; exit 1 ;;
esac

case "$ARCH" in
  x86_64|amd64) ARCH_LABEL="x86_64" ;;
  arm64|aarch64) ARCH_LABEL="aarch64" ;;
  *)             echo "  Unsupported architecture: $ARCH"; exit 1 ;;
esac

BINARY_NAME="intentos-cli-${PLATFORM}-${ARCH_LABEL}"
INSTALL_DIR="/usr/local/bin"

echo "  Platform: $OS ($ARCH_LABEL)"
echo "  Installing to: $INSTALL_DIR/intentos"
echo ""

# Get latest release download URL
DOWNLOAD_URL="https://github.com/$REPO/releases/latest/download/$BINARY_NAME"

echo "  Downloading..."
curl -fsSL "$DOWNLOAD_URL" -o /tmp/intentos
chmod +x /tmp/intentos

# Install (may need sudo)
if [ -w "$INSTALL_DIR" ]; then
  mv /tmp/intentos "$INSTALL_DIR/intentos"
else
  echo "  Need permission to install to $INSTALL_DIR"
  sudo mv /tmp/intentos "$INSTALL_DIR/intentos"
fi

echo ""
echo "  Done! Run 'intentos' to start."
echo ""

#!/usr/bin/env bash
# sign-demo.sh — Self-signed code signing for IntentOS demo builds
# Generates a self-signed Apple code signing certificate (if needed),
# signs the Tauri .app bundle, copies to /Applications, and clears quarantine.
set -euo pipefail

CERT_NAME="IntentOS Dev"
DEFAULT_APP="ui/desktop/src-tauri/target/release/bundle/macos/IntentOS.app"
APP_PATH="${1:-$DEFAULT_APP}"

# ---------------------------------------------------------------------------
# Step 1: Ensure a self-signed code signing certificate exists in Keychain
# ---------------------------------------------------------------------------
echo "[1/3] Checking for code signing certificate..."

if security find-identity -v -p codesigning 2>/dev/null | grep -q "$CERT_NAME"; then
    echo "  Certificate '$CERT_NAME' already exists in Keychain."
else
    echo "  Certificate not found — generating self-signed certificate..."
    CERT_CFG=$(mktemp /tmp/intentos-cert-XXXXXX.cfg)
    trap 'rm -f "$CERT_CFG" /tmp/intentos-dev.key /tmp/intentos-dev.crt' EXIT

    cat > "$CERT_CFG" <<CERT
[ req ]
default_bits = 2048
prompt = no
default_md = sha256
distinguished_name = dn
[ dn ]
CN = $CERT_NAME
O = IntentOS
[ extensions ]
keyUsage = digitalSignature
extendedKeyUsage = codeSigning
CERT

    openssl req -x509 -newkey rsa:2048 \
        -keyout /tmp/intentos-dev.key \
        -out /tmp/intentos-dev.crt \
        -days 365 -nodes \
        -config "$CERT_CFG" \
        -extensions extensions 2>/dev/null

    if [ $? -ne 0 ]; then
        echo "  ERROR: Failed to generate certificate with openssl."
        exit 1
    fi

    # Import certificate and key into login Keychain
    security import /tmp/intentos-dev.crt -k ~/Library/Keychains/login.keychain-db -T /usr/bin/codesign 2>/dev/null || {
        echo "  ERROR: Failed to import certificate into Keychain."
        exit 1
    }
    security import /tmp/intentos-dev.key -k ~/Library/Keychains/login.keychain-db -T /usr/bin/codesign 2>/dev/null || {
        echo "  ERROR: Failed to import private key into Keychain."
        exit 1
    }

    # Clean up temp files (trap also handles this)
    rm -f /tmp/intentos-dev.key /tmp/intentos-dev.crt "$CERT_CFG"
    echo "  Certificate '$CERT_NAME' created and imported into Keychain."
fi

# ---------------------------------------------------------------------------
# Step 2: Sign the .app bundle
# ---------------------------------------------------------------------------
echo "[2/3] Signing application bundle..."

if [ ! -d "$APP_PATH" ]; then
    echo "  ERROR: Application bundle not found at: $APP_PATH"
    echo "  Build the Tauri app first, or pass the path as an argument:"
    echo "    ./scripts/sign-demo.sh /path/to/IntentOS.app"
    exit 1
fi

codesign --deep --force --sign "$CERT_NAME" "$APP_PATH" || {
    echo "  ERROR: Code signing failed. You may need to unlock your Keychain:"
    echo "    security unlock-keychain ~/Library/Keychains/login.keychain-db"
    exit 1
}

codesign --verify "$APP_PATH" || {
    echo "  ERROR: Signature verification failed."
    exit 1
}
echo "  Application signed and verified."

# ---------------------------------------------------------------------------
# Step 3: Install to /Applications and clear quarantine
# ---------------------------------------------------------------------------
echo "[3/3] Installing to /Applications..."

rm -rf /Applications/IntentOS.app
cp -R "$APP_PATH" /Applications/IntentOS.app || {
    echo "  ERROR: Failed to copy to /Applications. You may need sudo."
    exit 1
}
xattr -cr /Applications/IntentOS.app 2>/dev/null || true

echo ""
echo "IntentOS installed and signed for demo."
echo "  Location: /Applications/IntentOS.app"
echo "  Certificate: $CERT_NAME (self-signed, valid 365 days)"

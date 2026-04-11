#!/usr/bin/env bash
# Build IntentOS .pkg installer for MDM deployment (Jamf, Mosyle, Kandji)
# Usage: bash scripts/build-mdm-pkg.sh [--policy /path/to/policy.json]
set -euo pipefail

VERSION="0.1.0"
IDENTIFIER="com.intentos.desktop"
APP_NAME="IntentOS"
PKG_NAME="${APP_NAME}-${VERSION}-mdm.pkg"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BUILD_DIR="${PROJECT_ROOT}/build"
APP_BUNDLE="${PROJECT_ROOT}/ui/desktop/src-tauri/target/release/bundle/macos/${APP_NAME}.app"

POLICY_PATH=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --policy)
            POLICY_PATH="$2"
            shift 2
            ;;
        -h|--help)
            echo "Usage: bash scripts/build-mdm-pkg.sh [--policy /path/to/policy.json]"
            echo ""
            echo "Options:"
            echo "  --policy PATH   Include enterprise policy.json in the package"
            echo "  -h, --help      Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

echo "================================================"
echo "  IntentOS MDM Package Builder (macOS)"
echo "  Version: ${VERSION}"
echo "================================================"
echo ""

# Step 1: Check app bundle exists
if [ ! -d "$APP_BUNDLE" ]; then
    echo "ERROR: App bundle not found at:"
    echo "  ${APP_BUNDLE}"
    echo ""
    echo "Build the Tauri app first:"
    echo "  cd ui/desktop && npm run tauri build"
    exit 1
fi
echo "[1/5] App bundle found: ${APP_BUNDLE}"

# Step 2: Create temporary pkg root
WORK_DIR=$(mktemp -d)
PKG_ROOT="${WORK_DIR}/pkg-root"
PKG_SCRIPTS="${WORK_DIR}/pkg-scripts"
mkdir -p "${PKG_ROOT}/Applications"
mkdir -p "${PKG_ROOT}/Library/IntentOS"
mkdir -p "${PKG_SCRIPTS}"

echo "[2/5] Copying app bundle to pkg root..."
cp -R "$APP_BUNDLE" "${PKG_ROOT}/Applications/${APP_NAME}.app"

# Copy policy if provided
if [ -n "$POLICY_PATH" ]; then
    if [ ! -f "$POLICY_PATH" ]; then
        echo "ERROR: Policy file not found: ${POLICY_PATH}"
        rm -rf "$WORK_DIR"
        exit 1
    fi
    cp "$POLICY_PATH" "${PKG_ROOT}/Library/IntentOS/policy.json"
    echo "  Included policy: ${POLICY_PATH}"

    # Also include enterprise.key if it exists alongside the policy
    POLICY_DIR="$(dirname "$POLICY_PATH")"
    if [ -f "${POLICY_DIR}/enterprise.key" ]; then
        cp "${POLICY_DIR}/enterprise.key" "${PKG_ROOT}/Library/IntentOS/enterprise.key"
        echo "  Included enterprise key"
    fi
fi

# Step 3: Create preinstall script
echo "[3/5] Creating installer scripts..."
cat > "${PKG_SCRIPTS}/preinstall" << 'PREINSTALL_EOF'
#!/bin/bash
# Preinstall: stop running IntentOS and clean quarantine
echo "IntentOS preinstall: $(date)" >> /var/log/intentos-install.log

# Kill any running IntentOS instance
pkill -f "IntentOS" 2>/dev/null || true
sleep 1

# Remove quarantine attribute if present
if [ -d "/Applications/IntentOS.app" ]; then
    xattr -rd com.apple.quarantine "/Applications/IntentOS.app" 2>/dev/null || true
fi

exit 0
PREINSTALL_EOF
chmod +x "${PKG_SCRIPTS}/preinstall"

# Step 4: Create postinstall script
cat > "${PKG_SCRIPTS}/postinstall" << 'POSTINSTALL_EOF'
#!/bin/bash
# Postinstall: distribute policy to user directories
echo "IntentOS postinstall: $(date)" >> /var/log/intentos-install.log

# Remove quarantine from newly installed app
xattr -rd com.apple.quarantine "/Applications/IntentOS.app" 2>/dev/null || true

# Distribute policy.json to each user's ~/.intentos/ directory
POLICY_SRC="/Library/IntentOS/policy.json"
if [ -f "$POLICY_SRC" ]; then
    for USER_HOME in /Users/*/; do
        # Skip Shared and system users
        USERNAME="$(basename "$USER_HOME")"
        if [ "$USERNAME" = "Shared" ] || [ "$USERNAME" = ".localized" ]; then
            continue
        fi

        INTENTOS_DIR="${USER_HOME}.intentos"
        mkdir -p "$INTENTOS_DIR"
        cp "$POLICY_SRC" "${INTENTOS_DIR}/policy.json"

        # Set ownership to the user
        USER_ID=$(stat -f "%u" "$USER_HOME" 2>/dev/null || echo "")
        GROUP_ID=$(stat -f "%g" "$USER_HOME" 2>/dev/null || echo "")
        if [ -n "$USER_ID" ] && [ -n "$GROUP_ID" ]; then
            chown -R "${USER_ID}:${GROUP_ID}" "$INTENTOS_DIR"
        fi
        chmod 700 "$INTENTOS_DIR"
        chmod 600 "${INTENTOS_DIR}/policy.json"

        echo "  Policy deployed to ${INTENTOS_DIR}" >> /var/log/intentos-install.log
    done
fi

# Copy enterprise key if present
KEY_SRC="/Library/IntentOS/enterprise.key"
if [ -f "$KEY_SRC" ]; then
    for USER_HOME in /Users/*/; do
        USERNAME="$(basename "$USER_HOME")"
        if [ "$USERNAME" = "Shared" ] || [ "$USERNAME" = ".localized" ]; then
            continue
        fi
        INTENTOS_DIR="${USER_HOME}.intentos"
        mkdir -p "$INTENTOS_DIR"
        cp "$KEY_SRC" "${INTENTOS_DIR}/enterprise.key"
        USER_ID=$(stat -f "%u" "$USER_HOME" 2>/dev/null || echo "")
        GROUP_ID=$(stat -f "%g" "$USER_HOME" 2>/dev/null || echo "")
        if [ -n "$USER_ID" ] && [ -n "$GROUP_ID" ]; then
            chown "${USER_ID}:${GROUP_ID}" "${INTENTOS_DIR}/enterprise.key"
        fi
        chmod 600 "${INTENTOS_DIR}/enterprise.key"
    done
fi

echo "IntentOS installation complete: $(date)" >> /var/log/intentos-install.log
exit 0
POSTINSTALL_EOF
chmod +x "${PKG_SCRIPTS}/postinstall"

# Step 5: Build the .pkg
echo "[4/5] Building .pkg..."
mkdir -p "$BUILD_DIR"

pkgbuild \
    --root "${PKG_ROOT}" \
    --identifier "${IDENTIFIER}" \
    --version "${VERSION}" \
    --install-location / \
    --scripts "${PKG_SCRIPTS}" \
    "${BUILD_DIR}/${PKG_NAME}"

# Cleanup
rm -rf "$WORK_DIR"

# Step 6: Report
echo "[5/5] Done!"
echo ""
PKG_SIZE=$(du -h "${BUILD_DIR}/${PKG_NAME}" | cut -f1)
echo "================================================"
echo "  Output: ${BUILD_DIR}/${PKG_NAME}"
echo "  Size:   ${PKG_SIZE}"
echo "================================================"
echo ""
echo "Deploy via MDM:"
echo "  Jamf:   Upload to Jamf Pro > Packages"
echo "  Mosyle: Upload to Mosyle > Apps > Custom"
echo "  Kandji: Upload to Kandji > Library > Custom Apps"

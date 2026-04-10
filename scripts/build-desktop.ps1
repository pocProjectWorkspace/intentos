# Build the IntentOS desktop app for Windows.
#
# Prerequisites:
#   - Rust toolchain (rustup.rs)
#   - Node.js 18+
#   - Python 3.9+ with pyinstaller
#   - Visual Studio Build Tools (for MSVC)
#
# Usage:
#   powershell -File scripts/build-desktop.ps1          # lite installer
#   powershell -File scripts/build-desktop.ps1 -Full    # full installer (bundles Ollama)

param(
    [switch]$Full
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
$DesktopDir = Join-Path $ProjectRoot "ui/desktop"

Write-Host ""
Write-Host "  IntentOS Desktop Build" -ForegroundColor Cyan
Write-Host "  ======================" -ForegroundColor Cyan
Write-Host ""

# 1. Check prerequisites
Write-Host "  [..] Checking prerequisites..."
$checks = @(
    @{ cmd = "cargo"; name = "Rust"; url = "https://rustup.rs" },
    @{ cmd = "node"; name = "Node.js"; url = "https://nodejs.org" },
    @{ cmd = "python"; name = "Python"; url = "https://python.org" }
)
foreach ($check in $checks) {
    if (-not (Get-Command $check.cmd -ErrorAction SilentlyContinue)) {
        Write-Host "  [!!] $($check.name) not found. Install: $($check.url)" -ForegroundColor Red
        exit 1
    }
}
Write-Host "  [ok] All prerequisites found" -ForegroundColor Green

# 2. Build Python sidecar
Write-Host "  [..] Building Python sidecar..."
& pip install pyinstaller --quiet 2>$null
& python "$ScriptDir/build-sidecar.py"
Write-Host ""

# 3. Install frontend dependencies
Write-Host "  [..] Installing frontend dependencies..."
Set-Location $DesktopDir
& npm install --silent 2>$null
Write-Host "  [ok] Frontend deps installed" -ForegroundColor Green

# 4. Build Tauri app
Write-Host "  [..] Building Tauri desktop app..."
if ($Full) {
    # Download Ollama for bundling
    Write-Host "  [..] Downloading Ollama for bundling..."
    $resourceDir = Join-Path $DesktopDir "src-tauri/resources"
    New-Item -ItemType Directory -Path $resourceDir -Force | Out-Null
    try {
        Invoke-WebRequest -Uri "https://ollama.com/download/OllamaSetup.exe" -OutFile "$resourceDir/ollama-setup.exe" -UseBasicParsing
        Write-Host "  [ok] Ollama bundled" -ForegroundColor Green
        & npm run tauri build -- --config src-tauri/tauri.full.conf.json
    } catch {
        Write-Host "  [!!] Could not download Ollama. Building lite variant." -ForegroundColor Yellow
        & npm run tauri build
    }
} else {
    & npm run tauri build
}

Write-Host ""
Write-Host "  Build complete!" -ForegroundColor Green
Write-Host ""

# Find output
$nsisDir = Join-Path $DesktopDir "src-tauri/target/release/bundle/nsis"
$installer = Get-ChildItem -Path $nsisDir -Filter "*.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
if ($installer) {
    $sizeMB = [math]::Round($installer.Length / 1MB, 1)
    Write-Host "  Installer: $($installer.FullName) ($sizeMB MB)" -ForegroundColor White
} else {
    Write-Host "  Output: $DesktopDir\src-tauri\target\release\bundle\" -ForegroundColor White
}
Write-Host ""

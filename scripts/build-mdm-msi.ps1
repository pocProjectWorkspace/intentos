# Build IntentOS .msi installer for MDM deployment (Intune, SCCM, GPO)
# Requires: WiX Toolset v4+ (https://wixtoolset.org)
# Usage: powershell -File scripts/build-mdm-msi.ps1 [-Policy C:\path\to\policy.json]

param(
    [string]$Policy = "",
    [string]$Version = "0.1.0"
)

$ErrorActionPreference = "Stop"

$AppName = "IntentOS"
$Identifier = "com.intentos.desktop"
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$BuildDir = Join-Path $ProjectRoot "build"
$AppBundle = Join-Path $ProjectRoot "ui\desktop\src-tauri\target\release\IntentOS.exe"

Write-Host "================================================"
Write-Host "  IntentOS MDM Package Builder (Windows)"
Write-Host "  Version: $Version"
Write-Host "================================================"
Write-Host ""

# Step 1: Check WiX Toolset is available
$wixPath = Get-Command "wix" -ErrorAction SilentlyContinue
if (-not $wixPath) {
    Write-Host "ERROR: WiX Toolset not found."
    Write-Host "Install WiX v4+: https://wixtoolset.org/docs/intro/"
    Write-Host "  dotnet tool install --global wix"
    exit 1
}
Write-Host "[1/5] WiX Toolset found: $($wixPath.Source)"

# Step 2: Check app executable exists
if (-not (Test-Path $AppBundle)) {
    Write-Host "ERROR: App executable not found at:"
    Write-Host "  $AppBundle"
    Write-Host ""
    Write-Host "Build the Tauri app first:"
    Write-Host "  cd ui/desktop && npm run tauri build"
    exit 1
}
Write-Host "[2/5] App executable found: $AppBundle"

# Step 3: Generate WiX source
Write-Host "[3/5] Generating WiX source..."

# TODO: Generate the WiX XML (.wxs) file
# The WiX source should include:
# - Product element with UpgradeCode GUID
# - Directory structure:
#   - ProgramFilesFolder\IntentOS\IntentOS.exe
#   - CommonAppDataFolder\IntentOS\policy.json (if --Policy provided)
# - Component for the main executable
# - Component for the policy file (conditional)
# - Feature element grouping components
# - CustomAction for:
#   - Kill running IntentOS on install/upgrade
#   - Copy policy.json to each user's %USERPROFILE%\.intentos\
#   - Register uninstall entry
# - MajorUpgrade element for clean upgrades
# - Shortcut to Start Menu

$wxsContent = @"
<?xml version="1.0" encoding="UTF-8"?>
<Wix xmlns="http://wixtoolset.org/schemas/v4/wxs">
  <Package Name="$AppName"
           Version="$Version"
           Manufacturer="IntentOS Inc."
           UpgradeCode="E8F2B3A4-1C5D-4E6F-A7B8-9C0D1E2F3A4B">

    <MajorUpgrade DowngradeErrorMessage="A newer version of $AppName is already installed." />
    <MediaTemplate EmbedCab="yes" />

    <StandardDirectory Id="ProgramFiles6432Folder">
      <Directory Id="INSTALLFOLDER" Name="$AppName">
        <!-- TODO: Add Component for IntentOS.exe -->
        <!-- TODO: Add Component for policy.json if applicable -->
      </Directory>
    </StandardDirectory>

    <StandardDirectory Id="CommonAppDataFolder">
      <Directory Id="APPDATAFOLDER" Name="$AppName">
        <!-- TODO: Add Component for system-wide policy.json -->
      </Directory>
    </StandardDirectory>

    <Feature Id="ProductFeature" Title="$AppName" Level="1">
      <!-- TODO: ComponentRef elements -->
    </Feature>

    <!-- TODO: CustomAction to distribute policy.json to user profiles -->
    <!-- TODO: CustomAction to kill running IntentOS process -->

  </Package>
</Wix>
"@

$wxsPath = Join-Path $BuildDir "$AppName.wxs"
New-Item -ItemType Directory -Force -Path $BuildDir | Out-Null
Set-Content -Path $wxsPath -Value $wxsContent
Write-Host "  WiX source written to: $wxsPath"

# Step 4: Build MSI
Write-Host "[4/5] Building MSI..."
Write-Host "  TODO: Run 'wix build $wxsPath -o $BuildDir\$AppName-$Version-mdm.msi'"
Write-Host "  This step requires the WiX source to be completed with actual component definitions."
Write-Host ""

# TODO: Uncomment when WiX source is complete:
# wix build $wxsPath -o "$BuildDir\$AppName-$Version-mdm.msi"

# Step 5: Report
Write-Host "[5/5] WiX source generated (MSI build requires completed .wxs)"
Write-Host ""
Write-Host "================================================"
Write-Host "  WiX Source: $wxsPath"
Write-Host "  Output:     $BuildDir\$AppName-$Version-mdm.msi (pending)"
Write-Host "================================================"
Write-Host ""
Write-Host "Deploy via MDM:"
Write-Host "  Intune: Upload to Intune > Apps > Windows > Line-of-business app"
Write-Host "  SCCM:   Import to SCCM > Software Library > Application Management"
Write-Host "  GPO:    Add to Group Policy > Software Installation"

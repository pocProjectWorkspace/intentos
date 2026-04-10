# IntentOS - Windows Setup Script
# Usage: powershell -ExecutionPolicy Bypass -File setup.ps1
#        powershell -ExecutionPolicy Bypass -File setup.ps1 -Silent
#        powershell -ExecutionPolicy Bypass -File setup.ps1 -Silent -WithOllama

param(
    [switch]$Silent,
    [switch]$WithOllama
)

$ErrorActionPreference = "Stop"

$VenvDir = ".venv"
$EnvFile = ".env"
$EnvExample = ".env.example"

Write-Host ""
Write-Host "  +==========================================+" -ForegroundColor Cyan
Write-Host "  |            IntentOS Setup                |" -ForegroundColor Cyan
Write-Host "  |    Your computer, finally on your side.  |" -ForegroundColor Cyan
Write-Host "  +==========================================+" -ForegroundColor Cyan
Write-Host ""

# 1. Check Python
$PythonCmd = $null
foreach ($cmd in @("python", "python3", "py")) {
    try {
        $ver = & $cmd --version 2>&1
        if ($ver -match "Python 3\.(\d+)") {
            $PythonCmd = $cmd
            break
        }
    } catch {}
}

if (-not $PythonCmd) {
    Write-Host "  [!!] Python 3 is required. Install from https://python.org" -ForegroundColor Red
    Write-Host "       Make sure to check 'Add Python to PATH' during install." -ForegroundColor Red
    exit 1
}

$PythonVersion = & $PythonCmd -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
Write-Host "  [ok] Python $PythonVersion detected (using '$PythonCmd')" -ForegroundColor Green

# 2. Create virtual environment
if (Test-Path $VenvDir) {
    Write-Host "  [ok] Virtual environment already exists at $VenvDir" -ForegroundColor Green
} else {
    Write-Host "  [..] Creating virtual environment..."
    & $PythonCmd -m venv $VenvDir
    Write-Host "  [ok] Virtual environment created at $VenvDir" -ForegroundColor Green
}

# 3. Activate it
$ActivateScript = Join-Path $VenvDir "Scripts\Activate.ps1"
if (-not (Test-Path $ActivateScript)) {
    Write-Host "  [!!] Could not find venv activation script at $ActivateScript" -ForegroundColor Red
    exit 1
}
Write-Host "  [..] Activating virtual environment..."
& $ActivateScript
Write-Host "  [ok] Activated ($VenvDir\Scripts\python.exe)" -ForegroundColor Green

# 4. Install core dependencies
Write-Host "  [..] Installing core dependencies..."
& pip install --upgrade pip --quiet 2>$null
& pip install -r requirements.txt --quiet
Write-Host "  [ok] Core dependencies installed" -ForegroundColor Green

# 5. Optional extras
if (-not $Silent) {
    Write-Host ""
    Write-Host "  Optional capabilities:"
    Write-Host "    [1] OpenAI support      (openai)"
    Write-Host "    [2] Gemini support      (google-generativeai)"
    Write-Host "    [3] Voice input         (SpeechRecognition)"
    Write-Host "    [4] All of the above"
    Write-Host "    [5] Skip (install later with: pip install -e '.[all]')"
    Write-Host ""

    $ExtrasChoice = Read-Host "  Install optional extras? [1-5, default=5]"
    if ([string]::IsNullOrWhiteSpace($ExtrasChoice)) { $ExtrasChoice = "5" }

    switch ($ExtrasChoice) {
        "1" {
            & pip install --quiet "openai>=1.0.0"
            Write-Host "  [ok] OpenAI support installed" -ForegroundColor Green
        }
        "2" {
            & pip install --quiet "google-generativeai>=0.3.0"
            Write-Host "  [ok] Gemini support installed" -ForegroundColor Green
        }
        "3" {
            & pip install --quiet "SpeechRecognition>=3.10.0"
            Write-Host "  [ok] Voice input installed" -ForegroundColor Green
        }
        "4" {
            & pip install --quiet "openai>=1.0.0" "google-generativeai>=0.3.0" "SpeechRecognition>=3.10.0"
            Write-Host "  [ok] All extras installed" -ForegroundColor Green
        }
        default {
            Write-Host "  [ok] Skipped optional extras" -ForegroundColor Green
        }
    }
} else {
    Write-Host "  [ok] Skipped optional extras (silent mode)" -ForegroundColor Green
}

# 6. Ollama - local AI engine
$OllamaSetup = $false
if (-not $Silent) {
    Write-Host ""
    Write-Host "  Local AI Engine (Ollama):"
    Write-Host "    IntentOS can run AI entirely on your device."
    Write-Host "    This requires Ollama and a one-time download (~2-4 GB)."
    Write-Host ""

    $OllamaChoice = Read-Host "  Set up local AI? [y/N]"
    if ($OllamaChoice -match "^[Yy]") {
        $OllamaSetup = $true
    }
} elseif ($WithOllama) {
    $OllamaSetup = $true
}

if ($OllamaSetup) {
    $ollamaCmd = Get-Command ollama -ErrorAction SilentlyContinue

    if ($ollamaCmd) {
        Write-Host "  [ok] Ollama already installed" -ForegroundColor Green
    } else {
        Write-Host "  [..] Installing Ollama..."

        $wingetCmd = Get-Command winget -ErrorAction SilentlyContinue
        if ($wingetCmd) {
            try {
                winget install Ollama.Ollama --accept-package-agreements --accept-source-agreements --silent 2>$null
                Write-Host "  [ok] Ollama installed via winget" -ForegroundColor Green
            } catch {
                Write-Host "  [..] Trying direct download..." -ForegroundColor Yellow
                try {
                    $installerUrl = "https://ollama.com/download/OllamaSetup.exe"
                    $installerPath = Join-Path $env:TEMP "OllamaSetup.exe"
                    Invoke-WebRequest -Uri $installerUrl -OutFile $installerPath -UseBasicParsing
                    Start-Process -FilePath $installerPath -ArgumentList "/S" -Wait
                    Remove-Item $installerPath -ErrorAction SilentlyContinue
                    Write-Host "  [ok] Ollama installed" -ForegroundColor Green
                } catch {
                    Write-Host "  [!!] Could not install Ollama. Install manually: https://ollama.com/download" -ForegroundColor Yellow
                }
            }
        } else {
            try {
                $installerUrl = "https://ollama.com/download/OllamaSetup.exe"
                $installerPath = Join-Path $env:TEMP "OllamaSetup.exe"
                Invoke-WebRequest -Uri $installerUrl -OutFile $installerPath -UseBasicParsing
                Start-Process -FilePath $installerPath -ArgumentList "/S" -Wait
                Remove-Item $installerPath -ErrorAction SilentlyContinue
                Write-Host "  [ok] Ollama installed" -ForegroundColor Green
            } catch {
                Write-Host "  [!!] Could not install Ollama. Install manually: https://ollama.com/download" -ForegroundColor Yellow
            }
        }

        # Refresh PATH so ollama is found
        $env:PATH = [System.Environment]::GetEnvironmentVariable("PATH", "Machine") + ";" +
                     [System.Environment]::GetEnvironmentVariable("PATH", "User")
    }

    # Pull models via OllamaManager module
    $ollamaCmd = Get-Command ollama -ErrorAction SilentlyContinue
    if ($ollamaCmd) {
        Write-Host "  [..] Preparing local AI..."
        try {
            & python -m core.inference.ollama_manager --setup auto
        } catch {
            Write-Host "  [!!] Model setup had issues - you can retry later with:" -ForegroundColor Yellow
            Write-Host "       python -m core.inference.ollama_manager --setup auto" -ForegroundColor Yellow
        }
        Write-Host ""
    }
}

# 7. Ensure .env exists
if (Test-Path $EnvFile) {
    Write-Host "  [ok] .env file found" -ForegroundColor Green
} elseif (Test-Path $EnvExample) {
    Copy-Item $EnvExample $EnvFile
    Write-Host ""
    Write-Host "  =============================================" -ForegroundColor Yellow
    Write-Host "  ACTION REQUIRED" -ForegroundColor Yellow
    Write-Host "  .env was created from .env.example." -ForegroundColor Yellow
    Write-Host "  Open .env and set your API key, or" -ForegroundColor Yellow
    Write-Host "  IntentOS will prompt you on first run." -ForegroundColor Yellow
    Write-Host "  =============================================" -ForegroundColor Yellow
    Write-Host ""
} else {
    Write-Host "  [!!] .env.example not found - .env will be created on first run" -ForegroundColor Yellow
}

# 8. Install as editable package
Write-Host "  [..] Installing IntentOS as package..."
try {
    & pip install --quiet -e . 2>$null
} catch {
    Write-Host "  [!!] Editable install skipped (pyproject.toml may be missing)" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "  Setup complete!" -ForegroundColor Green
Write-Host ""
Write-Host "  To start IntentOS:" -ForegroundColor Cyan
Write-Host "    $VenvDir\Scripts\Activate.ps1" -ForegroundColor White
Write-Host "    intentos" -ForegroundColor White
Write-Host ""
Write-Host "  Or run directly:" -ForegroundColor Cyan
Write-Host "    python core\kernel_v2.py" -ForegroundColor White
Write-Host ""

; IntentOS NSIS Installer — Custom template with component selection
; This extends Tauri's default NSIS installer with component checkboxes.
;
; Components:
;   1. Desktop App (GUI) — always included via Tauri bundle
;   2. Command Line Tool — adds 'intentos' to PATH
;   3. Local AI Engine — installs Ollama

!include "MUI2.nsh"
!include "FileFunc.nsh"

; ---------------------------------------------------------------------------
; General
; ---------------------------------------------------------------------------

Name "IntentOS"
OutFile "IntentOS-Setup.exe"
InstallDir "$PROGRAMFILES64\IntentOS"
RequestExecutionLevel admin

; ---------------------------------------------------------------------------
; Interface
; ---------------------------------------------------------------------------

!define MUI_ICON "..\icons\icon.ico"
!define MUI_WELCOMEPAGE_TITLE "Welcome to IntentOS"
!define MUI_WELCOMEPAGE_TEXT "Your computer, finally on your side.$\n$\nIntentOS is an AI assistant that runs on your device. Your files never leave.$\n$\nClick Next to choose what to install."
!define MUI_COMPONENTSPAGE_TEXT_COMPLIST "Select the components you want to install:"
!define MUI_FINISHPAGE_RUN "$INSTDIR\IntentOS.exe"
!define MUI_FINISHPAGE_RUN_TEXT "Launch IntentOS"

; ---------------------------------------------------------------------------
; Pages
; ---------------------------------------------------------------------------

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_LANGUAGE "English"

; ---------------------------------------------------------------------------
; Sections (Components)
; ---------------------------------------------------------------------------

Section "Desktop App (recommended)" SecGUI
    SectionIn RO  ; Required — always installed
    SetOutPath "$INSTDIR"

    ; Tauri app files are placed here by the build process
    File /r "${TAURI_BUNDLE_DIR}\*.*"

    ; Start menu shortcut
    CreateDirectory "$SMPROGRAMS\IntentOS"
    CreateShortcut "$SMPROGRAMS\IntentOS\IntentOS.lnk" "$INSTDIR\IntentOS.exe"
    CreateShortcut "$DESKTOP\IntentOS.lnk" "$INSTDIR\IntentOS.exe"

    ; Uninstaller
    WriteUninstaller "$INSTDIR\Uninstall.exe"

    ; Add/Remove Programs entry
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\IntentOS" \
        "DisplayName" "IntentOS"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\IntentOS" \
        "UninstallString" '"$INSTDIR\Uninstall.exe"'
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\IntentOS" \
        "DisplayVersion" "2.0.0"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\IntentOS" \
        "Publisher" "IntentOS Team"
SectionEnd

Section "Command Line Tool" SecCLI
    SetOutPath "$INSTDIR\cli"

    ; CLI binary
    File "${CLI_BINARY_PATH}\intentos.exe"

    ; Add to PATH
    EnVar::AddValue "PATH" "$INSTDIR\cli"

    DetailPrint "Added 'intentos' to your PATH."
    DetailPrint "Open a new terminal and type 'intentos' to start."
SectionEnd

Section "Local AI Engine" SecOllama
    DetailPrint "Checking for Ollama..."

    ; Check if already installed
    nsExec::ExecToStack 'where ollama'
    Pop $0
    ${If} $0 == 0
        DetailPrint "Ollama already installed."
    ${Else}
        DetailPrint "Installing Ollama..."

        ; Try winget first
        nsExec::ExecToStack 'winget install Ollama.Ollama --accept-package-agreements --accept-source-agreements --silent'
        Pop $0
        ${If} $0 != 0
            ; Fallback: download installer
            DetailPrint "Downloading Ollama installer..."
            inetc::get "https://ollama.com/download/OllamaSetup.exe" "$TEMP\OllamaSetup.exe" /END
            Pop $0
            ${If} $0 == "OK"
                DetailPrint "Running Ollama installer..."
                ExecWait '"$TEMP\OllamaSetup.exe" /S'
                Delete "$TEMP\OllamaSetup.exe"
            ${Else}
                DetailPrint "Could not download Ollama. You can install it later from https://ollama.com"
            ${EndIf}
        ${EndIf}
    ${EndIf}

    DetailPrint "Local AI engine setup complete."
    DetailPrint "IntentOS will download AI models on first launch."
SectionEnd

; ---------------------------------------------------------------------------
; Component descriptions
; ---------------------------------------------------------------------------

!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
    !insertmacro MUI_DESCRIPTION_TEXT ${SecGUI} \
        "The IntentOS desktop application with full graphical interface."
    !insertmacro MUI_DESCRIPTION_TEXT ${SecCLI} \
        "The 'intentos' command for PowerShell and Command Prompt. Adds to your PATH."
    !insertmacro MUI_DESCRIPTION_TEXT ${SecOllama} \
        "Ollama — runs AI on your device. Private, free, works offline after setup."
!insertmacro MUI_FUNCTION_DESCRIPTION_END

; ---------------------------------------------------------------------------
; Uninstaller
; ---------------------------------------------------------------------------

Section "Uninstall"
    ; Remove files
    RMDir /r "$INSTDIR"

    ; Remove shortcuts
    Delete "$DESKTOP\IntentOS.lnk"
    RMDir /r "$SMPROGRAMS\IntentOS"

    ; Remove from PATH
    EnVar::DeleteValue "PATH" "$INSTDIR\cli"

    ; Remove registry
    DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\IntentOS"
SectionEnd

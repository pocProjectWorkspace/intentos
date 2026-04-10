# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the standalone IntentOS CLI binary.

Produces a single-file 'intentos' executable that runs the full kernel
with the interactive REPL. This is what gets installed to /usr/local/bin
(macOS) or added to PATH (Windows) by the installer.

Build:
    pyinstaller scripts/intentos-cli.spec --distpath build/cli-dist/
"""

import os

project_root = os.path.abspath(os.path.join(os.path.dirname(SPEC), '..'))

a = Analysis(
    [os.path.join(project_root, 'core', 'kernel_v2.py')],
    pathex=[project_root],
    binaries=[],
    datas=[],
    hiddenimports=[
        'core.api.server',
        'core.config',
        'core.first_run',
        'core.security.pipeline',
        'core.security.credential_provider',
        'core.inference.llm',
        'core.inference.router',
        'core.inference.providers',
        'core.inference.hardware',
        'core.inference.ollama_manager',
        'core.orchestration.sop',
        'core.orchestration.scheduler',
        'core.orchestration.mode_router',
        'core.orchestration.cost_manager',
        'core.orchestration.message_bus',
        'core.rag.context',
        'core.voice.stt',
        'core.voice.tts',
        'capabilities.file_agent.agent',
        'capabilities.system_agent.agent',
        'capabilities.browser_agent.agent',
        'capabilities.document_agent.agent',
        'capabilities.image_agent.agent',
        'capabilities.media_agent.agent',
        'anthropic',
        'dotenv',
        'requests',
        'bs4',
        'docx',
        'pypdf',
        'cryptography',
        'keyring',
        'PIL',
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'scipy', 'numpy', 'pandas', 'jupyter'],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name='intentos',
    debug=False,
    strip=True,
    upx=True,
    console=True,   # CLI needs a console window
    onefile=True,
)

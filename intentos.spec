# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for IntentOS Desktop.

Bundles the Python backend + React UI into a single distributable.

Build:
    pyinstaller intentos.spec

Output:
    dist/IntentOS.app (macOS)
    dist/IntentOS.exe (Windows)
"""

import os
import sys
from PyInstaller.utils.hooks import collect_all, collect_submodules, collect_data_files

block_cipher = None
project_root = os.path.dirname(os.path.abspath(SPEC))

# ---------------------------------------------------------------------------
# Collect packages that PyInstaller misses with just hiddenimports
# ---------------------------------------------------------------------------
all_datas = []
all_binaries = []
all_hiddenimports = []

# Packages with native extensions or complex internal imports
_packages_to_collect = [
    'anthropic',
    'requests',
    'bs4',
    'docx',
    'pypdf',
    'keyring',
    'cryptography',
    'rich',
    'prompt_toolkit',
    'dotenv',
    'soundfile',
    'certifi',
    'httpx',
    'httpcore',
    'anyio',
    'sniffio',
    'h11',
    'idna',
    'charset_normalizer',
    'urllib3',
    'soupsieve',
]

# Optional heavy packages — collect if installed, skip if not
_optional_packages = [
    'faster_whisper',
    'ctranslate2',
    'piper',
    'onnxruntime',
    'PIL',
    'chromadb',
    'tokenizers',
    'pyttsx3',
]

for pkg in _packages_to_collect:
    try:
        datas, binaries, hiddenimports = collect_all(pkg)
        all_datas += datas
        all_binaries += binaries
        all_hiddenimports += hiddenimports
    except Exception:
        print(f"  [warn] Could not collect {pkg} — skipping")

for pkg in _optional_packages:
    try:
        datas, binaries, hiddenimports = collect_all(pkg)
        all_datas += datas
        all_binaries += binaries
        all_hiddenimports += hiddenimports
    except Exception:
        print(f"  [info] Optional package {pkg} not installed — skipping")

# ---------------------------------------------------------------------------
# IntentOS source modules (explicit hiddenimports for dynamic loads)
# ---------------------------------------------------------------------------
_intentos_modules = [
    # Core
    'core.kernel_v2',
    'core.api.server',
    'core.config',
    'core.first_run',
    # Inference
    'core.inference.llm',
    'core.inference.providers',
    'core.inference.router',
    'core.inference.hardware',
    'core.inference.ollama_manager',
    # Security
    'core.security.pipeline',
    'core.security.credential_provider',
    # Orchestration
    'core.orchestration.sop',
    'core.orchestration.scheduler',
    'core.orchestration.mode_router',
    'core.orchestration.cost_manager',
    'core.orchestration.message_bus',
    # RAG
    'core.rag.context',
    'core.rag.task_index',
    'core.rag.experience',
    'core.rag.file_index',
    # Storage
    'core.storage.chat_store',
    # Voice
    'core.voice.stt',
    'core.voice.tts',
    # Agents (dynamically imported via importlib.import_module)
    'capabilities.file_agent.agent',
    'capabilities.file_agent.primitives',
    'capabilities.file_agent.planner',
    'capabilities.file_agent.audit',
    'capabilities.browser_agent.agent',
    'capabilities.document_agent.agent',
    'capabilities.system_agent.agent',
    'capabilities.image_agent.agent',
    'capabilities.media_agent.agent',
    'capabilities.memory_agent.agent',
]

all_hiddenimports += _intentos_modules

# ---------------------------------------------------------------------------
# Runtime hook to fix paths in frozen mode
# ---------------------------------------------------------------------------
_runtime_hook = os.path.join(project_root, 'scripts', '_pyinstaller_runtime.py')
if not os.path.exists(_runtime_hook):
    # Create the runtime hook inline
    with open(_runtime_hook, 'w') as f:
        f.write("""\
import os, sys
# In frozen mode, make sure project modules can find each other
if getattr(sys, 'frozen', False):
    _meipass = sys._MEIPASS
    if _meipass not in sys.path:
        sys.path.insert(0, _meipass)
    # Set a flag so modules can detect frozen mode
    os.environ['INTENTOS_FROZEN'] = '1'
    os.environ['INTENTOS_BUNDLE_DIR'] = _meipass
""")

# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------
a = Analysis(
    [os.path.join(project_root, 'scripts', 'launcher.py')],
    pathex=[project_root],
    binaries=all_binaries,
    datas=[
        # React UI build
        (os.path.join(project_root, 'ui', 'desktop', 'dist'), 'ui/desktop/dist'),
        # Core Python modules (as data, so dynamic imports can find them)
        (os.path.join(project_root, 'core'), 'core'),
        (os.path.join(project_root, 'capabilities'), 'capabilities'),
        # .env.example as template
        (os.path.join(project_root, '.env.example'), '.'),
    ] + all_datas,
    hiddenimports=all_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[_runtime_hook],
    excludes=[
        'tkinter',
        'matplotlib',
        'scipy',
        'pandas',
        'jupyter',
        'notebook',
        'test',
        'tests',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='IntentOS',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,  # Keep console for debugging; set False for release
    disable_windowed_traceback=False,
    argv_emulation=True,  # macOS argv emulation
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # Add icon path here when ready
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='IntentOS',
)

# macOS .app bundle
app = BUNDLE(
    coll,
    name='IntentOS.app',
    icon=None,  # Add .icns file when ready
    bundle_identifier='com.intentos.desktop',
    info_plist={
        'CFBundleName': 'IntentOS',
        'CFBundleDisplayName': 'IntentOS',
        'CFBundleVersion': '0.1.0',
        'CFBundleShortVersionString': '0.1.0',
        'NSMicrophoneUsageDescription': 'IntentOS uses the microphone for voice input.',
        'NSHighResolutionCapable': True,
    },
)

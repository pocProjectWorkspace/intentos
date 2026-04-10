"""PyInstaller runtime hook for IntentOS.

Sets up sys.path and environment for frozen mode so that
dynamic imports (importlib.import_module) and __file__-based
path resolution work correctly inside the bundle.
"""
import os
import sys

if getattr(sys, 'frozen', False):
    _meipass = sys._MEIPASS
    if _meipass not in sys.path:
        sys.path.insert(0, _meipass)
    # Flag so modules can detect frozen mode
    os.environ['INTENTOS_FROZEN'] = '1'
    os.environ['INTENTOS_BUNDLE_DIR'] = _meipass

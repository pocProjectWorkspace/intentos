"""IntentOS Desktop Launcher.

Single entry point that:
1. Starts the IntentOS kernel + API server
2. Serves the built React UI as static files
3. Opens the browser automatically
4. Handles graceful shutdown

Used by PyInstaller to create a distributable executable.
"""

from __future__ import annotations

import os
import signal
import sys
import threading
import time
import webbrowser
from http.server import HTTPServer, SimpleHTTPRequestHandler
from functools import partial

# Ensure project root is on path
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPT_DIR)

# For PyInstaller bundled mode, adjust paths
if getattr(sys, 'frozen', False):
    _PROJECT_ROOT = sys._MEIPASS
    # Set up env from bundled .env if it exists
    env_path = os.path.join(os.path.expanduser("~"), ".intentos", ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


# ---------------------------------------------------------------------------
# Static file server for the React UI
# ---------------------------------------------------------------------------

class _UIHandler(SimpleHTTPRequestHandler):
    """Serves React build files and proxies /api requests to the kernel."""

    def __init__(self, *args, api_port: int = 7891, **kwargs):
        self._api_port = api_port
        super().__init__(*args, **kwargs)

    def log_message(self, format, *args):
        pass  # Suppress request logging

    def do_GET(self):
        # Proxy /api requests to the kernel API server
        if self.path.startswith("/api"):
            self._proxy_to_api("GET")
            return
        super().do_GET()

    def do_POST(self):
        if self.path.startswith("/api"):
            self._proxy_to_api("POST")
            return
        super().do_POST()

    def do_PUT(self):
        if self.path.startswith("/api"):
            self._proxy_to_api("PUT")
            return
        # SimpleHTTPRequestHandler doesn't handle PUT
        self.send_error(405)

    def do_DELETE(self):
        if self.path.startswith("/api"):
            self._proxy_to_api("DELETE")
            return
        self.send_error(405)

    def do_OPTIONS(self):
        if self.path.startswith("/api"):
            self._proxy_to_api("OPTIONS")
            return
        self.send_response(200)
        self.end_headers()

    def _proxy_to_api(self, method: str):
        """Forward request to the API server running on localhost."""
        import urllib.request
        import urllib.error

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else None

        url = f"http://127.0.0.1:{self._api_port}{self.path}"
        req = urllib.request.Request(url, data=body, method=method)
        req.add_header("Content-Type", self.headers.get("Content-Type", "application/json"))

        try:
            resp = urllib.request.urlopen(req, timeout=300)
            self.send_response(resp.status)
            for key, val in resp.headers.items():
                if key.lower() not in ("transfer-encoding", "connection"):
                    self.send_header(key, val)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()
            self.wfile.write(resp.read())
        except urllib.error.HTTPError as e:
            self.send_response(e.code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(e.read())
        except Exception:
            self.send_error(502, "API server not responding")

    def translate_path(self, path):
        """Serve from the React build directory."""
        # Strip query string
        path = path.split("?")[0].split("#")[0]

        # Serve index.html for SPA routes (anything not a real file)
        file_path = super().translate_path(path)
        if not os.path.exists(file_path) or os.path.isdir(file_path):
            return os.path.join(self.directory, "index.html")
        return file_path


# ---------------------------------------------------------------------------
# Main launcher
# ---------------------------------------------------------------------------

def main():
    import argparse

    parser = argparse.ArgumentParser(description="IntentOS Desktop")
    parser.add_argument("--port", type=int, default=3000,
                        help="UI port (default: 3000)")
    parser.add_argument("--api-port", type=int, default=7891,
                        help="API port (default: 7891)")
    parser.add_argument("--no-browser", action="store_true",
                        help="Don't auto-open browser")
    args = parser.parse_args()

    print()
    print("  IntentOS Desktop")
    print("  ================")
    print()

    # Step 1: Start the kernel + API server
    print("  [1/3] Starting AI engine...")
    try:
        from core.kernel_v2 import IntentKernel
        from core.api.server import APIBridge

        kernel = IntentKernel()
        api = APIBridge(kernel=kernel)
        api.start(port=args.api_port)
        print(f"  [ok]  API server on :{args.api_port}")
    except Exception as e:
        print(f"  [!!]  API server failed: {e}")
        return

    # Step 2: Start the static file server for React UI
    print("  [2/3] Starting interface...")

    # Find the React build directory
    ui_dir = None
    candidates = [
        os.path.join(_PROJECT_ROOT, "ui", "desktop", "dist"),
        os.path.join(_PROJECT_ROOT, "_internal", "ui", "desktop", "dist"),
        os.path.join(_PROJECT_ROOT, "dist"),
        os.path.join(os.path.dirname(_PROJECT_ROOT), "ui", "desktop", "dist"),
        os.path.join(os.path.dirname(_PROJECT_ROOT), "_internal", "ui", "desktop", "dist"),
    ]
    for c in candidates:
        if os.path.exists(os.path.join(c, "index.html")):
            ui_dir = c
            break

    if ui_dir is None:
        print("  [!!]  UI build not found. Run: cd ui/desktop && npm run build")
        print(f"  [!!]  Checked: {candidates}")
        # Still run in API-only mode
        print(f"\n  API running at http://127.0.0.1:{args.api_port}")
        print("  Press Ctrl+C to stop.\n")
    else:
        handler = partial(_UIHandler, directory=ui_dir, api_port=args.api_port)
        ui_server = HTTPServer(("127.0.0.1", args.port), handler)
        ui_thread = threading.Thread(target=ui_server.serve_forever, daemon=True)
        ui_thread.start()
        print(f"  [ok]  Interface on :{args.port}")

        # Step 3: Open browser
        if not args.no_browser:
            print("  [3/3] Opening browser...")
            time.sleep(0.5)
            webbrowser.open(f"http://localhost:{args.port}")

        print(f"\n  IntentOS is running at http://localhost:{args.port}")
        print("  Press Ctrl+C to stop.\n")

    # Block until Ctrl+C
    shutdown = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: shutdown.set())
    signal.signal(signal.SIGTERM, lambda *_: shutdown.set())

    try:
        shutdown.wait()
    except KeyboardInterrupt:
        pass

    print("\n  Shutting down...")
    api.stop()


if __name__ == "__main__":
    if getattr(sys, 'frozen', False):
        # In bundled mode, catch and log all crashes to a file
        _crash_log = os.path.join(
            os.path.expanduser("~"), ".intentos", "crash.log"
        )
        os.makedirs(os.path.dirname(_crash_log), exist_ok=True)
        try:
            main()
        except Exception:
            import traceback
            with open(_crash_log, "a") as f:
                f.write(f"\n--- Crash at {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
                traceback.print_exc(file=f)
            traceback.print_exc()
            input("\n  IntentOS crashed. Press Enter to exit...")
    else:
        main()

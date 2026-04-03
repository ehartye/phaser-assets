#!/usr/bin/env python3
"""Local server for the phaser-assets plugin.

Core: HTTP server, session state, database, route dispatch.
Routes are defined in scripts/routes/ as mixin classes.
"""

import argparse
import json
import os
import sqlite3
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

DB_DIR = os.path.join(os.path.expanduser("~"), ".phaser-assets")
DB_PATH = os.path.join(DB_DIR, "assets.db")


def get_db():
    """Return a connection to the assets database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create the database directory and tables if they don't exist."""
    os.makedirs(DB_DIR, exist_ok=True)
    conn = get_db()
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
            id          TEXT PRIMARY KEY,
            project_path TEXT,
            search_context TEXT,
            created_at  TEXT
        );
        CREATE TABLE IF NOT EXISTS assets (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id  TEXT REFERENCES sessions(id),
            asset_id    TEXT,
            name        TEXT,
            source      TEXT,
            source_url  TEXT,
            license     TEXT,
            type        TEXT,
            project_path TEXT,
            local_path  TEXT,
            status      TEXT DEFAULT 'pending',
            error       TEXT,
            created_at  TEXT
        );
    """)
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

class Session:
    """In-memory state for the current server session."""

    def __init__(self):
        self.session_id = None
        self.assets = []
        self.project_path = None
        self.search_context = None
        self.asset_structure = None
        self.status = "idle"          # idle | downloading | done
        self.results = {"downloaded": [], "failed": []}
        self.lock = threading.Lock()
        self.inspector = {
            "image_path": None,
            "tile_config": {},
            "status": "idle",
            "results": None,
        }
        self.designer = {
            "project_path": None,
            "grid": {"width": 20, "height": 15},
            "tile_size": {"width": 16, "height": 16},
            "tilesets": [],
            "layers": [],
            "zones": [],
            "status": "idle",
            "results": None,
        }

    def reset(self):
        self.__init__()


# Global session instance
session = Session()

# Will be set to the HTTPServer instance so /shutdown can stop it
_server_ref = None


# ---------------------------------------------------------------------------
# Route imports
# ---------------------------------------------------------------------------

# Ensure scripts/ is on sys.path so route modules can `from server import ...`
_script_dir = os.path.dirname(os.path.abspath(__file__))
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)

# When run as `python server.py`, the module is __main__ not server.
# Route modules do `from server import session` which would create a second
# copy of the module. Register __main__ as 'server' so they share state.
if __name__ == "__main__" and "server" not in sys.modules:
    sys.modules["server"] = sys.modules[__name__]

from routes import collect_routes  # noqa: E402
from routes.health import HealthRoutes  # noqa: E402
from routes.asset_finder import AssetFinderRoutes  # noqa: E402
from routes.inspector import InspectorRoutes  # noqa: E402
from routes.assets import AssetsRoutes  # noqa: E402

# Scene designer module is optional until created
try:
    from routes.scene_designer import SceneDesignerRoutes  # noqa: E402
except ModuleNotFoundError:
    SceneDesignerRoutes = None

_base_mixins = [HealthRoutes, AssetFinderRoutes, InspectorRoutes, AssetsRoutes]
if SceneDesignerRoutes is not None:
    _base_mixins.append(SceneDesignerRoutes)

# itch.io module is optional — requires Playwright
try:
    from routes.itch_io import ItchIoRoutes  # noqa: E402
except (ModuleNotFoundError, ImportError):
    ItchIoRoutes = None

if ItchIoRoutes is not None:
    _base_mixins.append(ItchIoRoutes)


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------

class RequestTooLarge(Exception):
    """Raised by read_body() when Content-Length exceeds MAX_BODY_SIZE."""
    pass


class AssetHandler(BaseHTTPRequestHandler, *_base_mixins):
    """Route-dispatching HTTP handler for the asset preview server."""

    MAX_BODY_SIZE = 50 * 1024 * 1024  # 50 MB

    # Suppress default stderr logging
    def log_message(self, format, *args):
        pass

    # ---- helpers ----------------------------------------------------------

    @staticmethod
    def safe_json_for_html(data):
        """JSON-encode data, escaping </ to prevent script injection in HTML."""
        return json.dumps(data).replace("</", "<\\/")

    def read_body(self):
        """Read and parse JSON from the request body."""
        length = int(self.headers.get("Content-Length", 0))
        if length > self.MAX_BODY_SIZE:
            self.send_json({"error": "request body too large"}, 413)
            raise RequestTooLarge()
        raw = self.rfile.read(length)
        if not raw:
            return {}
        return json.loads(raw)

    def send_json(self, data, status=200):
        """Send a JSON response with CORS headers."""
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_html(self, html, status=200):
        """Send an HTML response."""
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def serve_project_file(self, relative_path):
        """Serve a file from the project directory with path traversal protection."""
        if not relative_path or not session.project_path:
            self.send_json({"error": "no file path or project path"}, 400)
            return
        full_path = os.path.realpath(os.path.join(session.project_path, relative_path))
        project_real = os.path.realpath(session.project_path)
        if not full_path.startswith(project_real + os.sep) and full_path != project_real:
            self.send_json({"error": "path escapes project directory"}, 403)
            return
        if not os.path.isfile(full_path):
            self.send_json({"error": "file not found"}, 404)
            return
        ext = os.path.splitext(full_path)[1].lower()
        ct = {
            ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".gif": "image/gif", ".svg": "image/svg+xml", ".webp": "image/webp",
            ".json": "application/json",
        }.get(ext, "application/octet-stream")
        with open(full_path, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ct)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def serve_ui_file(self, filename):
        """Serve a static file from scripts/ui/."""
        if "/" in filename or "\\" in filename or filename.startswith("."):
            self.send_json({"error": "forbidden"}, 403)
            return
        script_dir = os.path.dirname(os.path.abspath(__file__))
        full_path = os.path.join(script_dir, "ui", filename)
        if not os.path.isfile(full_path):
            self.send_json({"error": "not found"}, 404)
            return
        ext = os.path.splitext(filename)[1].lower()
        ct = {".css": "text/css", ".js": "application/javascript"}.get(ext, "text/plain")
        with open(full_path, "r", encoding="utf-8") as f:
            data = f.read().encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", ct)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    # ---- CORS preflight ---------------------------------------------------

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    # ---- route dispatch ---------------------------------------------------

    def do_GET(self):
        path = self.path.split("?")[0]
        if path.startswith("/ui/"):
            self.serve_ui_file(path[4:])
            return
        handler = self._get_routes.get(path)
        if handler:
            getattr(self, handler)()
        else:
            self.send_json({"error": "not found"}, 404)

    def do_POST(self):
        path = self.path.split("?")[0]
        handler = self._post_routes.get(path)
        if handler:
            try:
                getattr(self, handler)()
            except RequestTooLarge:
                return
        else:
            self.send_json({"error": "not found"}, 404)


# Build route tables from modules
AssetHandler._get_routes, AssetHandler._post_routes = collect_routes()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Phaser Assets local server")
    parser.add_argument("--port", type=int, default=0, help="Port (0 = auto)")
    parser.add_argument("--no-open", action="store_true", help="Don't open browser")
    args = parser.parse_args()

    init_db()

    global _server_ref
    server = ThreadingHTTPServer(("127.0.0.1", args.port), AssetHandler)
    _server_ref = server

    host, port = server.server_address
    url = f"http://localhost:{port}"

    # Print JSON for Claude to parse
    print(json.dumps({"port": port, "url": url}), flush=True)

    if not args.no_open:
        def _open_browser(target_url):
            try:
                if sys.platform == "win32":
                    os.startfile(target_url)
                else:
                    webbrowser.open(target_url)
            except Exception:
                pass
        threading.Thread(target=_open_browser, args=(url,), daemon=True).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

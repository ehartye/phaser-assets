#!/usr/bin/env python3
"""Local asset preview server for Phaser Asset Finder.

Serves the asset preview UI, downloads assets into the user's project,
and tracks everything in SQLite. Stdlib only.
"""

import argparse
import io
import json
import os
import secrets
import sqlite3
import sys
import threading
import urllib.request
import urllib.error
import webbrowser
import zipfile
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# ---------------------------------------------------------------------------
# Task 1: SQLite
# ---------------------------------------------------------------------------

DB_DIR = os.path.join(os.path.expanduser("~"), ".phaser-asset-finder")
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
# Task 2: Session state
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

    def reset(self):
        self.__init__()


# Global session instance
session = Session()

# Will be set to the HTTPServer instance so /shutdown can stop it
_server_ref = None

# Default asset structure when none is provided
DEFAULT_ASSET_STRUCTURE = {
    "images": "assets/images",
    "audio": "assets/audio",
    "tilemaps": "assets/tilemaps",
}


# ---------------------------------------------------------------------------
# Task 3: HTTP handler
# ---------------------------------------------------------------------------

class AssetHandler(BaseHTTPRequestHandler):
    """Route-dispatching HTTP handler for the asset preview server."""

    # Suppress default stderr logging
    def log_message(self, format, *args):
        pass

    # ---- helpers ----------------------------------------------------------

    def read_body(self):
        """Read and parse JSON from the request body."""
        length = int(self.headers.get("Content-Length", 0))
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
        routes = {
            "/":            self.handle_index,
            "/health":      self.handle_health,
            "/api/status":  self.handle_status,
            "/api/results": self.handle_results,
        }
        handler = routes.get(path)
        if handler:
            handler()
        else:
            self.send_json({"error": "not found"}, 404)

    def do_POST(self):
        path = self.path.split("?")[0]
        routes = {
            "/start":        self.handle_start,
            "/api/download": self.handle_download,
            "/shutdown":     self.handle_shutdown,
        }
        handler = routes.get(path)
        if handler:
            handler()
        else:
            self.send_json({"error": "not found"}, 404)

    # ------------------------------------------------------------------
    # Task 4: GET /health
    # ------------------------------------------------------------------

    def handle_health(self):
        self.send_json({
            "status": "ok",
            "session_id": session.session_id,
        })

    # ------------------------------------------------------------------
    # Task 5: POST /start
    # ------------------------------------------------------------------

    def handle_start(self):
        body = self.read_body()

        session.reset()
        session.session_id = secrets.token_hex(4)
        session.assets = body.get("assets", [])
        session.project_path = body.get("project_path", "")
        session.search_context = body.get("search_context", "")
        session.asset_structure = body.get("asset_structure") or DEFAULT_ASSET_STRUCTURE

        now = datetime.now(timezone.utc).isoformat()

        conn = get_db()
        conn.execute(
            "INSERT INTO sessions (id, project_path, search_context, created_at) VALUES (?, ?, ?, ?)",
            (session.session_id, session.project_path, session.search_context, now),
        )
        for asset in session.assets:
            conn.execute(
                "INSERT INTO assets (session_id, asset_id, name, source, source_url, license, type, project_path, status, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)",
                (
                    session.session_id,
                    asset.get("id", ""),
                    asset.get("name", ""),
                    asset.get("source", ""),
                    asset.get("sourceUrl", ""),
                    asset.get("license", ""),
                    asset.get("type", ""),
                    session.project_path,
                    now,
                ),
            )
        conn.commit()
        conn.close()

        self.send_json({
            "session_id": session.session_id,
            "asset_count": len(session.assets),
        })

    # ------------------------------------------------------------------
    # Task 6: GET / (serve HTML)
    # ------------------------------------------------------------------

    def handle_index(self):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        template_path = os.path.join(
            script_dir, "..", "skills", "phaser-asset-finder", "assets", "asset-preview.html"
        )
        try:
            with open(template_path, "r", encoding="utf-8") as f:
                html = f.read()
        except FileNotFoundError:
            self.send_json({"error": "template not found", "path": template_path}, 500)
            return

        assets_json = json.dumps(session.assets) if session.assets else "[]"
        html = html.replace("__ASSET_DATA_PLACEHOLDER__", assets_json)
        html = html.replace('"__SEARCH_CONTEXT_PLACEHOLDER__"', json.dumps(session.search_context or ""))
        html = html.replace('"__PROJECT_PATH_PLACEHOLDER__"', json.dumps(session.project_path or ""))
        html = html.replace('"__SESSION_ID_PLACEHOLDER__"', json.dumps(session.session_id or ""))

        self.send_html(html)

    # ------------------------------------------------------------------
    # Task 7a: POST /api/download
    # ------------------------------------------------------------------

    def handle_download(self):
        body = self.read_body()
        selected_ids = set(body.get("selected", []))

        if not selected_ids:
            self.send_json({"error": "no assets selected"}, 400)
            return

        with session.lock:
            session.status = "downloading"
            session.results = {"downloaded": [], "failed": []}

        # Respond immediately
        self.send_json({"status": "downloading", "count": len(selected_ids)})

        # Download in background
        thread = threading.Thread(
            target=_download_assets,
            args=(selected_ids,),
            daemon=True,
        )
        thread.start()

    # ------------------------------------------------------------------
    # Task 7b: GET /api/status
    # ------------------------------------------------------------------

    def handle_status(self):
        with session.lock:
            data = {
                "status": session.status,
                "downloaded": len(session.results.get("downloaded", [])),
                "failed": len(session.results.get("failed", [])),
            }
        self.send_json(data)

    # ------------------------------------------------------------------
    # Task 7c: GET /api/results
    # ------------------------------------------------------------------

    def handle_results(self):
        with session.lock:
            data = dict(session.results)
        self.send_json(data)

    # ------------------------------------------------------------------
    # POST /shutdown
    # ------------------------------------------------------------------

    def handle_shutdown(self):
        self.send_json({"status": "shutting down"})
        if _server_ref:
            threading.Thread(target=_server_ref.shutdown, daemon=True).start()


# ---------------------------------------------------------------------------
# Download logic (runs in background thread)
# ---------------------------------------------------------------------------

# Map asset type -> subdirectory under the project
TYPE_DIR_MAP = {
    "sprite":      ("images", "characters"),
    "sprites":     ("images", "characters"),
    "character":   ("images", "characters"),
    "characters":  ("images", "characters"),
    "tile":        ("images", "tiles"),
    "tiles":       ("images", "tiles"),
    "tileset":     ("images", "tiles"),
    "tilesets":    ("images", "tiles"),
    "tilemap":     ("tilemaps", ""),
    "tilemaps":    ("tilemaps", ""),
    "background":  ("images", "backgrounds"),
    "backgrounds": ("images", "backgrounds"),
    "audio":       ("audio", "sfx"),
    "sfx":         ("audio", "sfx"),
    "music":       ("audio", "music"),
    "ui":          ("images", "ui"),
    "icon":        ("images", "ui"),
    "icons":       ("images", "ui"),
    "font":        ("images", "fonts"),
    "fonts":       ("images", "fonts"),
}


def _safe_extractall(zf, dest_dir):
    """Extract zip contents after verifying no member escapes dest_dir (Zip Slip)."""
    dest = os.path.realpath(str(dest_dir))
    for member in zf.infolist():
        target = os.path.realpath(os.path.join(dest, member.filename))
        if not target.startswith(dest + os.sep) and target != dest:
            raise ValueError(f"Zip member {member.filename!r} escapes target directory")
    zf.extractall(dest_dir)


def _dest_dir_for_asset(asset):
    """Determine the destination directory for an asset based on its type."""
    asset_type = asset.get("type", "").lower()
    structure = session.asset_structure or DEFAULT_ASSET_STRUCTURE

    mapping = TYPE_DIR_MAP.get(asset_type)
    if mapping:
        base_key, sub = mapping
        base = structure.get(base_key, f"assets/{base_key}")
        if sub:
            return os.path.join(session.project_path, base, sub)
        return os.path.join(session.project_path, base)

    # Fallback: use images dir
    return os.path.join(session.project_path, structure.get("images", "assets/images"))


def _download_one(asset):
    """Download a single asset. Returns (success: bool, local_path|None, error|None)."""
    url = asset.get("sourceUrl", "")
    if not url:
        return False, None, "no sourceUrl"

    dest_dir = _dest_dir_for_asset(asset)
    os.makedirs(dest_dir, exist_ok=True)

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "PhaserAssetFinder/1.0"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read()
            content_type = resp.headers.get("Content-Type", "")

            # Derive filename from URL
            url_path = url.split("?")[0].split("#")[0]
            filename = os.path.basename(url_path) or f"{asset.get('id', 'asset')}"
            if not os.path.splitext(filename)[1]:
                # Try to guess extension from content type
                ext_map = {
                    "image/png": ".png",
                    "image/jpeg": ".jpg",
                    "image/gif": ".gif",
                    "image/svg+xml": ".svg",
                    "audio/mpeg": ".mp3",
                    "audio/ogg": ".ogg",
                    "audio/wav": ".wav",
                    "application/json": ".json",
                    "application/zip": ".zip",
                }
                ext = ext_map.get(content_type.split(";")[0].strip(), "")
                filename += ext

            # Handle zip files
            if filename.endswith(".zip") or "zip" in content_type:
                buf = io.BytesIO(data)
                try:
                    with zipfile.ZipFile(buf) as zf:
                        _safe_extractall(zf, dest_dir)
                    return True, dest_dir, None
                except zipfile.BadZipFile:
                    # Not actually a zip — save as-is
                    pass

            # Write file
            local_path = os.path.join(dest_dir, filename)
            with open(local_path, "wb") as f:
                f.write(data)
            return True, local_path, None

    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
        return False, None, str(exc)


def _download_assets(selected_ids):
    """Download selected assets (runs in a background thread)."""
    # Build lookup of selected assets
    selected = [a for a in session.assets if a.get("id") in selected_ids]

    conn = get_db()
    for asset in selected:
        success, local_path, error = _download_one(asset)
        aid = asset.get("id", "")
        name = asset.get("name", "")
        source_url = asset.get("sourceUrl", "")
        license_info = asset.get("license", "")

        # Return paths relative to project_path
        rel_path = local_path
        if success and local_path and session.project_path:
            try:
                rel_path = os.path.relpath(local_path, session.project_path)
            except ValueError:
                rel_path = local_path

        if success:
            with session.lock:
                session.results["downloaded"].append({
                    "id": aid,
                    "name": name,
                    "path": rel_path,
                    "license": license_info,
                })
            conn.execute(
                "UPDATE assets SET status='downloaded', local_path=? WHERE session_id=? AND asset_id=?",
                (local_path, session.session_id, aid),
            )
        else:
            with session.lock:
                session.results["failed"].append({
                    "id": aid,
                    "name": name,
                    "source_url": source_url,
                    "license": license_info,
                    "error": error,
                })
            conn.execute(
                "UPDATE assets SET status='failed', error=? WHERE session_id=? AND asset_id=?",
                (error, session.session_id, aid),
            )
        conn.commit()

    conn.close()
    with session.lock:
        session.status = "done"


# ---------------------------------------------------------------------------
# Task 8: CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Phaser Asset Finder local server")
    parser.add_argument(
        "--port", type=int, default=0,
        help="Port to listen on (0 = auto-assign)",
    )
    parser.add_argument(
        "--no-open", action="store_true",
        help="Don't open the browser automatically",
    )
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
        # Open browser in a background thread.
        # On Windows, use os.startfile to avoid inheriting subprocess handles
        # which can block parent pipe reads.
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

# Scene Designer Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use h-superpowers:subagent-driven-development, h-superpowers:team-driven-development, or h-superpowers:executing-plans to implement this plan (ask user which approach).

**Goal:** Modularize the server into route modules, then add a tile-based scene designer that outputs Tiled-compatible JSON for Phaser.

**Architecture:** Refactor `server.py` into a thin core (HTTP server, session, DB, dispatch) + route modules as mixin classes. Then add the scene designer as a new route module + HTML template + SKILL.md. The scene designer lets Claude pre-populate a grid, the user edits visually, and the result is standard Tiled JSON.

**Tech Stack:** Python stdlib, vanilla HTML/CSS/JS, Tiled JSON format

---

## Phase 1: Server Modularization

### Task 1: Create routes package and shared utilities

**Files:**
- Create: `scripts/routes/__init__.py`

**Step 1: Create the routes package**

```bash
mkdir -p scripts/routes
```

**Step 2: Create `__init__.py` with route collection utility**

```python
"""Route modules for the phaser-assets server.

Each module exports:
- A mixin class with handler methods
- A ROUTES dict: {"GET": {"/path": "method_name"}, "POST": {...}}
"""

from . import health, asset_finder, inspector, scene_designer

ALL_MODULES = [health, asset_finder, inspector, scene_designer]


def collect_routes():
    """Aggregate ROUTES dicts from all modules. Returns (get_routes, post_routes)."""
    get_routes = {}
    post_routes = {}
    for mod in ALL_MODULES:
        routes = getattr(mod, "ROUTES", {})
        get_routes.update(routes.get("GET", {}))
        post_routes.update(routes.get("POST", {}))
    return get_routes, post_routes
```

**Step 3: Commit**

```bash
git add scripts/routes/__init__.py
git commit -m "feat: create routes package with route collection utility"
```

---

### Task 2: Extract health and shutdown routes

**Files:**
- Create: `scripts/routes/health.py`

**Step 1: Create health.py**

Extract `handle_health` and `handle_shutdown` from `server.py`. These need access to `session` and `_server_ref` globals — import them from server.

```python
"""Health check and shutdown routes."""

import threading


ROUTES = {
    "GET": {
        "/health": "handle_health",
    },
    "POST": {
        "/shutdown": "handle_shutdown",
    },
}


class HealthRoutes:
    """Mixin providing /health and /shutdown handlers."""

    def handle_health(self):
        from server import session
        self.send_json({
            "status": "ok",
            "session_id": session.session_id,
        })

    def handle_shutdown(self):
        from server import _server_ref
        self.send_json({"status": "shutting down"})
        if _server_ref:
            threading.Thread(target=_server_ref.shutdown, daemon=True).start()
```

**Step 2: Commit**

```bash
git add scripts/routes/health.py
git commit -m "feat: extract health/shutdown routes to routes/health.py"
```

---

### Task 3: Extract asset finder routes

**Files:**
- Create: `scripts/routes/asset_finder.py`

**Step 1: Create asset_finder.py**

Extract from `server.py`:
- `handle_start` (POST /start)
- `handle_index` (GET /)
- `handle_download` (POST /api/download)
- `handle_status` (GET /api/status)
- `handle_results` (GET /api/results)
- All download helper functions: `TYPE_DIR_MAP`, `_safe_extractall`, `_dest_dir_for_asset`, `_download_one`, `_download_assets`
- `DEFAULT_ASSET_STRUCTURE` constant

```python
"""Asset finder routes — search, preview, download assets."""

import io
import json
import os
import secrets
import threading
import urllib.request
import urllib.error
import zipfile
from datetime import datetime, timezone


ROUTES = {
    "GET": {
        "/":            "handle_index",
        "/api/status":  "handle_status",
        "/api/results": "handle_results",
    },
    "POST": {
        "/start":        "handle_start",
        "/api/download": "handle_download",
    },
}

DEFAULT_ASSET_STRUCTURE = {
    "images": "assets/images",
    "audio": "assets/audio",
    "tilemaps": "assets/tilemaps",
}

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
    """Extract zip contents after verifying no member escapes dest_dir."""
    dest = os.path.realpath(str(dest_dir))
    for member in zf.infolist():
        target = os.path.realpath(os.path.join(dest, member.filename))
        if not target.startswith(dest + os.sep) and target != dest:
            raise ValueError(f"Zip member {member.filename!r} escapes target directory")
    zf.extractall(dest_dir)


def _dest_dir_for_asset(asset, session):
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
    return os.path.join(session.project_path, structure.get("images", "assets/images"))


def _download_one(asset, session):
    """Download a single asset. Returns (success, local_path|None, error|None)."""
    url = asset.get("sourceUrl", "")
    if not url:
        return False, None, "no sourceUrl"
    dest_dir = _dest_dir_for_asset(asset, session)
    os.makedirs(dest_dir, exist_ok=True)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "PhaserAssetFinder/1.0"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read()
            content_type = resp.headers.get("Content-Type", "")
            url_path = url.split("?")[0].split("#")[0]
            filename = os.path.basename(url_path) or f"{asset.get('id', 'asset')}"
            if not os.path.splitext(filename)[1]:
                ext_map = {
                    "image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif",
                    "image/svg+xml": ".svg", "audio/mpeg": ".mp3", "audio/ogg": ".ogg",
                    "audio/wav": ".wav", "application/json": ".json", "application/zip": ".zip",
                }
                ext = ext_map.get(content_type.split(";")[0].strip(), "")
                filename += ext
            if filename.endswith(".zip") or "zip" in content_type:
                buf = io.BytesIO(data)
                try:
                    with zipfile.ZipFile(buf) as zf:
                        _safe_extractall(zf, dest_dir)
                    return True, dest_dir, None
                except zipfile.BadZipFile:
                    pass
            local_path = os.path.join(dest_dir, filename)
            with open(local_path, "wb") as f:
                f.write(data)
            return True, local_path, None
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
        return False, None, str(exc)


def _download_assets(selected_ids, session, get_db):
    """Download selected assets (runs in a background thread)."""
    selected = [a for a in session.assets if a.get("id") in selected_ids]
    conn = get_db()
    for asset in selected:
        success, local_path, error = _download_one(asset, session)
        aid = asset.get("id", "")
        name = asset.get("name", "")
        source_url = asset.get("sourceUrl", "")
        license_info = asset.get("license", "")
        rel_path = local_path
        if success and local_path and session.project_path:
            try:
                rel_path = os.path.relpath(local_path, session.project_path)
            except ValueError:
                rel_path = local_path
        if success:
            with session.lock:
                session.results["downloaded"].append({
                    "id": aid, "name": name, "path": rel_path, "license": license_info,
                })
            conn.execute(
                "UPDATE assets SET status='downloaded', local_path=? WHERE session_id=? AND asset_id=?",
                (local_path, session.session_id, aid),
            )
        else:
            with session.lock:
                session.results["failed"].append({
                    "id": aid, "name": name, "source_url": source_url,
                    "license": license_info, "error": error,
                })
            conn.execute(
                "UPDATE assets SET status='failed', error=? WHERE session_id=? AND asset_id=?",
                (error, session.session_id, aid),
            )
        conn.commit()
    conn.close()
    with session.lock:
        session.status = "done"


class AssetFinderRoutes:
    """Mixin providing asset finder handlers."""

    def handle_start(self):
        from server import session, get_db
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
                (session.session_id, asset.get("id", ""), asset.get("name", ""),
                 asset.get("source", ""), asset.get("sourceUrl", ""), asset.get("license", ""),
                 asset.get("type", ""), session.project_path, now),
            )
        conn.commit()
        conn.close()
        self.send_json({"session_id": session.session_id, "asset_count": len(session.assets)})

    def handle_index(self):
        from server import session
        script_dir = os.path.dirname(os.path.abspath(__file__))
        template_path = os.path.join(
            script_dir, "..", "skills", "asset-finder", "assets", "asset-preview.html"
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

    def handle_download(self):
        from server import session, get_db
        body = self.read_body()
        selected_ids = set(body.get("selected", []))
        if not selected_ids:
            self.send_json({"error": "no assets selected"}, 400)
            return
        with session.lock:
            session.status = "downloading"
            session.results = {"downloaded": [], "failed": []}
        self.send_json({"status": "downloading", "count": len(selected_ids)})
        thread = threading.Thread(
            target=_download_assets, args=(selected_ids, session, get_db), daemon=True,
        )
        thread.start()

    def handle_status(self):
        from server import session
        with session.lock:
            data = {
                "status": session.status,
                "downloaded": len(session.results.get("downloaded", [])),
                "failed": len(session.results.get("failed", [])),
            }
        self.send_json(data)

    def handle_results(self):
        from server import session
        with session.lock:
            data = dict(session.results)
        self.send_json(data)
```

Note: `_download_assets` and `_dest_dir_for_asset` now take `session` as a parameter instead of using the global directly. `_download_assets` also takes `get_db`. The handler methods import `session` and `get_db` lazily from `server` to avoid circular imports.

**Step 2: Commit**

```bash
git add scripts/routes/asset_finder.py
git commit -m "feat: extract asset finder routes to routes/asset_finder.py"
```

---

### Task 4: Extract inspector routes

**Files:**
- Create: `scripts/routes/inspector.py`

**Step 1: Create inspector.py**

Extract from `server.py`:
- `handle_inspector_load` (POST /api/inspector/load)
- `handle_inspector` (GET /inspector)
- `handle_inspector_image` (GET /inspector/image)
- `handle_inspector_submit` (POST /api/inspector/submit)
- `handle_inspector_results` (GET /api/inspector/results)

Shared helper: `serve_project_image(self, image_path)` — extracted from `handle_inspector_image` since the scene designer will also need to serve images from the project. Put this in a utility or keep it in the inspector module and import from scene_designer.

Actually, better to create a shared utility function `serve_project_file` that both inspector and scene_designer can use. Add it to `server.py` core since it needs `session.project_path`.

```python
"""Sprite inspector routes."""

import json
import os


ROUTES = {
    "GET": {
        "/inspector":             "handle_inspector",
        "/inspector/image":       "handle_inspector_image",
        "/api/inspector/results": "handle_inspector_results",
    },
    "POST": {
        "/api/inspector/load":   "handle_inspector_load",
        "/api/inspector/submit": "handle_inspector_submit",
    },
}


IMAGE_CONTENT_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
    ".webp": "image/webp",
}


class InspectorRoutes:
    """Mixin providing sprite inspector handlers."""

    def handle_inspector_load(self):
        from server import session
        body = self.read_body()
        if body.get("project_path"):
            session.project_path = body["project_path"]
        session.inspector = {
            "image_path": body.get("image_path", ""),
            "tile_config": {
                "tile_width": body.get("tile_width", 32),
                "tile_height": body.get("tile_height", 32),
                "margin": body.get("margin", 0),
                "spacing": body.get("spacing", 0),
            },
            "status": "active",
            "results": None,
        }
        self.send_json({"status": "loaded", "image_path": session.inspector["image_path"]})

    def handle_inspector(self):
        from server import session
        script_dir = os.path.dirname(os.path.abspath(__file__))
        template_path = os.path.join(
            script_dir, "..", "skills", "sprite-inspector", "assets", "sprite-inspector.html"
        )
        try:
            with open(template_path, "r", encoding="utf-8") as f:
                html = f.read()
        except FileNotFoundError:
            self.send_json({"error": "inspector template not found"}, 500)
            return
        html = html.replace("__TILE_CONFIG_PLACEHOLDER__", json.dumps(session.inspector.get("tile_config", {})))
        html = html.replace('"__IMAGE_PATH_PLACEHOLDER__"', json.dumps(session.inspector.get("image_path", "")))
        self.send_html(html)

    def handle_inspector_image(self):
        from server import session
        image_path = session.inspector.get("image_path", "")
        self.serve_project_file(image_path)

    def handle_inspector_submit(self):
        from server import session
        body = self.read_body()
        session.inspector["results"] = {
            "sprite_sheet": session.inspector.get("image_path", ""),
            "tile_size": [
                session.inspector["tile_config"].get("tile_width", 32),
                session.inspector["tile_config"].get("tile_height", 32),
            ],
            "animations": body.get("animations", {}),
            "selections": body.get("selections", {}),
            "compositions": body.get("compositions", {}),
        }
        session.inspector["status"] = "submitted"
        self.send_json({"status": "submitted"})

    def handle_inspector_results(self):
        from server import session
        if session.inspector.get("status") != "submitted":
            self.send_json({"status": session.inspector.get("status", "idle"), "results": None})
            return
        self.send_json({"status": "submitted", "results": session.inspector.get("results")})
```

**Step 2: Add `serve_project_file` helper to server.py core**

This is a reusable method on `AssetHandler` that serves a file from the project directory with path traversal protection. Both inspector and scene designer use it.

```python
    def serve_project_file(self, relative_path):
        """Serve a file from the project directory with path traversal protection."""
        if not relative_path or not session.project_path:
            self.send_json({"error": "no file path or project path"}, 400)
            return

        full_path = os.path.join(session.project_path, relative_path)
        full_path = os.path.realpath(full_path)

        project_real = os.path.realpath(session.project_path)
        if not full_path.startswith(project_real + os.sep) and full_path != project_real:
            self.send_json({"error": "path escapes project directory"}, 403)
            return

        if not os.path.isfile(full_path):
            self.send_json({"error": "file not found"}, 404)
            return

        ext = os.path.splitext(full_path)[1].lower()
        content_types = {
            ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".gif": "image/gif", ".svg": "image/svg+xml", ".webp": "image/webp",
            ".json": "application/json",
        }
        ct = content_types.get(ext, "application/octet-stream")

        with open(full_path, "rb") as f:
            data = f.read()

        self.send_response(200)
        self.send_header("Content-Type", ct)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)
```

**Step 3: Commit**

```bash
git add scripts/routes/inspector.py
git commit -m "feat: extract inspector routes to routes/inspector.py"
```

---

### Task 5: Refactor server.py to use route modules

**Files:**
- Modify: `scripts/server.py`

**Step 1: Rewrite server.py as thin core**

Remove all handler methods and download logic. Import mixins and build the handler class. Keep: Session, DB, `serve_project_file`, helpers, CLI.

The new `server.py` should be approximately:

```python
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
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    os.makedirs(DB_DIR, exist_ok=True)
    conn = get_db()
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY, project_path TEXT,
            search_context TEXT, created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS assets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT REFERENCES sessions(id),
            asset_id TEXT, name TEXT, source TEXT, source_url TEXT,
            license TEXT, type TEXT, project_path TEXT, local_path TEXT,
            status TEXT DEFAULT 'pending', error TEXT, created_at TEXT
        );
    """)
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

class Session:
    def __init__(self):
        self.session_id = None
        self.assets = []
        self.project_path = None
        self.search_context = None
        self.asset_structure = None
        self.status = "idle"
        self.results = {"downloaded": [], "failed": []}
        self.lock = threading.Lock()
        self.inspector = {
            "image_path": None, "tile_config": {},
            "status": "idle", "results": None,
        }
        self.designer = {
            "project_path": None,
            "grid": {"width": 20, "height": 15},
            "tile_size": {"width": 16, "height": 16},
            "tilesets": [], "layers": [], "zones": [],
            "status": "idle", "results": None,
        }

    def reset(self):
        self.__init__()


session = Session()
_server_ref = None


# ---------------------------------------------------------------------------
# Route imports
# ---------------------------------------------------------------------------

# Ensure scripts/ is on sys.path so route modules can import server
_script_dir = os.path.dirname(os.path.abspath(__file__))
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)

from routes import collect_routes
from routes.health import HealthRoutes
from routes.asset_finder import AssetFinderRoutes
from routes.inspector import InspectorRoutes
from routes.scene_designer import SceneDesignerRoutes


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------

class AssetHandler(BaseHTTPRequestHandler, HealthRoutes, AssetFinderRoutes, InspectorRoutes, SceneDesignerRoutes):

    def log_message(self, format, *args):
        pass

    def read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        if not raw:
            return {}
        return json.loads(raw)

    def send_json(self, data, status=200):
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

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        path = self.path.split("?")[0]
        handler = self._get_routes.get(path)
        if handler:
            getattr(self, handler)()
        else:
            self.send_json({"error": "not found"}, 404)

    def do_POST(self):
        path = self.path.split("?")[0]
        handler = self._post_routes.get(path)
        if handler:
            getattr(self, handler)()
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
```

**Step 2: Verify all existing routes still work**

```bash
python scripts/server.py --port 8483 --no-open &
curl -s http://localhost:8483/health
# Expected: {"status": "ok", "session_id": null}
curl -s -X POST http://localhost:8483/shutdown
```

**Step 3: Commit**

```bash
git add scripts/server.py
git commit -m "refactor: slim server.py to core + route module dispatch"
```

---

### Task 6: Verify full server after refactor

**Step 1: Start server and test all existing routes**

```bash
python scripts/server.py --port 8483 --no-open &

# Health
curl -s http://localhost:8483/health

# Start session
curl -s -X POST http://localhost:8483/start -H "Content-Type: application/json" \
  -d '{"assets":[],"project_path":"/tmp/test","search_context":"test"}'

# Asset finder
curl -s http://localhost:8483/
curl -s http://localhost:8483/api/status
curl -s http://localhost:8483/api/results

# Inspector
curl -s -X POST http://localhost:8483/api/inspector/load -H "Content-Type: application/json" \
  -d '{"project_path":"/tmp/test","image_path":"test.png","tile_width":16,"tile_height":16}'
curl -s http://localhost:8483/api/inspector/results

# Shutdown
curl -s -X POST http://localhost:8483/shutdown
```

All should return valid JSON responses (templates may 500 if test files don't exist — that's OK, the route dispatch works).

**Step 2: Commit any fixes**

```bash
git add -A
git commit -m "fix: adjustments from post-refactor verification"
```

---

## Phase 2: Scene Designer

### Task 7: Create scene designer route module

**Files:**
- Create: `scripts/routes/scene_designer.py`

**Step 1: Create the route module**

```python
"""Scene designer routes — tile-based level editor with Tiled JSON export."""

import json
import os
from urllib.parse import parse_qs, urlparse


ROUTES = {
    "GET": {
        "/designer":             "handle_designer",
        "/designer/tileset":     "handle_designer_tileset",
        "/api/designer/results": "handle_designer_results",
        "/api/designer/export":  "handle_designer_export",
    },
    "POST": {
        "/api/designer/load":   "handle_designer_load",
        "/api/designer/submit": "handle_designer_submit",
    },
}


class SceneDesignerRoutes:
    """Mixin providing scene designer handlers."""

    def handle_designer_load(self):
        from server import session
        body = self.read_body()
        if body.get("project_path"):
            session.project_path = body["project_path"]
        session.designer = {
            "project_path": body.get("project_path", session.project_path),
            "grid": body.get("grid", {"width": 20, "height": 15}),
            "tile_size": body.get("tile_size", {"width": 16, "height": 16}),
            "tilesets": body.get("tilesets", []),
            "layers": body.get("layers", []),
            "zones": body.get("zones", []),
            "status": "active",
            "results": None,
        }
        self.send_json({
            "status": "loaded",
            "grid": session.designer["grid"],
            "layer_count": len(session.designer["layers"]),
            "tileset_count": len(session.designer["tilesets"]),
        })

    def handle_designer(self):
        from server import session
        script_dir = os.path.dirname(os.path.abspath(__file__))
        template_path = os.path.join(
            script_dir, "..", "skills", "scene-designer", "assets", "scene-designer.html"
        )
        try:
            with open(template_path, "r", encoding="utf-8") as f:
                html = f.read()
        except FileNotFoundError:
            self.send_json({"error": "scene designer template not found"}, 500)
            return

        html = html.replace("__GRID_CONFIG_PLACEHOLDER__", json.dumps(session.designer.get("grid", {})))
        html = html.replace("__TILE_SIZE_PLACEHOLDER__", json.dumps(session.designer.get("tile_size", {})))
        html = html.replace("__TILESETS_PLACEHOLDER__", json.dumps(session.designer.get("tilesets", [])))
        html = html.replace("__LAYERS_PLACEHOLDER__", json.dumps(session.designer.get("layers", [])))
        html = html.replace("__ZONES_PLACEHOLDER__", json.dumps(session.designer.get("zones", [])))

        self.send_html(html)

    def handle_designer_tileset(self):
        """Serve a tileset image. Path passed as ?path=relative/path.png"""
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        image_path = params.get("path", [None])[0]
        if not image_path:
            self.send_json({"error": "missing path parameter"}, 400)
            return
        self.serve_project_file(image_path)

    def handle_designer_submit(self):
        from server import session
        body = self.read_body()
        session.designer["results"] = {
            "grid": body.get("grid", session.designer.get("grid")),
            "tile_size": body.get("tile_size", session.designer.get("tile_size")),
            "tilesets": body.get("tilesets", session.designer.get("tilesets")),
            "layers": body.get("layers", []),
            "zones": body.get("zones", []),
        }
        session.designer["status"] = "submitted"
        self.send_json({"status": "submitted"})

    def handle_designer_results(self):
        from server import session
        if session.designer.get("status") != "submitted":
            self.send_json({"status": session.designer.get("status", "idle"), "results": None})
            return
        self.send_json({
            "status": "submitted",
            "results": session.designer.get("results"),
        })

    def handle_designer_export(self):
        """Export the submitted scene as Tiled-compatible JSON."""
        from server import session
        results = session.designer.get("results")
        if not results:
            self.send_json({"error": "no scene data submitted"}, 400)
            return

        grid = results["grid"]
        tile_size = results["tile_size"]
        tilesets = results.get("tilesets", [])
        layers = results.get("layers", [])
        zones = results.get("zones", [])

        # Build Tiled tileset references with firstgid
        tiled_tilesets = []
        gid = 1
        for ts in tilesets:
            tiled_tilesets.append({
                "firstgid": gid,
                "name": ts.get("name", "tileset"),
                "image": ts.get("image_path", ""),
                "tilewidth": ts.get("tile_width", tile_size["width"]),
                "tileheight": ts.get("tile_height", tile_size["height"]),
                "margin": ts.get("margin", 0),
                "spacing": ts.get("spacing", 0),
                "tilecount": ts.get("tile_count", 0),
                "columns": ts.get("columns", 0),
            })
            gid += ts.get("tile_count", 256)

        # Build Tiled layers
        tiled_layers = []
        for layer in layers:
            if layer.get("type") == "objectgroup":
                tiled_layers.append({
                    "name": layer.get("name", "objects"),
                    "type": "objectgroup",
                    "objects": layer.get("objects", []),
                    "opacity": 1, "visible": True,
                    "x": 0, "y": 0,
                })
            else:
                tiled_layers.append({
                    "name": layer.get("name", "layer"),
                    "type": "tilelayer",
                    "data": layer.get("data", [0] * (grid["width"] * grid["height"])),
                    "width": grid["width"],
                    "height": grid["height"],
                    "opacity": 1, "visible": True,
                    "x": 0, "y": 0,
                })

        # Add zones as an object layer
        if zones:
            zone_objects = []
            for z in zones:
                zone_objects.append({
                    "name": z.get("name", "zone"),
                    "type": z.get("type", "zone"),
                    "x": z.get("x", 0), "y": z.get("y", 0),
                    "width": z.get("width", tile_size["width"]),
                    "height": z.get("height", tile_size["height"]),
                    "visible": True,
                })
            tiled_layers.append({
                "name": "Zones",
                "type": "objectgroup",
                "objects": zone_objects,
                "opacity": 1, "visible": True,
                "x": 0, "y": 0,
            })

        tiled_map = {
            "version": "1.10",
            "tiledversion": "1.10.0",
            "orientation": "orthogonal",
            "renderorder": "right-down",
            "width": grid["width"],
            "height": grid["height"],
            "tilewidth": tile_size["width"],
            "tileheight": tile_size["height"],
            "infinite": False,
            "layers": tiled_layers,
            "tilesets": tiled_tilesets,
            "type": "map",
        }

        body = json.dumps(tiled_map, indent=2).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Disposition", "attachment; filename=scene.json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)
```

**Step 2: Commit**

```bash
git add scripts/routes/scene_designer.py
git commit -m "feat: add scene designer route module with Tiled JSON export"
```

---

### Task 8: Create scene-designer.html template

**Files:**
- Create: `skills/scene-designer/assets/scene-designer.html`

**Step 1: Create directory**

```bash
mkdir -p skills/scene-designer/assets
```

**Step 2: Build the HTML**

This is the largest piece. Self-contained HTML with:

**Placeholders (injected by server):**
- `__GRID_CONFIG_PLACEHOLDER__` — JS object `{width, height}`
- `__TILE_SIZE_PLACEHOLDER__` — JS object `{width, height}`
- `__TILESETS_PLACEHOLDER__` — JS array of tileset configs
- `__LAYERS_PLACEHOLDER__` — JS array of layers with data
- `__ZONES_PLACEHOLDER__` — JS array of zone objects

**CSS:** Same dark theme variables as other plugin UIs (--bg: #0f1118, etc.). Three-panel layout.

**Left Panel — Tileset Palette:**
- Load tileset images from `/designer/tileset?path=...`
- Show tiles in a grid, click to select as active brush
- "Recently Used" at top sorted by usage count (maintained in JS state)
- Tabs to switch between loaded tilesets

**Center — Scene Canvas:**
- HTML5 Canvas element, sized to grid * tile_size * zoom
- Render all visible tile layers bottom-to-top
- Overlay: grid lines (toggleable), zone rectangles, current tool indicator
- Mouse handling: paint (click/drag places active tile), erase (click/drag sets to 0), fill (flood fill from click point), select (click zones)
- Zoom in/out buttons
- Scroll with overflow

**Right Panel — Layers & Properties:**
- Layer list: name, visibility eye toggle, active highlight, delete button, "Add Layer" button
- Zone list: name, type, position, delete button, "Add Zone" button (then click-drag on canvas to define)
- Grid size: width/height number inputs with "Resize" button

**Bottom Bar:**
- Tool buttons: Paint, Erase, Fill, Zone (draw collision/zone rectangles)
- "Send to Claude" button — collects all state and POSTs to `/api/designer/submit`
- "Export Tiled JSON" button — window.open('/api/designer/export')

**JS Architecture:**
- State: `grid`, `tileSize`, `tilesets` (with loaded Image objects), `layers` (array of layer objects with data arrays), `zones` (array of zone objects), `activeTileset`, `activeTile`, `activeLayer`, `activeTool`, `recentTiles` (Map of tileId -> count)
- Init: parse placeholders, load all tileset images from `/designer/tileset?path=...`, render grid from pre-populated layer data
- Paint: on mousedown/mousemove with button held, set `layers[activeLayer].data[row * width + col] = activeTile` and re-render
- Fill: standard flood fill algorithm from click point on active layer
- Zone drawing: mousedown sets start point, mousemove shows preview rect, mouseup creates zone object
- Resize: creates new data arrays, copies old data that fits

**Reference:** Use the existing `sprite-inspector.html` for dark theme CSS patterns. Use `C:/Users/ehart/anika-projects/kwest-slayurz/inspector.html` for canvas rendering approach.

**Step 3: Verify in browser**

Start server, POST to `/api/designer/load` with test data (empty layers, one tileset), open `/designer`, verify three-panel layout renders, tiles are paintable.

**Step 4: Commit**

```bash
git add skills/scene-designer/assets/scene-designer.html
git commit -m "feat: add scene designer HTML template with tile editor UI"
```

---

### Task 9: Create scene-designer SKILL.md

**Files:**
- Create: `skills/scene-designer/SKILL.md`

**Step 1: Write the skill**

```markdown
---
name: scene-designer
description: Visually design game levels, rooms, and structures using sprite sheet tiles for Phaser JS games. Triggers when the user wants to design a level, create a scene, build a room, lay out a map, place tiles, or compose a game area from sprite sheets. Also triggers for Tiled tilemap creation.
---

# Scene Designer

Open a visual tile-based scene editor so the user can design game levels, rooms, and structures. Claude pre-populates the grid with tiles and zones, the user refines visually, and the result is a Tiled-compatible JSON tilemap that Phaser loads natively.

## When to Use

Use this when the user wants to create or edit a game level, room, building, or any tile-based structure. Works for both top-down and side-scrolling layouts. Requires sprite sheets already in the project (via asset-finder or manually added).

## Step 1: Determine Scene Parameters

Before opening the designer, determine:
- **Grid size**: Width x height in tiles (e.g., 20x15 for a single screen, 100x20 for a scrolling level)
- **Tile size**: Usually 16x16 or 32x32 pixels
- **Tilesets**: Which sprite sheets to load as tile palettes (paths relative to project)
- **Layers**: What tile layers are needed (Ground, Buildings, Decorations, etc.)
- **Collision/zones**: Where collision, spawn points, exits, etc. should go

If the user is vague, suggest sensible defaults based on game type:
- Side-scroller: 40x15, ground layer + platform layer + decoration layer + collision
- Top-down RPG: 20x20, ground + walls + objects + collision
- Single room: 12x10, floor + walls + furniture + collision

## Step 2: Pre-populate and Launch

1. Ensure the server is running:
\`\`\`bash
curl -s http://localhost:8483/health || python "$CLAUDE_PLUGIN_ROOT/scripts/server.py" --port 8483 --no-open &
\`\`\`

2. POST the scene config with pre-populated data:
\`\`\`bash
curl -s -X POST http://localhost:8483/api/designer/load \
  -H "Content-Type: application/json" \
  -d '{
    "project_path": "<absolute_project_path>",
    "grid": {"width": 20, "height": 15},
    "tile_size": {"width": 16, "height": 16},
    "tilesets": [
      {
        "name": "terrain",
        "image_path": "assets/images/tiles/terrain.png",
        "tile_width": 16, "tile_height": 16,
        "margin": 0, "spacing": 0
      }
    ],
    "layers": [
      {"name": "Ground", "type": "tilelayer", "data": [...]},
      {"name": "Buildings", "type": "tilelayer", "data": [0, 0, ...]},
      {"name": "Collision", "type": "objectgroup", "objects": []}
    ],
    "zones": [
      {"name": "spawn", "x": 32, "y": 192, "width": 16, "height": 16}
    ]
  }'
\`\`\`

Use tile indices from sprite-inspector results to pre-fill layers. For example, if grass is tile index 5 in the terrain tileset, fill the Ground layer data array with 6 (index 5 + firstgid 1).

3. Tell the user to open http://localhost:8483/designer. Explain:
   - **Left panel**: Tile palette — click a tile to select it as your brush
   - **Center**: Scene canvas — paint tiles, draw zones
   - **Right panel**: Manage layers, zones, and grid size
   - **Tools**: Paint, Erase, Fill, Zone drawing

## Step 3: Get Results and Generate Output

1. Poll for results:
\`\`\`bash
curl -s http://localhost:8483/api/designer/results
\`\`\`
Wait until `status` is `"submitted"`.

2. Export as Tiled JSON:
\`\`\`bash
curl -s http://localhost:8483/api/designer/export > "<project_path>/assets/tilemaps/level1.json"
\`\`\`

3. Generate Phaser loading code:
\`\`\`javascript
// preload()
this.load.tilemapTiledJSON('level1', 'assets/tilemaps/level1.json');
this.load.image('terrain-tiles', 'assets/images/tiles/terrain.png');

// create()
const map = this.make.tilemap({ key: 'level1' });
const tileset = map.addTilesetImage('terrain', 'terrain-tiles');
const groundLayer = map.createLayer('Ground', tileset, 0, 0);
const buildingLayer = map.createLayer('Buildings', tileset, 0, 0);

// Collision from object layer
const collisionLayer = map.getObjectLayer('Collision');
// ... or from tile properties
\`\`\`

4. Read `references/phaser-integration.md` (in the asset-finder skill directory) for complete tilemap code patterns.

5. Shut down the server when done:
\`\`\`bash
curl -s -X POST http://localhost:8483/shutdown
\`\`\`
```

**Step 2: Commit**

```bash
git add skills/scene-designer/SKILL.md
git commit -m "feat: add scene-designer skill with SKILL.md"
```

---

### Task 10: Update routes/__init__.py to include scene_designer

**Files:**
- Modify: `scripts/routes/__init__.py`

**Step 1: Ensure scene_designer is imported**

This should already be handled in Task 1, but verify the import list includes `scene_designer` and `ALL_MODULES` includes it.

**Step 2: Commit if changed**

```bash
git add scripts/routes/__init__.py
git commit -m "chore: ensure scene_designer in route module list"
```

---

### Task 11: End-to-end verification

**Step 1: Start server**

```bash
python scripts/server.py --port 8483 --no-open &
```

**Step 2: Test all existing routes still work**

```bash
curl -s http://localhost:8483/health
curl -s -X POST http://localhost:8483/start -H "Content-Type: application/json" -d '{"assets":[],"project_path":"/tmp/test","search_context":"test"}'
curl -s http://localhost:8483/api/status
curl -s http://localhost:8483/api/results
```

**Step 3: Test designer routes**

```bash
# Load scene
curl -s -X POST http://localhost:8483/api/designer/load -H "Content-Type: application/json" \
  -d '{"project_path":"C:/Users/ehart/anika-projects/kwest-slayurz","grid":{"width":10,"height":8},"tile_size":{"width":16,"height":16},"tilesets":[{"name":"roguelike","image_path":"assets/images/characters/kenney-roguelike/Spritesheet/roguelikeChar_transparent.png","tile_width":16,"tile_height":16,"margin":1,"spacing":0}],"layers":[{"name":"Ground","type":"tilelayer","data":[]}],"zones":[]}'

# Serve designer HTML
curl -s http://localhost:8483/designer | head -3

# Check results before submit
curl -s http://localhost:8483/api/designer/results

# Submit test data
curl -s -X POST http://localhost:8483/api/designer/submit -H "Content-Type: application/json" \
  -d '{"grid":{"width":10,"height":8},"tile_size":{"width":16,"height":16},"tilesets":[{"name":"roguelike","image_path":"test.png","tile_width":16,"tile_height":16,"tile_count":100,"columns":10}],"layers":[{"name":"Ground","type":"tilelayer","data":[1,1,1,1,1,1,1,1,1,1,1,0,0,0,0,0,0,0,0,1,1,0,0,0,0,0,0,0,0,1,1,0,0,0,0,0,0,0,0,1,1,0,0,0,0,0,0,0,0,1,1,0,0,0,0,0,0,0,0,1,1,0,0,0,0,0,0,0,0,1,1,1,1,1,1,1,1,1,1,1]}],"zones":[{"name":"spawn","x":32,"y":32,"width":16,"height":16}]}'

# Get results
curl -s http://localhost:8483/api/designer/results

# Export Tiled JSON
curl -s http://localhost:8483/api/designer/export | python -m json.tool | head -20
```

**Step 4: Visual browser test**

Open `http://localhost:8483/designer` in browser. Verify:
- Three-panel layout renders
- Tileset palette shows tiles from loaded tileset
- Canvas shows the grid
- Can paint tiles on canvas
- Can switch layers
- Can draw zones
- "Send to Claude" works

**Step 5: Shutdown**

```bash
curl -s -X POST http://localhost:8483/shutdown
```

**Step 6: Commit any fixes**

```bash
git add -A
git commit -m "fix: adjustments from scene designer e2e testing"
```

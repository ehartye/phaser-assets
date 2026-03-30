# Asset Preview Server Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use h-superpowers:subagent-driven-development, h-superpowers:team-driven-development, or h-superpowers:executing-plans to implement this plan (ask user which approach).

**Goal:** Replace the temp-file preview flow with a local Python web server that serves the preview UI, downloads assets directly into the project, and tracks everything in SQLite.

**Architecture:** Single `server.py` using Python stdlib (`http.server`, `sqlite3`, `urllib.request`). Server starts on demand, serves preview HTML, handles asset downloads, exposes status/results API, shuts down when Claude is done. SQLite at `~/.phaser-assets/assets.db` persists asset history across sessions.

**Tech Stack:** Python 3 stdlib only

---

### Task 1: Create server.py with SQLite initialization

**Files:**
- Create: `scripts/server.py`

**Step 1: Create the file with imports and DB setup**

```python
#!/usr/bin/env python3
"""Local asset preview server with download and SQLite tracking."""

import json
import os
import secrets
import sqlite3
import sys
import threading
import urllib.request
import urllib.error
import zipfile
import io
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

DB_DIR = Path.home() / ".phaser-assets"
DB_PATH = DB_DIR / "assets.db"


def init_db():
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            project_path TEXT NOT NULL,
            search_context TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS assets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT REFERENCES sessions(id),
            asset_id TEXT NOT NULL,
            name TEXT NOT NULL,
            source TEXT,
            source_url TEXT,
            license TEXT,
            type TEXT,
            project_path TEXT,
            local_path TEXT,
            status TEXT DEFAULT 'pending',
            error TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
    """)
    conn.close()
```

**Step 2: Verify the DB initializes**

Run: `python scripts/server.py 2>&1 || true` (will fail since there's no entry point yet, but import should work)
Then: `python -c "import sys; sys.path.insert(0,'scripts'); from server import init_db; init_db(); print('OK')"`
Expected: `OK` and `~/.phaser-assets/assets.db` exists

**Step 3: Commit**

```bash
git add scripts/server.py
git commit -m "feat: add server.py with SQLite schema initialization"
```

---

### Task 2: Add session state and server globals

**Files:**
- Modify: `scripts/server.py`

**Step 1: Add session state class after the DB functions**

```python
class Session:
    """Holds state for the current server session."""

    def __init__(self):
        self.session_id = None
        self.assets = []
        self.project_path = None
        self.search_context = None
        self.asset_structure = None
        self.status = "idle"  # idle, downloading, done
        self.results = {"downloaded": [], "failed": []}

    def reset(self):
        self.__init__()


# Global session state
session = Session()
```

**Step 2: Commit**

```bash
git add scripts/server.py
git commit -m "feat: add Session state class for server globals"
```

---

### Task 3: Add HTTP request handler with route dispatch

**Files:**
- Modify: `scripts/server.py`

**Step 1: Add the request handler class**

```python
class AssetHandler(BaseHTTPRequestHandler):
    """Routes requests to handler methods."""

    def do_GET(self):
        routes = {
            "/health": self.handle_health,
            "/": self.handle_preview,
            "/api/status": self.handle_status,
            "/api/results": self.handle_results,
        }
        handler = routes.get(self.path)
        if handler:
            handler()
        else:
            self.send_error(404)

    def do_POST(self):
        routes = {
            "/start": self.handle_start,
            "/api/download": self.handle_download,
            "/shutdown": self.handle_shutdown,
        }
        handler = routes.get(self.path)
        if handler:
            handler()
        else:
            self.send_error(404)

    def read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length)) if length else {}

    def send_json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, format, *args):
        """Suppress default logging to stderr."""
        pass
```

**Step 2: Commit**

```bash
git add scripts/server.py
git commit -m "feat: add HTTP request handler with route dispatch and CORS"
```

---

### Task 4: Implement /health, /start, and /shutdown routes

**Files:**
- Modify: `scripts/server.py`

**Step 1: Add handler methods inside `AssetHandler`**

```python
    def handle_health(self):
        self.send_json({"status": "ok", "session_id": session.session_id})

    def handle_start(self):
        body = self.read_body()
        session.reset()
        session.session_id = secrets.token_hex(4)
        session.assets = body.get("assets", [])
        session.project_path = body.get("project_path", "")
        session.search_context = body.get("search_context", "")
        session.asset_structure = body.get("asset_structure", {
            "images": "assets/images",
            "audio": "assets/audio",
            "tilemaps": "assets/tilemaps",
        })
        session.status = "idle"
        session.results = {"downloaded": [], "failed": []}

        # Record session in DB
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute(
            "INSERT INTO sessions (id, project_path, search_context) VALUES (?, ?, ?)",
            (session.session_id, session.project_path, session.search_context),
        )
        # Insert all assets as pending
        for asset in session.assets:
            conn.execute(
                """INSERT INTO assets
                   (session_id, asset_id, name, source, source_url, license, type, project_path, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending')""",
                (session.session_id, asset.get("id", ""), asset.get("name", ""),
                 asset.get("source", ""), asset.get("sourceUrl", ""),
                 asset.get("license", ""), asset.get("type", ""), session.project_path),
            )
        conn.commit()
        conn.close()

        self.send_json({"session_id": session.session_id, "asset_count": len(session.assets)})

    def handle_shutdown(self):
        self.send_json({"status": "shutting_down"})
        threading.Thread(target=self.server.shutdown).start()
```

**Step 2: Verify /health and /start work**

Add a temporary `__main__` block at the bottom of the file:

```python
if __name__ == "__main__":
    init_db()
    server = HTTPServer(("127.0.0.1", 8483), AssetHandler)
    print(json.dumps({"port": 8483}))
    server.serve_forever()
```

Run: `python scripts/server.py &`
Then: `curl http://localhost:8483/health`
Expected: `{"status": "ok", "session_id": null}`
Then: `curl -X POST http://localhost:8483/shutdown`
Clean up: server exits

**Step 3: Commit**

```bash
git add scripts/server.py
git commit -m "feat: implement /health, /start, /shutdown routes with DB recording"
```

---

### Task 5: Implement preview HTML serving (/ route)

**Files:**
- Modify: `scripts/server.py`

**Step 1: Add handle_preview method inside `AssetHandler`**

```python
    def handle_preview(self):
        # Read template relative to this script
        script_dir = Path(__file__).resolve().parent
        template_path = script_dir / ".." / "skills" / "asset-finder" / "assets" / "asset-preview.html"

        if not template_path.exists():
            self.send_error(500, "Template not found")
            return

        html = template_path.read_text(encoding="utf-8")
        html = html.replace("__ASSET_DATA_PLACEHOLDER__", json.dumps(session.assets))
        html = html.replace("__SEARCH_CONTEXT_PLACEHOLDER__", session.search_context or "")
        html = html.replace("__PROJECT_PATH_PLACEHOLDER__", session.project_path or "")
        html = html.replace("__SESSION_ID_PLACEHOLDER__", session.session_id or "")

        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
```

**Step 2: Verify preview renders**

Run server, POST to /start with test asset data, then open `http://localhost:8483/` in browser.

```bash
python scripts/server.py &
curl -X POST http://localhost:8483/start -H "Content-Type: application/json" -d '{"assets":[{"id":"test","name":"Test Asset","source":"Kenney.nl","sourceUrl":"https://kenney.nl","previewUrl":"","license":"CC0","type":"sprite","description":"Test asset","formats":["PNG"],"tags":["test"]}],"project_path":"/tmp/test","search_context":"test search"}'
```

Open `http://localhost:8483/` — should render the asset card grid with one test card.
Then: `curl -X POST http://localhost:8483/shutdown`

**Step 3: Commit**

```bash
git add scripts/server.py
git commit -m "feat: serve preview HTML with template population from session state"
```

---

### Task 6: Implement /api/download route (asset downloading)

**Files:**
- Modify: `scripts/server.py`

**Step 1: Add download helper function before the handler class**

```python
def determine_asset_dir(asset_type, asset_structure, project_path):
    """Map asset type to the correct subdirectory in the project."""
    type_map = {
        "sprite": "images/characters",
        "character": "images/characters",
        "tileset": "images/tiles",
        "tile": "images/tiles",
        "background": "images/backgrounds",
        "ui": "images/ui",
        "icon": "images/ui",
        "audio": "audio/sfx",
        "sfx": "audio/sfx",
        "music": "audio/music",
        "tilemap": "tilemaps",
    }
    base = asset_structure.get("images", "assets/images")
    # Use the first word of the type for lookup
    asset_type_lower = (asset_type or "sprite").lower()
    subdir = type_map.get(asset_type_lower, "images")

    # If the base paths from asset_structure differ from defaults, use them
    if asset_type_lower in ("audio", "sfx"):
        base = asset_structure.get("audio", "assets/audio")
        subdir = "sfx"
    elif asset_type_lower == "music":
        base = asset_structure.get("audio", "assets/audio")
        subdir = "music"
    elif asset_type_lower in ("tilemap",):
        base = asset_structure.get("tilemaps", "assets/tilemaps")
        subdir = ""
    else:
        parts = type_map.get(asset_type_lower, "images").split("/", 1)
        category = parts[0]  # "images" or "audio"
        base = asset_structure.get(category, f"assets/{category}")
        subdir = parts[1] if len(parts) > 1 else ""

    dest = Path(project_path) / base / subdir
    dest.mkdir(parents=True, exist_ok=True)
    return dest


def download_asset(asset, asset_structure, project_path):
    """Download a single asset. Returns (local_path, error)."""
    source_url = asset.get("sourceUrl", "")
    if not source_url:
        return None, "No source URL"

    dest_dir = determine_asset_dir(asset.get("type", "sprite"), asset_structure, project_path)

    # Derive filename from URL or asset name
    url_filename = source_url.rstrip("/").split("/")[-1]
    if not url_filename or "." not in url_filename:
        safe_name = asset.get("id", "asset").replace(" ", "-").lower()
        url_filename = f"{safe_name}.zip"
    filename = url_filename.lower().replace(" ", "-")

    dest_path = dest_dir / filename

    try:
        req = urllib.request.Request(source_url, headers={"User-Agent": "PhaserAssetFinder/0.1"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read()

        # Handle zip files
        if filename.endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                zf.extractall(dest_dir)
            # Return the directory, not the zip
            return str(dest_dir.relative_to(project_path)), None
        else:
            dest_path.write_bytes(data)
            return str(dest_path.relative_to(project_path)), None

    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
        return None, str(e)
```

**Step 2: Add handle_download method inside `AssetHandler`**

```python
    def handle_download(self):
        body = self.read_body()
        selected_ids = body.get("selected", [])

        if not selected_ids:
            self.send_json({"error": "No assets selected"}, 400)
            return

        session.status = "downloading"
        session.results = {"downloaded": [], "failed": []}

        # Respond immediately, download in background
        self.send_json({"status": "downloading", "count": len(selected_ids)})

        def do_downloads():
            conn = sqlite3.connect(str(DB_PATH))
            for asset in session.assets:
                if asset.get("id") not in selected_ids:
                    continue

                local_path, error = download_asset(
                    asset, session.asset_structure, session.project_path
                )

                if error:
                    session.results["failed"].append({
                        "id": asset.get("id"),
                        "name": asset.get("name"),
                        "source_url": asset.get("sourceUrl"),
                        "license": asset.get("license"),
                        "error": error,
                    })
                    conn.execute(
                        "UPDATE assets SET status='failed', error=? WHERE session_id=? AND asset_id=?",
                        (error, session.session_id, asset.get("id")),
                    )
                else:
                    session.results["downloaded"].append({
                        "id": asset.get("id"),
                        "name": asset.get("name"),
                        "path": local_path,
                        "license": asset.get("license"),
                    })
                    conn.execute(
                        "UPDATE assets SET status='downloaded', local_path=? WHERE session_id=? AND asset_id=?",
                        (local_path, session.session_id, asset.get("id")),
                    )
                conn.commit()

            session.status = "done"
            conn.close()

        threading.Thread(target=do_downloads, daemon=True).start()
```

**Step 3: Commit**

```bash
git add scripts/server.py
git commit -m "feat: implement /api/download with threaded asset downloading and DB tracking"
```

---

### Task 7: Implement /api/status and /api/results routes

**Files:**
- Modify: `scripts/server.py`

**Step 1: Add handler methods inside `AssetHandler`**

```python
    def handle_status(self):
        downloaded = len(session.results.get("downloaded", []))
        failed = len(session.results.get("failed", []))
        total = len([a for a in session.assets if a.get("id") in
                    [r["id"] for r in session.results["downloaded"]] +
                    [r["id"] for r in session.results["failed"]]]) if session.status == "downloading" else 0
        self.send_json({
            "status": session.status,
            "downloaded": downloaded,
            "failed": failed,
        })

    def handle_results(self):
        self.send_json(session.results)
```

**Step 2: Commit**

```bash
git add scripts/server.py
git commit -m "feat: implement /api/status and /api/results routes"
```

---

### Task 8: Add CLI entry point with port selection

**Files:**
- Modify: `scripts/server.py`

**Step 1: Replace the temporary `__main__` block with proper CLI**

```python
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Asset preview server")
    parser.add_argument("--port", type=int, default=0, help="Port to listen on (0 = auto)")
    args = parser.parse_args()

    init_db()

    server = HTTPServer(("127.0.0.1", args.port), AssetHandler)
    port = server.server_address[1]

    # Open browser
    import webbrowser
    webbrowser.open(f"http://localhost:{port}")

    # Output connection info for Claude
    print(json.dumps({"port": port, "url": f"http://localhost:{port}"}))
    sys.stdout.flush()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
```

**Step 2: Verify full lifecycle**

```bash
python scripts/server.py --port 0 &
# Read the port from stdout JSON
# curl http://localhost:PORT/health
# curl -X POST .../start with test data
# curl http://localhost:PORT/ (should render HTML)
# curl -X POST .../shutdown
```

**Step 3: Commit**

```bash
git add scripts/server.py
git commit -m "feat: add CLI entry point with auto port selection and browser launch"
```

---

### Task 9: Update asset-preview.html for server-backed downloads

**Files:**
- Modify: `skills/asset-finder/assets/asset-preview.html`

**Step 1: Replace the `exportSelections()` function and add progress states**

Changes to the existing HTML:

1. Replace the `exportSelections()` function body: instead of creating a blob + download link, `fetch('/api/download', { method: 'POST', body: JSON.stringify({ selected: [...selected] }) })`. Then poll `/api/status` every second to update card states.

2. Add CSS classes for download states on cards:
   - `.card.downloading` — pulsing border animation
   - `.card.downloaded` — green border + checkmark overlay
   - `.card.download-failed` — red border + error icon

3. Add a `pollStatus()` function that hits `/api/status` and once `status === "done"`, fetches `/api/results` and updates each card to show success/failure.

4. Update the banner on completion: "X assets downloaded to your project. You can close this tab."

5. Keep all placeholder tokens (`__ASSET_DATA_PLACEHOLDER__` etc.) — the server still uses them.

6. Update the status banner default text: "Browse the assets below. Select the ones you want, then click Download to Project."

7. Rename the "Confirm Selection" button to "Download to Project".

**Step 2: Verify in browser**

Start server, POST /start with test data, open `localhost:PORT`, click "Download to Project", verify progress UI appears.

**Step 3: Commit**

```bash
git add skills/asset-finder/assets/asset-preview.html
git commit -m "feat: update preview HTML to use server API for downloads with progress UI"
```

---

### Task 10: Update SKILL.md for server flow

**Files:**
- Modify: `skills/asset-finder/SKILL.md`

**Step 1: Replace Step 3 (Show the Preview UI) with server-based flow**

Replace the current Step 3 content (preview.py + Downloads polling) with:

```markdown
## Step 3: Show the Preview UI and Download Assets

1. For each found asset, prepare a JSON object:
   [keep existing JSON example]

2. Ensure the asset server is running:
\`\`\`bash
curl -s http://localhost:8483/health || python "$CLAUDE_PLUGIN_ROOT/scripts/server.py" --port 8483 &
\`\`\`

3. POST asset data to start a session:
\`\`\`bash
curl -s -X POST http://localhost:8483/start \
  -H "Content-Type: application/json" \
  -d '{"assets": <asset_json>, "project_path": "<project_path>", "search_context": "<context>"}'
\`\`\`

4. Tell the user to open http://localhost:8483 (or it opens automatically) to browse and select assets. The user clicks "Download to Project" and the server downloads assets directly into the project.

5. Poll for completion:
\`\`\`bash
curl -s http://localhost:8483/api/status
\`\`\`
   Wait until `status` is `"done"`.

6. Get results:
\`\`\`bash
curl -s http://localhost:8483/api/results
\`\`\`
   The response contains `downloaded` (array of assets with `path` relative to project) and `failed` (array with `source_url` preserved).

7. If any assets failed to download, retry them with curl using the `source_url` from the failed array — do NOT re-search:
\`\`\`bash
curl -L -o "<project_path>/<appropriate_subdir>/<filename>" "<source_url>"
\`\`\`

8. Shut down the server:
\`\`\`bash
curl -s -X POST http://localhost:8483/shutdown
\`\`\`
```

**Step 2: Remove Step 4 (Download Assets into the Project)**

The server handles downloads now. Remove the entire Step 4 section. Keep the asset directory structure reference but move it into Step 3 as context for the `asset_structure` field. Renumber Step 5 to Step 4.

**Step 3: Update Step 5 (now Step 4) to use results paths**

Change the Phaser code generation step to reference `path` from the `/api/results` response instead of assuming paths.

**Step 4: Commit**

```bash
git add skills/asset-finder/SKILL.md
git commit -m "feat: update SKILL.md for server-based asset preview and download flow"
```

---

### Task 11: Delete preview.py

**Files:**
- Delete: `scripts/preview.py`

**Step 1: Remove the old script**

```bash
rm scripts/preview.py
```

**Step 2: Commit**

```bash
git rm scripts/preview.py
git commit -m "chore: remove preview.py, replaced by server.py"
```

---

### Task 12: End-to-end verification

**Step 1: Start the server**

```bash
python scripts/server.py --port 8483 &
```

**Step 2: Health check**

```bash
curl -s http://localhost:8483/health
```
Expected: `{"status": "ok", "session_id": null}`

**Step 3: Start a session with test data**

```bash
curl -s -X POST http://localhost:8483/start \
  -H "Content-Type: application/json" \
  -d '{"assets":[{"id":"kenney-platformer","name":"Kenney Platformer Pack","source":"Kenney.nl","sourceUrl":"https://kenney.nl/media/items/kenney_simplified-platformer-pack.zip","previewUrl":"","license":"CC0 (Public Domain)","type":"sprite","description":"Platformer character and tiles","formats":["PNG"],"tags":["platformer","pixel-art"]}],"project_path":"/tmp/test-game","search_context":"platformer assets"}'
```

**Step 4: Open browser and verify UI**

Open `http://localhost:8483/`, verify asset card renders, select it, click "Download to Project".

**Step 5: Check results**

```bash
curl -s http://localhost:8483/api/status
curl -s http://localhost:8483/api/results
```

Verify downloaded array has the asset with a `path` field, or failed array has `source_url` preserved.

**Step 6: Verify DB**

```bash
python -c "
import sqlite3
conn = sqlite3.connect(str(__import__('pathlib').Path.home() / '.phaser-assets' / 'assets.db'))
for row in conn.execute('SELECT asset_id, status, local_path, error FROM assets'):
    print(row)
"
```

**Step 7: Shutdown**

```bash
curl -s -X POST http://localhost:8483/shutdown
```

**Step 8: Final commit if any fixes were needed**

```bash
git add -A
git commit -m "fix: adjustments from end-to-end testing"
```

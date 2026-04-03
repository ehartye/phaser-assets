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
            dest = os.path.join(session.project_path, base, sub)
        else:
            dest = os.path.join(session.project_path, base)
    else:
        dest = os.path.join(session.project_path, structure.get("images", "assets/images"))
    # Separate each asset into its own subfolder by ID
    asset_id = asset.get("id", "")
    if asset_id:
        dest = os.path.join(dest, asset_id)
    return dest


def _download_one(asset, session):
    """Download a single asset. Returns (success, local_path|None, error|None)."""
    url = asset.get("sourceUrl", "")
    if not url:
        return False, None, "no sourceUrl"
    dest_dir = _dest_dir_for_asset(asset, session)
    os.makedirs(dest_dir, exist_ok=True)

    # Delegate itch.io URLs to the Playwright-based downloader
    if "itch.io" in url:
        try:
            from routes.itch_io import _run_on_pw, _pw_download
            saved, error = _run_on_pw(_pw_download, url, dest_dir)
            if saved:
                return True, saved[0]["path"], error
            return False, None, error or "no files downloaded"
        except ImportError:
            return False, None, "itch.io downloads require playwright"
        except Exception as exc:
            return False, None, str(exc)

    # Standard urllib download for non-itch.io URLs
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
        if body is None:
            return
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
            script_dir, "..", "..", "skills", "asset-finder", "assets", "asset-preview.html"
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
        if body is None:
            return
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

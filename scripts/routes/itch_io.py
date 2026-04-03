"""itch.io routes — search, inspect, and download free game assets via Playwright."""

import os
import queue
import threading
import time
import urllib.parse

ROUTES = {
    "GET": {},
    "POST": {
        "/api/itch/search":   "handle_itch_search",
        "/api/itch/start":    "handle_itch_start",
        "/api/itch/details":  "handle_itch_details",
        "/api/itch/download": "handle_itch_download",
    },
}

# ---------------------------------------------------------------------------
# Shared browser instance — runs on a dedicated thread
#
# Playwright's sync API is bound to the thread that calls start().
# Since the HTTP server dispatches requests on pool threads, we run
# Playwright on a single long-lived daemon thread and proxy work to it.
# ---------------------------------------------------------------------------

_pw_thread = None
_pw_lock = threading.Lock()
_pw_queue = queue.Queue()


def _playwright_worker():
    """Dedicated thread that owns the Playwright browser instance."""
    from playwright.sync_api import sync_playwright
    pw = sync_playwright().start()
    browser = pw.chromium.launch(
        headless=False,
        channel="msedge",
        args=["--disable-blink-features=AutomationControlled", "--start-minimized"],
    )
    context = browser.new_context(
        viewport={"width": 1920, "height": 1080},
        locale="en-US",
        accept_downloads=True,
    )
    while True:
        item = _pw_queue.get()
        if item is None:  # shutdown sentinel
            try:
                browser.close()
            except Exception:
                pass
            try:
                pw.stop()
            except Exception:
                pass
            _pw_queue.task_done()
            break
        func, args, result_q = item
        try:
            rv = func(context, *args)
            result_q.put(("ok", rv))
        except Exception as exc:
            result_q.put(("error", exc))
        _pw_queue.task_done()


def _ensure_worker():
    """Start the Playwright worker thread if not already running."""
    global _pw_thread
    with _pw_lock:
        if _pw_thread is not None and _pw_thread.is_alive():
            return
        _pw_thread = threading.Thread(target=_playwright_worker, daemon=True)
        _pw_thread.start()


def _run_on_pw(func, *args):
    """Submit work to the Playwright thread and block for the result."""
    _ensure_worker()
    result_q = queue.Queue()
    _pw_queue.put((func, args, result_q))
    status, value = result_q.get()
    if status == "error":
        raise value
    return value


def _shutdown_browser():
    """Close the browser if it was started. Called on server shutdown."""
    global _pw_thread
    with _pw_lock:
        if _pw_thread is not None and _pw_thread.is_alive():
            _pw_queue.put(None)
            _pw_thread.join(timeout=10)
            _pw_thread = None


def _new_page(context):
    """Create a new page with anti-detection init script."""
    page = context.new_page()
    page.add_init_script(
        'Object.defineProperty(navigator, "webdriver", {get: () => undefined});'
    )
    return page


def _wait_for_cloudflare(page, timeout=20):
    """Wait for Cloudflare challenge to resolve. Returns True if passed."""
    for _ in range(timeout):
        try:
            title = page.title()
            if "moment" not in title.lower() and "cloudflare" not in title.lower():
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


# ---------------------------------------------------------------------------
# Search helpers
# ---------------------------------------------------------------------------

VALID_SORTS = {"top-rated", "most-recent", "most-downloaded"}


def _build_search_url(tags=None, sort=None, query=None):
    """Build an itch.io game-assets URL from filter parameters."""
    parts = ["https://itch.io/game-assets/free"]
    for tag in (tags or []):
        # Sanitize: lowercase, strip, replace spaces with hyphens
        safe = tag.strip().lower().replace(" ", "-")
        if safe:
            parts.append(f"tag-{safe}")
    url = "/".join(parts)
    params = []
    if sort and sort in VALID_SORTS:
        params.append(f"sort={sort}")
    if query:
        params.append(f"q={urllib.parse.quote_plus(query)}")
    if params:
        url += "?" + "&".join(params)
    return url


def _scrape_listing(page, url, max_results=30):
    """Navigate to an itch.io listing page and scrape asset cards."""
    page.goto(url, wait_until="domcontentloaded", timeout=30000)
    if not _wait_for_cloudflare(page):
        return []
    # Wait for game cells to render
    try:
        page.wait_for_selector(".game_cell", timeout=5000)
    except Exception:
        return []
    cells = page.query_selector_all(".game_cell")
    results = []
    for cell in cells[:max_results]:
        name_el = cell.query_selector(".title")
        link_el = cell.query_selector("a.title")
        thumb = cell.query_selector(".game_thumb img, .lazy_loaded")
        sub_el = cell.query_selector(".sub")
        if not name_el or not link_el:
            continue
        name = name_el.inner_text()
        href = link_el.get_attribute("href") or ""
        img = ""
        if thumb:
            img = (
                thumb.get_attribute("data-lazy_src")
                or thumb.get_attribute("src")
                or ""
            )
        sub = sub_el.inner_text() if sub_el else ""
        results.append({
            "name": name,
            "url": href,
            "previewUrl": img,
            "creator": sub,
            "source": "itch.io",
        })
    return results


# ---------------------------------------------------------------------------
# Details helpers
# ---------------------------------------------------------------------------

def _scrape_details(page, asset_url):
    """Scrape a single itch.io asset page for metadata and file info."""
    page.goto(asset_url, wait_until="domcontentloaded", timeout=30000)
    if not _wait_for_cloudflare(page):
        return {"error": "Cloudflare challenge failed"}

    result = {"url": asset_url, "files": [], "license": "", "description": ""}

    # Title
    try:
        result["name"] = page.title().split(" by ")[0].strip()
    except Exception:
        result["name"] = ""

    # Description
    desc_el = page.query_selector(".formatted_description")
    if desc_el:
        result["description"] = desc_el.inner_text()[:1000]

    # License — scan page text for common license keywords
    page_text = page.inner_text("body")
    for pattern in ["CC0", "CC-BY", "public domain", "MIT", "Apache"]:
        if pattern.lower() in page_text.lower():
            idx = page_text.lower().index(pattern.lower())
            result["license"] = page_text[max(0, idx - 30):idx + 80].strip()
            break

    # Detect download type
    buy_btn = page.query_selector('a.buy_btn[href*="purchase"]')
    direct_uploads = page.query_selector_all(".upload a[data-upload_id]")

    if not direct_uploads and buy_btn:
        result["download_type"] = "name-your-price"
    elif direct_uploads:
        result["download_type"] = "direct"
    else:
        result["download_type"] = "unknown"

    # Gather file info from upload elements (if visible)
    uploads = page.query_selector_all(".upload")
    for u in uploads:
        dl_btn = u.query_selector("a[data-upload_id]")
        name_el = u.query_selector(".name")
        size_el = u.query_selector(".file_size span")
        if dl_btn and name_el:
            result["files"].append({
                "name": name_el.inner_text(),
                "upload_id": dl_btn.get_attribute("data-upload_id"),
                "size": size_el.inner_text() if size_el else "",
            })

    return result


# ---------------------------------------------------------------------------
# Download helpers
# ---------------------------------------------------------------------------

def _download_from_itch(page, asset_url, dest_dir):
    """Download files from an itch.io asset page. Returns list of saved file dicts."""
    os.makedirs(dest_dir, exist_ok=True)
    page.goto(asset_url, wait_until="domcontentloaded", timeout=30000)
    if not _wait_for_cloudflare(page):
        return [], "Cloudflare challenge failed"

    # Handle name-your-price gate
    buy_btn = page.query_selector('a.buy_btn[href*="purchase"]')
    direct_uploads = page.query_selector_all(".upload a[data-upload_id]")

    if not direct_uploads and buy_btn:
        purchase_url = buy_btn.get_attribute("href")
        if purchase_url:
            if not purchase_url.startswith("http"):
                # Relative URL — resolve against current page
                base = asset_url.rstrip("/")
                purchase_url = base + "/purchase" if "/purchase" not in purchase_url else purchase_url
            page.goto(purchase_url, wait_until="domcontentloaded", timeout=30000)
            if not _wait_for_cloudflare(page):
                return [], "Cloudflare challenge failed on purchase page"
            no_thanks = page.query_selector('a:has-text("No thanks")')
            if no_thanks:
                no_thanks.click()
                time.sleep(2)
                _wait_for_cloudflare(page)
            else:
                return [], "Could not find 'No thanks' bypass on purchase page"

    # Gather files
    uploads = page.query_selector_all(".upload")
    files = []
    for u in uploads:
        dl_btn = u.query_selector("a[data-upload_id]")
        name_el = u.query_selector(".name")
        size_el = u.query_selector(".file_size span")
        if dl_btn and name_el:
            files.append({
                "name": name_el.inner_text(),
                "upload_id": dl_btn.get_attribute("data-upload_id"),
                "size": size_el.inner_text() if size_el else "",
                "btn": dl_btn,
            })

    if not files:
        return [], "No downloadable files found"

    # Prefer ZIPs if available
    zips = [f for f in files if f["name"].lower().endswith(".zip")]
    to_download = zips if zips else files

    saved = []
    errors = []
    for f in to_download:
        try:
            with page.expect_download(timeout=30000) as dl_info:
                page.evaluate("(btn) => btn.click()", f["btn"])
            download = dl_info.value
            # Dismiss lightbox
            try:
                close_btn = page.query_selector(".close_button")
                if close_btn:
                    page.evaluate("(btn) => btn.click()", close_btn)
                    time.sleep(0.3)
            except Exception:
                pass
            save_path = os.path.join(dest_dir, f["name"])
            download.save_as(save_path)
            saved.append({
                "name": f["name"],
                "path": save_path,
                "size": os.path.getsize(save_path),
            })
        except Exception as exc:
            errors.append({"name": f["name"], "error": str(exc)})

    error_summary = "; ".join(f'{e["name"]}: {e["error"]}' for e in errors) if errors else None
    return saved, error_summary


# ---------------------------------------------------------------------------
# Route handler mixin
# ---------------------------------------------------------------------------

def _pw_search(context, url, max_results):
    """Run search on the Playwright thread."""
    page = _new_page(context)
    try:
        return _scrape_listing(page, url, max_results=max_results)
    finally:
        page.close()


def _pw_details(context, asset_url):
    """Run details scrape on the Playwright thread."""
    page = _new_page(context)
    try:
        return _scrape_details(page, asset_url)
    finally:
        page.close()


def _pw_download(context, asset_url, dest_dir):
    """Run download on the Playwright thread."""
    page = _new_page(context)
    try:
        return _download_from_itch(page, asset_url, dest_dir)
    finally:
        page.close()


class ItchIoRoutes:
    """Mixin providing itch.io search, details, and download handlers."""

    def handle_itch_search(self):
        body = self.read_body()
        if body is None:
            return
        tags = body.get("tags", [])
        sort = body.get("sort")
        query = body.get("query")
        max_results = min(body.get("max_results", 30), 60)
        url = _build_search_url(tags=tags, sort=sort, query=query)
        try:
            results = _run_on_pw(_pw_search, url, max_results)
            self.send_json({"url": url, "count": len(results), "assets": results})
        except Exception as exc:
            self.send_json({"error": str(exc)}, 500)

    def handle_itch_start(self):
        """Search itch.io and create a preview session in one call."""
        import secrets
        from datetime import datetime, timezone
        from server import session, get_db

        body = self.read_body()
        if body is None:
            return
        tags = body.get("tags", [])
        sort = body.get("sort")
        query = body.get("query")
        max_results = min(body.get("max_results", 30), 60)
        project_path = body.get("project_path", "")
        url = _build_search_url(tags=tags, sort=sort, query=query)

        try:
            results = _run_on_pw(_pw_search, url, max_results)
        except Exception as exc:
            self.send_json({"error": str(exc)}, 500)
            return

        # Convert search results to asset format for the preview session
        assets = []
        for r in results:
            slug = r["url"].rstrip("/").rsplit("/", 1)[-1] if r["url"] else ""
            assets.append({
                "id": slug or r["name"].lower().replace(" ", "-")[:40],
                "name": r["name"],
                "source": "itch.io",
                "sourceUrl": r["url"],
                "previewUrl": r["previewUrl"],
                "license": "Check itch.io page",
                "type": "sprite",
                "description": f"By {r['creator']}" if r.get("creator") else "",
                "formats": ["PNG"],
                "tags": tags,
            })

        # Create session
        session.reset()
        session.session_id = secrets.token_hex(4)
        session.assets = assets
        session.project_path = project_path
        search_context = f"itch.io: {query or ''} tags={','.join(tags)}"
        session.search_context = search_context

        now = datetime.now(timezone.utc).isoformat()
        conn = get_db()
        conn.execute(
            "INSERT INTO sessions (id, project_path, search_context, created_at) VALUES (?, ?, ?, ?)",
            (session.session_id, session.project_path, search_context, now),
        )
        for asset in assets:
            conn.execute(
                "INSERT INTO assets (session_id, asset_id, name, source, source_url, license, type, project_path, status, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)",
                (session.session_id, asset.get("id", ""), asset.get("name", ""),
                 asset.get("source", ""), asset.get("sourceUrl", ""), asset.get("license", ""),
                 asset.get("type", ""), project_path, now),
            )
        conn.commit()
        conn.close()

        self.send_json({
            "session_id": session.session_id,
            "search_url": url,
            "asset_count": len(assets),
            "message": "Session created. Open the server root URL to browse.",
        })

    def handle_itch_details(self):
        body = self.read_body()
        if body is None:
            return
        asset_url = body.get("url", "")
        if not asset_url or "itch.io" not in asset_url:
            self.send_json({"error": "missing or invalid itch.io URL"}, 400)
            return
        try:
            details = _run_on_pw(_pw_details, asset_url)
            self.send_json(details)
        except Exception as exc:
            self.send_json({"error": str(exc)}, 500)

    def handle_itch_download(self):
        body = self.read_body()
        if body is None:
            return
        asset_url = body.get("url", "")
        dest_dir = body.get("dest_dir", "")
        if not asset_url or "itch.io" not in asset_url:
            self.send_json({"error": "missing or invalid itch.io URL"}, 400)
            return
        if not dest_dir:
            self.send_json({"error": "missing dest_dir"}, 400)
            return
        try:
            saved, error = _run_on_pw(_pw_download, asset_url, dest_dir)
            result = {"downloaded": saved, "count": len(saved)}
            if error:
                result["error"] = error
            self.send_json(result)
        except Exception as exc:
            self.send_json({"error": str(exc)}, 500)

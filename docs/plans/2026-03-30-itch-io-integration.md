# itch.io Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use h-superpowers:subagent-driven-development, h-superpowers:team-driven-development, or h-superpowers:executing-plans to implement this plan (ask user which approach).

**Goal:** Add Playwright-based itch.io scraping and downloading to the phaser-assets server so the asset-finder skill can search, filter, inspect, and download free itch.io game assets.

**Architecture:** New route module `scripts/routes/itch_io.py` with a shared Edge browser instance (headed, `channel='msedge'`) that launches on first use and persists for the server lifetime. Three endpoints: search (listing pages with tag/sort/query filters), details (single asset page scrape), and download (handles both direct-download and name-your-price gate flows). The existing `asset_finder.py` `_download_one()` gets a hook to delegate itch.io URLs to the new module.

**Tech Stack:** Python 3.13, Playwright (sync API), Microsoft Edge (system browser), existing BaseHTTPRequestHandler server

---

### Task 1: Create the itch.io browser manager

**Files:**
- Create: `scripts/routes/itch_io.py`

This task creates the module skeleton with the shared browser lifecycle. The browser launches on first use (not server start) to avoid popping a window when itch.io isn't needed.

**Step 1: Create `scripts/routes/itch_io.py` with browser manager and route constants**

```python
"""itch.io routes — search, inspect, and download free game assets via Playwright."""

import os
import threading
import time

ROUTES = {
    "GET": {},
    "POST": {
        "/api/itch/search":   "handle_itch_search",
        "/api/itch/details":  "handle_itch_details",
        "/api/itch/download": "handle_itch_download",
    },
}

# ---------------------------------------------------------------------------
# Shared browser instance
# ---------------------------------------------------------------------------

_browser = None
_browser_context = None
_browser_lock = threading.Lock()


def _get_browser_context():
    """Return a shared Playwright browser context, launching Edge on first call."""
    global _browser, _browser_context
    with _browser_lock:
        if _browser_context is not None:
            return _browser_context
        from playwright.sync_api import sync_playwright
        pw = sync_playwright().start()
        _browser = pw.chromium.launch(
            headless=False,
            channel="msedge",
            args=["--disable-blink-features=AutomationControlled", "--start-minimized"],
        )
        _browser_context = _browser.new_context(
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
            accept_downloads=True,
        )
        return _browser_context


def _shutdown_browser():
    """Close the browser if it was started. Called on server shutdown."""
    global _browser, _browser_context
    with _browser_lock:
        if _browser:
            try:
                _browser.close()
            except Exception:
                pass
            _browser = None
            _browser_context = None


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
```

**Step 2: Verify the file is syntactically valid**

Run: `python -c "import ast; ast.parse(open('scripts/routes/itch_io.py').read()); print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add scripts/routes/itch_io.py
git commit -m "feat: add itch_io route module skeleton with browser manager"
```

---

### Task 2: Implement the search endpoint

**Files:**
- Modify: `scripts/routes/itch_io.py`

The search endpoint scrapes itch.io listing pages with tag, sort, and query filters.

**Step 1: Add the `_build_search_url` helper and `_scrape_listing` function**

Append after `_wait_for_cloudflare`:

```python
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
        params.append(f"q={query.replace(' ', '+')}")
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
```

**Step 2: Add the `handle_itch_search` method to the route class**

Append at the end of the file:

```python
class ItchIoRoutes:
    """Mixin providing itch.io search, details, and download handlers."""

    def handle_itch_search(self):
        body = self.read_body()
        tags = body.get("tags", [])
        sort = body.get("sort")
        query = body.get("query")
        max_results = min(body.get("max_results", 30), 60)
        url = _build_search_url(tags=tags, sort=sort, query=query)
        try:
            ctx = _get_browser_context()
            page = _new_page(ctx)
            try:
                results = _scrape_listing(page, url, max_results=max_results)
                self.send_json({"url": url, "count": len(results), "assets": results})
            finally:
                page.close()
        except Exception as exc:
            self.send_json({"error": str(exc)}, 500)
```

**Step 3: Verify syntax**

Run: `python -c "import ast; ast.parse(open('scripts/routes/itch_io.py').read()); print('OK')"`
Expected: `OK`

**Step 4: Commit**

```bash
git add scripts/routes/itch_io.py
git commit -m "feat: add itch.io search endpoint with tag/sort/query filters"
```

---

### Task 3: Implement the details endpoint

**Files:**
- Modify: `scripts/routes/itch_io.py`

Scrapes a single itch.io asset page for description, license info, and file list.

**Step 1: Add `_scrape_details` function**

Append before the `ItchIoRoutes` class:

```python
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
```

**Step 2: Add `handle_itch_details` to the `ItchIoRoutes` class**

Add this method inside the class, after `handle_itch_search`:

```python
    def handle_itch_details(self):
        body = self.read_body()
        asset_url = body.get("url", "")
        if not asset_url or "itch.io" not in asset_url:
            self.send_json({"error": "missing or invalid itch.io URL"}, 400)
            return
        try:
            ctx = _get_browser_context()
            page = _new_page(ctx)
            try:
                details = _scrape_details(page, asset_url)
                self.send_json(details)
            finally:
                page.close()
        except Exception as exc:
            self.send_json({"error": str(exc)}, 500)
```

**Step 3: Verify syntax**

Run: `python -c "import ast; ast.parse(open('scripts/routes/itch_io.py').read()); print('OK')"`
Expected: `OK`

**Step 4: Commit**

```bash
git add scripts/routes/itch_io.py
git commit -m "feat: add itch.io details endpoint for asset page scraping"
```

---

### Task 4: Implement the download endpoint

**Files:**
- Modify: `scripts/routes/itch_io.py`

Handles both direct-download and name-your-price gate flows, downloads all files (or just ZIPs if available).

**Step 1: Add `_download_from_itch` function**

Append before the `ItchIoRoutes` class:

```python
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
```

**Step 2: Add `handle_itch_download` to the `ItchIoRoutes` class**

Add this method inside the class:

```python
    def handle_itch_download(self):
        body = self.read_body()
        asset_url = body.get("url", "")
        dest_dir = body.get("dest_dir", "")
        if not asset_url or "itch.io" not in asset_url:
            self.send_json({"error": "missing or invalid itch.io URL"}, 400)
            return
        if not dest_dir:
            self.send_json({"error": "missing dest_dir"}, 400)
            return
        try:
            ctx = _get_browser_context()
            page = _new_page(ctx)
            try:
                saved, error = _download_from_itch(page, asset_url, dest_dir)
                result = {"downloaded": saved, "count": len(saved)}
                if error:
                    result["error"] = error
                self.send_json(result)
            finally:
                page.close()
        except Exception as exc:
            self.send_json({"error": str(exc)}, 500)
```

**Step 3: Verify syntax**

Run: `python -c "import ast; ast.parse(open('scripts/routes/itch_io.py').read()); print('OK')"`
Expected: `OK`

**Step 4: Commit**

```bash
git add scripts/routes/itch_io.py
git commit -m "feat: add itch.io download endpoint with purchase gate bypass"
```

---

### Task 5: Register the route module and wire up browser shutdown

**Files:**
- Modify: `scripts/routes/__init__.py` — add `"itch_io"` to `_MODULE_NAMES`
- Modify: `scripts/server.py` — import the mixin, add to `_base_mixins`, hook browser shutdown into `/shutdown`

**Step 1: Add `"itch_io"` to `_MODULE_NAMES` in `__init__.py`**

Change line 10 from:
```python
_MODULE_NAMES = ["health", "asset_finder", "inspector", "scene_designer"]
```
to:
```python
_MODULE_NAMES = ["health", "asset_finder", "inspector", "scene_designer", "itch_io"]
```

**Step 2: Import and register the mixin in `server.py`**

After the scene_designer import block (lines 129-132), add:

```python
try:
    from routes.itch_io import ItchIoRoutes  # noqa: E402
except (ModuleNotFoundError, ImportError):
    ItchIoRoutes = None
```

After line 136 (`_base_mixins.append(SceneDesignerRoutes)`), add:

```python
if ItchIoRoutes is not None:
    _base_mixins.append(ItchIoRoutes)
```

**Step 3: Hook browser shutdown into the `/shutdown` handler**

In `scripts/routes/health.py`, modify `handle_shutdown` to also close the itch.io browser:

```python
    def handle_shutdown(self):
        from server import _server_ref
        try:
            from routes.itch_io import _shutdown_browser
            _shutdown_browser()
        except ImportError:
            pass
        self.send_json({"status": "shutting down"})
        if _server_ref:
            threading.Thread(target=_server_ref.shutdown, daemon=True).start()
```

**Step 4: Verify the server starts and health check works**

Run: `python scripts/server.py --port 8483 --no-open &`
Then: `curl -s http://localhost:8483/health`
Expected: `{"status": "ok", "session_id": null}`
Then: `curl -s -X POST http://localhost:8483/shutdown`

**Step 5: Commit**

```bash
git add scripts/routes/__init__.py scripts/server.py scripts/routes/health.py
git commit -m "feat: register itch_io routes and wire browser shutdown"
```

---

### Task 6: Hook itch.io downloads into existing asset_finder `_download_one`

**Files:**
- Modify: `scripts/routes/asset_finder.py`

When `_download_one` receives an itch.io `sourceUrl`, delegate to the itch_io module instead of using urllib.

**Step 1: Add itch.io detection and delegation at the top of `_download_one`**

Replace the current `_download_one` function (lines 80-115) with:

```python
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
            from routes.itch_io import _get_browser_context, _new_page, _download_from_itch
            ctx = _get_browser_context()
            page = _new_page(ctx)
            try:
                saved, error = _download_from_itch(page, url, dest_dir)
            finally:
                page.close()
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
```

**Step 2: Verify syntax**

Run: `python -c "import ast; ast.parse(open('scripts/routes/asset_finder.py').read()); print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add scripts/routes/asset_finder.py
git commit -m "feat: delegate itch.io URLs to Playwright downloader in asset_finder"
```

---

### Task 7: Integration test — full end-to-end

**Files:** None (manual test)

**Step 1: Start the server**

```bash
python scripts/server.py --port 8483 --no-open &
```

**Step 2: Test search endpoint**

```bash
curl -s -X POST http://localhost:8483/api/itch/search \
  -H "Content-Type: application/json" \
  -d '{"tags": ["pixel-art", "space"], "sort": "top-rated", "max_results": 5}'
```

Expected: JSON with `count` > 0 and `assets` array containing itch.io results with name, url, previewUrl.

**Step 3: Test details endpoint**

Use a URL from the search results:

```bash
curl -s -X POST http://localhost:8483/api/itch/details \
  -H "Content-Type: application/json" \
  -d '{"url": "https://gvituri.itch.io/space-shooter"}'
```

Expected: JSON with name, description, files array (with upload_ids), download_type "direct".

**Step 4: Test download endpoint**

```bash
curl -s -X POST http://localhost:8483/api/itch/download \
  -H "Content-Type: application/json" \
  -d '{"url": "https://gvituri.itch.io/space-shooter", "dest_dir": "C:\\Users\\ehart\\repos\\phaser-assets\\test_download"}'
```

Expected: JSON with `downloaded` array, `count` > 0, files saved to `test_download/`.

**Step 5: Test name-your-price gate**

```bash
curl -s -X POST http://localhost:8483/api/itch/download \
  -H "Content-Type: application/json" \
  -d '{"url": "https://sethbb.itch.io/32rogues", "dest_dir": "C:\\Users\\ehart\\repos\\phaser-assets\\test_download"}'
```

Expected: JSON with downloaded files from the 32rogues pack.

**Step 6: Verify server shutdown cleans up browser**

```bash
curl -s -X POST http://localhost:8483/shutdown
```

Expected: Edge window closes, server exits.

**Step 7: Clean up and commit**

```bash
rm -rf test_download
git add -A
git commit -m "test: verify itch.io integration end-to-end"
```

---

### Task 8: Update the asset-finder skill documentation

**Files:**
- Modify: `skills/asset-finder/SKILL.md` — add itch.io server endpoints as a search/download option
- Modify: `skills/asset-finder/references/asset-sources.md` — update itch.io section with automation notes

**Step 1: Add itch.io server endpoints to SKILL.md**

In the search strategy section, add guidance that when the asset server is running, Claude can use the `/api/itch/search` endpoint for itch.io searches instead of WebSearch+WebFetch (which get blocked by Cloudflare). Document the request/response format for all three endpoints.

**Step 2: Update asset-sources.md**

Update the itch.io entry to note:
- Listing pages are Cloudflare-protected — use `/api/itch/search` endpoint instead of WebFetch
- Downloads require Playwright — use `/api/itch/download` or the asset_finder download flow (which auto-delegates)
- System Edge browser required (`channel='msedge'`, headed mode)

**Step 3: Commit**

```bash
git add skills/asset-finder/SKILL.md skills/asset-finder/references/asset-sources.md
git commit -m "docs: update asset-finder skill with itch.io server endpoints"
```

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

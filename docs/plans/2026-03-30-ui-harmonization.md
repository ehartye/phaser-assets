# UI Harmonization Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use h-superpowers:subagent-driven-development, h-superpowers:team-driven-development, or h-superpowers:executing-plans to implement this plan (ask user which approach).

**Goal:** Extract shared CSS and JS from all three UI HTML files into `scripts/ui/` modules served at `/ui/*`, preventing style/logic drift and making scene-designer.html maintainable.

**Architecture:** A new `/ui/*` static route serves files from `scripts/ui/`. Shared CSS tokens and button styles go in `theme.css`. Shared tileset math goes in `tileset.js`. Scene-designer's ~1200 lines of JS move to `scene-designer.js`; its ~770 lines of CSS (minus shared parts) move to `scene-designer.css`. HTML files reference these via `<link>` and `<script src>` tags; server-injected config stays inline.

**Tech Stack:** Python `http.server`, vanilla HTML/CSS/JS, no build step.

---

## Overview of files and their current size

| File | Lines | CSS block | JS block |
|------|-------|-----------|----------|
| `skills/scene-designer/assets/scene-designer.html` | 2217 | 7–777 | 938–2217 |
| `skills/sprite-inspector/assets/sprite-inspector.html` | 1309 | 7–507 | 623–1309 |
| `skills/asset-finder/assets/asset-preview.html` | 658 | 7–383 | ~500–658 |

## Shared patterns to extract

**`theme.css`** — identical across all three:
- `:root` CSS custom properties
- `* { margin: 0; padding: 0; box-sizing: border-box; }`
- `body { font-family: 'Segoe UI'... }`
- `.btn` base + `.btn-accent`, `.btn-primary`, `.btn-success`, `.btn-outline`, `.btn-secondary`
- `.toggle-btn` (used in scene-designer; harmless for the others)

**`tileset.js`** — shared between sprite-inspector and scene-designer:
- `tileSourceXY(col, row, tileW, tileH, margin, spacing)` → `{sx, sy}`
- `tileColRow(index, cols)` → `{col, row}`
- `sheetLayout(imgWidth, imgHeight, tileW, tileH, margin, spacing)` → `{cols, rows}`
- `drawTile(ctx, img, index, cols, tileW, tileH, margin, spacing, dx, dy, dw, dh)`

**`scene-designer.js`** — all JS from scene-designer.html EXCEPT the 9-line server-injected config block (which stays inline so the server can replace placeholders).

**`scene-designer.css`** — all CSS from scene-designer.html EXCEPT the `:root`, reset, `body`, `.btn*`, and `.toggle-btn` blocks that go into `theme.css`.

---

### Task 1: Server — `/ui/*` static route

**Files:**
- Modify: `scripts/server.py`
- Create: `scripts/ui/` (directory — will be populated in later tasks)

**Step 1: Read server.py `do_GET` and `send_html`**

Already done above. Confirm the dispatch loop at line 231:
```python
def do_GET(self):
    path = self.path.split("?")[0]
    handler = self._get_routes.get(path)
    if handler:
        getattr(self, handler)()
    else:
        self.send_json({"error": "not found"}, 404)
```

**Step 2: Add `serve_ui_file` helper to `AssetHandler`**

Add after `serve_project_file` (around line 218):
```python
def serve_ui_file(self, filename):
    """Serve a static file from scripts/ui/."""
    # Reject path traversal attempts
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
```

**Step 3: Add prefix dispatch to `do_GET`**

```python
def do_GET(self):
    path = self.path.split("?")[0]
    if path.startswith("/ui/"):
        self.serve_ui_file(path[4:])  # strip "/ui/"
        return
    handler = self._get_routes.get(path)
    if handler:
        getattr(self, handler)()
    else:
        self.send_json({"error": "not found"}, 404)
```

**Step 4: Create the directory**

```bash
mkdir -p scripts/ui
```

**Step 5: Smoke-test the route (after theme.css is created in Task 2)**

```bash
curl -s http://localhost:8483/ui/theme.css | head -5
```
Expected: `:root {` line appears.

**Step 6: Commit**

```bash
git add scripts/server.py scripts/ui/
git commit -m "feat: add /ui/* static route for shared UI modules"
```

---

### Task 2: Create `scripts/ui/theme.css`

**Files:**
- Create: `scripts/ui/theme.css`

**Step 1: Write `theme.css`**

```css
/* ============================================================
   Shared design tokens and base styles
   Used by: asset-preview, sprite-inspector, scene-designer
   ============================================================ */

:root {
  --bg: #0f1118;
  --surface: #1a1d2e;
  --surface-hover: #242840;
  --border: #2d3154;
  --border-selected: #6c5ce7;
  --accent: #6c5ce7;
  --accent-glow: rgba(108, 92, 231, 0.3);
  --text: #e8e6f0;
  --text-dim: #8b89a0;
  --tag-bg: #2d3154;
  --success: #00b894;
  --danger: #e17055;
  --warning: #fdcb6e;
  /* asset-preview extras */
  --cc0: #00b894;
  --ccby: #fdcb6e;
  --other: #e17055;
}

* { margin: 0; padding: 0; box-sizing: border-box; }

body {
  font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, sans-serif;
  background: var(--bg);
  color: var(--text);
}

/* ---- Buttons ---- */

.btn {
  padding: 8px 16px;
  border: none;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}

.btn:disabled { opacity: 0.4; cursor: not-allowed; }

/* accent / primary (purple) */
.btn-accent,
.btn-primary {
  background: var(--accent);
  color: white;
}
.btn-accent:hover:not(:disabled),
.btn-primary:hover:not(:disabled) { filter: brightness(1.15); }

/* success (green) */
.btn-success {
  background: var(--success);
  color: white;
}
.btn-success:hover:not(:disabled) { filter: brightness(1.15); }

/* outline / secondary */
.btn-outline,
.btn-secondary {
  background: transparent;
  color: var(--text);
  border: 1px solid var(--border);
}
.btn-outline:hover:not(:disabled),
.btn-secondary:hover:not(:disabled) { background: var(--surface-hover); }

/* ---- Toggle buttons ---- */

.toggle-btn {
  padding: 6px 12px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg);
  color: var(--text-dim);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
}
.toggle-btn:hover { color: var(--text); }
.toggle-btn.active {
  border-color: var(--accent);
  color: var(--accent);
}
```

**Step 2: Verify file exists and looks correct**

```bash
cat scripts/ui/theme.css | head -5
```

**Step 3: Test via running server**

```bash
curl -s http://localhost:8483/ui/theme.css | grep ":root"
```
Expected: `:root {`

**Step 4: Commit**

```bash
git add scripts/ui/theme.css
git commit -m "feat: add shared theme.css with design tokens and button styles"
```

---

### Task 3: Create `scripts/ui/tileset.js`

**Files:**
- Create: `scripts/ui/tileset.js`

**Step 1: Write `tileset.js` with parameterized functions**

```javascript
/**
 * tileset.js — shared spritesheet math utilities
 * Used by: sprite-inspector, scene-designer
 *
 * All functions are pure; no global state.
 */

/**
 * Compute the pixel position of a tile in a spritesheet.
 * @returns {{sx: number, sy: number}}
 */
function tileSourceXY(col, row, tileW, tileH, margin, spacing) {
  return {
    sx: margin + col * (tileW + spacing),
    sy: margin + row * (tileH + spacing),
  };
}

/**
 * Convert a 0-based tile index to column and row.
 * @returns {{col: number, row: number}}
 */
function tileColRow(index, cols) {
  return { col: index % cols, row: Math.floor(index / cols) };
}

/**
 * Compute the number of columns and rows in a spritesheet image.
 * @returns {{cols: number, rows: number}}
 */
function sheetLayout(imgWidth, imgHeight, tileW, tileH, margin, spacing) {
  const cols = Math.floor((imgWidth - margin) / (tileW + spacing));
  const rows = Math.floor((imgHeight - margin) / (tileH + spacing));
  return { cols, rows };
}

/**
 * Draw a single tile from a spritesheet onto a canvas context.
 * dx/dy/dw/dh define destination rect; tileW/tileH define source rect size.
 */
function drawTile(ctx, img, index, cols, tileW, tileH, margin, spacing, dx, dy, dw, dh) {
  const { col, row } = tileColRow(index, cols);
  const { sx, sy } = tileSourceXY(col, row, tileW, tileH, margin, spacing);
  ctx.drawImage(img, sx, sy, tileW, tileH, dx, dy, dw, dh);
}
```

**Step 2: Verify via curl**

```bash
curl -s http://localhost:8483/ui/tileset.js | grep "function tileColRow"
```
Expected: `function tileColRow(index, cols) {`

**Step 3: Commit**

```bash
git add scripts/ui/tileset.js
git commit -m "feat: add shared tileset.js with spritesheet math utilities"
```

---

### Task 4: Update `asset-preview.html` — link theme.css

**Files:**
- Modify: `skills/asset-finder/assets/asset-preview.html`

**Step 1: Read the existing `<style>` block (lines 7–383)**

Identify the CSS that is identical to theme.css:
- Lines 8–23: `:root` block
- Lines 25: `* { margin: 0; ... }`
- Lines 27–32: `body { ... }`
- Lines 73–95: `.btn`, `.btn-primary`, `.btn-secondary`

**Step 2: Replace the `<style>` opening with a `<link>` and remove duplicated rules**

Replace lines 7–95 in asset-preview.html:

```html
<link rel="stylesheet" href="/ui/theme.css">
<style>
```

Then delete the `:root`, `*`, `body`, `.btn`, `.btn-primary:hover`, `.btn-primary:disabled`, `.btn-secondary`, `.btn-secondary:hover` rule blocks (they are now in theme.css).

**Step 3: Manual smoke test**

Open http://localhost:8483 in a browser. Confirm:
- Page background is dark (`#0f1118`)
- Buttons are purple with correct hover states
- Asset cards render correctly

**Step 4: Commit**

```bash
git add skills/asset-finder/assets/asset-preview.html
git commit -m "refactor: asset-preview.html links theme.css for shared styles"
```

---

### Task 5: Update `sprite-inspector.html` — link theme.css and tileset.js

**Files:**
- Modify: `skills/sprite-inspector/assets/sprite-inspector.html`

**Step 1: Replace shared CSS with theme.css link**

Same approach as Task 4. In sprite-inspector.html, the shared blocks are:
- Lines 8–21: `:root`
- Line 23: `*` reset
- Lines 25–32: `body`
- Lines 452–484: `.btn`, `.btn-accent`, `.btn-success`, `.btn-outline`

Replace `<style>` tag's opening and remove those rule blocks. Keep all inspector-specific CSS (`.tile-canvas`, `#grid-panel`, `#sidebar`, `.mode-tab`, `.frame-item`, `.field`, etc.).

Result:
```html
<link rel="stylesheet" href="/ui/theme.css">
<style>
  /* inspector-specific styles only */
  #grid-panel { ... }
  ...
</style>
```

**Step 2: Add `<script src="/ui/tileset.js">` before the inline script**

Between `</body>` opening and the existing `<script>` block, insert:
```html
<script src="/ui/tileset.js"></script>
```

**Step 3: Update sprite-inspector's JS to use shared functions**

The inspector currently uses closure-based versions:
```javascript
function getTileSourceXY(col, row) { ... uses tileWidth, tileHeight, margin, spacing }
function getTileColRow(index) { ... uses cols }
function drawTileToCanvas(ctx, index, dx, dy, dw, dh) { ... }
```

And computes cols/rows in `img.onload`:
```javascript
cols = Math.floor((img.width - margin) / (tileWidth + spacing));
rows = Math.floor((img.height - margin) / (tileHeight + spacing));
```

After adding tileset.js, replace these:
```javascript
// DELETE these three functions:
// getTileSourceXY, getTileColRow, drawTileToCanvas

// In img.onload, replace the cols/rows computation:
const layout = sheetLayout(img.width, img.height, tileWidth, tileHeight, margin, spacing);
cols = layout.cols;
rows = layout.rows;

// Update all callers:
// getTileSourceXY(col, row) → tileSourceXY(col, row, tileWidth, tileHeight, margin, spacing)
// getTileColRow(index) → tileColRow(index, cols)
// drawTileToCanvas(ctx, idx, dx, dy, dw, dh) → drawTile(ctx, img, idx, cols, tileWidth, tileHeight, margin, spacing, dx, dy, dw, dh)
```

Callers to update:
- `buildGrid()` line ~720: `getTileSourceXY(c, r)` → `tileSourceXY(c, r, tileWidth, tileHeight, margin, spacing)`
- `inspectTile()` line ~757: `getTileSourceXY(col, row)` → `tileSourceXY(col, row, tileWidth, tileHeight, margin, spacing)`
- `renderAnimFrames()` line ~813: `drawTileToCanvas(ctx, tileIdx, ...)` → `drawTile(ctx, img, tileIdx, cols, ...)`
- `buildGrid()` canvas draw: `drawTileToCanvas` calls → `drawTile` calls

**Step 4: Manual smoke test**

Open http://localhost:8483/inspector (after loading a spritesheet). Confirm:
- Tiles render correctly in the grid
- Clicking a tile shows correct inspect preview
- Animation frames render correctly

**Step 5: Commit**

```bash
git add skills/sprite-inspector/assets/sprite-inspector.html
git commit -m "refactor: sprite-inspector links theme.css and shared tileset.js"
```

---

### Task 6: Extract scene-designer CSS → `scripts/ui/scene-designer.css`

**Files:**
- Create: `scripts/ui/scene-designer.css`
- Modify: `skills/scene-designer/assets/scene-designer.html`

**Step 1: Read scene-designer.html CSS block (lines 7–777)**

Identify the shared blocks to remove (already in theme.css):
- Lines 8–22: `:root`
- Line 24: `*` reset
- Lines 26–34: `body`
- Lines 587–605: `.toggle-btn`, `.toggle-btn:hover`, `.toggle-btn.active`
- Lines 615–638: `.btn`, `.btn:disabled`, `.btn-accent`, `.btn-accent:hover`

Everything else (lines 36–585 and 607–613 and 639–777) is scene-designer-specific.

**Step 2: Create `scripts/ui/scene-designer.css`**

Copy all CSS from scene-designer.html's style block EXCEPT the shared blocks identified above. This includes all layout, panel, palette, canvas, layer, zone, and modal styles.

**Step 3: Update scene-designer.html `<head>`**

Replace `<style>` block (lines 7–778) with:
```html
<link rel="stylesheet" href="/ui/theme.css">
<link rel="stylesheet" href="/ui/scene-designer.css">
```

Note: `.spacer` and `.info-text` are scene-designer-specific — keep them in scene-designer.css.

**Step 4: Verify via browser**

Open http://localhost:8483/designer. Confirm:
- Full layout renders (palette panel, canvas area, layer panel)
- Buttons work
- Grid/Bounds toggles work
- Layer panel styles look correct

**Step 5: Commit**

```bash
git add scripts/ui/scene-designer.css skills/scene-designer/assets/scene-designer.html
git commit -m "refactor: extract scene-designer CSS to scripts/ui/scene-designer.css"
```

---

### Task 7: Extract scene-designer JS → `scripts/ui/scene-designer.js`

**Files:**
- Create: `scripts/ui/scene-designer.js`
- Modify: `skills/scene-designer/assets/scene-designer.html`

**Step 1: Identify the split point in scene-designer.html**

The JS block starts at line 938 with `<script>`. The server-injected config block is:
```javascript
// ====== Server-injected Data ======
const GRID_CONFIG = __GRID_CONFIG_PLACEHOLDER__;
const TILE_SIZE = __TILE_SIZE_PLACEHOLDER__;
const TILESETS = __TILESETS_PLACEHOLDER__;
const LAYERS = __LAYERS_PLACEHOLDER__;
const ZONES = __ZONES_PLACEHOLDER__;
```
(approximately lines 939–947)

Everything from line 948 onward (State, Canvas Setup, Init, etc.) moves to `scene-designer.js`.

**Step 2: Create `scripts/ui/scene-designer.js`**

Copy lines 948–2215 of scene-designer.html JS into `scripts/ui/scene-designer.js`. This file starts with the state declarations:

```javascript
// ====== State ======
// (all the let/const state vars)
...
// ====== Canvas Setup ======
...
// all the way through keyboard shortcuts and the init() call at the bottom
```

**Important:** The `const` declarations in the server-injected block (`GRID_CONFIG`, `TILE_SIZE`, `TILESETS`, `LAYERS`, `ZONES`) are in global scope because they're in a plain `<script>` block. The external `scene-designer.js` can read them as globals — no changes needed to the code inside.

**Step 3: Update scene-designer.html `<body>` / script section**

Replace the entire `<script>` block (lines 938–2217) with:

```html
<script src="/ui/tileset.js"></script>
<script>
// ====== Server-injected Data ======
const GRID_CONFIG = __GRID_CONFIG_PLACEHOLDER__;
const TILE_SIZE = __TILE_SIZE_PLACEHOLDER__;
const TILESETS = __TILESETS_PLACEHOLDER__;
const LAYERS = __LAYERS_PLACEHOLDER__;
const ZONES = __ZONES_PLACEHOLDER__;
</script>
<script src="/ui/scene-designer.js"></script>
```

**Step 4: Update `getTileInfo` and `getTileInfoAt` to use tileset.js**

In `scene-designer.js`, `getTileInfo` and `getTileInfoAt` do their own math. Update them to use `tileSourceXY` and `tileColRow` from tileset.js. These functions take a `globalId` and look up the tileset from the `tilesets` array. The key math:

Before:
```javascript
const col = Math.floor((gid - 1) % cols);
const row = Math.floor((gid - 1) / cols);
const sx = ts.margin + col * (ts_size + ts.spacing);
const sy = ts.margin + row * (ts_size + ts.spacing);
```

After:
```javascript
const { col, row } = tileColRow(gid - 1, cols);
const { sx, sy } = tileSourceXY(col, row, ts_size, ts_size, ts.margin, ts.spacing);
```

**Step 5: Comprehensive manual test**

Test all scene-designer features:
1. Open http://localhost:8483/designer
2. Paint tiles on a layer — tiles should appear correctly
3. Switch layers — tile size sync should work
4. Add a new layer — should accept tiles immediately
5. Change tile size on a layer with content — modal appears, scope/clear options work
6. Palette zoom in/out — palette tiles resize
7. Recently used tiles — updates per tile size
8. Drag layer reorder — layers swap correctly
9. Bounds toggle — blue border appears/disappears
10. Grid toggle — grid overlay toggles
11. Send to Claude — submits and shows status

**Step 6: Commit**

```bash
git add scripts/ui/scene-designer.js skills/scene-designer/assets/scene-designer.html
git commit -m "refactor: extract scene-designer JS to scripts/ui/scene-designer.js"
```

---

### Task 8: Final verification and file size check

**Step 1: Check resulting file sizes**

```bash
wc -l skills/scene-designer/assets/scene-designer.html \
       skills/sprite-inspector/assets/sprite-inspector.html \
       skills/asset-finder/assets/asset-preview.html \
       scripts/ui/theme.css \
       scripts/ui/tileset.js \
       scripts/ui/scene-designer.css \
       scripts/ui/scene-designer.js
```

Expected approximate results:
- `scene-designer.html`: ~200 lines (markup + config script + links)
- `sprite-inspector.html`: ~900 lines
- `asset-preview.html`: ~550 lines
- `theme.css`: ~80 lines
- `tileset.js`: ~50 lines
- `scene-designer.css`: ~730 lines
- `scene-designer.js`: ~1250 lines

**Step 2: End-to-end test all three UIs**

```bash
# Start server
python scripts/server.py --port 8483 --no-open &

# Load inspector
curl -s -X POST http://localhost:8483/api/inspector/load \
  -H "Content-Type: application/json" \
  -d '{"image_path": "assets/images/characters/test.png", "tile_width": 16, "tile_height": 16}'
curl -s http://localhost:8483/inspector | grep "<link"

# Load designer
curl -s -X POST http://localhost:8483/api/designer/load \
  -H "Content-Type: application/json" \
  -d '{"project_path": ".","grid":{"width":10,"height":10},"tile_size":{"width":16,"height":16},"tilesets":[],"layers":[],"zones":[]}'
curl -s http://localhost:8483/designer | grep "<link"

# Verify theme.css loads
curl -s http://localhost:8483/ui/theme.css | grep ":root"
curl -s http://localhost:8483/ui/tileset.js | grep "function tileColRow"
curl -s http://localhost:8483/ui/scene-designer.css | grep "#palette-panel"
curl -s http://localhost:8483/ui/scene-designer.js | grep "function renderScene"
```

**Step 3: Commit any final cleanup**

```bash
git add -A
git commit -m "chore: ui harmonization complete — shared theme.css, tileset.js, scene-designer extracted"
```

---

## Summary of files created/modified

| Action | File |
|--------|------|
| Modify | `scripts/server.py` — `/ui/*` prefix route |
| Create | `scripts/ui/theme.css` |
| Create | `scripts/ui/tileset.js` |
| Create | `scripts/ui/scene-designer.css` |
| Create | `scripts/ui/scene-designer.js` |
| Modify | `skills/asset-finder/assets/asset-preview.html` |
| Modify | `skills/sprite-inspector/assets/sprite-inspector.html` |
| Modify | `skills/scene-designer/assets/scene-designer.html` |

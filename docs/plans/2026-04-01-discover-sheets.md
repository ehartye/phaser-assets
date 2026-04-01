# Discover Sheets Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use h-superpowers:subagent-driven-development, h-superpowers:team-driven-development, or h-superpowers:executing-plans to implement this plan (ask user which approach).

**Goal:** Add a "Discover Sheets" button to both the sprite inspector and scene designer that opens a shared fuzzy-searchable image picker with thumbnails; also refactor the inspector so tile config is per-mode instead of per-sheet.

**Architecture:** A new shared `asset-picker.js` + `asset-picker.css` module (served via `/ui/*`) implements the picker as a modal with a single `openAssetPicker(callback)` function. A new `/api/assets/list` server route walks the project directory. The inspector's `activeCfg()` changes to return the active mode's tile config instead of the active sheet's config.

**Tech Stack:** Python `http.server` mixins, vanilla JS (ES5-compatible), CSS custom properties from `theme.css`.

---

### Task 1: Server — `/api/assets/list` endpoint

**Files:**
- Create: `scripts/routes/assets.py`
- Modify: `scripts/routes/__init__.py` (add `"assets"` to `_MODULE_NAMES`)
- Modify: `scripts/server.py` (import `AssetsRoutes`, add to `_base_mixins`)

**Step 1: Create `scripts/routes/assets.py`**

```python
"""Assets discovery route."""

import os

ROUTES = {
    "GET": {
        "/api/assets/list": "handle_assets_list",
    },
    "POST": {},
}

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
_SKIP_DIRS = {".git", "node_modules", ".worktrees", "__pycache__"}


class AssetsRoutes:
    """Mixin providing asset discovery handlers."""

    def handle_assets_list(self):
        from server import session
        if not session.project_path:
            self.send_json([])
            return

        project_real = os.path.realpath(session.project_path)
        paths = []

        for root, dirs, files in os.walk(project_real):
            dirs[:] = sorted(d for d in dirs if d not in _SKIP_DIRS and not d.startswith("."))
            for fname in sorted(files):
                if os.path.splitext(fname)[1].lower() in _IMAGE_EXTS:
                    full = os.path.join(root, fname)
                    rel = os.path.relpath(full, project_real).replace(os.sep, "/")
                    paths.append(rel)

        self.send_json(paths)
```

**Step 2: Register the module**

In `scripts/routes/__init__.py`, add `"assets"` to `_MODULE_NAMES`:
```python
_MODULE_NAMES = ["health", "asset_finder", "inspector", "scene_designer", "itch_io", "assets"]
```

In `scripts/server.py`, add after the existing route imports (around line 125):
```python
from routes.assets import AssetsRoutes  # noqa: E402
```
And add `AssetsRoutes` to `_base_mixins`:
```python
_base_mixins = [HealthRoutes, AssetFinderRoutes, InspectorRoutes, AssetsRoutes]
```

**Step 3: Restart server and verify**

```bash
# Restart server
curl -s -X POST http://localhost:8483/shutdown
python scripts/server.py --port 8483 --no-open &
sleep 3

# Load a session so project_path is set
curl -s -X POST http://localhost:8483/api/inspector/load \
  -H "Content-Type: application/json" \
  -d @inspector-test.json

# Check results
curl -s http://localhost:8483/api/assets/list | python -m json.tool | head -20
```

Expected: JSON array of relative image paths like `["assets/images/characters/..."]`.

**Step 4: Commit**

```bash
git add scripts/routes/assets.py scripts/routes/__init__.py scripts/server.py
git commit -m "feat: add /api/assets/list endpoint for project image discovery"
```

---

### Task 2: Shared CSS — `scripts/ui/asset-picker.css`

**Files:**
- Create: `scripts/ui/asset-picker.css`

**Step 1: Create the file**

```css
/* Shared asset picker modal */

#asset-picker-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.72);
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
}

#ap-modal {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  width: 800px;
  max-width: 95vw;
  max-height: 86vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
}

#ap-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 20px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

#ap-header h2 {
  font-size: 15px;
  font-weight: 600;
  margin: 0;
  color: var(--text);
}

#ap-close {
  background: transparent;
  border: none;
  color: var(--text-dim);
  font-size: 18px;
  cursor: pointer;
  padding: 2px 6px;
  border-radius: 4px;
  line-height: 1;
}

#ap-close:hover {
  color: var(--text);
  background: var(--surface-hover);
}

#ap-filter-row {
  padding: 10px 20px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

#ap-filter {
  width: 100%;
  box-sizing: border-box;
}

#ap-grid {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
  align-content: start;
  min-height: 0;
}

#ap-empty {
  grid-column: 1 / -1;
  text-align: center;
  color: var(--text-dim);
  font-size: 13px;
  padding: 32px 0;
}

.ap-card {
  background: var(--bg);
  border: 2px solid transparent;
  border-radius: 6px;
  padding: 8px;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  transition: border-color 0.12s;
  min-width: 0;
}

.ap-card:hover,
.ap-card.ap-highlighted {
  border-color: var(--accent);
}

.ap-thumb {
  width: 100%;
  aspect-ratio: 1;
  object-fit: contain;
  image-rendering: pixelated;
  background: var(--surface);
  border-radius: 4px;
}

.ap-label {
  font-size: 11px;
  color: var(--text-dim);
  text-align: center;
  word-break: break-all;
  line-height: 1.3;
  max-height: 2.6em;
  overflow: hidden;
  width: 100%;
}

#ap-pagination {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 20px;
  border-top: 1px solid var(--border);
  flex-shrink: 0;
  font-size: 13px;
}

#ap-page-info {
  color: var(--text-dim);
  font-size: 12px;
}
```

**Step 2: Verify it's served**

```bash
curl -s http://localhost:8483/ui/asset-picker.css | head -5
```

Expected: `/* Shared asset picker modal */`

**Step 3: Commit**

```bash
git add scripts/ui/asset-picker.css
git commit -m "feat: add asset-picker.css shared modal styles"
```

---

### Task 3: Shared JS — `scripts/ui/asset-picker.js`

**Files:**
- Create: `scripts/ui/asset-picker.js`

**Step 1: Create the file**

```javascript
/* Shared asset picker — exposes window.openAssetPicker(callback) */

(function () {
  'use strict';

  var _el = null;
  var _allPaths = [];
  var _filtered = [];
  var _page = 0;
  var _highlighted = -1;
  var _callback = null;
  var PAGE_SIZE = 16;

  // ---- Fuzzy scoring ----
  function fuzzyScore(path, query) {
    if (!query) return 1;
    var s = path.toLowerCase();
    var q = query.toLowerCase();
    var i = 0, j = 0, score = 0, last = -1;
    while (i < q.length && j < s.length) {
      if (q[i] === s[j]) {
        score += (j === last + 1) ? 2 : 1;
        last = j;
        i++;
      }
      j++;
    }
    return i === q.length ? score : 0;
  }

  function applyFilter(query) {
    if (!query) {
      _filtered = _allPaths.slice();
    } else {
      _filtered = _allPaths
        .map(function (p) { return { path: p, score: fuzzyScore(p, query) }; })
        .filter(function (x) { return x.score > 0; })
        .sort(function (a, b) { return b.score - a.score; })
        .map(function (x) { return x.path; });
    }
    _page = 0;
    _highlighted = -1;
    renderGrid();
  }

  // ---- Rendering ----
  function renderGrid() {
    if (!_el) return;
    var grid = _el.querySelector('#ap-grid');
    grid.innerHTML = '';

    var start = _page * PAGE_SIZE;
    var pageItems = _filtered.slice(start, start + PAGE_SIZE);
    var totalPages = Math.max(1, Math.ceil(_filtered.length / PAGE_SIZE));

    if (pageItems.length === 0) {
      var empty = document.createElement('div');
      empty.id = 'ap-empty';
      empty.textContent = _allPaths.length === 0 ? 'Loading…' : 'No images match';
      grid.appendChild(empty);
    } else {
      pageItems.forEach(function (path, i) {
        var card = document.createElement('div');
        card.className = 'ap-card' + (i === _highlighted ? ' ap-highlighted' : '');

        var img = document.createElement('img');
        img.src = '/inspector/image?path=' + encodeURIComponent(path);
        img.className = 'ap-thumb';
        img.alt = '';

        var label = document.createElement('div');
        label.className = 'ap-label';
        var parts = path.replace(/\\/g, '/').split('/');
        label.textContent = parts[parts.length - 1];
        label.title = path;

        card.appendChild(img);
        card.appendChild(label);
        card.addEventListener('click', function () { select(path); });
        card.addEventListener('mouseenter', function () {
          _highlighted = i;
          updateHighlight();
        });
        grid.appendChild(card);
      });
    }

    _el.querySelector('#ap-page-info').textContent =
      'Page ' + (_page + 1) + ' of ' + totalPages + ' — ' + _filtered.length + ' images';
    _el.querySelector('#ap-prev').disabled = _page === 0;
    _el.querySelector('#ap-next').disabled = _page >= totalPages - 1;
  }

  function updateHighlight() {
    if (!_el) return;
    _el.querySelectorAll('.ap-card').forEach(function (c, i) {
      c.classList.toggle('ap-highlighted', i === _highlighted);
    });
  }

  // ---- Actions ----
  function select(path) {
    close();
    if (_callback) _callback(path);
  }

  function close() {
    if (_el) { _el.remove(); _el = null; }
    document.removeEventListener('keydown', onKey);
  }

  function onKey(e) {
    if (!_el) return;
    var cards = _el.querySelectorAll('.ap-card');
    if (e.key === 'Escape') {
      close();
    } else if (e.key === 'Enter') {
      if (_highlighted >= 0 && cards[_highlighted]) {
        select(cards[_highlighted].dataset.path);
      }
    } else if (e.key === 'ArrowRight') {
      _highlighted = Math.min(_highlighted + 1, cards.length - 1);
      updateHighlight();
      e.preventDefault();
    } else if (e.key === 'ArrowLeft') {
      _highlighted = Math.max(_highlighted - 1, 0);
      updateHighlight();
      e.preventDefault();
    }
  }

  // ---- Build modal DOM ----
  function buildModal() {
    var overlay = document.createElement('div');
    overlay.id = 'asset-picker-overlay';

    var modal = document.createElement('div');
    modal.id = 'ap-modal';
    modal.addEventListener('click', function (e) { e.stopPropagation(); });

    var header = document.createElement('div');
    header.id = 'ap-header';
    var title = document.createElement('h2');
    title.textContent = 'Discover Sheets';
    var closeBtn = document.createElement('button');
    closeBtn.id = 'ap-close';
    closeBtn.textContent = '✕';
    closeBtn.addEventListener('click', close);
    header.appendChild(title);
    header.appendChild(closeBtn);

    var filterRow = document.createElement('div');
    filterRow.id = 'ap-filter-row';
    var filterInput = document.createElement('input');
    filterInput.id = 'ap-filter';
    filterInput.type = 'text';
    filterInput.placeholder = 'Filter by filename…';
    filterInput.autocomplete = 'off';
    filterInput.addEventListener('input', function () { applyFilter(this.value.trim()); });
    filterRow.appendChild(filterInput);

    var grid = document.createElement('div');
    grid.id = 'ap-grid';

    var pagination = document.createElement('div');
    pagination.id = 'ap-pagination';
    var prevBtn = document.createElement('button');
    prevBtn.id = 'ap-prev';
    prevBtn.className = 'btn btn-outline';
    prevBtn.textContent = '← Prev';
    prevBtn.addEventListener('click', function () {
      if (_page > 0) { _page--; _highlighted = -1; renderGrid(); }
    });
    var pageInfo = document.createElement('span');
    pageInfo.id = 'ap-page-info';
    var nextBtn = document.createElement('button');
    nextBtn.id = 'ap-next';
    nextBtn.className = 'btn btn-outline';
    nextBtn.textContent = 'Next →';
    nextBtn.addEventListener('click', function () {
      var total = Math.max(1, Math.ceil(_filtered.length / PAGE_SIZE));
      if (_page < total - 1) { _page++; _highlighted = -1; renderGrid(); }
    });
    pagination.appendChild(prevBtn);
    pagination.appendChild(pageInfo);
    pagination.appendChild(nextBtn);

    modal.appendChild(header);
    modal.appendChild(filterRow);
    modal.appendChild(grid);
    modal.appendChild(pagination);
    overlay.appendChild(modal);

    // Click backdrop to close
    overlay.addEventListener('click', close);

    return overlay;
  }

  // ---- Public API ----
  window.openAssetPicker = function (callback) {
    if (_el) close();
    _callback = callback;
    _allPaths = [];
    _filtered = [];
    _page = 0;
    _highlighted = -1;

    _el = buildModal();
    document.body.appendChild(_el);
    _el.querySelector('#ap-filter').focus();
    document.addEventListener('keydown', onKey);

    renderGrid(); // shows "Loading…"

    fetch('/api/assets/list')
      .then(function (r) { return r.json(); })
      .then(function (paths) {
        _allPaths = paths;
        _filtered = paths.slice();
        renderGrid();
      })
      .catch(function () {
        if (_el) {
          var grid = _el.querySelector('#ap-grid');
          grid.innerHTML = '<div id="ap-empty">Failed to load asset list</div>';
        }
      });
  };
})();
```

**Step 2: Verify it's served**

```bash
curl -s http://localhost:8483/ui/asset-picker.js | head -3
```

Expected: `/* Shared asset picker — exposes window.openAssetPicker(callback) */`

**Step 3: Commit**

```bash
git add scripts/ui/asset-picker.js
git commit -m "feat: add asset-picker.js shared picker module"
```

---

### Task 4: Inspector — per-mode tile config

**Files:**
- Modify: `skills/sprite-inspector/assets/sprite-inspector.html`

**Context:** Currently `activeCfg()` returns `SHEETS[activeSheetIdx]` which has `tile_width`, `tile_height`, `margin`, `spacing`. After this task, `activeCfg()` returns a per-mode object. Each mode panel (Animation, Layer, Selection) gets 4 number inputs. The grid redraws when inputs change or mode switches.

**Step 1: Replace `activeCfg()` and add mode config state**

Find and replace the `activeCfg()` definition (near the top of the `<script>` block):

Old:
```javascript
function activeCfg() { return SHEETS[activeSheetIdx]; }
```

New — add mode config state and redefine `activeCfg()`:
```javascript
// Initial tile config: use first sheet's values if provided, otherwise 32/32/0/0
var _defaultCfg = (SHEETS[0] && SHEETS[0].tile_width)
  ? { tile_width: SHEETS[0].tile_width, tile_height: SHEETS[0].tile_height,
      margin: SHEETS[0].margin || 0, spacing: SHEETS[0].spacing || 0 }
  : { tile_width: 32, tile_height: 32, margin: 0, spacing: 0 };

var modeCfgs = {
  animation: Object.assign({}, _defaultCfg),
  layer:     Object.assign({}, _defaultCfg),
  selection: Object.assign({}, _defaultCfg),
};

function activeCfg() { return modeCfgs[currentMode]; }
```

**Step 2: Add tile config inputs to each mode panel**

Each mode panel needs this HTML block at the top, before its first `<div class="field">`. Add it to Animation, Layer, and Selection panels:

```html
<div class="field-row tile-cfg-row">
  <div class="field">
    <label>Tile W</label>
    <input type="number" class="tile-cfg-input" data-mode="animation" data-key="tile_width" value="32" min="1" max="512">
  </div>
  <div class="field">
    <label>Tile H</label>
    <input type="number" class="tile-cfg-input" data-mode="animation" data-key="tile_height" value="32" min="1" max="512">
  </div>
  <div class="field">
    <label>Margin</label>
    <input type="number" class="tile-cfg-input" data-mode="animation" data-key="margin" value="0" min="0">
  </div>
  <div class="field">
    <label>Spacing</label>
    <input type="number" class="tile-cfg-input" data-mode="animation" data-key="spacing" value="0" min="0">
  </div>
</div>
```

Change `data-mode` to `layer` and `selection` for the other two panels.

**Step 3: Wire up the inputs**

Add this near the bottom of the `<script>` (before the final `// Initialize` block):

```javascript
// Tile config inputs — update modeCfg and redraw grid
document.querySelectorAll('.tile-cfg-input').forEach(function(input) {
  input.addEventListener('change', function() {
    var mode = this.dataset.mode;
    var key  = this.dataset.key;
    var val  = parseInt(this.value) || 0;
    if (key === 'tile_width' || key === 'tile_height') val = Math.max(1, val);
    modeCfgs[mode][key] = val;
    if (mode === currentMode && sheetImages[activeSheetIdx]) {
      // Recompute layout for new tile size
      var cfg = activeCfg();
      var img = activeImg();
      var layout = sheetLayout(img.width, img.height, cfg.tile_width, cfg.tile_height, cfg.margin, cfg.spacing);
      sheetCols[activeSheetIdx] = layout.cols;
      sheetRows[activeSheetIdx] = layout.rows;
      updateGridForActiveSheet();
    }
  });
});
```

**Step 4: Sync inputs when switching modes**

In `switchMode()`, after `updateGridHighlights()`, add:

```javascript
// Sync the tile config inputs to show this mode's values
var cfg = modeCfgs[mode];
document.querySelectorAll('.tile-cfg-input[data-mode="' + mode + '"]').forEach(function(inp) {
  inp.value = cfg[inp.dataset.key];
});
// Redraw grid with this mode's tile config
if (sheetImages[activeSheetIdx]) {
  var layout = sheetLayout(activeImg().width, activeImg().height,
    cfg.tile_width, cfg.tile_height, cfg.margin, cfg.spacing);
  sheetCols[activeSheetIdx] = layout.cols;
  sheetRows[activeSheetIdx] = layout.rows;
  updateGridForActiveSheet();
}
```

**Step 5: Sync inputs on initial sheet load**

In `updateGridForActiveSheet()`, after the existing `buildGrid()` call, add:

```javascript
// Update tile config inputs to reflect active mode's current values
var cfg = activeCfg();
document.querySelectorAll('.tile-cfg-input[data-mode="' + currentMode + '"]').forEach(function(inp) {
  inp.value = cfg[inp.dataset.key];
});
```

**Step 6: Verify manually**

```bash
# Load inspector
curl -s -X POST http://localhost:8483/api/inspector/load \
  -H "Content-Type: application/json" \
  -d @inspector-test.json
```

Open http://localhost:8483/inspector. Confirm:
- Each mode panel shows Tile W/H/Margin/Spacing inputs
- Changing tile W/H on Animation mode redraws the grid with new tile size
- Switching to Layer mode shows that mode's (independent) tile config

**Step 7: Commit**

```bash
git add skills/sprite-inspector/assets/sprite-inspector.html
git commit -m "feat: per-mode tile config in sprite inspector"
```

---

### Task 5: Inspector — Discover Sheets button

**Depends on:** Tasks 3, 4

**Files:**
- Modify: `skills/sprite-inspector/assets/sprite-inspector.html`

**Step 1: Import picker CSS and JS**

In the `<head>`, after the existing link tags:
```html
<link rel="stylesheet" href="/ui/asset-picker.css">
```

Before `</body>` (after the existing scripts):
```html
<script src="/ui/asset-picker.js"></script>
```

**Step 2: Add the button to the grid panel header**

Current HTML in the grid panel:
```html
<div id="grid-panel">
  <div id="sheet-tabs"></div>
  <h2 id="grid-header">Loading sprite sheet...</h2>
```

Replace with:
```html
<div id="grid-panel">
  <div id="sheet-tabs-bar">
    <div id="sheet-tabs"></div>
    <button class="btn btn-outline" id="discover-btn" onclick="openDiscoverPicker()">+ Discover</button>
  </div>
  <h2 id="grid-header">Loading sprite sheet...</h2>
```

Add CSS for the bar (in the `<style>` block):
```css
#sheet-tabs-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  border-bottom: 1px solid var(--border);
  background: var(--surface);
}

#sheet-tabs-bar #sheet-tabs {
  flex: 1;
  padding: 0;
  border-bottom: none;
}
```

**Step 3: Add `openDiscoverPicker()` function**

In the `<script>` block, add:

```javascript
function openDiscoverPicker() {
  openAssetPicker(function(path) {
    // Use active mode's current tile config as defaults for the new sheet
    var cfg = activeCfg();
    SHEETS.push({
      image_path: path,
      tile_width:  cfg.tile_width,
      tile_height: cfg.tile_height,
      margin:      cfg.margin,
      spacing:     cfg.spacing,
    });
    sheetImages.push(null);
    sheetCols.push(0);
    sheetRows.push(0);
    buildSheetTabs();
    switchSheet(SHEETS.length - 1);
  });
}
```

**Step 4: Verify manually**

Open http://localhost:8483/inspector. Click "+ Discover". Confirm:
- Modal opens, thumbnails load
- Typing filters by filename fuzzy
- Clicking a thumbnail closes the modal and adds a new sheet tab
- New sheet loads and grid renders

**Step 5: Commit**

```bash
git add skills/sprite-inspector/assets/sprite-inspector.html
git commit -m "feat: Discover Sheets button in sprite inspector"
```

---

### Task 6: Scene designer — Discover Sheets button

**Depends on:** Task 3

**Files:**
- Modify: `scripts/ui/scene-designer.js`
- Modify: `skills/scene-designer/assets/scene-designer.html`

**Step 1: Add `addTilesetFromPath()` to `scene-designer.js`**

Add after the `loadTilesets()` function (around line 127):

```javascript
function addTilesetFromPath(imagePath) {
  var parts = imagePath.replace(/\\/g, '/').split('/');
  var name = parts[parts.length - 1].replace(/\.[^.]+$/, ''); // strip extension
  var activeLayer = layers[activeLayerIndex];
  var tileSize = (activeLayer && activeLayer.tileSize) ? activeLayer.tileSize : 32;

  tilesetConfigs.push({
    name: name,
    image_path: imagePath,
    tile_width: tileSize,
    tile_height: tileSize,
    margin: 0,
    spacing: 0,
  });

  var idx = tilesetConfigs.length - 1;
  var img = new Image();
  img.crossOrigin = 'anonymous';
  tilesetImages[idx] = img;
  tilesetReady[idx] = false;

  img.onload = function() {
    tilesetReady[idx] = true;
    buildPaletteGrid(idx);
    renderScene();
    document.getElementById('palette-info').textContent =
      tilesetConfigs.length + ' tileset(s) loaded';
  };
  img.onerror = function() {
    console.error('Failed to load tileset:', imagePath);
  };
  img.src = '/designer/tileset?path=' + encodeURIComponent(imagePath);

  activeTilesetIndex = idx;
  buildTilesetTabs();
}
```

**Step 2: Import picker CSS/JS in `scene-designer.html`**

In the `<head>`:
```html
<link rel="stylesheet" href="/ui/asset-picker.css">
```

Just before `</body>`:
```html
<script src="/ui/asset-picker.js"></script>
```

**Step 3: Add the Discover button near the tileset tabs**

In `scene-designer.html`, find the palette header area (around the `<div class="tileset-tabs" id="tileset-tabs">` line). Add after it:

```html
<div id="discover-sheets-bar">
  <button class="btn btn-outline" onclick="openAssetPicker(addTilesetFromPath)">+ Discover Sheets</button>
</div>
```

Add CSS in `scripts/ui/scene-designer.css`:
```css
#discover-sheets-bar {
  padding: 6px 12px;
  border-bottom: 1px solid var(--border);
}
```

**Step 4: Verify manually**

Start the scene designer. Click "+ Discover Sheets". Confirm:
- Picker modal opens with thumbnails
- Selecting an image adds a new tileset tab and loads the tileset into the palette

**Step 5: Commit**

```bash
git add scripts/ui/scene-designer.js skills/scene-designer/assets/scene-designer.html scripts/ui/scene-designer.css
git commit -m "feat: Discover Sheets button in scene designer"
```

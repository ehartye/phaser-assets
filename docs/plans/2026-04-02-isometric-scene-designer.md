# Isometric Scene Designer Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use h-superpowers:subagent-driven-development, h-superpowers:team-driven-development, or h-superpowers:executing-plans to implement this plan (ask user which approach).

**Goal:** Add isometric rendering mode and sprite-collection tileset support to the scene designer.

**Architecture:** A scene-level `orientation` field switches between orthographic and isometric. Two transform functions (`tileToScreen`, `screenToTile`) replace all direct `col * tileW` math — trivial pass-throughs in ortho mode, diamond-projection math in iso mode. Sprite-collection tilesets load a folder of individual PNGs as one tileset (one file = one tile), with Tiled image-collection export format.

**Tech Stack:** Vanilla JS (browser), Python http.server mixin routes, HTML/CSS. No test framework exists — verification is manual via browser and curl.

---

### Task 1: Server orientation injection

Add `orientation` to the session state and inject it into the HTML template.

**Files:**
- Modify: `scripts/routes/scene_designer.py`

**Step 1: Add orientation to handle_designer_load**

In `handle_designer_load` (line 30), add `orientation` to the session dict:

```python
session.designer = {
    "project_path": body.get("project_path", session.project_path),
    "grid": body.get("grid", {"width": 20, "height": 15}),
    "tile_size": body.get("tile_size", {"width": 16, "height": 16}),
    "orientation": body.get("orientation", "orthogonal"),
    "tilesets": body.get("tilesets", []),
    "layers": body.get("layers", []),
    "zones": body.get("zones", []),
    "status": "active",
    "results": None,
}
```

**Step 2: Inject orientation into HTML template**

In `handle_designer` (after line 64, following the zones replace), add:

```python
html = html.replace("__ORIENTATION_PLACEHOLDER__", json.dumps(session.designer.get("orientation", "orthogonal")))
```

**Step 3: Add orientation to handle_designer_submit**

In `handle_designer_submit` (lines 81–88), add orientation to results:

```python
session.designer["results"] = {
    "grid": body.get("grid", session.designer.get("grid")),
    "tile_size": body.get("tile_size", session.designer.get("tile_size")),
    "orientation": body.get("orientation", session.designer.get("orientation", "orthogonal")),
    "tilesets": body.get("tilesets", session.designer.get("tilesets")),
    "layers": body.get("layers", []),
    "zones": body.get("zones", []),
}
```

**Step 4: Verify with curl**

Start server: `python scripts/server.py`

```bash
curl -s -X POST http://localhost:8483/api/designer/load \
  -H "Content-Type: application/json" \
  -d "{\"project_path\": \"C:/Users/ehart/repos/phaser-assets\", \"orientation\": \"isometric\"}"
```

Expected: `{"status": "loaded", "grid": {"width": 20, "height": 15}, "layer_count": 0, "tileset_count": 0}`

Then fetch the page and check the source contains `var orientation = "isometric"`:

```bash
curl -s http://localhost:8483/designer | grep "var orientation"
```

**Step 5: Commit**

```bash
git add scripts/routes/scene_designer.py
git commit -m "feat: add orientation field to scene designer session"
```

---

### Task 2: JS orientation state + scene config variable

**Files:**
- Modify: `skills/scene-designer/assets/scene-designer.html` (line 177–184 script block)
- Modify: `scripts/ui/scene-designer.js` (top of file, state section)

**Step 1: Add orientation to the HTML inline script**

In `scene-designer.html`, in the inline script block (around line 177), add after `var zones = ...`:

```javascript
var orientation = __ORIENTATION_PLACEHOLDER__;
```

**Step 2: Add orientation to JS state section**

In `scene-designer.js`, at the top state section (after line 15, after `var zoneCurrent`), add:

```javascript
var _pendingOrientation = null;
```

(The `orientation` var comes from the HTML — no need to redeclare it here. `_pendingOrientation` is used by the confirm dialog.)

**Step 3: Add setOrientation function**

Add after the `_pendingTileSize` / `tileSizeConfirmCancel` functions (around line 1142):

```javascript
// ====== Orientation ======
function setOrientation(mode) {
  if (orientation === mode) return;

  var hasData = false;
  for (var i = 0; i < layers.length; i++) {
    if (_hasTileData(i)) { hasData = true; break; }
  }

  if (hasData) {
    _pendingOrientation = mode;
    document.getElementById('orientation-confirm').classList.add('visible');
  } else {
    _applyOrientation(mode);
  }
}

function orientationConfirmClear() {
  document.getElementById('orientation-confirm').classList.remove('visible');
  for (var i = 0; i < layers.length; i++) { _clearLayerData(i); }
  _applyOrientation(_pendingOrientation);
  _pendingOrientation = null;
}

function orientationConfirmCancel() {
  document.getElementById('orientation-confirm').classList.remove('visible');
  _pendingOrientation = null;
  // Re-sync toggle buttons to current orientation
  _syncOrientationButtons();
}

function _applyOrientation(mode) {
  orientation = mode;
  if (mode === 'isometric') {
    // Force 2:1 aspect ratio: tileH = tileW / 2
    tileSize.height = Math.max(1, Math.floor(tileSize.width / 2));
  } else {
    tileSize.height = tileSize.width;
  }
  _syncOrientationButtons();
  resizeCanvases();
  renderScene();
}

function _syncOrientationButtons() {
  document.getElementById('orient-ortho').classList.toggle('active', orientation === 'orthogonal');
  document.getElementById('orient-iso').classList.toggle('active', orientation === 'isometric');
}
```

**Step 4: Call _syncOrientationButtons in init()**

In `init()` (around line 88, end of function), add:

```javascript
_syncOrientationButtons();
```

**Step 5: Verify manually**

Open browser at `http://localhost:8483/designer`. No errors in console. (Buttons will be added in Task 3.)

**Step 6: Commit**

```bash
git add skills/scene-designer/assets/scene-designer.html scripts/ui/scene-designer.js
git commit -m "feat: add orientation state and setOrientation function"
```

---

### Task 3: Orientation toggle UI + confirm dialog

**Files:**
- Modify: `skills/scene-designer/assets/scene-designer.html`
- Modify: `scripts/ui/scene-designer.css`

**Step 1: Add orientation toggle to the Scene Size panel**

In `scene-designer.html`, find the `<!-- Tile Size -->` prop-section (around line 82). Add a new section **before** it:

```html
<!-- Orientation -->
<div class="prop-section">
  <h3>Orientation</h3>
  <div class="orient-toggle">
    <button id="orient-ortho" class="orient-btn active" onclick="setOrientation('orthogonal')">Orthographic</button>
    <button id="orient-iso" class="orient-btn" onclick="setOrientation('isometric')">Isometric</button>
  </div>
  <div id="iso-hint" class="iso-hint">Recommended tile size: 64×32 (2:1 ratio)</div>
</div>
```

**Step 2: Add orientation confirm dialog**

In `scene-designer.html`, after the existing `<!-- Tile Size: Confirm clear -->` modal (around line 147), add:

```html
<!-- Orientation: Confirm clear -->
<div class="modal-overlay" id="orientation-confirm">
  <div class="modal-box">
    <h3>Clear existing tiles?</h3>
    <p>Switching orientation will clear all tile data. Continue?</p>
    <div class="modal-actions">
      <button class="btn btn-sm btn-outline" style="border-color:var(--danger);color:var(--danger)" onclick="orientationConfirmClear()">Clear &amp; switch</button>
      <button class="btn btn-sm btn-outline" onclick="orientationConfirmCancel()">Cancel</button>
    </div>
  </div>
</div>
```

**Step 3: Add CSS for orientation toggle and iso hint**

In `scripts/ui/scene-designer.css`, add at the end:

```css
.orient-toggle {
  display: flex;
  gap: 4px;
}

.orient-btn {
  flex: 1;
  padding: 5px 8px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 4px;
  color: var(--text-dim);
  font-size: 12px;
  cursor: pointer;
}

.orient-btn.active {
  background: var(--accent);
  border-color: var(--accent);
  color: #fff;
}

.iso-hint {
  font-size: 11px;
  color: var(--text-dim);
  margin-top: 6px;
  display: none;
}
```

**Step 4: Show iso-hint when isometric is active**

In `_syncOrientationButtons()` (added in Task 2), add:

```javascript
var hint = document.getElementById('iso-hint');
if (hint) hint.style.display = (orientation === 'isometric') ? 'block' : 'none';
```

**Step 5: Verify manually**

Reload `http://localhost:8483/designer`. Orientation section appears in right panel. Clicking Isometric highlights the button and shows the hint. Clicking back to Orthographic restores it. With tiles painted, switching shows the confirm dialog.

**Step 6: Commit**

```bash
git add skills/scene-designer/assets/scene-designer.html scripts/ui/scene-designer.css
git commit -m "feat: add orientation toggle UI to scene designer"
```

---

### Task 4: Coordinate transform functions + canvas sizing

**Files:**
- Modify: `scripts/ui/scene-designer.js`

**Step 1: Add tileToScreen and screenToTile**

Add after `_layerGridRows` (around line 1079), before `_hasTileData`:

```javascript
// ====== Isometric Coordinate Transforms ======
// tileToScreen: returns top-left corner of tile bounding rect in canvas pixels (unzoomed)
function tileToScreen(col, row, tileW, tileH) {
  if (orientation === 'isometric') {
    var originX = grid.height * (tileW / 2);
    return {
      x: originX + (col - row) * (tileW / 2),
      y: (col + row) * (tileH / 2)
    };
  }
  return { x: col * tileW, y: row * tileH };
}

// screenToTile: converts canvas pixel position (unzoomed) to tile col/row
function screenToTile(screenX, screenY, tileW, tileH) {
  if (orientation === 'isometric') {
    var originX = grid.height * (tileW / 2);
    var dx = screenX - originX;
    return {
      col: Math.floor((dx / (tileW / 2) + screenY / (tileH / 2)) / 2),
      row: Math.floor((screenY / (tileH / 2) - dx / (tileW / 2)) / 2)
    };
  }
  return {
    col: Math.floor(screenX / tileW),
    row: Math.floor(screenY / tileH)
  };
}
```

**Step 2: Update resizeCanvases for isometric**

Replace the body of `resizeCanvases()` (lines 397–424) with:

```javascript
function resizeCanvases() {
  var maxPxW = 0, maxPxH = 0;
  for (var i = 0; i < layers.length; i++) {
    if (layers[i].type !== 'tilelayer') continue;
    var lts = _layerTileSize(layers[i]);
    var lth = (orientation === 'isometric') ? Math.max(1, Math.floor(lts / 2)) : lts;
    var cols = _layerGridCols(layers[i]);
    var rows = _layerGridRows(layers[i]);
    var lpxW, lpxH;
    if (orientation === 'isometric') {
      lpxW = (cols + rows) * (lts / 2);
      lpxH = (cols + rows) * (lth / 2);
    } else {
      lpxW = cols * lts;
      lpxH = rows * lts;
    }
    if (lpxW > maxPxW) maxPxW = lpxW;
    if (lpxH > maxPxH) maxPxH = lpxH;
  }
  if (maxPxW === 0) {
    if (orientation === 'isometric') {
      maxPxW = (grid.width + grid.height) * (tileSize.width / 2);
      maxPxH = (grid.width + grid.height) * (tileSize.height / 2);
    } else {
      maxPxW = grid.width * tileSize.width;
      maxPxH = grid.height * tileSize.height;
    }
  }

  var w = Math.ceil(maxPxW * zoom);
  var h = Math.ceil(maxPxH * zoom);

  sceneCanvas.width = w;
  sceneCanvas.height = h;
  gridCanvas.width = w;
  gridCanvas.height = h;
  zoneCanvas.width = w;
  zoneCanvas.height = h;

  sceneCtx.imageSmoothingEnabled = false;
}
```

**Step 3: Verify**

In the browser console (with isometric mode active), call:

```javascript
tileToScreen(0, 0, 64, 32)  // Expected: {x: 480, y: 0} for 15-row grid
tileToScreen(1, 0, 64, 32)  // Expected: {x: 512, y: 16}
tileToScreen(0, 1, 64, 32)  // Expected: {x: 448, y: 16}
screenToTile(480, 0, 64, 32) // Expected: {col: 0, row: 0}
```

Also verify canvas resizes when switching orientation. Canvas should be wider and shorter in iso mode than ortho.

**Step 4: Commit**

```bash
git add scripts/ui/scene-designer.js
git commit -m "feat: add isometric coordinate transforms and canvas sizing"
```

---

### Task 5: Isometric rendering (scene tiles + grid overlay)

**Files:**
- Modify: `scripts/ui/scene-designer.js`

**Step 1: Update renderScene background**

In `renderScene()` (around line 427), replace the checkerboard block with:

```javascript
// Background
if (orientation === 'isometric') {
  sceneCtx.fillStyle = '#0e1019';
  sceneCtx.fillRect(0, 0, sceneCanvas.width, sceneCanvas.height);
} else {
  var cw = tileSize.width * zoom;
  var ch = tileSize.height * zoom;
  for (var r = 0; r < grid.height; r++) {
    for (var c = 0; c < grid.width; c++) {
      sceneCtx.fillStyle = (r + c) % 2 === 0 ? '#12141f' : '#0e1019';
      sceneCtx.fillRect(c * cw, r * ch, cw, ch);
    }
  }
}
```

**Step 2: Update tile layer rendering loop**

Replace the tile rendering loop inside `renderScene()` (lines 441–467) with:

```javascript
for (var li = 0; li < layers.length; li++) {
  var layer = layers[li];
  if (!layer.visible || layer.type !== 'tilelayer') continue;
  if (!layer.data) continue;

  var lts = _layerTileSize(layer);
  var lth = (orientation === 'isometric') ? Math.max(1, Math.floor(lts / 2)) : lts;
  var lcols = _layerGridCols(layer);
  var lrows = _layerGridRows(layer);

  if (orientation === 'isometric') {
    // Diagonal-band (back-to-front) render order
    for (var sum = 0; sum <= lcols + lrows - 2; sum++) {
      for (var c = 0; c < lcols; c++) {
        var r = sum - c;
        if (r < 0 || r >= lrows) continue;
        var gid = layer.data[r * lcols + c];
        if (gid <= 0) continue;

        var info = getTileInfo(gid);
        if (!info) continue;

        var pos = tileToScreen(c, r, lts, lth);
        var srcW = info.tw, srcH = info.th;

        // Scale sprite-collection tiles to tile width; scale sheet tiles to lts x lth
        var destW, destH;
        if (info.isCollection) {
          var scale = lts / srcW;
          destW = lts * zoom;
          destH = srcH * scale * zoom;
        } else {
          destW = lts * zoom;
          destH = lth * zoom;
        }

        var destX = pos.x * zoom;
        // Anchor at bottom of diamond (tall sprites extend upward)
        var destY = (pos.y + lth) * zoom - destH;

        sceneCtx.drawImage(info.img, info.sx, info.sy, srcW, srcH, destX, destY, destW, destH);
      }
    }
  } else {
    // Orthographic: row-major order
    var lcw = lts * zoom;
    var lch = lts * zoom;
    for (var idx = 0; idx < layer.data.length; idx++) {
      var gid = layer.data[idx];
      if (gid <= 0) continue;
      var info = getTileInfoAt(gid, lts);
      if (!info) continue;
      var col = idx % lcols;
      var row = Math.floor(idx / lcols);
      sceneCtx.drawImage(info.img, info.sx, info.sy, info.tw, info.th, col * lcw, row * lch, lcw, lch);
    }
  }
}
```

**Step 3: Update renderGridOverlay for isometric**

Replace `renderGridOverlay()` (lines 473–510) with:

```javascript
function renderGridOverlay() {
  gridCtx.clearRect(0, 0, gridCanvas.width, gridCanvas.height);

  if (showGrid) {
    gridCtx.strokeStyle = 'rgba(255, 255, 255, 0.06)';
    gridCtx.lineWidth = 1;

    if (orientation === 'isometric') {
      var tw = tileSize.width;
      var th = tileSize.height;
      // Draw diamond grid lines: NW-SE lines (constant col+row = sum)
      // and NE-SW lines (constant col-row = diff)
      var cols = grid.width;
      var rows = grid.height;

      // NW-SE lines: for each col (0..cols), draw line from (col,0) to (col + rows - 1, rows - 1) roughly
      for (var c = 0; c <= cols; c++) {
        var p1 = tileToScreen(c, 0, tw, th);
        var p2 = tileToScreen(c - 1, rows, tw, th);
        // Clamp to actual tile corners
        var start = tileToScreen(c, 0, tw, th);
        var end = tileToScreen(c - 1 + 1 - 1, rows - 1, tw, th);
        // Simpler: just draw from top-edge to bottom-edge of this "column"
        var topLeft = tileToScreen(Math.max(0, c - rows), Math.max(0, rows - 1 - (cols - 1 - c)), tw, th);
        gridCtx.beginPath();
        var ax = tileToScreen(c, 0, tw, th);
        var bx = tileToScreen(c, rows, tw, th);
        gridCtx.moveTo(ax.x * zoom + 0.5, ax.y * zoom + 0.5);
        gridCtx.lineTo(bx.x * zoom + 0.5, bx.y * zoom + 0.5);
        gridCtx.stroke();
      }

      // NE-SW lines: for each row (0..rows)
      for (var r = 0; r <= rows; r++) {
        gridCtx.beginPath();
        var ay = tileToScreen(0, r, tw, th);
        var by = tileToScreen(cols, r, tw, th);
        gridCtx.moveTo(ay.x * zoom + 0.5, ay.y * zoom + 0.5);
        gridCtx.lineTo(by.x * zoom + 0.5, by.y * zoom + 0.5);
        gridCtx.stroke();
      }
    } else {
      var cw = tileSize.width * zoom;
      var ch = tileSize.height * zoom;
      var canvasW = gridCanvas.width;
      var canvasH = gridCanvas.height;

      for (var c = 0; c <= grid.width; c++) {
        var x = c * cw + 0.5;
        gridCtx.beginPath();
        gridCtx.moveTo(x, 0);
        gridCtx.lineTo(x, canvasH);
        gridCtx.stroke();
      }
      for (var r = 0; r <= grid.height; r++) {
        var y = r * ch + 0.5;
        gridCtx.beginPath();
        gridCtx.moveTo(0, y);
        gridCtx.lineTo(canvasW, y);
        gridCtx.stroke();
      }
    }
  }

  if (showBounds) {
    if (orientation === 'isometric') {
      // Draw the four corners of the diamond map as a rhombus outline
      var tw = tileSize.width;
      var th = tileSize.height;
      var topCorner    = tileToScreen(0, 0, tw, th);
      var rightCorner  = tileToScreen(grid.width, 0, tw, th);
      var bottomCorner = tileToScreen(grid.width, grid.height, tw, th);
      var leftCorner   = tileToScreen(0, grid.height, tw, th);
      // Adjust to tile center (add half-tile)
      gridCtx.strokeStyle = 'rgba(80, 140, 255, 0.6)';
      gridCtx.lineWidth = 2;
      gridCtx.beginPath();
      gridCtx.moveTo(topCorner.x * zoom, topCorner.y * zoom);
      gridCtx.lineTo(rightCorner.x * zoom + tw * zoom, rightCorner.y * zoom);
      gridCtx.lineTo(bottomCorner.x * zoom + tw * zoom, (bottomCorner.y + th) * zoom);
      gridCtx.lineTo(leftCorner.x * zoom, (leftCorner.y + th) * zoom);
      gridCtx.closePath();
      gridCtx.stroke();
    } else {
      var bw = scenePixels.width * zoom;
      var bh = scenePixels.height * zoom;
      gridCtx.strokeStyle = 'rgba(80, 140, 255, 0.6)';
      gridCtx.lineWidth = 2;
      gridCtx.strokeRect(-0.5, -0.5, bw + 1, bh + 1);
    }
  }
}
```

**Step 4: Verify**

Switch to Isometric mode. Grid lines should form a diamond pattern. Painting tiles should show them in isometric positions. Toggle grid on/off — should work in both modes.

**Step 5: Commit**

```bash
git add scripts/ui/scene-designer.js
git commit -m "feat: isometric tile rendering and diamond grid overlay"
```

---

### Task 6: Mouse input and sendToClaude for isometric

**Files:**
- Modify: `scripts/ui/scene-designer.js`

**Step 1: Update getCanvasPos to use screenToTile**

Replace `getCanvasPos()` (lines 660–670) with:

```javascript
function getCanvasPos(e) {
  var rect = sceneCanvas.getBoundingClientRect();
  var x = (e.clientX - rect.left) / zoom;
  var y = (e.clientY - rect.top) / zoom;
  var tw = tileSize.width;
  var th = tileSize.height;
  var pos = screenToTile(x, y, tw, th);
  var col = pos.col;
  var row = pos.row;
  if (col < 0 || col >= grid.width || row < 0 || row >= grid.height) return null;
  return { col: col, row: row };
}
```

**Step 2: Add orientation to sendToClaude payload**

In `sendToClaude()` (around line 1210), add `orientation` to the payload object:

```javascript
var payload = {
  grid: grid,
  tile_size: tileSize,
  orientation: orientation,
  tilesets: tilesetConfigs,
  scene_pixels: scenePixels,
  layers: layers.map(function(l) { ... }),
  zones: zones
};
```

**Step 3: Update setTileSize to enforce 2:1 ratio in iso mode**

In `_applyLayerTileSize` (around line 1145), after setting `tileSize.width = size` and `tileSize.height = size`, add:

```javascript
if (orientation === 'isometric') {
  tileSize.height = Math.max(1, Math.floor(size / 2));
}
```

Also update the parallel array sync loop that follows:

```javascript
for (var i = 0; i < tilesetConfigs.length; i++) {
  tilesetConfigs[i].tile_width = tileSize.width;
  tilesetConfigs[i].tile_height = tileSize.height;
}
```

**Step 4: Verify**

In isometric mode, paint a tile. Cursor info at bottom should show correct col/row. Tile appears under cursor. Right-click erases correct tile.

**Step 5: Commit**

```bash
git add scripts/ui/scene-designer.js
git commit -m "feat: isometric mouse input and orientation in submit payload"
```

---

### Task 7: Tiled export — isometric orientation

**Files:**
- Modify: `scripts/routes/scene_designer.py`

**Step 1: Update handle_designer_export**

In `handle_designer_export` (around line 174), replace the `tiled_map` dict with:

```python
orient = results.get("orientation", "orthogonal")
render_order = "right-down"

tiled_map = {
    "version": "1.10",
    "tiledversion": "1.10.0",
    "orientation": orient,
    "renderorder": render_order,
    "width": grid["width"],
    "height": grid["height"],
    "tilewidth": tile_size["width"],
    "tileheight": tile_size["height"],
    "infinite": False,
    "layers": tiled_layers,
    "tilesets": tiled_tilesets,
    "type": "map",
}
```

**Step 2: Verify with curl**

```bash
# First submit a scene
curl -s -X POST http://localhost:8483/api/designer/submit \
  -H "Content-Type: application/json" \
  -d "{\"grid\":{\"width\":20,\"height\":15},\"tile_size\":{\"width\":64,\"height\":32},\"orientation\":\"isometric\",\"tilesets\":[],\"layers\":[],\"zones\":[]}"

# Then export
curl -s http://localhost:8483/api/designer/export | python -m json.tool | grep orientation
```

Expected: `"orientation": "isometric"`

**Step 3: Commit**

```bash
git add scripts/routes/scene_designer.py
git commit -m "feat: isometric orientation in Tiled JSON export"
```

---

### Task 8: Sprite-collection tileset loading

Update `getTileInfo`, `getFirstGid`, and `loadTilesets` to handle `type: "sprite-collection"` tilesets. For sprite-collections, `tilesetImages[idx]` is an array of Image objects (one per sprite).

**Files:**
- Modify: `scripts/ui/scene-designer.js`

**Step 1: Update loadTilesets**

Replace `loadTilesets()` (lines 91–127) with:

```javascript
function loadTilesets() {
  tilesetImages = [];
  tilesetReady = [];
  var totalTilesets = tilesetConfigs.length;
  var loadedTilesets = 0;

  function onTilesetReady() {
    loadedTilesets++;
    if (loadedTilesets === totalTilesets) {
      document.getElementById('palette-info').textContent =
        tilesetConfigs.length + ' tileset(s) loaded';
    }
    buildPaletteGrid(activeTilesetIndex);
    renderScene();
  }

  for (var i = 0; i < tilesetConfigs.length; i++) {
    (function(idx) {
      var ts = tilesetConfigs[idx];

      if (ts.type === 'sprite-collection') {
        // Load one Image per sprite
        tilesetImages[idx] = [];
        tilesetReady[idx] = false;
        var sprites = ts.sprites || [];
        var spritesLoaded = 0;

        if (sprites.length === 0) {
          tilesetReady[idx] = true;
          onTilesetReady();
          return;
        }

        sprites.forEach(function(spriteName, spriteIdx) {
          var img = new Image();
          img.crossOrigin = 'anonymous';
          var fullPath = ts.folder_path.replace(/\\/g, '/') + '/' + spriteName;
          img.onload = function() {
            spritesLoaded++;
            if (spritesLoaded === sprites.length) {
              tilesetReady[idx] = true;
              onTilesetReady();
            }
          };
          img.onerror = function() {
            spritesLoaded++;
            console.error('Failed to load sprite:', fullPath);
            if (spritesLoaded === sprites.length) {
              tilesetReady[idx] = true;
              onTilesetReady();
            }
          };
          img.src = '/designer/tileset?path=' + encodeURIComponent(fullPath);
          tilesetImages[idx][spriteIdx] = img;
        });

      } else {
        // Standard spritesheet
        var img = new Image();
        img.crossOrigin = 'anonymous';
        tilesetImages[idx] = img;
        tilesetReady[idx] = false;

        img.onload = function() {
          tilesetReady[idx] = true;
          onTilesetReady();
        };
        img.onerror = function() {
          tilesetReady[idx] = false;
          loadedTilesets++;
          console.error('Failed to load tileset:', ts.name);
        };
        img.src = '/designer/tileset?path=' + encodeURIComponent(ts.image_path);
      }
    })(i);
  }

  if (tilesetConfigs.length === 0) {
    document.getElementById('palette-info').textContent = 'No tilesets loaded';
  }
}
```

**Step 2: Update getFirstGid**

Replace `getFirstGid()` (lines 248–260) with:

```javascript
function getFirstGid(tsIdx) {
  var gid = 1;
  for (var i = 0; i < tsIdx; i++) {
    if (!tilesetReady[i]) continue;
    var ts = tilesetConfigs[i];
    if (ts.type === 'sprite-collection') {
      gid += (ts.sprites || []).length;
    } else {
      var img = tilesetImages[i];
      var margin = ts.margin || 0;
      var spacing = ts.spacing || 0;
      var cols = Math.floor((img.width - margin + spacing) / (ts.tile_width + spacing));
      var rows = Math.floor((img.height - margin + spacing) / (ts.tile_height + spacing));
      gid += cols * rows;
    }
  }
  return gid;
}
```

**Step 3: Update getTileInfo**

Replace `getTileInfo()` (lines 332–363) with:

```javascript
function getTileInfo(globalId) {
  if (globalId <= 0) return null;

  var gid = 1;
  for (var i = 0; i < tilesetConfigs.length; i++) {
    if (!tilesetReady[i]) continue;
    var ts = tilesetConfigs[i];

    if (ts.type === 'sprite-collection') {
      var sprites = ts.sprites || [];
      var count = sprites.length;
      if (globalId >= gid && globalId < gid + count) {
        var localIdx = globalId - gid;
        var img = tilesetImages[i][localIdx];
        if (!img || !img.naturalWidth) return null;
        return {
          tsIdx: i, tsName: ts.name, localIdx: localIdx,
          img: img, sx: 0, sy: 0,
          tw: img.naturalWidth, th: img.naturalHeight,
          cols: 1, rows: 1,
          isCollection: true
        };
      }
      gid += count;
    } else {
      var img = tilesetImages[i];
      var margin = ts.margin || 0;
      var spacing = ts.spacing || 0;
      var cols = Math.floor((img.width - margin + spacing) / (ts.tile_width + spacing));
      var rows = Math.floor((img.height - margin + spacing) / (ts.tile_height + spacing));
      var count = cols * rows;
      if (globalId >= gid && globalId < gid + count) {
        var localIdx = globalId - gid;
        var cr = tileColRow(localIdx, cols);
        var pos = tileSourceXY(cr.col, cr.row, ts.tile_width, ts.tile_height, margin, spacing);
        return {
          tsIdx: i, tsName: ts.name, localIdx: localIdx,
          img: img, sx: pos.sx, sy: pos.sy,
          tw: ts.tile_width, th: ts.tile_height,
          cols: cols, rows: rows,
          isCollection: false
        };
      }
      gid += count;
    }
  }
  return null;
}
```

**Step 4: Verify**

In the console, after loading a sprite-collection tileset:

```javascript
tilesetConfigs[0].type  // "sprite-collection"
tilesetImages[0].length // number of sprites
getTileInfo(1)          // returns {img, sx:0, sy:0, tw: <naturalWidth>, isCollection: true}
```

**Step 5: Commit**

```bash
git add scripts/ui/scene-designer.js
git commit -m "feat: sprite-collection tileset loading and tile lookup"
```

---

### Task 9: Sprite-collection palette UI

**Files:**
- Modify: `scripts/ui/scene-designer.js`
- Modify: `scripts/ui/scene-designer.css`

**Step 1: Update buildPaletteGrid for sprite-collections**

In `buildPaletteGrid()` (lines 186–246), add a branch at the top after the guard:

```javascript
function buildPaletteGrid(tsIdx) {
  var container = document.getElementById('palette-grid');
  container.innerHTML = '';

  if (!tilesetReady[tsIdx]) return;

  var ts = tilesetConfigs[tsIdx];

  // ---- Sprite-collection: one canvas per sprite ----
  if (ts.type === 'sprite-collection') {
    var sprites = ts.sprites || [];
    var images = tilesetImages[tsIdx] || [];
    var thumbSize = 48 * palZoom;
    container.style.gridTemplateColumns = 'repeat(auto-fill, ' + thumbSize + 'px)';
    document.getElementById('palette-panel').style.width = '';

    var firstgid = getFirstGid(tsIdx);

    sprites.forEach(function(spriteName, spriteIdx) {
      var img = images[spriteIdx];
      if (!img) return;

      var globalId = firstgid + spriteIdx;

      var canvas = document.createElement('canvas');
      canvas.width = thumbSize;
      canvas.height = thumbSize;
      canvas.className = 'palette-tile' + (globalId === activeTile ? ' selected' : '');
      canvas.dataset.tsIdx = tsIdx;
      canvas.dataset.tileIdx = spriteIdx;
      canvas.dataset.globalId = globalId;
      canvas.title = spriteName;

      var ctx = canvas.getContext('2d');
      ctx.imageSmoothingEnabled = true;
      // Fit image into square thumbnail with padding
      var pad = 4;
      var maxSide = thumbSize - pad * 2;
      var scale = Math.min(maxSide / img.naturalWidth, maxSide / img.naturalHeight);
      var dw = img.naturalWidth * scale;
      var dh = img.naturalHeight * scale;
      var dx = (thumbSize - dw) / 2;
      var dy = (thumbSize - dh) / 2;
      ctx.drawImage(img, 0, 0, img.naturalWidth, img.naturalHeight, dx, dy, dw, dh);

      canvas.addEventListener('click', function() {
        selectTile(parseInt(this.dataset.globalId), parseInt(this.dataset.tsIdx));
      });

      container.appendChild(canvas);
    });
    return;
  }

  // ---- Standard spritesheet (existing code unchanged) ----
  var img = tilesetImages[tsIdx];
  var tw = ts.tile_width;
  // ... (rest of existing buildPaletteGrid code unchanged)
```

**Step 2: Update renderRecentTiles for sprite-collections**

`renderRecentTiles` uses `getTileInfo` which now returns `isCollection: true` for sprite tiles. The existing `drawImage` call uses `info.sx, info.sy, info.tw, info.th` — this already works because `sx=0, sy=0, tw=imgW, th=imgH`. No change needed.

**Step 3: Add CSS for collection palette tiles**

In `scripts/ui/scene-designer.css`, add:

```css
.palette-tile {
  image-rendering: pixelated;
}
```

(If this rule already exists elsewhere, skip it.)

**Step 4: Verify manually**

Load a sprite-collection tileset (via the folder loader in Task 11). The palette panel should show a grid of square thumbnails, one per sprite. Clicking a thumbnail selects it. Painting in iso mode places that sprite on the canvas.

**Step 5: Commit**

```bash
git add scripts/ui/scene-designer.js scripts/ui/scene-designer.css
git commit -m "feat: sprite-collection palette thumbnail grid"
```

---

### Task 10: Folder picker in asset-picker.js

Add `window.openFolderPicker(callback)` to the shared picker. Shows directory names inferred from `/api/assets/list` paths instead of image thumbnails. Reuses the same modal overlay.

**Files:**
- Modify: `scripts/ui/asset-picker.js`
- Modify: `scripts/ui/asset-picker.css`

**Step 1: Add openFolderPicker to asset-picker.js**

At the end of the IIFE, after `window.openAssetPicker = function(...)`, add:

```javascript
window.openFolderPicker = function(callback) {
  if (_el) close();
  _callback = null; // not used for folders
  var folderCallback = callback;

  // Build a simple folder picker overlay (reuses same CSS classes)
  var overlay = document.createElement('div');
  overlay.id = 'asset-picker-overlay';

  var modal = document.createElement('div');
  modal.id = 'ap-modal';
  modal.addEventListener('click', function(e) { e.stopPropagation(); });

  var header = document.createElement('div');
  header.id = 'ap-header';
  var title = document.createElement('h2');
  title.textContent = 'Load Folder as Tileset';
  var closeBtn = document.createElement('button');
  closeBtn.id = 'ap-close';
  closeBtn.textContent = '✕';
  closeBtn.addEventListener('click', function() {
    overlay.remove();
    document.removeEventListener('keydown', folderKeyHandler);
  });
  header.appendChild(title);
  header.appendChild(closeBtn);

  var filterRow = document.createElement('div');
  filterRow.id = 'ap-filter-row';
  var filterInput = document.createElement('input');
  filterInput.id = 'ap-filter';
  filterInput.type = 'text';
  filterInput.placeholder = 'Filter folders…';
  filterInput.autocomplete = 'off';
  filterRow.appendChild(filterInput);

  var list = document.createElement('div');
  list.id = 'ap-folder-list';
  list.innerHTML = '<div id="ap-empty">Loading…</div>';

  modal.appendChild(header);
  modal.appendChild(filterRow);
  modal.appendChild(list);
  overlay.appendChild(modal);
  overlay.addEventListener('click', function() {
    overlay.remove();
    document.removeEventListener('keydown', folderKeyHandler);
  });
  document.body.appendChild(overlay);
  filterInput.focus();

  var allFolders = [];

  function renderFolderList(query) {
    var items = query
      ? allFolders.filter(function(f) { return f.toLowerCase().indexOf(query.toLowerCase()) !== -1; })
      : allFolders.slice();

    list.innerHTML = '';
    if (items.length === 0) {
      list.innerHTML = '<div id="ap-empty">No folders found</div>';
      return;
    }
    items.forEach(function(folderPath) {
      var row = document.createElement('div');
      row.className = 'ap-folder-row';
      row.textContent = folderPath;
      row.title = folderPath;
      row.addEventListener('click', function() {
        overlay.remove();
        document.removeEventListener('keydown', folderKeyHandler);
        folderCallback(folderPath);
      });
      list.appendChild(row);
    });
  }

  filterInput.addEventListener('input', function() {
    renderFolderList(this.value.trim());
  });

  function folderKeyHandler(e) {
    if (e.key === 'Escape') {
      overlay.remove();
      document.removeEventListener('keydown', folderKeyHandler);
    }
  }
  document.addEventListener('keydown', folderKeyHandler);

  fetch('/api/assets/list')
    .then(function(r) { return r.json(); })
    .then(function(paths) {
      // Extract unique parent directories from all image paths
      var folderSet = {};
      paths.forEach(function(p) {
        var norm = p.replace(/\\/g, '/');
        var lastSlash = norm.lastIndexOf('/');
        if (lastSlash > 0) {
          var dir = norm.substring(0, lastSlash);
          folderSet[dir] = true;
        }
      });
      allFolders = Object.keys(folderSet).sort();
      renderFolderList(filterInput.value.trim());
    })
    .catch(function() {
      list.innerHTML = '<div id="ap-empty">Failed to load asset list</div>';
    });
};
```

**Step 2: Add folder list CSS**

In `scripts/ui/asset-picker.css`, add:

```css
#ap-folder-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px 0;
  min-height: 0;
}

.ap-folder-row {
  padding: 8px 20px;
  cursor: pointer;
  font-size: 13px;
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.ap-folder-row:hover {
  background: var(--surface-hover);
  color: var(--accent);
}
```

**Step 3: Verify manually**

Call `openFolderPicker(function(path) { console.log(path); })` in the browser console. A modal appears with a filterable list of all directories containing images. Clicking a directory logs the path and closes the modal.

**Step 4: Commit**

```bash
git add scripts/ui/asset-picker.js scripts/ui/asset-picker.css
git commit -m "feat: openFolderPicker modal for sprite-collection folder selection"
```

---

### Task 11: addFolderAsTileset + Load Folder button

**Files:**
- Modify: `scripts/ui/scene-designer.js`
- Modify: `skills/scene-designer/assets/scene-designer.html`

**Step 1: Add addFolderAsTileset function**

In `scene-designer.js`, after `addTilesetFromPath()` (around line 164), add:

```javascript
function addFolderAsTileset(folderPath) {
  var normalized = folderPath.replace(/\\/g, '/');

  fetch('/api/assets/list')
    .then(function(r) { return r.json(); })
    .then(function(allPaths) {
      // Find all images directly inside this folder (not in subfolders)
      var prefix = normalized + '/';
      var sprites = allPaths
        .filter(function(p) {
          var norm = p.replace(/\\/g, '/');
          return norm.startsWith(prefix) && norm.indexOf('/', prefix.length) === -1;
        })
        .map(function(p) {
          return p.replace(/\\/g, '/').substring(prefix.length);
        });

      if (sprites.length === 0) {
        console.warn('No images found in folder:', normalized);
        return;
      }

      var parts = normalized.split('/');
      var name = parts[parts.length - 1];

      var idx = tilesetConfigs.length;
      tilesetConfigs.push({
        type: 'sprite-collection',
        name: name,
        folder_path: normalized,
        sprites: sprites
      });

      tilesetImages[idx] = [];
      tilesetReady[idx] = false;

      var loadedCount = 0;
      sprites.forEach(function(spriteName, spriteIdx) {
        var img = new Image();
        img.crossOrigin = 'anonymous';
        var fullPath = normalized + '/' + spriteName;
        img.onload = function() {
          loadedCount++;
          if (loadedCount === sprites.length) {
            tilesetReady[idx] = true;
            document.getElementById('palette-info').textContent =
              tilesetConfigs.length + ' tileset(s) loaded';
            buildPaletteGrid(idx);
            renderScene();
          }
        };
        img.onerror = function() {
          loadedCount++;
          console.error('Failed to load:', fullPath);
          if (loadedCount === sprites.length && !tilesetReady[idx]) {
            tilesetReady[idx] = true;
            buildPaletteGrid(idx);
          }
        };
        img.src = '/designer/tileset?path=' + encodeURIComponent(fullPath);
        tilesetImages[idx][spriteIdx] = img;
      });

      activeTilesetIndex = idx;
      buildTilesetTabs();
    })
    .catch(function(err) {
      console.error('addFolderAsTileset failed:', err);
    });
}
```

**Step 2: Add Load Folder button to HTML**

In `scene-designer.html`, find the `#discover-sheets-bar` div (line 29–31):

```html
<div id="discover-sheets-bar">
  <button class="btn btn-outline" onclick="openAssetPicker(addTilesetFromPath)">+ Discover Sheets</button>
</div>
```

Replace with:

```html
<div id="discover-sheets-bar">
  <button class="btn btn-outline" onclick="openAssetPicker(addTilesetFromPath)">+ Discover Sheets</button>
  <button class="btn btn-outline" onclick="openFolderPicker(addFolderAsTileset)">+ Load Folder</button>
</div>
```

**Step 3: Verify manually**

Click "Load Folder". Select `assets/images/tilesets/isometric-tower-defence/Isometric Tower defence pack/Sprites/Enviroument tiles`. A new tileset tab appears named "Enviroument tiles" with thumbnails for ground, ground(1), water, trees, stones. Selecting a tile and painting in iso mode places it on the canvas.

**Step 4: Commit**

```bash
git add scripts/ui/scene-designer.js skills/scene-designer/assets/scene-designer.html
git commit -m "feat: addFolderAsTileset and Load Folder button"
```

---

### Task 12: Sprite-collection Tiled export

**Files:**
- Modify: `scripts/routes/scene_designer.py`

**Step 1: Update handle_designer_export tilesets section**

In `handle_designer_export`, replace the tileset loop (lines 116–130) with:

```python
tiled_tilesets = []
gid = 1
for ts in tilesets:
    if ts.get("type") == "sprite-collection":
        sprites = ts.get("sprites", [])
        folder = ts.get("folder_path", "").replace("\\", "/")
        tile_entries = []
        for tile_id, sprite_name in enumerate(sprites):
            tile_entries.append({
                "id": tile_id,
                "image": folder + "/" + sprite_name,
            })
        tiled_tilesets.append({
            "firstgid": gid,
            "name": ts.get("name", "tileset"),
            "type": "tileset",
            "tiles": tile_entries,
        })
        gid += len(sprites)
    else:
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
```

**Step 2: Verify with curl**

```bash
# Submit a scene with a sprite-collection tileset
curl -s -X POST http://localhost:8483/api/designer/submit \
  -H "Content-Type: application/json" \
  -d "{\"grid\":{\"width\":20,\"height\":15},\"tile_size\":{\"width\":64,\"height\":32},\"orientation\":\"isometric\",\"tilesets\":[{\"type\":\"sprite-collection\",\"name\":\"ground\",\"folder_path\":\"assets/images/tilesets/isometric-tower-defence/Isometric Tower defence pack/Sprites/Enviroument tiles\",\"sprites\":[\"ground.png\",\"water.png\"]}],\"layers\":[],\"zones\":[]}"

curl -s http://localhost:8483/api/designer/export | python -m json.tool
```

Expected: tilesets array contains an entry with `"tiles": [{"id": 0, "image": "assets/.../ground.png"}, ...]` and no top-level `"image"` key.

**Step 3: Commit**

```bash
git add scripts/routes/scene_designer.py
git commit -m "feat: sprite-collection Tiled image-collection export format"
```

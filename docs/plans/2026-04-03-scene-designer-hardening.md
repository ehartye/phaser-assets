# Scene Designer Hardening Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use h-superpowers:subagent-driven-development, h-superpowers:team-driven-development, or h-superpowers:executing-plans to implement this plan (ask user which approach).

**Goal:** Fix 10 findings from the perspective review — security fixes, data corruption bugs, architecture improvements, and client-side Tiled export.

**Architecture:** Bottom-up approach: fix data integrity and security issues first (Tasks 1-3), then collapse duplicated code enabled by those fixes (Task 4), then refactor coordinate transforms (Task 5), add safety limits (Task 6), extract architecture patterns (Tasks 7-9), and finally build client-side export (Task 10).

**Tech Stack:** Vanilla JS (var-style, no modules/bundler), Python 3 (Flask-like custom HTTP server), HTML templates with server-injected JSON.

---

## Task 1: Make Tileset Configs Immutable

**Finding:** `syncToActiveLayer` and `_applyLayerTileSize` overwrite every tileset config's `tile_width`/`tile_height` to match the active layer. Since `sendToClaude()` serializes `tilesetConfigs` directly, exports contain wrong tile dimensions.

**Files:**
- Modify: `scripts/ui/scene-designer.js:1345-1383` (`syncToActiveLayer`)
- Modify: `scripts/ui/scene-designer.js:1545-1579` (`_applyLayerTileSize`)
- Modify: `scripts/ui/scene-designer.js:1609-1644` (`sendToClaude`)

**Step 1: Remove tileset config mutation from `syncToActiveLayer`**

Delete lines 1359-1362 (the loop that overwrites all tileset configs):

```js
// REMOVE these lines from syncToActiveLayer:
//    for (var i = 0; i < tilesetConfigs.length; i++) {
//      tilesetConfigs[i].tile_width = size;
//      tilesetConfigs[i].tile_height = size;
//    }
```

The function should become:

```js
function syncToActiveLayer() {
  var layer = layers[activeLayerIndex];
  if (!layer || layer.type !== 'tilelayer') return;

  var size = _layerTileSize(layer);
  var oldSize = tileSize.width;
  var sizeChanged = size !== oldSize;

  if (sizeChanged) {
    recentTilesBySize[oldSize] = recentTiles;
    activeTileBySize[oldSize] = activeTile;

    tileSize.width = size;
    tileSize.height = _isoTileHeight(size);

    recentTiles = recentTilesBySize[size] || {};
    activeTile = activeTileBySize[size] || 0;
  }

  // Always sync grid to active layer's dimensions
  grid.width = _layerGridCols(layer);
  grid.height = _layerGridRows(layer);

  document.querySelectorAll('.tile-size-btn').forEach(function(btn) {
    btn.classList.toggle('active', parseInt(btn.textContent) === size);
  });
  updateGridTileInfo();

  if (sizeChanged) {
    loadTilesets();
    renderRecentTiles();
  }
  resizeCanvases();
  renderScene();
}
```

**Step 2: Remove tileset config mutation from `_applyLayerTileSize`**

Delete lines 1556-1559 (same pattern). The function becomes:

```js
function _applyLayerTileSize(layerIdx, size) {
  var layer = layers[layerIdx];
  var oldSize = _layerTileSize(layer);
  recentTilesBySize[oldSize] = recentTiles;
  activeTileBySize[oldSize] = activeTile;

  layer.tileSize = size;

  // Update active tile size to match active layer
  tileSize.width = size;
  tileSize.height = _isoTileHeight(size);

  recentTiles = recentTilesBySize[size] || {};
  activeTile = activeTileBySize[size] || 0;

  // Resize this layer's data to new grid dimensions
  _resizeLayerData(layer);

  // Update grid to match active layer (for painting/cursor)
  grid.width = _layerGridCols(layer);
  grid.height = _layerGridRows(layer);

  document.querySelectorAll('.tile-size-btn').forEach(function(btn) {
    btn.classList.toggle('active', parseInt(btn.textContent) === size);
  });
  updateGridTileInfo();
  loadTilesets();
  renderRecentTiles();
  resizeCanvases();
  renderScene();
}
```

**Step 3: Update rendering to pass layer tile size explicitly**

The orthogonal rendering path (line 718) already uses `getTileInfoAt(gid, lts)` which accepts an override size. The isometric path (line 692) uses `getTileInfo(gid)` which reads from the (now-immutable) tileset config — this is correct for isometric because sprite-collection tiles use their natural size, and spritesheet tiles should use their native tile dimensions for isometric rendering.

However, if we want orthogonal rendering to use the layer's tile size for spritesheets, we need to ensure `getTileInfoAt` handles this properly. Currently it does — it uses `ts_size` for spritesheets and natural dimensions for sprite-collections.

**Step 4: Verify `sendToClaude` serializes original configs**

`sendToClaude()` at line 1615 already sends `tilesets: tilesetConfigs`. With the mutation removed, this will now correctly serialize the original tile dimensions. No change needed here.

**Step 5: Test manually**

1. Load a spritesheet tileset at 16px
2. Add a second layer, set it to 32px tile size
3. Switch between layers — verify palette re-renders correctly
4. Click "Send to Claude" — verify the payload (in Network tab) shows original tileset tile_width/tile_height values, not the active layer's size
5. Verify rendering is correct on both layers

**Step 6: Commit**

```bash
git add scripts/ui/scene-designer.js
git commit -m "fix: stop mutating tilesetConfigs in syncToActiveLayer and _applyLayerTileSize

Tileset configs are now immutable source-of-truth. Layer tile size is
passed explicitly to rendering functions. Fixes silent data corruption
in exports when layers have different tile sizes."
```

---

## Task 2: Fix XSS in Template JSON Injection

**Finding:** `json.dumps()` does not escape `</script>` sequences. User-controlled data (filenames, folder paths) injected into `<script>` blocks can break out of JSON and execute arbitrary JS. Same pattern exists in both scene_designer.py and inspector.py.

**Files:**
- Modify: `scripts/server.py:162-168` (add `safe_json_for_html` helper)
- Modify: `scripts/routes/scene_designer.py:61-66`
- Modify: `scripts/routes/inspector.py:61-68`

**Step 1: Add a safe JSON escaping helper to server.py**

Add this after the `read_body` method (around line 169):

```python
@staticmethod
def safe_json_for_html(data):
    """JSON-encode data, escaping sequences that break <script> blocks."""
    return json.dumps(data).replace("</", "<\\/")
```

**Step 2: Update scene_designer.py to use the helper**

Replace lines 61-66:

```python
html = html.replace("__GRID_CONFIG_PLACEHOLDER__", self.safe_json_for_html(session.designer.get("grid", {})))
html = html.replace("__TILE_SIZE_PLACEHOLDER__", self.safe_json_for_html(session.designer.get("tile_size", {})))
html = html.replace("__TILESETS_PLACEHOLDER__", self.safe_json_for_html(session.designer.get("tilesets", [])))
html = html.replace("__LAYERS_PLACEHOLDER__", self.safe_json_for_html(session.designer.get("layers", [])))
html = html.replace("__ZONES_PLACEHOLDER__", self.safe_json_for_html(session.designer.get("zones", [])))
html = html.replace("__ORIENTATION_PLACEHOLDER__", self.safe_json_for_html(session.designer.get("orientation", "orthogonal")))
```

**Step 3: Update inspector.py to use the helper**

Replace lines 61-68:

```python
html = html.replace("__TILE_CONFIG_PLACEHOLDER__", self.safe_json_for_html({
    "tile_width": first.get("tile_width", 32),
    "tile_height": first.get("tile_height", 32),
    "margin": first.get("margin", 0),
    "spacing": first.get("spacing", 0),
}))
html = html.replace('"__IMAGE_PATH_PLACEHOLDER__"', self.safe_json_for_html(first.get("image_path", "")))
html = html.replace("__SHEETS_PLACEHOLDER__", self.safe_json_for_html(sheets))
```

**Step 4: Test**

Verify the server starts without errors. Load both `/designer` and `/inspector` — confirm pages render correctly. The JSON values should now have `<\/script>` instead of `</script>` if any such string appears in data.

**Step 5: Commit**

```bash
git add scripts/server.py scripts/routes/scene_designer.py scripts/routes/inspector.py
git commit -m "fix: escape </script> in JSON template injection to prevent XSS

Adds safe_json_for_html() helper that escapes </ sequences in JSON
output injected into HTML script blocks. Applied to both scene designer
and inspector template rendering."
```

---

## Task 3: Add read_body Size Limit

**Finding:** `read_body` reads the full request body with no upper bound on `Content-Length`, allowing memory exhaustion.

**Files:**
- Modify: `scripts/server.py:162-168`

**Step 1: Add size limit to read_body**

Replace the method:

```python
MAX_BODY_SIZE = 50 * 1024 * 1024  # 50 MB

def read_body(self):
    """Read and parse JSON from the request body."""
    length = int(self.headers.get("Content-Length", 0))
    if length > self.MAX_BODY_SIZE:
        self.send_json({"error": "request body too large"}, 413)
        return {}
    raw = self.rfile.read(length)
    if not raw:
        return {}
    return json.loads(raw)
```

Add `MAX_BODY_SIZE` as a class attribute on `AssetHandler` (around line 155).

**Step 2: Test**

Start the server, submit a normal scene — verify it works. The 50MB limit is generous enough for any reasonable scene data.

**Step 3: Commit**

```bash
git add scripts/server.py
git commit -m "fix: add 50MB size limit to read_body to prevent memory exhaustion"
```

---

## Task 4: Merge getTileInfo and getTileInfoAt

**Finding:** These two functions (lines 511-608) are ~90% identical. The only difference: `getTileInfo` reads `ts.tile_width`/`ts.tile_height` from the tileset config, while `getTileInfoAt` uses a passed-in `ts_size`. Now that tileset configs are immutable (Task 1), we can merge them with an optional override parameter.

**Files:**
- Modify: `scripts/ui/scene-designer.js:510-608`
- Modify: `scripts/ui/scene-designer.js:478` (caller in `renderRecentTiles`)
- Modify: `scripts/ui/scene-designer.js:692` (caller in isometric rendering)
- Modify: `scripts/ui/scene-designer.js:718` (caller in orthogonal rendering)

**Step 1: Replace both functions with a single merged function**

Delete lines 510-608 and replace with:

```js
// ====== Tile Info Lookup ======
function getTileInfo(globalId, overrideTileSize) {
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
      var tw = overrideTileSize || ts.tile_width;
      var th = overrideTileSize || ts.tile_height;
      var cols = Math.floor((img.width - margin + spacing) / (tw + spacing));
      var rows = Math.floor((img.height - margin + spacing) / (th + spacing));
      var count = cols * rows;
      if (globalId >= gid && globalId < gid + count) {
        var localIdx = globalId - gid;
        var cr = tileColRow(localIdx, cols);
        var pos = tileSourceXY(cr.col, cr.row, tw, th, margin, spacing);
        return {
          tsIdx: i, tsName: ts.name, localIdx: localIdx,
          img: img, sx: pos.sx, sy: pos.sy,
          tw: tw, th: th,
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

**Step 2: Update callers**

- `renderRecentTiles` (line 478): `getTileInfo(gid)` — no change needed (no override).
- Isometric rendering (line 692): `getTileInfo(gid)` — no change needed (uses native size).
- Orthogonal rendering (line 718): change `getTileInfoAt(gid, lts)` to `getTileInfo(gid, lts)`.

```js
// Line ~718 in orthogonal rendering loop:
var info = getTileInfo(gid, lts);
```

**Step 3: Test**

Load a scene with both spritesheet and sprite-collection tilesets. Paint tiles in orthogonal mode at different tile sizes per layer. Switch orientation. Verify all tiles render correctly.

**Step 4: Commit**

```bash
git add scripts/ui/scene-designer.js
git commit -m "refactor: merge getTileInfo and getTileInfoAt into single function

Optional overrideTileSize parameter replaces the separate getTileInfoAt.
Sprite-collections always use natural dimensions; spritesheets use
override when provided, native dimensions otherwise."
```

---

## Task 5: Make Coordinate Transforms Pure Functions

**Finding:** `tileToScreen` reads `grid.height` for the isometric origin. `screenToTile` reads `layers[activeLayerIndex]` to get `isoRows`. If these diverge, coordinate transforms are inconsistent. Both functions should be pure.

**Files:**
- Modify: `scripts/ui/scene-designer.js:1405-1434` (the two functions)
- Modify: all callers of `tileToScreen` and `screenToTile`

**Step 1: Add `originRows` parameter to both functions**

```js
// tileToScreen: returns the top vertex of the tile diamond in canvas pixels (unzoomed)
function tileToScreen(col, row, tileW, tileH, originRows) {
  if (orientation === 'isometric') {
    var originX = originRows * (tileW / 2);
    return {
      x: originX + (col - row) * (tileW / 2),
      y: (col + row) * (tileH / 2)
    };
  }
  return { x: col * tileW, y: row * tileH };
}

// screenToTile: converts canvas pixel position (unzoomed) to tile col/row
function screenToTile(screenX, screenY, tileW, tileH, originRows) {
  if (orientation === 'isometric') {
    var originX = originRows * (tileW / 2);
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

**Step 2: Update all callers**

Search for all calls to `tileToScreen` and `screenToTile`:

In `renderScene` isometric path (~line 695):
```js
var pos = tileToScreen(c, r, lts, lth, lrows);
```

In `renderGridOverlay` isometric grid lines (~lines 748-760):
```js
var ax = tileToScreen(c, 0, tw, th, rows);
var bx = tileToScreen(c, rows, tw, th, rows);
// ...
var ay = tileToScreen(0, r, tw, th, rows);
var by = tileToScreen(cols, r, tw, th, rows);
```

In `renderGridOverlay` bounds (~lines 791-794):
```js
var topCorner    = tileToScreen(0, 0, tw, th, rows);
var rightCorner  = tileToScreen(grid.width, 0, tw, th, rows);
var bottomCorner = tileToScreen(grid.width, grid.height, tw, th, rows);
var leftCorner   = tileToScreen(0, grid.height, tw, th, rows);
```

In `getCanvasPos` (~line 971):
```js
var pos = screenToTile(x, y, tw, th, rows);
```

**Step 3: Test**

Paint tiles in isometric mode. Switch layers with different tile sizes. Verify cursor position matches painted tiles. Verify grid overlay aligns with painted tiles.

**Step 4: Commit**

```bash
git add scripts/ui/scene-designer.js
git commit -m "refactor: make tileToScreen and screenToTile pure functions

Both functions now accept originRows as an explicit parameter instead of
reading from global grid.height or layers[activeLayerIndex]. Eliminates
inconsistency when these values diverge."
```

---

## Task 6: Add Flood Fill Iteration Limit

**Finding:** Flood fill uses an unbounded loop that can push millions of entries onto the stack, crashing the browser tab.

**Files:**
- Modify: `scripts/ui/scene-designer.js:999-1035`

**Step 1: Add iteration cap**

Replace the `floodFill` function:

```js
function floodFill(startRow, startCol) {
  var layer = layers[activeLayerIndex];
  if (!layer || layer.type !== 'tilelayer') return;

  var cols = _layerGridCols(layer);
  var rows = _layerGridRows(layer);
  var target = layer.data[startRow * cols + startCol];
  var replacement = activeTile;
  if (target === replacement) return;

  var stack = [[startRow, startCol]];
  var visited = {};
  var MAX_FILL = 250000;
  var count = 0;

  while (stack.length > 0) {
    if (count >= MAX_FILL) {
      console.warn('Flood fill hit limit of ' + MAX_FILL + ' tiles');
      break;
    }

    var cell = stack.pop();
    var r = cell[0];
    var c = cell[1];
    var key = r + ',' + c;

    if (visited[key]) continue;
    if (r < 0 || r >= rows || c < 0 || c >= cols) continue;

    var idx = r * cols + c;
    if (layer.data[idx] !== target) continue;

    visited[key] = true;
    layer.data[idx] = replacement;
    count++;

    stack.push([r - 1, c]);
    stack.push([r + 1, c]);
    stack.push([r, c - 1]);
    stack.push([r, c + 1]);
  }

  if (replacement > 0) trackRecentTile(replacement);
  renderScene();
}
```

**Step 2: Commit**

```bash
git add scripts/ui/scene-designer.js
git commit -m "fix: cap flood fill at 250k tiles to prevent browser tab crash"
```

---

## Task 7: Extract Orientation Strategy Pattern

**Finding:** `orientation === 'isometric'` appears 11 times across 6 areas. Adding a new orientation (e.g., hexagonal) would require modifying all 6 areas.

**Files:**
- Create: `scripts/ui/orientation.js`
- Modify: `scripts/ui/scene-designer.js` (replace scattered checks with strategy calls)
- Modify: `skills/scene-designer/assets/scene-designer.html` (add script tag)

**Step 1: Create orientation.js with strategy objects**

```js
/**
 * orientation.js — orientation strategy pattern for scene designer
 * Each strategy provides coordinate transforms, canvas sizing, and grid rendering.
 */

var OrientationStrategies = {
  orthogonal: {
    name: 'orthogonal',

    tileHeight: function(tileWidth) {
      return tileWidth;
    },

    canvasSize: function(cols, rows, tileW, tileH) {
      return { width: cols * tileW, height: rows * tileH };
    },

    tileToScreen: function(col, row, tileW, tileH) {
      return { x: col * tileW, y: row * tileH };
    },

    screenToTile: function(screenX, screenY, tileW, tileH) {
      return {
        col: Math.floor(screenX / tileW),
        row: Math.floor(screenY / tileH)
      };
    },

    renderOrder: function(cols, rows, callback) {
      for (var r = 0; r < rows; r++) {
        for (var c = 0; c < cols; c++) {
          callback(c, r);
        }
      }
    },

    drawGridLines: function(ctx, cols, rows, tileW, tileH, zoom) {
      var canvasW = cols * tileW * zoom;
      var canvasH = rows * tileH * zoom;
      for (var c = 0; c <= cols; c++) {
        var x = c * tileW * zoom + 0.5;
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, canvasH);
        ctx.stroke();
      }
      for (var r = 0; r <= rows; r++) {
        var y = r * tileH * zoom + 0.5;
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(canvasW, y);
        ctx.stroke();
      }
    },

    drawBounds: function(ctx, cols, rows, tileW, tileH, zoom) {
      var bw = cols * tileW * zoom;
      var bh = rows * tileH * zoom;
      ctx.strokeRect(-0.5, -0.5, bw + 1, bh + 1);
    },

    drawTileAt: function(ctx, info, col, row, tileW, tileH, zoom) {
      ctx.drawImage(info.img, info.sx, info.sy, info.tw, info.th,
        col * tileW * zoom, row * tileH * zoom, tileW * zoom, tileH * zoom);
    }
  },

  isometric: {
    name: 'isometric',

    tileHeight: function(tileWidth) {
      return Math.max(1, Math.floor(tileWidth / 2));
    },

    canvasSize: function(cols, rows, tileW, tileH) {
      return {
        width: (cols + rows) * (tileW / 2),
        height: (cols + rows) * (tileH / 2)
      };
    },

    tileToScreen: function(col, row, tileW, tileH, originRows) {
      var originX = (originRows || 0) * (tileW / 2);
      return {
        x: originX + (col - row) * (tileW / 2),
        y: (col + row) * (tileH / 2)
      };
    },

    screenToTile: function(screenX, screenY, tileW, tileH, originRows) {
      var originX = (originRows || 0) * (tileW / 2);
      var dx = screenX - originX;
      return {
        col: Math.floor((dx / (tileW / 2) + screenY / (tileH / 2)) / 2),
        row: Math.floor((screenY / (tileH / 2) - dx / (tileW / 2)) / 2)
      };
    },

    renderOrder: function(cols, rows, callback) {
      for (var sum = 0; sum <= cols + rows - 2; sum++) {
        for (var c = 0; c < cols; c++) {
          var r = sum - c;
          if (r < 0 || r >= rows) continue;
          callback(c, r);
        }
      }
    },

    drawGridLines: function(ctx, cols, rows, tileW, tileH, zoom) {
      var self = this;
      for (var c = 0; c <= cols; c++) {
        ctx.beginPath();
        var a = self.tileToScreen(c, 0, tileW, tileH, rows);
        var b = self.tileToScreen(c, rows, tileW, tileH, rows);
        ctx.moveTo(a.x * zoom + 0.5, a.y * zoom + 0.5);
        ctx.lineTo(b.x * zoom + 0.5, b.y * zoom + 0.5);
        ctx.stroke();
      }
      for (var r = 0; r <= rows; r++) {
        ctx.beginPath();
        var a = self.tileToScreen(0, r, tileW, tileH, rows);
        var b = self.tileToScreen(cols, r, tileW, tileH, rows);
        ctx.moveTo(a.x * zoom + 0.5, a.y * zoom + 0.5);
        ctx.lineTo(b.x * zoom + 0.5, b.y * zoom + 0.5);
        ctx.stroke();
      }
    },

    drawBounds: function(ctx, cols, rows, tileW, tileH, zoom) {
      var self = this;
      var top    = self.tileToScreen(0, 0, tileW, tileH, rows);
      var right  = self.tileToScreen(cols, 0, tileW, tileH, rows);
      var bottom = self.tileToScreen(cols, rows, tileW, tileH, rows);
      var left   = self.tileToScreen(0, rows, tileW, tileH, rows);
      ctx.beginPath();
      ctx.moveTo(top.x * zoom, top.y * zoom);
      ctx.lineTo(right.x * zoom, right.y * zoom);
      ctx.lineTo(bottom.x * zoom, bottom.y * zoom);
      ctx.lineTo(left.x * zoom, left.y * zoom);
      ctx.closePath();
      ctx.stroke();
    },

    drawTileAt: function(ctx, info, col, row, tileW, tileH, zoom, originRows) {
      var pos = this.tileToScreen(col, row, tileW, tileH, originRows);
      var srcW = info.tw, srcH = info.th;
      var destW = tileW * zoom;
      var destH = (srcH / srcW) * tileW * zoom;
      var destX = (pos.x - tileW / 2) * zoom;
      var destY = (pos.y + tileH) * zoom - destH;
      ctx.drawImage(info.img, info.sx, info.sy, srcW, srcH, destX, destY, destW, destH);
    }
  }
};

function getOrientationStrategy() {
  return OrientationStrategies[orientation] || OrientationStrategies.orthogonal;
}
```

**Step 2: Add script tag to HTML**

In `scene-designer.html`, after the `tileset.js` script tag (line 197), add:

```html
<script src="/ui/orientation.js"></script>
```

**Step 3: Replace scattered checks in scene-designer.js**

Replace `_isoTileHeight` (line 1387-1389):

```js
function _isoTileHeight(tw) {
  return getOrientationStrategy().tileHeight(tw);
}
```

Replace the `resizeCanvases` orientation branches (lines 620-638) with strategy calls:

```js
// Inside the layer loop:
var strat = getOrientationStrategy();
var canvasSize = strat.canvasSize(cols, rows, lts, lth);
lpxW = canvasSize.width;
lpxH = canvasSize.height;
```

And the fallback:
```js
var strat = getOrientationStrategy();
var fallback = strat.canvasSize(grid.width, grid.height, tileSize.width, tileSize.height);
maxPxW = fallback.width;
maxPxH = fallback.height;
```

Replace `renderScene` background and tile rendering branches:

```js
// Background
var strat = getOrientationStrategy();
if (orientation === 'isometric') {
  sceneCtx.fillStyle = '#0e1019';
  sceneCtx.fillRect(0, 0, sceneCanvas.width, sceneCanvas.height);
} else {
  // ... existing checkerboard code
}

// Per-layer tile rendering — replace both branches with:
strat.renderOrder(lcols, lrows, function(c, r) {
  var gid = layer.data[r * lcols + c];
  if (gid <= 0) return;
  var info = getTileInfo(gid, orientation === 'isometric' ? undefined : lts);
  if (!info) return;
  strat.drawTileAt(sceneCtx, info, c, r, lts, lth, zoom, lrows);
});
```

Replace `renderGridOverlay` grid and bounds branches with:

```js
var strat = getOrientationStrategy();
if (showGrid) {
  gridCtx.strokeStyle = 'rgba(255, 255, 255, 0.06)';
  gridCtx.lineWidth = 1;
  strat.drawGridLines(gridCtx, grid.width, grid.height, tileSize.width, tileSize.height, zoom);
}

if (showBounds) {
  gridCtx.strokeStyle = 'rgba(80, 140, 255, 0.6)';
  gridCtx.lineWidth = 2;
  strat.drawBounds(gridCtx, grid.width, grid.height, tileSize.width, tileSize.height, zoom);
}
```

Replace `tileToScreen` and `screenToTile` functions with thin wrappers:

```js
function tileToScreen(col, row, tileW, tileH, originRows) {
  return getOrientationStrategy().tileToScreen(col, row, tileW, tileH, originRows);
}

function screenToTile(screenX, screenY, tileW, tileH, originRows) {
  return getOrientationStrategy().screenToTile(screenX, screenY, tileW, tileH, originRows);
}
```

**Step 4: Test**

Toggle between orthogonal and isometric. Paint in both modes. Verify grid overlay, bounds, tile rendering, and mouse input all work identically to before.

**Step 5: Commit**

```bash
git add scripts/ui/orientation.js scripts/ui/scene-designer.js skills/scene-designer/assets/scene-designer.html
git commit -m "refactor: extract orientation strategy pattern into orientation.js

Replaces 11 scattered orientation checks with strategy object methods.
Adding a new orientation (e.g. hexagonal) now requires only adding a
new strategy object."
```

---

## Task 8: Extract Tileset Type Abstraction

**Finding:** `ts.type === 'sprite-collection'` checks are scattered through 5 functions: `loadTilesets`, `buildPaletteGrid`, `getFirstGid`, `getTileInfo`, and the Tiled export. Adding a third tileset type would require modifying all 5.

**Files:**
- Modify: `scripts/ui/tileset.js` (add tileset type helpers)
- Modify: `scripts/ui/scene-designer.js` (use helpers)

**Step 1: Add tileset type helpers to tileset.js**

Append to tileset.js:

```js
/**
 * Get the tile count for a tileset config.
 * Works for both spritesheets and sprite-collections.
 */
function tilesetTileCount(ts, img) {
  if (ts.type === 'sprite-collection') {
    return (ts.sprites || []).length;
  }
  var layout = sheetLayout(img.width, img.height, ts.tile_width, ts.tile_height, ts.margin || 0, ts.spacing || 0);
  return layout.cols * layout.rows;
}

/**
 * Look up a tile within a single tileset by local index.
 * Returns { img, sx, sy, tw, th, cols, rows, isCollection } or null.
 * overrideTileSize: optional tile size override for spritesheets.
 */
function tilesetLookup(ts, tsImages, localIdx, overrideTileSize) {
  if (ts.type === 'sprite-collection') {
    var img = tsImages[localIdx];
    if (!img || !img.naturalWidth) return null;
    return {
      img: img, sx: 0, sy: 0,
      tw: img.naturalWidth, th: img.naturalHeight,
      cols: 1, rows: 1,
      isCollection: true
    };
  }
  var img = tsImages;
  var tw = overrideTileSize || ts.tile_width;
  var th = overrideTileSize || ts.tile_height;
  var margin = ts.margin || 0;
  var spacing = ts.spacing || 0;
  var layout = sheetLayout(img.width, img.height, tw, th, margin, spacing);
  var cr = tileColRow(localIdx, layout.cols);
  var pos = tileSourceXY(cr.col, cr.row, tw, th, margin, spacing);
  return {
    img: img, sx: pos.sx, sy: pos.sy,
    tw: tw, th: th,
    cols: layout.cols, rows: layout.rows,
    isCollection: false
  };
}
```

**Step 2: Simplify getTileInfo using tilesetLookup**

```js
function getTileInfo(globalId, overrideTileSize) {
  if (globalId <= 0) return null;

  var gid = 1;
  for (var i = 0; i < tilesetConfigs.length; i++) {
    if (!tilesetReady[i]) continue;
    var ts = tilesetConfigs[i];
    var count = tilesetTileCount(ts, tilesetImages[i]);
    if (globalId >= gid && globalId < gid + count) {
      var localIdx = globalId - gid;
      var result = tilesetLookup(ts, tilesetImages[i], localIdx, overrideTileSize);
      if (!result) return null;
      result.tsIdx = i;
      result.tsName = ts.name;
      result.localIdx = localIdx;
      return result;
    }
    gid += count;
  }
  return null;
}
```

**Step 3: Simplify getFirstGid using tilesetTileCount**

```js
function getFirstGid(tsIdx) {
  var gid = 1;
  for (var i = 0; i < tsIdx; i++) {
    if (!tilesetReady[i]) continue;
    gid += tilesetTileCount(tilesetConfigs[i], tilesetImages[i]);
  }
  return gid;
}
```

**Step 4: Test**

Load scenes with both spritesheet and sprite-collection tilesets. Verify palette rendering, tile painting, and recent tiles all work.

**Step 5: Commit**

```bash
git add scripts/ui/tileset.js scripts/ui/scene-designer.js
git commit -m "refactor: extract tileset type abstraction into tileset.js helpers

tilesetTileCount() and tilesetLookup() centralize type-specific logic.
getTileInfo and getFirstGid are now type-agnostic. Adding a new tileset
type requires only updating these two helpers."
```

---

## Task 9: Extract Shared Modal Builder in asset-picker.js

**Finding:** `openFolderPicker` (lines 232-338) manually builds its own modal DOM, duplicating overlay/header/filter/close pattern from `buildModal()`.

**Files:**
- Modify: `scripts/ui/asset-picker.js`

**Step 1: Extract buildModalShell helper**

Add this function inside the IIFE (before `buildModal`):

```js
function buildModalShell(title) {
  var overlay = document.createElement('div');
  overlay.id = 'asset-picker-overlay';

  var modal = document.createElement('div');
  modal.id = 'ap-modal';
  modal.addEventListener('click', function(e) { e.stopPropagation(); });

  var header = document.createElement('div');
  header.id = 'ap-header';
  var titleEl = document.createElement('h2');
  titleEl.textContent = title;
  var closeBtn = document.createElement('button');
  closeBtn.id = 'ap-close';
  closeBtn.textContent = '\u2715';
  header.appendChild(titleEl);
  header.appendChild(closeBtn);

  var filterRow = document.createElement('div');
  filterRow.id = 'ap-filter-row';
  var filterInput = document.createElement('input');
  filterInput.id = 'ap-filter';
  filterInput.type = 'text';
  filterInput.autocomplete = 'off';
  filterRow.appendChild(filterInput);

  modal.appendChild(header);
  modal.appendChild(filterRow);
  overlay.appendChild(modal);

  // Click backdrop to close
  var closeOverlay = function() {
    overlay.remove();
    document.removeEventListener('keydown', escHandler);
  };
  overlay.addEventListener('click', closeOverlay);
  closeBtn.addEventListener('click', closeOverlay);

  var escHandler = function(e) {
    if (e.key === 'Escape') closeOverlay();
  };
  document.addEventListener('keydown', escHandler);

  return {
    overlay: overlay,
    modal: modal,
    filterInput: filterInput,
    close: closeOverlay
  };
}
```

**Step 2: Rewrite buildModal to use buildModalShell**

```js
function buildModal() {
  var shell = buildModalShell('Discover Sheets');
  shell.filterInput.placeholder = 'Filter by filename\u2026';
  shell.filterInput.addEventListener('input', function() { applyFilter(this.value.trim()); });

  // Remove the default escape handler (we have our own onKey)
  // Re-bind close to our module-level close function
  shell.overlay.removeEventListener('click', shell.close);
  shell.overlay.addEventListener('click', close);
  shell.modal.querySelector('#ap-close').removeEventListener('click', shell.close);
  shell.modal.querySelector('#ap-close').addEventListener('click', close);

  var grid = document.createElement('div');
  grid.id = 'ap-grid';

  var pagination = document.createElement('div');
  pagination.id = 'ap-pagination';
  var prevBtn = document.createElement('button');
  prevBtn.id = 'ap-prev';
  prevBtn.className = 'btn btn-outline';
  prevBtn.textContent = '\u2190 Prev';
  prevBtn.addEventListener('click', function() {
    if (_page > 0) { _page--; _highlighted = -1; renderGrid(); }
  });
  var pageInfo = document.createElement('span');
  pageInfo.id = 'ap-page-info';
  var nextBtn = document.createElement('button');
  nextBtn.id = 'ap-next';
  nextBtn.className = 'btn btn-outline';
  nextBtn.textContent = 'Next \u2192';
  nextBtn.addEventListener('click', function() {
    var total = Math.max(1, Math.ceil(_filtered.length / PAGE_SIZE));
    if (_page < total - 1) { _page++; _highlighted = -1; renderGrid(); }
  });
  pagination.appendChild(prevBtn);
  pagination.appendChild(pageInfo);
  pagination.appendChild(nextBtn);

  shell.modal.appendChild(grid);
  shell.modal.appendChild(pagination);

  return shell.overlay;
}
```

**Step 3: Rewrite openFolderPicker to use buildModalShell**

```js
window.openFolderPicker = function(callback) {
  if (_el) close();
  _callback = null;
  var folderCallback = callback;

  var shell = buildModalShell('Load Folder as Tileset');
  shell.filterInput.placeholder = 'Filter folders\u2026';

  var list = document.createElement('div');
  list.id = 'ap-folder-list';
  list.innerHTML = '<div id="ap-empty">Loading\u2026</div>';
  shell.modal.appendChild(list);

  document.body.appendChild(shell.overlay);
  shell.filterInput.focus();

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
        shell.close();
        folderCallback(folderPath);
      });
      list.appendChild(row);
    });
  }

  shell.filterInput.addEventListener('input', function() {
    renderFolderList(this.value.trim());
  });

  fetch('/api/assets/list')
    .then(function(r) { return r.json(); })
    .then(function(paths) {
      var folderSet = {};
      paths.forEach(function(p) {
        var norm = p.replace(/\\/g, '/');
        var lastSlash = norm.lastIndexOf('/');
        if (lastSlash > 0) {
          folderSet[norm.substring(0, lastSlash)] = true;
        }
      });
      allFolders = Object.keys(folderSet).sort();
      renderFolderList(shell.filterInput.value.trim());
    })
    .catch(function() {
      list.innerHTML = '<div id="ap-empty">Failed to load asset list</div>';
    });
};
```

**Step 4: Test**

Click "Discover Sheets" — verify modal opens, filter works, pagination works, close works. Click "Load Folder" — verify modal opens, folders list, filter works, clicking a folder triggers the callback.

**Step 5: Commit**

```bash
git add scripts/ui/asset-picker.js
git commit -m "refactor: extract shared buildModalShell in asset-picker.js

Both openAssetPicker and openFolderPicker now use a shared modal shell
builder for overlay, header, filter input, close/escape handling."
```

---

## Task 10: Client-Side Tiled Export

**Finding:** `exportTiled()` calls `window.open('/api/designer/export')` which requires a prior `sendToClaude()` to populate server session. Users get a confusing 400 error if they export without submitting first. Building the Tiled JSON client-side eliminates this coupling.

**Files:**
- Modify: `scripts/ui/scene-designer.js:1647-1649` (exportTiled function)
- Modify: `scripts/routes/scene_designer.py:86` (add orientation to submit, keep server export as fallback)

**Step 1: Add a `gatherSceneState` helper**

Add before `sendToClaude`:

```js
function gatherSceneState() {
  return {
    grid: { width: grid.width, height: grid.height },
    tile_size: { width: tileSize.width, height: tileSize.height },
    orientation: orientation,
    scene_pixels: { width: scenePixels.width, height: scenePixels.height },
    tilesets: tilesetConfigs.map(function(ts) {
      // Snapshot — never reference the mutable config directly
      var copy = {};
      for (var k in ts) { if (ts.hasOwnProperty(k)) copy[k] = ts[k]; }
      return copy;
    }),
    layers: layers.map(function(l) {
      var out = { name: l.name, type: l.type };
      if (l.type === 'tilelayer') {
        out.data = Array.from(l.data);
        out.tileSize = l.tileSize || tileSize.width;
        out.gridCols = _layerGridCols(l);
        out.gridRows = _layerGridRows(l);
      }
      if (l.type === 'objectgroup') out.objects = l.objects || [];
      return out;
    }),
    zones: zones.slice()
  };
}
```

**Step 2: Rewrite sendToClaude to use gatherSceneState**

```js
function sendToClaude() {
  var payload = gatherSceneState();

  fetch('/api/designer/submit', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  }).then(function(resp) {
    if (resp.ok) {
      document.getElementById('status-banner').classList.add('visible');
      document.getElementById('send-btn').disabled = true;
      document.getElementById('send-btn').textContent = 'Sent!';
    }
  }).catch(function() {
    document.getElementById('send-btn').textContent = 'Error - try again';
  });
}
```

**Step 3: Rewrite exportTiled to build JSON client-side**

```js
function exportTiled() {
  var state = gatherSceneState();
  var ts = state.tile_size;
  var g = state.grid;

  // Build Tiled tileset references
  var tiledTilesets = [];
  var gid = 1;
  for (var i = 0; i < state.tilesets.length; i++) {
    var tileset = state.tilesets[i];
    if (tileset.type === 'sprite-collection') {
      var sprites = tileset.sprites || [];
      var entries = sprites.map(function(name, id) {
        var folder = (tileset.folder_path || '').replace(/\\/g, '/');
        return { id: id, image: folder + '/' + name };
      });
      tiledTilesets.push({
        firstgid: gid, name: tileset.name || 'tileset',
        type: 'tileset', tiles: entries
      });
      gid += sprites.length;
    } else {
      tiledTilesets.push({
        firstgid: gid, name: tileset.name || 'tileset',
        image: tileset.image_path || '',
        tilewidth: tileset.tile_width || ts.width,
        tileheight: tileset.tile_height || ts.height,
        margin: tileset.margin || 0, spacing: tileset.spacing || 0,
        tilecount: tileset.tile_count || 0, columns: tileset.columns || 0
      });
      gid += tileset.tile_count || 256;
    }
  }

  // Build Tiled layers
  var tiledLayers = [];
  for (var i = 0; i < state.layers.length; i++) {
    var layer = state.layers[i];
    if (layer.type === 'objectgroup') {
      tiledLayers.push({
        name: layer.name || 'objects', type: 'objectgroup',
        objects: layer.objects || [],
        opacity: 1, visible: true, x: 0, y: 0
      });
    } else {
      tiledLayers.push({
        name: layer.name || 'layer', type: 'tilelayer',
        data: layer.data || [],
        width: g.width, height: g.height,
        opacity: 1, visible: true, x: 0, y: 0
      });
    }
  }

  // Add zones as object layer
  if (state.zones.length > 0) {
    var zoneObjects = state.zones.map(function(z) {
      return {
        name: z.name || 'zone', type: z.type || 'zone',
        x: z.x || 0, y: z.y || 0,
        width: z.width || ts.width, height: z.height || ts.height,
        visible: true
      };
    });
    tiledLayers.push({
      name: 'Zones', type: 'objectgroup',
      objects: zoneObjects,
      opacity: 1, visible: true, x: 0, y: 0
    });
  }

  var orient = state.orientation || 'orthogonal';
  if (orient !== 'orthogonal' && orient !== 'isometric') {
    orient = 'orthogonal';
  }

  var tiledMap = {
    version: '1.10', tiledversion: '1.10.0',
    orientation: orient, renderorder: 'right-down',
    width: g.width, height: g.height,
    tilewidth: ts.width, tileheight: ts.height,
    infinite: false,
    layers: tiledLayers, tilesets: tiledTilesets,
    type: 'map'
  };

  // Download as file
  var blob = new Blob([JSON.stringify(tiledMap, null, 2)], { type: 'application/json' });
  var url = URL.createObjectURL(blob);
  var a = document.createElement('a');
  a.href = url;
  a.download = 'scene.json';
  a.click();
  URL.revokeObjectURL(url);
}
```

**Step 4: Add orientation validation to server-side export (keep as fallback)**

In `scene_designer.py`, line 194, validate the orientation:

```python
orient = results.get("orientation", "orthogonal")
if orient not in ("orthogonal", "isometric"):
    orient = "orthogonal"
```

**Step 5: Test**

1. Paint some tiles and zones
2. Click "Export Tiled JSON" — verify a file downloads without needing to "Send to Claude" first
3. Open the downloaded JSON — verify structure matches Tiled format
4. Click "Send to Claude" then try server-side export at `/api/designer/export` — verify it still works as fallback

**Step 6: Commit**

```bash
git add scripts/ui/scene-designer.js scripts/routes/scene_designer.py
git commit -m "feat: client-side Tiled JSON export with gatherSceneState helper

Export no longer requires prior submit. gatherSceneState() is shared
between sendToClaude and exportTiled. Server-side export remains as
fallback. Orientation field validated to whitelist."
```

---

## Dependency Graph

```
Task 1 (immutable configs) ─┬─> Task 4 (merge getTileInfo)
                             │
Task 2 (XSS fix)            │   (independent)
Task 3 (body size limit)    │   (independent)
                             │
Task 5 (pure transforms) ───┤
Task 6 (flood fill limit)   │   (independent)
                             │
Task 7 (orientation strategy)┤── depends on Task 5
Task 8 (tileset abstraction) ┤── depends on Task 4
Task 9 (modal builder)       │   (independent)
Task 10 (client export) ─────┘── depends on Task 1
```

**Parallelizable groups:**
- Group A: Tasks 1, 2, 3, 6, 9 (all independent)
- Group B: Tasks 4, 5 (depend on Task 1)
- Group C: Tasks 7, 8, 10 (depend on Group B)

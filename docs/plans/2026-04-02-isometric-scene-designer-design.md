# Isometric Scene Designer Design

**Date:** 2026-04-02
**Status:** Approved

## Summary

Add isometric mode to the scene designer and support sprite-collection tilesets (individual PNG files as tiles). Uses Option A: mode-aware coordinate transforms — two small transform functions replace direct tile math everywhere, leaving the data model, layer system, zones, and export pipeline unchanged.

## Scene Config & Orientation Toggle

A single `orientation` field is added to the scene config: `"orthogonal"` (default) or `"isometric"`. Stored alongside `grid`, `tilesets`, and `layers`. Toggled via a two-button control in the scene settings panel. Switching orientation clears tile data (with a confirmation prompt) — mixed-mode paint data is not supported.

## Coordinate Transforms

Two functions replace all direct `col * tileW` / `row * tileH` math:

```javascript
// Tile grid → canvas screen position (top-left of tile bounding rect)
tileToScreen(col, row):
  x = originX + (col - row) * tileW / 2
  y = (col + row) * tileH / 2

// Canvas screen position → tile grid (for mouse input)
screenToTile(screenX, screenY):
  col = floor(((screenX - originX) / (tileW/2) + screenY / (tileH/2)) / 2)
  row = floor((screenY / (tileH/2) - (screenX - originX) / (tileW/2)) / 2)
```

`originX = gridRows * tileW / 2` shifts tile `(0,0)` to the top-center so the full diamond map fits without negative x coordinates.

In orthographic mode both functions are trivial pass-throughs (`x = col * tileW`, `y = row * tileH`), so the same code path handles both modes.

**Canvas sizing in isometric mode:** `(cols + rows) * tileW/2` wide by `(cols + rows) * tileH/2` tall — the bounding box of the full diamond map.

**Tall sprites** (image height > tileH) are anchored at the bottom of the diamond by subtracting `(imgH - tileH)` from the draw Y, so towers grow upward from the ground.

## Rendering Pipeline

Two changes to `renderScene()`:

**Back-to-front tile order.** In isometric mode, tiles draw by diagonal band — tiles where `col + row` is smallest first (furthest back), largest last (closest front):

```javascript
for (sum = 0; sum <= cols + rows - 2; sum++)
  for (col = 0; col < cols; col++)
    row = sum - col
    if row in bounds: drawTile(col, row)
```

This is the painter's algorithm that makes tall objects correctly occlude tiles behind them.

**Diamond grid overlay.** Instead of horizontal/vertical lines, two sets of diagonal lines running SW→NE and NW→SE. Same `rgba(255,255,255,0.06)` color as today.

Everything else — layers, zoom, checkerboard background, bounds rect, zone overlay — is unchanged. The transforms handle positioning automatically.

## Sprite-Collection Tilesets

A new tileset type alongside the existing spritesheet type:

```javascript
{
  type: "sprite-collection",
  name: "tower-defence-ground",
  folder_path: "assets/images/tilesets/.../Ground stones",
  sprites: ["ground stone(1).png", "ground stone(2).png", ...]
}
```

**Loading.** A "Load Folder" button in the tileset panel opens the existing asset picker modal in folder mode (shows directories inferred from `/api/assets/list` paths — no new server route). On confirm, all images in the selected folder are fetched and each becomes one tile. GIDs assigned sequentially as today.

**Rendering.** Each sprite loads as one `Image` object. `getTileInfo(globalId)` returns the individual image with `sx=0, sy=0, tw=imgW, th=imgH` — the full image is the tile. No sheet slicing.

**Palette.** Each sprite renders as a thumbnail in the existing scrollable grid. Same click-to-select behavior.

**Tiled export.** Sprite-collection tilesets export as Tiled's image collection format:

```json
{
  "firstgid": 1,
  "name": "tower-defence-ground",
  "tiles": [
    {"id": 0, "image": "ground stone(1).png", "imagewidth": 1202, "imageheight": 1159},
    {"id": 1, "image": "ground stone(2).png", "imagewidth": 1202, "imageheight": 1159}
  ]
}
```

Valid Tiled 1.10 and Phaser-loadable.

## Tiled Export

When orientation is isometric, the export adds:

```json
{
  "orientation": "isometric",
  "renderorder": "right-down",
  "tilewidth": 64,
  "tileheight": 32
}
```

Layer `data` arrays are unchanged — flat GID arrays in row-major order. Tiled's isometric renderer handles diamond projection when it reads `orientation: isometric`. Grid dimensions (`width`, `height`) unchanged.

## UI Changes

| Element | Change |
|---------|--------|
| Scene settings panel | Two-button orientation toggle: Orthographic / Isometric |
| Tile size inputs | Small hint in iso mode: recommended 2:1 width:height ratio (e.g. 64×32) |
| Tileset panel | "Load Folder" button alongside existing "Discover Sheets" |
| Asset picker modal | New folder mode: shows directory names inferred from path list, clicking a folder imports all images as a sprite-collection tileset |

## Files Affected

| File | Change |
|------|--------|
| `scripts/ui/scene-designer.js` | Orientation toggle, transform functions, iso render pipeline, sprite-collection tileset loading |
| `skills/scene-designer/assets/scene-designer.html` | Orientation toggle UI, tile size hint, Load Folder button |
| `scripts/ui/scene-designer.css` | Styles for orientation toggle |
| `scripts/ui/asset-picker.js` | Folder mode for the picker modal |
| `scripts/ui/asset-picker.css` | Folder mode styles (directory items vs image thumbnails) |
| `scripts/routes/scene_designer.py` | Export handler: isometric orientation fields, sprite-collection tileset format |

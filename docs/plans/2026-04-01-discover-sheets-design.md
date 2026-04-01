# Discover Sheets Design

**Date:** 2026-04-01  
**Status:** Approved

## Summary

Add a "Discover Sheets" button to the sprite inspector and scene designer that opens a shared image picker modal. The picker browses all images in the project's assets folder with fuzzy filtering and thumbnail previews. Alongside this, refactor the sprite inspector so each mode (Animation, Layer, Selection) has its own tile size config instead of a single per-sheet config.

## Server API

New route: `GET /api/assets/list`

- Walks `session.project_path` recursively
- Collects all `.png`, `.jpg`, `.jpeg`, `.gif`, `.webp` files
- Returns JSON array of relative paths, forward-slash normalized
- Lives in new `scripts/routes/assets.py` mixin
- Images continue to be served via existing `/inspector/image?path=<encoded>` endpoint

## Shared Picker Module

Two new files served via existing `/ui/*` route:
- `scripts/ui/asset-picker.js`
- `scripts/ui/asset-picker.css`

### Public API

```javascript
openAssetPicker(callback)  // callback(selectedPath: string)
```

### Behavior

- On open: fetches `/api/assets/list`, renders first page
- **Fuzzy filter**: client-side match against filename + full path, scored (consecutive > scattered), filters on keystroke, resets to page 1
- **Pagination**: 16 thumbnails per page (4×4 grid), prev/next buttons, page indicator
- **Thumbnails**: `<img>` loaded via `/inspector/image?path=...`, filename label below, click to select
- **Keyboard**: Escape closes, Enter selects highlighted item
- On select: calls callback with path, closes modal

### Styling

Uses existing `--accent`, `--surface`, `--border`, `--text`, `--text-dim` tokens from `theme.css`. Styles cover: modal backdrop, thumbnail grid, filter input, pagination controls, hover/active states.

## Sprite Inspector Changes

### Per-mode tile config

Each mode panel (Animation, Layer, Selection) gets four number inputs at the top:
- `Tile W`, `Tile H` (default 32)
- `Margin`, `Spacing` (default 0)

`activeCfg()` returns the active mode's config instead of the active sheet's config. Grid redraws when mode switches or any tile config input changes.

Saved items (animations, selections, compositions) record both `sheet` path and the `tile_config` used, so results sent to Claude are fully self-describing.

### Discover Sheets button

Placed in the grid panel header, next to sheet tabs. Calls:
```javascript
openAssetPicker(path => {
  SHEETS.push({ image_path: path, ...activeModeConfig() });
  buildSheetTabs();
  loadSheetImage(SHEETS.length - 1);
});
```

Initial tile config for the new sheet taken from the active mode's current settings.

## Scene Designer Changes

Add a "Discover Sheets" button near existing tileset controls. Calls:
```javascript
openAssetPicker(path => addTileset(path));
```

No changes to per-layer tile sizing — that already works correctly.

## Files Affected

| File | Change |
|------|--------|
| `scripts/routes/assets.py` | New — `/api/assets/list` handler |
| `scripts/server.py` | Register `AssetsRoutes` mixin |
| `scripts/ui/asset-picker.js` | New — shared picker module |
| `scripts/ui/asset-picker.css` | New — picker styles |
| `skills/sprite-inspector/assets/sprite-inspector.html` | Per-mode tile config + Discover Sheets button |
| `skills/scene-designer/assets/scene-designer.html` | Discover Sheets button |
| `scripts/ui/scene-designer.js` | `addTileset(path)` hook for picker callback |

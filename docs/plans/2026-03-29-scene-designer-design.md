# Scene Designer Design

## Problem

After finding assets and mapping sprite sheet animations, there's no visual way to compose them into actual game levels. Users have to describe layouts to Claude verbally, or use external tools like Tiled. A visual scene designer lets Claude set up an initial layout and the user refine it interactively, producing Tiled-compatible JSON that Phaser loads natively.

## Solution

Add a tile-based scene designer to the plugin as a new skill (`phaser-assets:scene-designer`). Claude pre-populates a grid with tiles and zones, the user paints/edits in the browser, and the result is a standard Tiled JSON tilemap. Supports top-down and side-scrolling layouts.

## Server Architecture Refactor

Modularize the existing monolithic `server.py` into core + route modules:

```
scripts/
├── server.py              # Core: HTTPServer, Session, DB, CLI, dispatch
├── routes/
│   ├── __init__.py        # collect_routes() aggregates all modules
│   ├── health.py          # /health, /shutdown
│   ├── asset_finder.py    # /start, /, /api/download, /api/status, /api/results
│   ├── inspector.py       # /inspector, /inspector/image, /api/inspector/*
│   └── scene_designer.py  # /designer, /designer/tileset, /api/designer/*
```

### Mixin Pattern

Each route module defines a mixin class and a ROUTES dict:

```python
# routes/inspector.py
class InspectorRoutes:
    def handle_inspector(self): ...
    def handle_inspector_load(self): ...

ROUTES = {
    "GET": {"/inspector": "handle_inspector"},
    "POST": {"/api/inspector/load": "handle_inspector_load"},
}
```

Core handler inherits all mixins:

```python
class AssetHandler(BaseHandler, InspectorRoutes, AssetFinderRoutes, SceneDesignerRoutes, HealthRoutes):
    ...
```

Routes auto-discovered from each module's ROUTES dict. Shared helpers (`send_json`, `send_html`, `read_body`) stay in core.

## Scene Designer Routes

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/designer/load` | POST | Accept scene config (grid, tiles, layers, tilesets) |
| `/designer` | GET | Serve the scene designer HTML |
| `/designer/tileset` | GET | Serve tileset images (`?path=relative/path.png`) |
| `/api/designer/submit` | POST | Receive final scene data from browser |
| `/api/designer/results` | GET | Claude polls for submitted data |
| `/api/designer/export` | GET | Returns Tiled-compatible JSON |

## Data Model

### Load Payload (Claude sends)

```json
{
  "project_path": "/path/to/game",
  "grid": { "width": 20, "height": 15 },
  "tile_size": { "width": 16, "height": 16 },
  "tilesets": [
    {
      "name": "terrain",
      "image_path": "assets/images/tiles/terrain.png",
      "tile_width": 16, "tile_height": 16,
      "margin": 0, "spacing": 0
    }
  ],
  "layers": [
    {
      "name": "Ground",
      "type": "tilelayer",
      "data": [1, 1, 1, 2, 2, 0, 0, ...]
    },
    {
      "name": "Buildings",
      "type": "tilelayer",
      "data": [0, 0, 0, 0, ...]
    },
    {
      "name": "Collision",
      "type": "objectgroup",
      "objects": [
        { "name": "wall", "x": 0, "y": 224, "width": 320, "height": 16 }
      ]
    }
  ],
  "zones": [
    { "name": "spawn", "x": 32, "y": 192, "width": 16, "height": 16 },
    { "name": "exit", "x": 288, "y": 192, "width": 16, "height": 16 }
  ]
}
```

Tile IDs use Tiled convention: 0 = empty, 1+ = tile index offset by tileset's `firstgid`.

### Results Payload (Claude gets back)

Same structure as load, reflecting all user modifications (resized grid, new layers, painted tiles, added zones).

### Tiled JSON Export

`/api/designer/export` assembles standard Tiled JSON:

- `width`, `height`, `tilewidth`, `tileheight` from grid/tile_size
- Tile layers: `{"name": "...", "type": "tilelayer", "data": [...], "width": W, "height": H}`
- Object layers for collision zones and zone markers
- Tileset references with `firstgid` calculated per tileset
- Standard fields: `version: "1.10"`, `orientation: "orthogonal"`, `renderorder: "right-down"`

## Scene Designer UI

### Layout

Three-panel layout:

- **Left — Tileset Palette:** Loaded tilesets as grids, click to select brush tile. Recently Used section at top sorted by frequency. Tabs to switch between tilesets.
- **Center — Scene Canvas:** Scrollable grid showing active layer's tiles. Paint, erase, fill, select tools. Grid overlay toggle. Zoom controls.
- **Right — Layers & Zones:** Layer list with visibility toggles, active layer, reorder, add/remove. Object layer for collision zones (draw rectangles). Zone list (spawn, exit, custom). Grid resize controls.
- **Bottom bar:** Tool bar (Paint, Erase, Fill, Select, Resize). "Send to Claude" and "Export Tiled JSON" buttons.

### Features

- Paint tiles by click or click-drag
- Erase (set to 0)
- Flood fill
- Multiple tile layers with visibility toggles
- Collision zone drawing (rectangles on object layer)
- Zone markers (spawn, exit, trigger)
- Grid resize (add/remove rows/cols, preserving existing data)
- Multiple tilesets loaded simultaneously
- Recently used palette sorted by usage count
- Dark theme matching existing plugin UI

## Session State

New `designer` section on Session class:

```python
self.designer = {
    "project_path": None,
    "grid": {"width": 20, "height": 15},
    "tile_size": {"width": 16, "height": 16},
    "tilesets": [],
    "layers": [],
    "zones": [],
    "status": "idle",   # idle, active, submitted
    "results": None,
}
```

No new SQLite tables — designer is ephemeral. Output is the Tiled JSON file.

## New Skill

New skill at `skills/scene-designer/SKILL.md`:
- Trigger phrases: "design a level", "create a scene", "build a room", "lay out a map", "scene designer"
- Instructions for Claude to set up grid, pre-populate layers, load tilesets, direct user to designer
- Uses results + export to save Tiled JSON and generate Phaser loading code

## Files

### Refactor (existing)
- Modify: `scripts/server.py` — extract to core only
- Create: `scripts/routes/__init__.py`
- Create: `scripts/routes/health.py` — /health, /shutdown
- Create: `scripts/routes/asset_finder.py` — existing asset finder routes
- Create: `scripts/routes/inspector.py` — existing inspector routes

### New
- Create: `scripts/routes/scene_designer.py` — designer routes
- Create: `skills/scene-designer/SKILL.md`
- Create: `skills/scene-designer/assets/scene-designer.html`

## Constraints

- Python stdlib only
- Tiled JSON output (standard format, Phaser-native)
- Extend existing server (one process, one port)
- Dark theme consistent with existing UI
- Tileset images served from project directory (same security checks as inspector)

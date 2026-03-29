---
name: scene-designer
description: Visually design game levels, rooms, and structures using sprite sheet tiles for Phaser JS games. Triggers when the user wants to design a level, create a scene, build a room, lay out a map, place tiles, or compose a game area from sprite sheets. Also triggers for Tiled tilemap creation.
---

# Scene Designer

Open a visual tile-based scene editor so the user can design game levels, rooms, and structures. Claude pre-populates the grid with tiles and zones, the user refines visually, and the result is a Tiled-compatible JSON tilemap that Phaser loads natively.

## When to Use

Use this when the user wants to create or edit a game level, room, building, or any tile-based structure. Works for both top-down and side-scrolling layouts. Requires sprite sheets already in the project (via asset-finder or manually added).

## Step 1: Determine Scene Parameters

Before opening the designer, determine:
- **Grid size**: Width x height in tiles (e.g., 20x15 for a single screen, 100x20 for a scrolling level)
- **Tile size**: Usually 16x16 or 32x32 pixels
- **Tilesets**: Which sprite sheets to load as tile palettes (paths relative to project)
- **Layers**: What tile layers are needed (Ground, Buildings, Decorations, etc.)
- **Collision/zones**: Where collision, spawn points, exits, etc. should go

If the user is vague, suggest sensible defaults based on game type:
- Side-scroller: 40x15, ground layer + platform layer + decoration layer + collision
- Top-down RPG: 20x20, ground + walls + objects + collision
- Single room: 12x10, floor + walls + furniture + collision

## Step 2: Pre-populate and Launch

1. Ensure the server is running:
```bash
curl -s http://localhost:8483/health || python "$CLAUDE_PLUGIN_ROOT/scripts/server.py" --port 8483 --no-open &
```

2. POST the scene config with pre-populated data:
```bash
curl -s -X POST http://localhost:8483/api/designer/load \
  -H "Content-Type: application/json" \
  -d '{
    "project_path": "<absolute_project_path>",
    "grid": {"width": 20, "height": 15},
    "tile_size": {"width": 16, "height": 16},
    "tilesets": [
      {
        "name": "terrain",
        "image_path": "assets/images/tiles/terrain.png",
        "tile_width": 16, "tile_height": 16,
        "margin": 0, "spacing": 0
      }
    ],
    "layers": [
      {"name": "Ground", "type": "tilelayer", "data": [...]},
      {"name": "Buildings", "type": "tilelayer", "data": [0, 0, ...]},
      {"name": "Collision", "type": "objectgroup", "objects": []}
    ],
    "zones": [
      {"name": "spawn", "x": 32, "y": 192, "width": 16, "height": 16}
    ]
  }'
```

Use tile indices from sprite-inspector results to pre-fill layers. For example, if grass is tile index 5 in the terrain tileset, fill the Ground layer data array with 6 (index 5 + firstgid 1).

3. Tell the user to open http://localhost:8483/designer. Explain:
   - **Left panel**: Tile palette — click a tile to select it as your brush
   - **Center**: Scene canvas — paint tiles, draw zones
   - **Right panel**: Manage layers, zones, and grid size
   - **Tools**: Paint, Erase, Fill, Zone drawing

## Step 3: Get Results and Generate Output

1. Poll for results:
```bash
curl -s http://localhost:8483/api/designer/results
```
Wait until `status` is `"submitted"`.

2. Export as Tiled JSON:
```bash
curl -s http://localhost:8483/api/designer/export > "<project_path>/assets/tilemaps/level1.json"
```

3. Generate Phaser loading code:
```javascript
// preload()
this.load.tilemapTiledJSON('level1', 'assets/tilemaps/level1.json');
this.load.image('terrain-tiles', 'assets/images/tiles/terrain.png');

// create()
const map = this.make.tilemap({ key: 'level1' });
const tileset = map.addTilesetImage('terrain', 'terrain-tiles');
const groundLayer = map.createLayer('Ground', tileset, 0, 0);
const buildingLayer = map.createLayer('Buildings', tileset, 0, 0);

// Collision from object layer
const collisionLayer = map.getObjectLayer('Collision');
// ... or from tile properties
```

4. Read `references/phaser-integration.md` (in the asset-finder skill directory) for complete tilemap code patterns.

5. Shut down the server when done:
```bash
curl -s -X POST http://localhost:8483/shutdown
```

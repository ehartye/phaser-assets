# Sprite Sheet Inspector Design

## Problem

After downloading sprite sheet assets, Claude needs to know which tiles map to which animations and how layers compose. Currently the user has to manually describe frame indices or Claude has to guess from documentation. A visual inspector lets the user define animations and compositions interactively, then sends structured data back to Claude for Phaser code generation.

## Solution

Add a sprite sheet inspector to the existing server with two modes: animation mapping and layer composition. Claude loads a sprite sheet into the inspector, the user defines animations/compositions visually, and the data is sent back to Claude via the server API.

## Inspector Flow

1. Claude ensures the server is running
2. Claude POSTs sprite sheet config to `/api/inspector/load`
3. User opens `localhost:PORT/inspector`
4. User defines animations (frame sequences) and/or compositions (layer stacks)
5. User clicks "Send to Claude"
6. Claude GETs `/api/inspector/results` and generates Phaser code

## New Server Routes

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/inspector/load` | POST | Accept sprite sheet path + tile config |
| `/inspector` | GET | Serve the inspector HTML |
| `/inspector/image` | GET | Serve the sprite sheet image file |
| `/api/inspector/submit` | POST | Receive animation/composition data from browser |
| `/api/inspector/results` | GET | Claude polls for submitted data |

### Load Payload

```json
{
  "image_path": "assets/images/characters/knight.png",
  "tile_width": 32,
  "tile_height": 32,
  "margin": 0,
  "spacing": 0
}
```

`image_path` is relative to the project directory (from asset-finder results). The server resolves it against `session.project_path` to serve the actual file.

### Results Payload (what Claude gets back)

```json
{
  "sprite_sheet": "assets/images/characters/knight.png",
  "tile_size": [32, 32],
  "animations": {
    "idle": {"frames": [0, 1, 2, 3], "frameRate": 8, "loop": true},
    "walk": {"frames": [4, 5, 6, 7, 8, 9, 10, 11], "frameRate": 12, "loop": true},
    "attack": {"frames": [12, 13, 14, 15, 16, 17], "frameRate": 12, "loop": false}
  },
  "compositions": {
    "player": {"layers": [45, 67, 89]}
  }
}
```

## Inspector UI

### Two Modes (tab toggle)

**Animation Mode** (default):
- Type animation name (e.g., "idle")
- Click tiles in order to build frame sequence
- Inline preview plays the animation at configurable frame rate
- "Add Animation" saves it, starts a new one
- Sidebar lists all defined animations with frame previews
- Can reorder/remove frames within an animation

**Layer Mode:**
- Click tiles to stack as layers for compositing
- Live preview shows stacked result
- Name the composition (e.g., "player")
- "Add Composition" saves it
- Sidebar lists compositions with layer details

### Shared Features

- Grid view of all tiles with index labels
- Click to inspect any tile (enlarged preview, index, row, col, pixel coords)
- "Send to Claude" button POSTs to `/api/inspector/submit`
- Dark theme matching the asset-finder preview UI

## Session State

New `inspector` section on the existing Session class:

```python
self.inspector = {
    "image_path": None,
    "tile_config": {},
    "status": "idle",  # idle, active, submitted
    "results": None,
}
```

No new SQLite tables — the inspector is ephemeral.

## New Skill

New skill at `skills/sprite-inspector/SKILL.md` with:
- Trigger phrases: "map animations", "inspect sprite sheet", "define frames", "sprite inspector"
- Instructions for Claude to POST sprite sheet config, direct user to inspector, poll for results
- Uses results to generate Phaser animation code via `references/phaser-integration.md`

## Files

- Modify: `scripts/server.py` — add 5 new routes, inspector session state
- Create: `skills/sprite-inspector/SKILL.md` — new skill
- Create: `skills/sprite-inspector/assets/sprite-inspector.html` — inspector UI template

## Constraints

- Extend existing server, no new server script
- Python stdlib only
- Sprite sheet path provided by Claude (no drag-and-drop)
- Dark theme consistent with asset-finder preview UI

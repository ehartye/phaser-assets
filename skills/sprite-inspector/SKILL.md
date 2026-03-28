---
name: sprite-inspector
description: Visually inspect and map sprite sheet tiles to animations and layer compositions for Phaser JS games. Triggers when the user wants to map animations, inspect a sprite sheet, define frame sequences, identify tile indices, or compose layered characters from a sprite sheet.
---

# Sprite Sheet Inspector

Open a visual inspector for sprite sheets so the user can define animation frame sequences and layer compositions interactively.

## When to Use

Use this after a sprite sheet has been downloaded into the project (via the asset-finder skill or manually). The user wants to:
- Define which tiles are which animations (idle, walk, attack, etc.)
- Compose a character from multiple overlapping tiles
- Identify specific tile indices in a sprite sheet

## Step 1: Determine Sprite Sheet Details

Before opening the inspector, determine:
- **Image path**: Relative path to the sprite sheet in the project (e.g., `assets/images/characters/knight.png`)
- **Tile dimensions**: Width and height of each tile/frame in pixels
- **Margin**: Pixels of margin around the edge of the sheet (default 0)
- **Spacing**: Pixels between tiles (default 0)

If the sprite sheet was downloaded by asset-finder, use the metadata from that session. If the user provides the sheet manually, ask for tile dimensions or inspect the image to determine them.

## Step 2: Load the Inspector

1. Ensure the server is running:
```bash
curl -s http://localhost:8483/health || python "$CLAUDE_PLUGIN_ROOT/scripts/server.py" --port 8483 --no-open &
```

2. POST the sprite sheet config:
```bash
curl -s -X POST http://localhost:8483/api/inspector/load \
  -H "Content-Type: application/json" \
  -d '{"image_path": "<relative_path>", "tile_width": <W>, "tile_height": <H>, "margin": <M>, "spacing": <S>}'
```

3. Tell the user to open http://localhost:8483/inspector to use the visual inspector. Explain the two modes:
   - **Animation mode**: Click tiles in order to build frame sequences, name each animation, set frame rate
   - **Layer mode**: Click tiles to stack them as layers for character composition

4. Wait for the user to finish and click "Send to Claude".

## Step 3: Get Results and Generate Code

1. Poll for results:
```bash
curl -s http://localhost:8483/api/inspector/results
```
Wait until `status` is `"submitted"`.

2. Use the results to generate Phaser animation code. The results contain:
   - `sprite_sheet`: path to the image
   - `tile_size`: [width, height]
   - `animations`: named animation sequences with frames, frameRate, and loop
   - `compositions`: named layer stacks with tile indices

3. For each animation, generate:
```javascript
this.anims.create({
  key: '<animation_name>',
  frames: this.anims.generateFrameNumbers('<sprite_key>', { frames: [<frame_indices>] }),
  frameRate: <frameRate>,
  repeat: <loop ? -1 : 0>
});
```

4. Read `references/phaser-integration.md` (in the asset-finder skill directory) for complete Phaser code patterns.

5. Shut down the server when done:
```bash
curl -s -X POST http://localhost:8483/shutdown
```

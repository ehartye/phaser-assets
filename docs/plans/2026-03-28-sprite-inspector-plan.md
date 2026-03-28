# Sprite Sheet Inspector Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use h-superpowers:subagent-driven-development, h-superpowers:team-driven-development, or h-superpowers:executing-plans to implement this plan (ask user which approach).

**Goal:** Add a sprite sheet inspector with animation mapping and layer composition modes to the existing server, as a new skill (`phaser-assets:sprite-inspector`).

**Architecture:** Extend `scripts/server.py` with 5 new routes for the inspector. New HTML template at `skills/sprite-inspector/assets/sprite-inspector.html` with two-mode UI (animation + layer). New SKILL.md triggers when user wants to map sprite sheet frames. Server serves the sprite sheet image directly so the browser can render the tile grid.

**Tech Stack:** Python stdlib (existing server), vanilla HTML/CSS/JS

---

### Task 1: Add inspector session state to server.py

**Files:**
- Modify: `scripts/server.py`

**Step 1: Add inspector state to Session class**

In the `Session.__init__` method (around line 77), add after `self.lock`:

```python
        self.inspector = {
            "image_path": None,       # relative path to sprite sheet
            "tile_config": {},        # tile_width, tile_height, margin, spacing
            "status": "idle",         # idle, active, submitted
            "results": None,
        }
```

Make sure `self.reset()` (which calls `self.__init__()`) will also reset this.

**Step 2: Verify**

Run: `python -c "import sys; sys.path.insert(0,'scripts'); from server import Session; s = Session(); print(s.inspector)"`
Expected: `{'image_path': None, 'tile_config': {}, 'status': 'idle', 'results': None}`

**Step 3: Commit**

```bash
git add scripts/server.py
git commit -m "feat: add inspector state to Session class"
```

---

### Task 2: Add inspector routes to server.py

**Files:**
- Modify: `scripts/server.py`

**Step 1: Add routes to the dispatch dicts in do_GET and do_POST**

In `do_GET` route dict (around line 160), add:
```python
            "/inspector":            self.handle_inspector,
            "/inspector/image":      self.handle_inspector_image,
            "/api/inspector/results": self.handle_inspector_results,
```

In `do_POST` route dict (around line 174), add:
```python
            "/api/inspector/load":   self.handle_inspector_load,
            "/api/inspector/submit": self.handle_inspector_submit,
```

**Step 2: Implement `POST /api/inspector/load`**

```python
    def handle_inspector_load(self):
        body = self.read_body()
        session.inspector = {
            "image_path": body.get("image_path", ""),
            "tile_config": {
                "tile_width": body.get("tile_width", 32),
                "tile_height": body.get("tile_height", 32),
                "margin": body.get("margin", 0),
                "spacing": body.get("spacing", 0),
            },
            "status": "active",
            "results": None,
        }
        self.send_json({"status": "loaded", "image_path": session.inspector["image_path"]})
```

**Step 3: Implement `GET /inspector`**

Read the template from `skills/sprite-inspector/assets/sprite-inspector.html` (relative to script dir, same pattern as `handle_index`). Replace placeholders:
- `__TILE_CONFIG_PLACEHOLDER__` with `json.dumps(session.inspector["tile_config"])`
- `__IMAGE_PATH_PLACEHOLDER__` with the image path (just the relative path; the browser will fetch it from `/inspector/image`)

```python
    def handle_inspector(self):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        template_path = os.path.join(
            script_dir, "..", "skills", "sprite-inspector", "assets", "sprite-inspector.html"
        )
        try:
            with open(template_path, "r", encoding="utf-8") as f:
                html = f.read()
        except FileNotFoundError:
            self.send_json({"error": "inspector template not found"}, 500)
            return

        html = html.replace("__TILE_CONFIG_PLACEHOLDER__", json.dumps(session.inspector.get("tile_config", {})))
        html = html.replace('"__IMAGE_PATH_PLACEHOLDER__"', json.dumps(session.inspector.get("image_path", "")))

        self.send_html(html)
```

**Step 4: Implement `GET /inspector/image`**

Serve the sprite sheet image file from the project directory. Resolve `session.inspector["image_path"]` against `session.project_path`. Determine content type from extension.

```python
    def handle_inspector_image(self):
        image_path = session.inspector.get("image_path", "")
        if not image_path or not session.project_path:
            self.send_json({"error": "no image loaded"}, 400)
            return

        full_path = os.path.join(session.project_path, image_path)
        full_path = os.path.realpath(full_path)

        # Security: ensure the resolved path is within the project directory
        project_real = os.path.realpath(session.project_path)
        if not full_path.startswith(project_real + os.sep) and full_path != project_real:
            self.send_json({"error": "path escapes project directory"}, 403)
            return

        if not os.path.isfile(full_path):
            self.send_json({"error": "image not found", "path": full_path}, 404)
            return

        ext = os.path.splitext(full_path)[1].lower()
        content_types = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".svg": "image/svg+xml",
            ".webp": "image/webp",
        }
        ct = content_types.get(ext, "application/octet-stream")

        with open(full_path, "rb") as f:
            data = f.read()

        self.send_response(200)
        self.send_header("Content-Type", ct)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)
```

**Step 5: Implement `POST /api/inspector/submit`**

```python
    def handle_inspector_submit(self):
        body = self.read_body()
        session.inspector["results"] = {
            "sprite_sheet": session.inspector.get("image_path", ""),
            "tile_size": [
                session.inspector["tile_config"].get("tile_width", 32),
                session.inspector["tile_config"].get("tile_height", 32),
            ],
            "animations": body.get("animations", {}),
            "compositions": body.get("compositions", {}),
        }
        session.inspector["status"] = "submitted"
        self.send_json({"status": "submitted"})
```

**Step 6: Implement `GET /api/inspector/results`**

```python
    def handle_inspector_results(self):
        if session.inspector.get("status") != "submitted":
            self.send_json({"status": session.inspector.get("status", "idle"), "results": None})
            return
        self.send_json({
            "status": "submitted",
            "results": session.inspector.get("results"),
        })
```

**Step 7: Verify routes**

Start server, POST to /api/inspector/load with test data, GET /inspector (will 500 if template doesn't exist yet — that's OK), verify /api/inspector/results returns idle.

```bash
python scripts/server.py --port 8483 --no-open &
curl -s -X POST http://localhost:8483/api/inspector/load -H "Content-Type: application/json" -d '{"image_path":"test.png","tile_width":16,"tile_height":16,"margin":1,"spacing":0}'
curl -s http://localhost:8483/api/inspector/results
curl -s -X POST http://localhost:8483/shutdown
```

**Step 8: Commit**

```bash
git add scripts/server.py
git commit -m "feat: add inspector routes to server (/inspector, /api/inspector/*)"
```

---

### Task 3: Create sprite-inspector.html template

**Files:**
- Create: `skills/sprite-inspector/assets/sprite-inspector.html`

**Step 1: Create the directory**

```bash
mkdir -p skills/sprite-inspector/assets
```

**Step 2: Build the HTML**

Create a self-contained HTML file with:

**Layout:** Left side = tile grid, Right side = sidebar with mode tabs + workspace.

**CSS:** Dark theme matching asset-finder (use the same CSS variables: `--bg: #0f1118`, `--surface: #1a1d2e`, `--accent: #6c5ce7`, etc.). Pixelated image rendering for the tile grid.

**Placeholders:**
- `__TILE_CONFIG_PLACEHOLDER__` — injected as JS object (no quotes): `const TILE_CONFIG = __TILE_CONFIG_PLACEHOLDER__;`
- `"__IMAGE_PATH_PLACEHOLDER__"` — injected as JS string: `const IMAGE_PATH = "__IMAGE_PATH_PLACEHOLDER__";`

**Image loading:** The sprite sheet is loaded via `<img src="/inspector/image">`. The tile config provides `tile_width`, `tile_height`, `margin`, `spacing`.

**Grid rendering:**
- Calculate cols/rows from image dimensions and tile config: `cols = floor((img.width - margin) / (tile_width + spacing))`, etc.
- Render each tile as a small canvas element, scaled up 3x, with its index number above it
- Click to inspect (shows enlarged preview in sidebar with index, row, col, pixel coords)

**Mode tabs:** Two buttons at top of sidebar: "Animation" (default active) and "Layer"

**Animation Mode:**
- Text input for animation name
- Number input for frame rate (default 8)
- Checkbox for loop (default true)
- "Click tiles to add frames" instruction
- When a tile is clicked, append its index to the current frame list
- Show current frames as small tile previews in order, with X to remove each
- Drag to reorder (or simple up/down buttons)
- Animation preview canvas that plays the frames at the configured frame rate
- "Save Animation" button adds it to the animations list
- Saved animations shown below with name, frame count, and a delete button

**Layer Mode:**
- Text input for composition name
- Click tiles to add as layers (stacked on top of each other)
- Live preview canvas shows all layers composited
- Layer list with remove buttons
- "Save Composition" button adds it to the compositions list

**Send to Claude button:** At the bottom of the sidebar. Collects all saved animations and compositions into JSON and POSTs to `/api/inspector/submit`:
```javascript
async function sendToClaude() {
    const payload = { animations: {}, compositions: {} };
    // For each saved animation:
    // payload.animations[name] = { frames: [...], frameRate: N, loop: bool }
    // For each saved composition:
    // payload.compositions[name] = { layers: [...indices] }
    await fetch('/api/inspector/submit', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload)
    });
    // Update banner: "Data sent to Claude. You can close this tab."
}
```

**Reference:** Use `C:/Users/ehart/anika-projects/kwest-slayurz/inspector.html` as inspiration for the grid rendering approach (tile canvas elements, inspect on click, layer compose on action), but adapt to use the server pattern and dual-mode UI.

**Step 3: Verify**

Start server with a real sprite sheet loaded, open `/inspector` in browser, verify grid renders, test both modes, click "Send to Claude", verify data arrives at `/api/inspector/results`.

**Step 4: Commit**

```bash
git add skills/sprite-inspector/assets/sprite-inspector.html
git commit -m "feat: add sprite inspector HTML template with animation and layer modes"
```

---

### Task 4: Create sprite-inspector SKILL.md

**Files:**
- Create: `skills/sprite-inspector/SKILL.md`

**Step 1: Write the skill file**

```markdown
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
```

**Step 2: Commit**

```bash
git add skills/sprite-inspector/SKILL.md
git commit -m "feat: add sprite-inspector skill with SKILL.md"
```

---

### Task 5: End-to-end verification

**Step 1: Start the server**

```bash
python scripts/server.py --port 8483 --no-open &
```

**Step 2: Load a sprite sheet**

Use any PNG file available in a test project, or create a simple one. POST config:

```bash
curl -s -X POST http://localhost:8483/start -H "Content-Type: application/json" -d '{"assets":[],"project_path":"<path_to_a_project_with_a_sprite_sheet>","search_context":"test"}'
curl -s -X POST http://localhost:8483/api/inspector/load -H "Content-Type: application/json" -d '{"image_path":"<relative_path_to_sprite_sheet>","tile_width":16,"tile_height":16,"margin":0,"spacing":0}'
```

**Step 3: Verify inspector serves**

```bash
curl -s http://localhost:8483/inspector | head -5
```
Expected: `<!DOCTYPE html>` and HTML content

**Step 4: Verify image serving**

```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:8483/inspector/image
```
Expected: `200` (or `404` if test image doesn't exist at path — that's OK for route verification)

**Step 5: Test submit**

```bash
curl -s -X POST http://localhost:8483/api/inspector/submit -H "Content-Type: application/json" -d '{"animations":{"idle":{"frames":[0,1,2,3],"frameRate":8,"loop":true}},"compositions":{"player":{"layers":[10,20,30]}}}'
```
Expected: `{"status": "submitted"}`

**Step 6: Get results**

```bash
curl -s http://localhost:8483/api/inspector/results
```
Expected: JSON with status "submitted", results containing animations and compositions

**Step 7: Shutdown**

```bash
curl -s -X POST http://localhost:8483/shutdown
```

**Step 8: Open in browser for visual verification**

Repeat steps 1-2 with a real sprite sheet, open `http://localhost:8483/inspector` in browser, verify:
- Tile grid renders with numbered tiles
- Animation mode: can name, click tiles, set frame rate, save
- Layer mode: can name, click tiles, see composite preview, save
- "Send to Claude" posts and shows confirmation

**Step 9: Commit any fixes**

```bash
git add -A
git commit -m "fix: adjustments from sprite inspector e2e testing"
```

---
name: phaser-asset-finder
description: Find and integrate free 2D game assets (sprites, tilesets, UI, audio) into Phaser JS projects. Triggers when the user needs game art, sprites, tilesets, backgrounds, UI elements, sound effects, or music for a Phaser game, or mentions OpenGameArt, Kenney, or itch.io assets.
---

# Phaser Asset Finder

Find free 2D game assets from trusted sources and integrate them into Phaser JS projects — complete with download, file organization, and ready-to-use loading code.

## How This Skill Works

This skill searches the web for free game assets, presents them visually so the user can pick what they like, downloads the selected assets, and generates Phaser JS code to load and use them. The goal is to go from "I need a character sprite" to playable assets in minutes, not hours of browsing asset sites.

## Step 1: Understand What the User Needs

Before searching, clarify these details (many will be obvious from context):

- **Asset type**: Sprites/characters, tilesets/backgrounds, UI elements, audio, or a mix
- **Art style**: Pixel art, hand-drawn, vector, cartoon, realistic — or "whatever looks good"
- **Game genre context**: Platformer, top-down RPG, space shooter, puzzle, etc. (this shapes search terms)
- **Specific items**: "a knight character with walk and attack animations" vs. "some enemies"
- **Size/resolution preferences**: 16x16 tiles, 32x32, 64x64, or flexible

If the user is vague ("find me some assets"), ask a quick question or two. If they're specific ("I need a 32x32 pixel art knight with idle and run animations"), go straight to searching.

## Step 2: Search for Assets

Use `WebSearch` to find assets from these trusted free sources. Read `references/asset-sources.md` for the full list of sources with search URL patterns and license details.

**Search strategy:**
1. Start with **Kenney.nl** — highest quality, always CC0 (no attribution needed), Phaser-friendly formats
2. Then try **OpenGameArt.org** — huge library, filter by CC0 or CC-BY
3. Then **itch.io** free game assets — great pixel art, check individual licenses
4. For audio specifically, also check **Freesound.org** and **OpenGameArt audio**

**Constructing good searches:**
```
site:kenney.nl {art_style} {asset_type} {genre_keywords}
site:opengameart.org {asset_type} {art_style} {genre_keywords}
site:itch.io game-assets free {asset_type} {art_style}
```

Use `WebFetch` on promising results to get:
- Direct download links or asset page URLs
- Preview image URLs (for the preview UI)
- License information
- File format details (PNG, sprite sheet dimensions, Tiled JSON, WAV/OGG, etc.)
- Any README or documentation about the asset pack

Aim to find **4-8 options** across sources so the user has real choices.

## Step 3: Show the Preview UI

This is the key step that makes asset selection visual and fun instead of a wall of text links.

1. For each found asset, prepare a JSON object:

```json
[
  {
    "id": "kenney-knight",
    "name": "Kenney Knight Character Pack",
    "source": "Kenney.nl",
    "sourceUrl": "https://kenney.nl/assets/...",
    "previewUrl": "https://..../preview.png",
    "license": "CC0 (Public Domain)",
    "type": "sprite",
    "description": "32x32 pixel knight with idle, walk, attack, and death animations. 4 color variants.",
    "formats": ["PNG sprite sheet", "Individual frames"],
    "tags": ["pixel-art", "character", "knight", "fantasy", "animated"]
  }
]
```

2. Run the preview script, piping the asset JSON via stdin:
```bash
echo '<asset_json_array>' | python "$CLAUDE_PLUGIN_ROOT/scripts/preview.py" \
  --context "description of what was searched for" \
  --project "/absolute/path/to/user/project"
```

The script handles template population, session ID generation, writing to the system temp directory, and opening the browser. It outputs JSON with `session_id` and `preview_path`.

3. The user browses the visual grid, selects assets they want, and clicks "Confirm Selection". This downloads a file named `asset-selections-{session_id}.json` to the user's Downloads folder. Tell the user you're waiting for their selection, then poll for the file:
```bash
# Look for the unique selections file using the session_id from the script output
ls ~/Downloads/asset-selections-{session_id}.json
```
   Once found, read it and proceed.

4. Download the selected assets into the project's `assets/` folder.

## Step 4: Download Assets into the Project

Download the selected assets directly into the project's asset directory — not the user's Downloads folder. Use the project's existing asset structure if it has one, otherwise create a sensible default:

```
assets/
├── images/
│   ├── characters/
│   ├── tiles/
│   ├── backgrounds/
│   └── ui/
├── audio/
│   ├── sfx/
│   └── music/
└── tilemaps/
```

For downloads:
- Use `curl` or `wget` via Bash to download files
- Unzip asset packs if they come as .zip files
- Rename files to be clean and consistent (no spaces, lowercase, descriptive)
- Keep a note of which assets came from where and their licenses

Create a `CREDITS.md` in the assets directory listing each asset, its source, author, and license. This is important — even CC0 assets deserve attribution, and CC-BY assets require it.

## Step 5: Generate Phaser JS Integration Code

Generate the code the user needs to load and use each asset in their Phaser game. Read `references/phaser-integration.md` for the exact code patterns for each asset type.

**What to generate:**

1. **Preload code** — `this.load.*` calls for each asset
2. **Create code** — How to create sprites, animations, tilemaps from the loaded assets
3. **Animation definitions** — If sprite sheets have multiple animations, define them

Present this code clearly, either:
- Add it directly to the user's existing scene files if the project structure is clear
- Show it as a code block they can copy in, with comments explaining each part

**Example output for a character sprite sheet:**
```javascript
// In your preload() method:
this.load.spritesheet('knight', 'assets/images/characters/knight.png', {
  frameWidth: 32,
  frameHeight: 32
});

// In your create() method:
this.anims.create({
  key: 'knight-idle',
  frames: this.anims.generateFrameNumbers('knight', { start: 0, end: 3 }),
  frameRate: 8,
  repeat: -1
});

this.anims.create({
  key: 'knight-run',
  frames: this.anims.generateFrameNumbers('knight', { start: 4, end: 11 }),
  frameRate: 12,
  repeat: -1
});

const player = this.physics.add.sprite(400, 300, 'knight');
player.anims.play('knight-idle');
```

## Important Notes

- **Always verify licenses** before downloading. CC0 and CC-BY are safe. Avoid assets with NC (non-commercial) or ND (no derivatives) restrictions unless the user confirms their use case allows it.
- **Sprite sheet dimensions matter** — if you can't determine the frame size from the asset page, download and inspect the image to figure out the grid before generating code.
- **Audio format compatibility** — Phaser works best with both OGG and MP3 for cross-browser support. If only one format is available, note this and suggest a conversion if needed.
- **Don't guess frame counts** — look at the actual sprite sheet or its documentation. Wrong frame dimensions will make animations look broken.

# phaser-assets

A Claude Code plugin that finds free 2D game assets and integrates them into Phaser JS projects. Searches trusted free sources (Kenney, OpenGameArt, itch.io), presents a visual preview UI for selection, downloads assets into your project, and generates ready-to-use Phaser loading code.

## Features

- Searches multiple free asset sources (Kenney.nl, OpenGameArt, itch.io, Freesound, and more)
- Visual HTML preview UI for browsing and selecting assets
- Downloads assets directly into your project with organized folder structure
- Generates Phaser 3 preload/create code with animations, tilemaps, and audio
- Tracks licenses and generates CREDITS.md attribution

## Installation

### Local install

Add this to your Claude Code settings (`~/.claude/settings.json`):

```json
{
  "plugins": {
    "marketplaces": [
      {
        "url": "file:///C:/Users/ehart/repos/phaser-assets/marketplace.json"
      }
    ]
  }
}
```

Or run Claude Code with the plugin directory directly:

```bash
claude --plugin-dir /path/to/phaser-assets
```

## Usage

The skill activates automatically when you ask for game assets in a Phaser project context. Examples:

- "I need a player character with walk and jump animations"
- "Find me some platformer tiles"
- "Add sound effects to my game"
- "I need UI elements for my RPG"

## Supported Asset Types

- Character sprites and sprite sheets
- Tilesets and backgrounds
- UI elements and icons
- Sound effects and music
- Bitmap fonts
- Complete game kits

## License

MIT

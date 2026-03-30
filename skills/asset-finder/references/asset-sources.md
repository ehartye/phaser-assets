# Free 2D Game Asset Sources

## Tier 1: Best Quality + Easiest Licensing

### Kenney.nl
- **URL**: https://kenney.nl/assets
- **License**: CC0 (Public Domain) — no attribution required
- **Strengths**: Extremely high quality, consistent art style within packs, Phaser-friendly formats, well-documented sprite sheet layouts
- **Asset types**: Sprites, tilesets, UI packs, backgrounds, audio, fonts
- **Formats**: PNG (individual + sprite sheets), SVG, Tiled-compatible tilesets, WAV/OGG audio
- **Search**: Browse by category at kenney.nl/assets or search: `site:kenney.nl {keywords}`
- **Download**: Direct ZIP download from asset pages, no account needed
- **Notes**: Always the first place to check. Packs are complete and well-organized. Most sprite sheets include metadata files or clear documentation about frame sizes.

### OpenGameArt.org
- **URL**: https://opengameart.org
- **License**: Mixed — filter by CC0, CC-BY 3.0/4.0, CC-BY-SA. Avoid GPL for assets.
- **Strengths**: Massive library, community contributed, good search/filter, license clearly stated per asset
- **Asset types**: Everything — sprites, tilesets, backgrounds, icons, audio, music
- **Formats**: PNG, SVG, XCF (GIMP), WAV, OGG, FLAC, MIDI
- **Search**: `https://opengameart.org/art-search-advanced?keys={keywords}&type[]=art2d`
- **API**: Has a basic search API but web search + fetch works better
- **Notes**: Quality varies widely. Check the preview images carefully. Look at download counts and favorites as quality signals.

## Tier 2: Great Options

### itch.io Game Assets
- **URL**: https://itch.io/game-assets/free
- **License**: Varies per asset — MUST check each one. Many are CC0 or CC-BY, some have custom licenses.
- **Strengths**: Incredible pixel art community, many polished asset packs, active creators
- **Asset types**: Sprites, tilesets, UI kits, backgrounds, fonts, complete game kits
- **Formats**: PNG sprite sheets, individual frames, Aseprite files, Tiled maps
- **Search**: `https://itch.io/game-assets/free/tag-{tag}` where tags include: `pixel-art`, `sprites`, `tileset`, `top-down`, `platformer`, `rpg`, `sci-fi`, `fantasy`
- **Sort options**: `top-rated`, `most-recent`, `most-downloaded`
- **Cloudflare protection**: Listing pages are behind Cloudflare — `WebFetch` will typically fail. Use the server's `POST /api/itch/search` endpoint instead, which uses Playwright with a headed Edge browser to bypass the challenge.
- **Downloads**: Use `POST /api/itch/download` or the asset_finder download flow (which auto-delegates itch.io URLs to the Playwright downloader). Handles both direct-download and name-your-price gate flows.
- **Browser requirement**: The itch.io endpoints require Microsoft Edge installed on the system (`channel='msedge'`, headed mode). The browser launches on first use (minimized) and persists until server shutdown.
- **Notes**: The free section is genuinely excellent. Sort by "Top rated" or "Most recent". Many creators also offer paid packs with free samples.

### Freesound.org
- **URL**: https://freesound.org
- **License**: CC0, CC-BY, CC-BY-NC (check each sound)
- **Strengths**: Enormous sound library, good search, spectral previews
- **Asset types**: Sound effects, ambient sounds, some music loops
- **Formats**: WAV, FLAC, OGG, MP3
- **Search**: `https://freesound.org/search/?q={keywords}&f=license:"Creative+Commons+0"`
- **Notes**: Requires free account to download. Search supports filtering by license, duration, sample rate. Best for SFX — for music, OpenGameArt or below sources are better.

## Tier 3: Specialized / Supplementary

### Game-icons.net
- **URL**: https://game-icons.net
- **License**: CC-BY 3.0
- **Strengths**: 4000+ game-themed SVG icons, perfect for UI
- **Asset types**: Icons only (inventory items, abilities, status effects, UI elements)
- **Formats**: SVG (convert to PNG for Phaser)
- **Notes**: Great for quick UI icons. Can customize colors on the site before downloading.

### Craftpix.net (Free Section)
- **URL**: https://craftpix.net/freebies/
- **License**: Custom free license (check terms — generally free for commercial use with some restrictions)
- **Strengths**: Professional quality, complete game kits, consistent art styles
- **Asset types**: Sprites, tilesets, backgrounds, UI, game kits
- **Formats**: PNG, PSD, AI
- **Notes**: Smaller free selection but high quality. Requires account for download.

## Search Strategy by Asset Type

| Need | Search First | Then Try |
|------|-------------|----------|
| Character sprites | Kenney, itch.io | OpenGameArt |
| Tilesets | Kenney, itch.io | OpenGameArt |
| Backgrounds | Kenney, OpenGameArt | itch.io, Craftpix |
| UI elements | Kenney, game-icons.net | itch.io |
| Sound effects | Freesound, Kenney | OpenGameArt |
| Music | OpenGameArt, Kenney | itch.io |
| Complete game kit | Kenney, itch.io | Craftpix |

## License Quick Reference

| License | Attribution? | Commercial OK? | Modify OK? | Safe for games? |
|---------|-------------|----------------|------------|-----------------|
| CC0 | No | Yes | Yes | Best choice |
| CC-BY 3.0/4.0 | Yes (in credits) | Yes | Yes | Great choice |
| CC-BY-SA | Yes + share alike | Yes | Yes (same license) | OK, but derivatives must use same license |
| CC-BY-NC | Yes | NO | Yes | Only for non-commercial |
| GPL | Yes + source code | Yes | Yes (GPL) | Complicated for games — avoid for assets |

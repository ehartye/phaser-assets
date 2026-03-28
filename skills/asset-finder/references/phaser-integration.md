# Phaser JS Asset Integration Patterns

Code patterns for loading and using different asset types in Phaser 3. All examples use the standard Phaser scene lifecycle methods.

## Table of Contents
1. [Static Images](#static-images)
2. [Sprite Sheets (Fixed Grid)](#sprite-sheets-fixed-grid)
3. [Texture Atlases (JSON)](#texture-atlases-json)
4. [Animations](#animations)
5. [Tilemaps (Tiled JSON)](#tilemaps-tiled-json)
6. [Audio](#audio)
7. [Bitmap Fonts](#bitmap-fonts)
8. [Multi-Asset Preloading](#multi-asset-preloading)
9. [Common Gotchas](#common-gotchas)

---

## Static Images

For backgrounds, UI elements, and non-animated objects.

```javascript
// preload()
this.load.image('background', 'assets/images/backgrounds/forest.png');
this.load.image('btn-play', 'assets/images/ui/play-button.png');

// create()
this.add.image(400, 300, 'background');                    // centered on point
this.add.image(400, 300, 'background').setOrigin(0, 0);   // top-left at point
```

## Sprite Sheets (Fixed Grid)

For sprite sheets where every frame is the same size in a uniform grid.

```javascript
// preload()
this.load.spritesheet('knight', 'assets/images/characters/knight.png', {
  frameWidth: 32,
  frameHeight: 32,
  // Optional: if the sheet has padding/margin
  // margin: 1,
  // spacing: 2
});

// create()
const player = this.add.sprite(100, 200, 'knight');
// or with physics:
const player = this.physics.add.sprite(100, 200, 'knight');
```

**How to determine frame size:** Look at the sprite sheet image dimensions and divide by the number of columns/rows. For example, a 256x128 image with 8 columns and 4 rows = 32x32 frames.

## Texture Atlases (JSON)

For assets packed with TexturePacker or similar tools that come with a JSON descriptor.

```javascript
// preload()
this.load.atlas('ui-pack', 'assets/images/ui/ui-pack.png', 'assets/images/ui/ui-pack.json');

// create() — use frame names from the JSON
const healthBar = this.add.image(50, 20, 'ui-pack', 'health-bar-full.png');
const coin = this.add.image(200, 20, 'ui-pack', 'coin-icon.png');
```

## Animations

Create animations from sprite sheet frames.

```javascript
// create() — define animations ONCE, use many times

// Simple loop (idle, walk)
this.anims.create({
  key: 'knight-idle',
  frames: this.anims.generateFrameNumbers('knight', { start: 0, end: 3 }),
  frameRate: 8,
  repeat: -1  // -1 = loop forever
});

// One-shot (attack, death, jump)
this.anims.create({
  key: 'knight-attack',
  frames: this.anims.generateFrameNumbers('knight', { start: 8, end: 13 }),
  frameRate: 12,
  repeat: 0  // play once
});

// Play animation on a sprite
player.anims.play('knight-idle');

// Switch animations
player.anims.play('knight-run', true);  // true = ignore if already playing

// Listen for animation complete (useful for one-shot anims)
player.on('animationcomplete-knight-attack', () => {
  player.anims.play('knight-idle');
});
```

**From atlas frames (named frames instead of indices):**
```javascript
this.anims.create({
  key: 'knight-walk',
  frames: this.anims.generateFrameNames('knight-atlas', {
    prefix: 'walk_',
    start: 0,
    end: 7,
    suffix: '.png',
    zeroPad: 2  // walk_00.png, walk_01.png, ...
  }),
  frameRate: 10,
  repeat: -1
});
```

## Tilemaps (Tiled JSON)

For levels created in the Tiled map editor.

```javascript
// preload()
this.load.tilemapTiledJSON('level1', 'assets/tilemaps/level1.json');
this.load.image('terrain-tiles', 'assets/images/tiles/terrain.png');

// create()
const map = this.make.tilemap({ key: 'level1' });

// The first argument must match the tileset name in Tiled
const tileset = map.addTilesetImage('terrain', 'terrain-tiles');

// Create layers — names must match layer names in Tiled
const groundLayer = map.createLayer('Ground', tileset, 0, 0);
const platformLayer = map.createLayer('Platforms', tileset, 0, 0);

// Set collision
platformLayer.setCollisionByProperty({ collides: true });
// or by tile index range:
platformLayer.setCollisionBetween(1, 20);

// Add collision with player
this.physics.add.collider(player, platformLayer);
```

**Multiple tilesets in one map:**
```javascript
const tileset1 = map.addTilesetImage('terrain', 'terrain-tiles');
const tileset2 = map.addTilesetImage('decorations', 'decoration-tiles');
const layer = map.createLayer('Ground', [tileset1, tileset2], 0, 0);
```

## Audio

```javascript
// preload() — provide multiple formats for cross-browser support
this.load.audio('jump', ['assets/audio/sfx/jump.ogg', 'assets/audio/sfx/jump.mp3']);
this.load.audio('bgm', ['assets/audio/music/theme.ogg', 'assets/audio/music/theme.mp3']);

// create()
// Sound effect (play on demand)
const jumpSound = this.sound.add('jump', { volume: 0.5 });
jumpSound.play();

// Background music (loop)
const music = this.sound.add('bgm', {
  volume: 0.3,
  loop: true
});
music.play();

// Quick one-liner for simple SFX
this.sound.play('jump');
```

## Bitmap Fonts

```javascript
// preload()
this.load.bitmapFont('pixelfont', 'assets/fonts/pixel.png', 'assets/fonts/pixel.xml');

// create()
this.add.bitmapText(100, 50, 'pixelfont', 'SCORE: 0', 16);
```

## Multi-Asset Preloading

When loading many assets, show a loading bar.

```javascript
preload() {
  // Loading bar
  const progressBar = this.add.graphics();
  this.load.on('progress', (value) => {
    progressBar.clear();
    progressBar.fillStyle(0xffffff, 1);
    progressBar.fillRect(250, 280, 300 * value, 30);
  });
  this.load.on('complete', () => progressBar.destroy());

  // Load everything
  this.load.image('bg', 'assets/images/backgrounds/sky.png');
  this.load.spritesheet('player', 'assets/images/characters/player.png', { frameWidth: 32, frameHeight: 32 });
  this.load.tilemapTiledJSON('map', 'assets/tilemaps/level1.json');
  this.load.image('tiles', 'assets/images/tiles/terrain.png');
  this.load.audio('bgm', ['assets/audio/music/theme.ogg']);
  this.load.audio('jump', ['assets/audio/sfx/jump.ogg']);
}
```

## Common Gotchas

1. **Sprite sheet frame size must exactly divide the image dimensions.** If your sheet is 256x128 and you set frameWidth: 30, you'll get garbled frames.

2. **Tilemap tileset name must match Tiled.** The first argument to `addTilesetImage()` is the name you gave the tileset *inside Tiled*, not the filename.

3. **Audio formats**: OGG works in Chrome/Firefox, MP3 in Safari. Provide both for cross-browser. WAV works everywhere but files are huge.

4. **Spritesheet vs Atlas**: Use `load.spritesheet` for uniform grids (every frame same size). Use `load.atlas` when frames have different sizes or come with a JSON descriptor.

5. **Frame numbering starts at 0.** A sheet with 8 frames uses indices 0-7.

6. **Set the base path** if all assets share a prefix:
   ```javascript
   this.load.setBaseURL('');
   this.load.setPath('assets/');
   ```

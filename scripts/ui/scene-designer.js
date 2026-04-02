// ====== State ======
var zoom = 3;
var palZoom = 2;
var activeTool = 'paint';
var activeLayerIndex = 0;
var activeTilesetIndex = 0;
var activeTile = 0; // 0 = eraser / empty
var activeTileBySize = {}; // { tileSize: globalId }
var showGrid = true;
var showBounds = true;
var painting = false;
var zoneDrawing = false;
var zoneStart = null;
var zoneCurrent = null;
var pendingZoneRect = null;
var _pendingOrientation = null;

// Tileset images (loaded async)
var tilesetImages = []; // Image objects, parallel to tilesetConfigs
var tilesetReady = [];  // booleans

// Recently used tiles: Map of "tilesetIdx:tileIdx" -> count
var recentTiles = {};
var recentTilesBySize = {}; // { tileSize: { globalId: count } }

// ====== Canvas Setup ======
var sceneCanvas = document.getElementById('scene-canvas');
var sceneCtx = sceneCanvas.getContext('2d');
var gridCanvas = document.getElementById('grid-overlay');
var gridCtx = gridCanvas.getContext('2d');
var zoneCanvas = document.getElementById('zone-overlay');
var zoneCtx = zoneCanvas.getContext('2d');

sceneCtx.imageSmoothingEnabled = false;

// ====== Init ======
function updateGridTileInfo() {
  document.getElementById('grid-tile-info').textContent =
    grid.width + ' \u00d7 ' + grid.height + ' tiles at ' + tileSize.width + 'px';
}

function init() {
  // Compute pixel dimensions from initial grid
  scenePixels.width = grid.width * tileSize.width;
  scenePixels.height = grid.height * tileSize.height;
  document.getElementById('scene-width-px').value = scenePixels.width;
  document.getElementById('scene-height-px').value = scenePixels.height;
  updateGridTileInfo();

  // Highlight active tile size button
  document.querySelectorAll('.tile-size-btn').forEach(function(btn) {
    btn.classList.toggle('active', parseInt(btn.textContent) === tileSize.width);
  });

  // Ensure layers have valid data arrays and per-layer tile size
  for (var i = 0; i < layers.length; i++) {
    if (layers[i].type === 'tilelayer') {
      if (!layers[i].tileSize) layers[i].tileSize = tileSize.width;
      var lc = _layerGridCols(layers[i]);
      var lr = _layerGridRows(layers[i]);
      var needed = lc * lr;
      if (!layers[i].data || layers[i].data.length !== needed) {
        var newData = new Array(needed).fill(0);
        if (layers[i].data) {
          for (var j = 0; j < Math.min(layers[i].data.length, needed); j++) {
            newData[j] = layers[i].data[j];
          }
        }
        layers[i].data = newData;
      }
      layers[i]._prevCols = lc;
    }
    if (layers[i].visible === undefined) layers[i].visible = true;
  }

  // Load tileset images
  loadTilesets();

  // Build layer/zone UI
  renderLayers();
  renderZones();
  buildTilesetTabs();

  // Size canvases
  resizeCanvases();

  // Set up mouse handlers on canvas panel
  setupCanvasEvents();

  _syncOrientationButtons();
}

// ====== Tileset Loading ======
function loadTilesets() {
  tilesetImages = [];
  tilesetReady = [];
  var totalTilesets = tilesetConfigs.length;
  var loadedTilesets = 0;

  function onTilesetReady() {
    loadedTilesets++;
    if (loadedTilesets === totalTilesets) {
      document.getElementById('palette-info').textContent =
        tilesetConfigs.length + ' tileset(s) loaded';
    }
    buildPaletteGrid(activeTilesetIndex);
    renderScene();
  }

  for (var i = 0; i < tilesetConfigs.length; i++) {
    (function(idx) {
      var ts = tilesetConfigs[idx];

      if (ts.type === 'sprite-collection') {
        // Load one Image per sprite
        tilesetImages[idx] = [];
        tilesetReady[idx] = false;
        var sprites = ts.sprites || [];
        var spritesLoaded = 0;

        if (sprites.length === 0) {
          tilesetReady[idx] = true;
          onTilesetReady();
          return;
        }

        sprites.forEach(function(spriteName, spriteIdx) {
          var img = new Image();
          img.crossOrigin = 'anonymous';
          var fullPath = ts.folder_path.replace(/\\/g, '/') + '/' + spriteName;
          img.onload = function() {
            spritesLoaded++;
            if (spritesLoaded === sprites.length) {
              tilesetReady[idx] = true;
              onTilesetReady();
            }
          };
          img.onerror = function() {
            spritesLoaded++;
            console.error('Failed to load sprite:', fullPath);
            if (spritesLoaded === sprites.length) {
              tilesetReady[idx] = true;
              onTilesetReady();
            }
          };
          img.src = '/designer/tileset?path=' + encodeURIComponent(fullPath);
          tilesetImages[idx][spriteIdx] = img;
        });

      } else {
        // Standard spritesheet
        var img = new Image();
        img.crossOrigin = 'anonymous';
        tilesetImages[idx] = img;
        tilesetReady[idx] = false;

        img.onload = function() {
          tilesetReady[idx] = true;
          onTilesetReady();
        };
        img.onerror = function() {
          tilesetReady[idx] = false;
          loadedTilesets++;
          console.error('Failed to load tileset:', ts.name);
        };
        img.src = '/designer/tileset?path=' + encodeURIComponent(ts.image_path);
      }
    })(i);
  }

  if (tilesetConfigs.length === 0) {
    document.getElementById('palette-info').textContent = 'No tilesets loaded';
  }
}

function addTilesetFromPath(imagePath) {
  var parts = imagePath.replace(/\\/g, '/').split('/');
  var name = parts[parts.length - 1].replace(/\.[^.]+$/, '');
  var activeLayer = layers[activeLayerIndex];
  var ts = (activeLayer && activeLayer.tileSize) ? activeLayer.tileSize : 32;

  tilesetConfigs.push({
    name: name,
    image_path: imagePath,
    tile_width: ts,
    tile_height: ts,
    margin: 0,
    spacing: 0,
  });

  var idx = tilesetConfigs.length - 1;
  var img = new Image();
  img.crossOrigin = 'anonymous';
  tilesetImages[idx] = img;
  tilesetReady[idx] = false;

  img.onload = function() {
    tilesetReady[idx] = true;
    buildPaletteGrid(idx);
    renderScene();
    document.getElementById('palette-info').textContent =
      tilesetConfigs.length + ' tileset(s) loaded';
  };
  img.onerror = function() {
    console.error('Failed to load tileset:', imagePath);
  };
  img.src = '/designer/tileset?path=' + encodeURIComponent(imagePath);

  activeTilesetIndex = idx;
  buildTilesetTabs();
}

// ====== Tileset Tabs ======
function buildTilesetTabs() {
  var container = document.getElementById('tileset-tabs');
  container.innerHTML = '';
  for (var i = 0; i < tilesetConfigs.length; i++) {
    var btn = document.createElement('button');
    btn.className = 'tileset-tab' + (i === activeTilesetIndex ? ' active' : '');
    btn.textContent = tilesetConfigs[i].name;
    btn.dataset.idx = i;
    btn.addEventListener('click', function() {
      activeTilesetIndex = parseInt(this.dataset.idx);
      document.querySelectorAll('.tileset-tab').forEach(function(t) { t.classList.remove('active'); });
      this.classList.add('active');
      buildPaletteGrid(activeTilesetIndex);
    });
    container.appendChild(btn);
  }
}

// ====== Palette Grid ======
function buildPaletteGrid(tsIdx) {
  var container = document.getElementById('palette-grid');
  container.innerHTML = '';

  if (!tilesetReady[tsIdx]) return;

  var ts = tilesetConfigs[tsIdx];
  var img = tilesetImages[tsIdx];
  var tw = ts.tile_width;
  var th = ts.tile_height;
  var margin = ts.margin || 0;
  var spacing = ts.spacing || 0;
  var cols = Math.floor((img.width - margin + spacing) / (tw + spacing));
  var rows = Math.floor((img.height - margin + spacing) / (th + spacing));

  // Set grid columns to match spritesheet layout
  var tilePx = tw * palZoom + 4; // tile canvas + border + gap
  container.style.gridTemplateColumns = 'repeat(' + cols + ', ' + (tw * palZoom + 2) + 'px)';

  // Size the palette panel to fit the spritesheet columns (+ padding/border)
  var panelWidth = cols * tilePx + 24; // 8px padding each side + some buffer
  var panel = document.getElementById('palette-panel');
  var maxWidth = window.innerWidth * 0.4;
  panel.style.width = Math.min(panelWidth, maxWidth) + 'px';

  for (var r = 0; r < rows; r++) {
    for (var c = 0; c < cols; c++) {
      var tileIdx = r * cols + c;
      var sx = margin + c * (tw + spacing);
      var sy = margin + r * (th + spacing);

      var canvas = document.createElement('canvas');
      canvas.width = tw * palZoom;
      canvas.height = th * palZoom;
      canvas.className = 'palette-tile';
      canvas.dataset.tsIdx = tsIdx;
      canvas.dataset.tileIdx = tileIdx;
      canvas.title = ts.name + ' #' + tileIdx;

      var ctx = canvas.getContext('2d');
      ctx.imageSmoothingEnabled = false;
      ctx.drawImage(img, sx, sy, tw, th, 0, 0, tw * palZoom, th * palZoom);

      // Compute global tile ID (firstgid + tileIdx)
      var firstgid = getFirstGid(tsIdx);
      var globalId = firstgid + tileIdx;
      canvas.dataset.globalId = globalId;

      if (globalId === activeTile) {
        canvas.classList.add('selected');
      }

      canvas.addEventListener('click', function() {
        var gid = parseInt(this.dataset.globalId);
        selectTile(gid, parseInt(this.dataset.tsIdx));
      });

      container.appendChild(canvas);
    }
  }
}

function getFirstGid(tsIdx) {
  var gid = 1;
  for (var i = 0; i < tsIdx; i++) {
    if (!tilesetReady[i]) continue;
    var ts = tilesetConfigs[i];
    if (ts.type === 'sprite-collection') {
      gid += (ts.sprites || []).length;
    } else {
      var img = tilesetImages[i];
      var margin = ts.margin || 0;
      var spacing = ts.spacing || 0;
      var cols = Math.floor((img.width - margin + spacing) / (ts.tile_width + spacing));
      var rows = Math.floor((img.height - margin + spacing) / (ts.tile_height + spacing));
      gid += cols * rows;
    }
  }
  return gid;
}

function selectTile(globalId, tsIdx) {
  activeTile = globalId;
  if (tsIdx !== undefined && tsIdx !== activeTilesetIndex) {
    activeTilesetIndex = tsIdx;
    document.querySelectorAll('.tileset-tab').forEach(function(t) { t.classList.remove('active'); });
    var tab = document.querySelector('.tileset-tab[data-idx="' + tsIdx + '"]');
    if (tab) tab.classList.add('active');
    buildPaletteGrid(tsIdx);
  }
  // Update selection highlight
  document.querySelectorAll('.palette-tile.selected').forEach(function(t) { t.classList.remove('selected'); });
  document.querySelectorAll('.palette-tile[data-global-id="' + globalId + '"]').forEach(function(t) {
    t.classList.add('selected');
  });
  document.querySelectorAll('.recent-tile.selected').forEach(function(t) { t.classList.remove('selected'); });
  document.querySelectorAll('.recent-tile[data-global-id="' + globalId + '"]').forEach(function(t) {
    t.classList.add('selected');
  });

  // Auto-switch to paint tool
  if (activeTool !== 'paint' && activeTool !== 'fill') {
    setTool('paint');
  }
}

// ====== Recently Used ======
function trackRecentTile(globalId) {
  if (globalId === 0) return;
  var key = String(globalId);
  recentTiles[key] = (recentTiles[key] || 0) + 1;
  renderRecentTiles();
}

function renderRecentTiles() {
  var container = document.getElementById('recent-tiles');
  container.innerHTML = '';

  // Sort by count descending
  var entries = Object.keys(recentTiles).map(function(k) {
    return { globalId: parseInt(k), count: recentTiles[k] };
  });
  entries.sort(function(a, b) { return b.count - a.count; });

  // Show top 16
  var limit = Math.min(entries.length, 16);
  for (var i = 0; i < limit; i++) {
    var gid = entries[i].globalId;
    var info = getTileInfo(gid);
    if (!info) continue;

    var canvas = document.createElement('canvas');
    canvas.width = info.tw * palZoom;
    canvas.height = info.th * palZoom;
    canvas.className = 'recent-tile' + (gid === activeTile ? ' selected' : '');
    canvas.dataset.globalId = gid;
    canvas.title = info.tsName + ' #' + info.localIdx + ' (used ' + entries[i].count + 'x)';

    var ctx = canvas.getContext('2d');
    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(info.img, info.sx, info.sy, info.tw, info.th, 0, 0, info.tw * palZoom, info.th * palZoom);

    canvas.addEventListener('click', function() {
      selectTile(parseInt(this.dataset.globalId));
    });

    container.appendChild(canvas);
  }
}

// ====== Tile Info Lookup ======
function getTileInfo(globalId) {
  if (globalId <= 0) return null;

  var gid = 1;
  for (var i = 0; i < tilesetConfigs.length; i++) {
    if (!tilesetReady[i]) continue;
    var ts = tilesetConfigs[i];

    if (ts.type === 'sprite-collection') {
      var sprites = ts.sprites || [];
      var count = sprites.length;
      if (globalId >= gid && globalId < gid + count) {
        var localIdx = globalId - gid;
        var img = tilesetImages[i][localIdx];
        if (!img || !img.naturalWidth) return null;
        return {
          tsIdx: i, tsName: ts.name, localIdx: localIdx,
          img: img, sx: 0, sy: 0,
          tw: img.naturalWidth, th: img.naturalHeight,
          cols: 1, rows: 1,
          isCollection: true
        };
      }
      gid += count;
    } else {
      var img = tilesetImages[i];
      var margin = ts.margin || 0;
      var spacing = ts.spacing || 0;
      var cols = Math.floor((img.width - margin + spacing) / (ts.tile_width + spacing));
      var rows = Math.floor((img.height - margin + spacing) / (ts.tile_height + spacing));
      var count = cols * rows;
      if (globalId >= gid && globalId < gid + count) {
        var localIdx = globalId - gid;
        var cr = tileColRow(localIdx, cols);
        var pos = tileSourceXY(cr.col, cr.row, ts.tile_width, ts.tile_height, margin, spacing);
        return {
          tsIdx: i, tsName: ts.name, localIdx: localIdx,
          img: img, sx: pos.sx, sy: pos.sy,
          tw: ts.tile_width, th: ts.tile_height,
          cols: cols, rows: rows,
          isCollection: false
        };
      }
      gid += count;
    }
  }
  return null;
}

function getTileInfoAt(globalId, ts_size) {
  if (globalId <= 0) return null;
  var gid = 1;
  for (var i = 0; i < tilesetConfigs.length; i++) {
    if (!tilesetReady[i]) continue;
    var ts = tilesetConfigs[i];

    if (ts.type === 'sprite-collection') {
      var sprites = ts.sprites || [];
      var count = sprites.length;
      if (globalId >= gid && globalId < gid + count) {
        var localIdx = globalId - gid;
        var img = tilesetImages[i][localIdx];
        if (!img || !img.naturalWidth) return null;
        return {
          tsIdx: i, tsName: ts.name, localIdx: localIdx,
          img: img, sx: 0, sy: 0,
          tw: img.naturalWidth, th: img.naturalHeight,
          cols: 1, rows: 1,
          isCollection: true
        };
      }
      gid += count;
    } else {
      var img = tilesetImages[i];
      var margin = ts.margin || 0;
      var spacing = ts.spacing || 0;
      var tw = ts_size;
      var th = ts_size;
      var cols = Math.floor((img.width - margin + spacing) / (tw + spacing));
      var rows = Math.floor((img.height - margin + spacing) / (th + spacing));
      var count = cols * rows;
      if (globalId >= gid && globalId < gid + count) {
        var localIdx = globalId - gid;
        var cr = tileColRow(localIdx, cols);
        var pos = tileSourceXY(cr.col, cr.row, tw, th, margin, spacing);
        return {
          tsIdx: i, tsName: ts.name, localIdx: localIdx,
          img: img, sx: pos.sx, sy: pos.sy,
          tw: tw, th: th,
          cols: cols, rows: rows,
          isCollection: false
        };
      }
      gid += count;
    }
  }
  return null;
}

// ====== Canvas Sizing ======
function resizeCanvases() {
  var maxPxW = 0, maxPxH = 0;
  for (var i = 0; i < layers.length; i++) {
    if (layers[i].type !== 'tilelayer') continue;
    var lts = _layerTileSize(layers[i]);
    var lth = (orientation === 'isometric') ? Math.max(1, Math.floor(lts / 2)) : lts;
    var cols = _layerGridCols(layers[i]);
    var rows = _layerGridRows(layers[i]);
    var lpxW, lpxH;
    if (orientation === 'isometric') {
      lpxW = (cols + rows) * (lts / 2);
      lpxH = (cols + rows) * (lth / 2);
    } else {
      lpxW = cols * lts;
      lpxH = rows * lts;
    }
    if (lpxW > maxPxW) maxPxW = lpxW;
    if (lpxH > maxPxH) maxPxH = lpxH;
  }
  if (maxPxW === 0) {
    if (orientation === 'isometric') {
      maxPxW = (grid.width + grid.height) * (tileSize.width / 2);
      maxPxH = (grid.width + grid.height) * (tileSize.height / 2);
    } else {
      maxPxW = grid.width * tileSize.width;
      maxPxH = grid.height * tileSize.height;
    }
  }

  var w = Math.ceil(maxPxW * zoom);
  var h = Math.ceil(maxPxH * zoom);

  sceneCanvas.width = w;
  sceneCanvas.height = h;
  gridCanvas.width = w;
  gridCanvas.height = h;
  zoneCanvas.width = w;
  zoneCanvas.height = h;

  sceneCtx.imageSmoothingEnabled = false;
}

// ====== Scene Rendering ======
function renderScene() {
  sceneCtx.clearRect(0, 0, sceneCanvas.width, sceneCanvas.height);

  // Fill background with a subtle checker pattern
  var cw = tileSize.width * zoom;
  var ch = tileSize.height * zoom;
  for (var r = 0; r < grid.height; r++) {
    for (var c = 0; c < grid.width; c++) {
      sceneCtx.fillStyle = (r + c) % 2 === 0 ? '#12141f' : '#0e1019';
      sceneCtx.fillRect(c * cw, r * ch, cw, ch);
    }
  }

  // Render tile layers bottom-to-top (each at its own tile size)
  for (var li = 0; li < layers.length; li++) {
    var layer = layers[li];
    if (!layer.visible || layer.type !== 'tilelayer') continue;
    if (!layer.data) continue;

    var lts = _layerTileSize(layer);
    var lcw = lts * zoom;
    var lch = lts * zoom;
    var lcols = _layerGridCols(layer);

    for (var idx = 0; idx < layer.data.length; idx++) {
      var gid = layer.data[idx];
      if (gid <= 0) continue;

      var info = getTileInfoAt(gid, lts);
      if (!info) continue;

      var col = idx % lcols;
      var row = Math.floor(idx / lcols);

      sceneCtx.drawImage(
        info.img,
        info.sx, info.sy, info.tw, info.th,
        col * lcw, row * lch, lcw, lch
      );
    }
  }

  renderGridOverlay();
  renderZoneOverlay();
}

function renderGridOverlay() {
  gridCtx.clearRect(0, 0, gridCanvas.width, gridCanvas.height);

  var cw = tileSize.width * zoom;
  var ch = tileSize.height * zoom;
  var canvasW = gridCanvas.width;
  var canvasH = gridCanvas.height;

  if (showGrid) {
    gridCtx.strokeStyle = 'rgba(255, 255, 255, 0.06)';
    gridCtx.lineWidth = 1;

    for (var c = 0; c <= grid.width; c++) {
      var x = c * cw + 0.5;
      gridCtx.beginPath();
      gridCtx.moveTo(x, 0);
      gridCtx.lineTo(x, canvasH);
      gridCtx.stroke();
    }

    for (var r = 0; r <= grid.height; r++) {
      var y = r * ch + 0.5;
      gridCtx.beginPath();
      gridCtx.moveTo(0, y);
      gridCtx.lineTo(canvasW, y);
      gridCtx.stroke();
    }
  }

  if (showBounds) {
    var bw = scenePixels.width * zoom;
    var bh = scenePixels.height * zoom;

    gridCtx.strokeStyle = 'rgba(80, 140, 255, 0.6)';
    gridCtx.lineWidth = 2;
    gridCtx.strokeRect(-0.5, -0.5, bw + 1, bh + 1);
  }
}

function renderZoneOverlay() {
  zoneCtx.clearRect(0, 0, zoneCanvas.width, zoneCanvas.height);

  var colors = {
    collision: 'rgba(225, 112, 85, 0.35)',
    spawn: 'rgba(0, 184, 148, 0.35)',
    exit: 'rgba(253, 203, 110, 0.35)',
    trigger: 'rgba(108, 92, 231, 0.35)'
  };

  var borderColors = {
    collision: '#e17055',
    spawn: '#00b894',
    exit: '#fdcb6e',
    trigger: '#6c5ce7'
  };

  for (var i = 0; i < zones.length; i++) {
    var z = zones[i];
    var zType = z.type || 'collision';
    var x = z.x * zoom;
    var y = z.y * zoom;
    var w = z.width * zoom;
    var h = z.height * zoom;

    zoneCtx.fillStyle = colors[zType] || colors.collision;
    zoneCtx.fillRect(x, y, w, h);

    zoneCtx.strokeStyle = borderColors[zType] || borderColors.collision;
    zoneCtx.lineWidth = 2;
    zoneCtx.strokeRect(x, y, w, h);

    // Label
    zoneCtx.fillStyle = borderColors[zType] || borderColors.collision;
    zoneCtx.font = '11px sans-serif';
    zoneCtx.fillText(z.name || zType, x + 3, y + 13);
  }

  // Draw pending zone rectangle
  if (zoneDrawing && zoneStart && zoneCurrent) {
    var rx = Math.min(zoneStart.x, zoneCurrent.x) * zoom;
    var ry = Math.min(zoneStart.y, zoneCurrent.y) * zoom;
    var rw = Math.abs(zoneCurrent.x - zoneStart.x) * zoom;
    var rh = Math.abs(zoneCurrent.y - zoneStart.y) * zoom;

    zoneCtx.fillStyle = 'rgba(108, 92, 231, 0.2)';
    zoneCtx.fillRect(rx, ry, rw, rh);
    zoneCtx.strokeStyle = '#6c5ce7';
    zoneCtx.lineWidth = 2;
    zoneCtx.setLineDash([5, 3]);
    zoneCtx.strokeRect(rx, ry, rw, rh);
    zoneCtx.setLineDash([]);
  }
}

// ====== Canvas Mouse Events ======
var _rightErasing = false;

function setupCanvasEvents() {
  var container = document.getElementById('canvas-container');

  // Block context menu on canvas so right-click erase works
  container.addEventListener('contextmenu', function(e) { e.preventDefault(); });

  container.addEventListener('mousedown', function(e) {
    // Right-click: erase
    if (e.button === 2) {
      e.preventDefault();
      var pos = getCanvasPos(e);
      if (!pos) return;
      _rightErasing = true;
      painting = true;
      applyBrushAs(pos.row, pos.col, 'erase');
      return;
    }
    if (e.button !== 0) return;
    var pos = getCanvasPos(e);
    if (!pos) return;

    _rightErasing = false;
    if (activeTool === 'zone') {
      zoneDrawing = true;
      // Snap to pixel (not tile)
      zoneStart = { x: pos.col * tileSize.width, y: pos.row * tileSize.height };
      zoneCurrent = {
        x: (pos.col + 1) * tileSize.width,
        y: (pos.row + 1) * tileSize.height
      };
      renderZoneOverlay();
    } else if (activeTool === 'fill') {
      floodFill(pos.row, pos.col);
    } else {
      painting = true;
      applyBrush(pos.row, pos.col);
    }
  });

  container.addEventListener('mousemove', function(e) {
    var pos = getCanvasPos(e);
    if (pos) {
      document.getElementById('cursor-info').textContent =
        'Col: ' + pos.col + ' Row: ' + pos.row +
        ' | Layer: ' + (layers[activeLayerIndex] ? layers[activeLayerIndex].name : '--');
    }

    if (zoneDrawing && zoneStart) {
      if (!pos) return;
      zoneCurrent = {
        x: (pos.col + 1) * tileSize.width,
        y: (pos.row + 1) * tileSize.height
      };
      renderZoneOverlay();
    }

    if (painting && pos) {
      if (_rightErasing) {
        applyBrushAs(pos.row, pos.col, 'erase');
      } else {
        applyBrush(pos.row, pos.col);
      }
    }
  });

  container.addEventListener('mouseup', function(e) {
    if (zoneDrawing && zoneStart && zoneCurrent) {
      zoneDrawing = false;
      var x1 = Math.min(zoneStart.x, zoneCurrent.x);
      var y1 = Math.min(zoneStart.y, zoneCurrent.y);
      var x2 = Math.max(zoneStart.x, zoneCurrent.x);
      var y2 = Math.max(zoneStart.y, zoneCurrent.y);
      if (x2 - x1 > 0 && y2 - y1 > 0) {
        pendingZoneRect = { x: x1, y: y1, width: x2 - x1, height: y2 - y1 };
        showZonePrompt();
      }
      zoneStart = null;
      zoneCurrent = null;
      renderZoneOverlay();
    }
    painting = false;
    _rightErasing = false;
  });

  container.addEventListener('mouseleave', function() {
    painting = false;
    _rightErasing = false;
  });
}

function getCanvasPos(e) {
  var rect = sceneCanvas.getBoundingClientRect();
  var x = e.clientX - rect.left;
  var y = e.clientY - rect.top;
  var cw = tileSize.width * zoom;
  var ch = tileSize.height * zoom;
  var col = Math.floor(x / cw);
  var row = Math.floor(y / ch);
  if (col < 0 || col >= grid.width || row < 0 || row >= grid.height) return null;
  return { col: col, row: row };
}

// ====== Paint / Erase ======
function applyBrush(row, col) {
  applyBrushAs(row, col, activeTool);
}

function applyBrushAs(row, col, tool) {
  var layer = layers[activeLayerIndex];
  if (!layer || layer.type !== 'tilelayer') return;

  var idx = row * grid.width + col;
  var newVal = tool === 'erase' ? 0 : activeTile;

  if (layer.data[idx] === newVal) return;

  layer.data[idx] = newVal;
  if (newVal > 0) trackRecentTile(newVal);
  renderScene();
}

// ====== Flood Fill ======
function floodFill(startRow, startCol) {
  var layer = layers[activeLayerIndex];
  if (!layer || layer.type !== 'tilelayer') return;

  var target = layer.data[startRow * grid.width + startCol];
  var replacement = activeTile;
  if (target === replacement) return;

  var stack = [[startRow, startCol]];
  var visited = {};

  while (stack.length > 0) {
    var cell = stack.pop();
    var r = cell[0];
    var c = cell[1];
    var key = r + ',' + c;

    if (visited[key]) continue;
    if (r < 0 || r >= grid.height || c < 0 || c >= grid.width) continue;

    var idx = r * grid.width + c;
    if (layer.data[idx] !== target) continue;

    visited[key] = true;
    layer.data[idx] = replacement;

    stack.push([r - 1, c]);
    stack.push([r + 1, c]);
    stack.push([r, c - 1]);
    stack.push([r, c + 1]);
  }

  if (replacement > 0) trackRecentTile(replacement);
  renderScene();
}

// ====== Tools ======
function setTool(tool) {
  activeTool = tool;
  document.querySelectorAll('.tool-btn').forEach(function(btn) {
    btn.classList.toggle('active', btn.dataset.tool === tool);
  });
  // Change cursor
  var container = document.getElementById('canvas-container');
  if (tool === 'zone') {
    container.style.cursor = 'crosshair';
  } else if (tool === 'fill') {
    container.style.cursor = 'cell';
  } else if (tool === 'erase') {
    container.style.cursor = 'not-allowed';
  } else {
    container.style.cursor = 'crosshair';
  }
}

// ====== Zoom ======
function zoomIn() {
  if (zoom >= 16) return;
  zoom++;
  document.getElementById('zoom-level').textContent = zoom + 'x';
  resizeCanvases();
  renderScene();
}

function zoomOut() {
  if (zoom <= 1) return;
  zoom--;
  document.getElementById('zoom-level').textContent = zoom + 'x';
  resizeCanvases();
  renderScene();
}

// ====== Palette Zoom ======
function palZoomIn() {
  if (palZoom >= 8) return;
  palZoom++;
  document.getElementById('pal-zoom-level').textContent = palZoom + 'x';
  buildPaletteGrid(activeTilesetIndex);
  renderRecentTiles();
}

function palZoomOut() {
  if (palZoom <= 1) return;
  palZoom--;
  document.getElementById('pal-zoom-level').textContent = palZoom + 'x';
  buildPaletteGrid(activeTilesetIndex);
  renderRecentTiles();
}

// ====== Grid Toggle ======
function toggleGrid() {
  showGrid = !showGrid;
  document.getElementById('grid-toggle').classList.toggle('active', showGrid);
  renderGridOverlay();
}

function toggleBounds() {
  showBounds = !showBounds;
  document.getElementById('bounds-toggle').classList.toggle('active', showBounds);
  renderGridOverlay();
}

// ====== Layers ======
var _dragLayerIdx = -1;

function renderLayers() {
  var container = document.getElementById('layer-list');
  container.innerHTML = '';

  for (var i = 0; i < layers.length; i++) {
    (function(idx) {
      var layer = layers[idx];
      var div = document.createElement('div');
      div.className = 'layer-item' + (idx === activeLayerIndex ? ' active' : '');
      div.draggable = true;
      div.dataset.idx = idx;

      // Drag handle — clicking it selects the layer
      var handle = document.createElement('span');
      handle.className = 'layer-drag-handle';
      handle.innerHTML = '&#9776;';
      handle.title = 'Drag to reorder';
      handle.addEventListener('click', function(e) {
        e.stopPropagation();
        activeLayerIndex = idx;
        syncToActiveLayer();
        renderLayers();
      });

      // Drag events
      div.addEventListener('dragstart', function(e) {
        _dragLayerIdx = idx;
        e.dataTransfer.effectAllowed = 'move';
        this.style.opacity = '0.4';
      });
      div.addEventListener('dragend', function() {
        this.style.opacity = '';
        _dragLayerIdx = -1;
        container.querySelectorAll('.layer-item').forEach(function(el) {
          el.classList.remove('drag-over');
        });
      });
      div.addEventListener('dragover', function(e) {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        container.querySelectorAll('.layer-item').forEach(function(el) {
          el.classList.remove('drag-over');
        });
        this.classList.add('drag-over');
      });
      div.addEventListener('drop', function(e) {
        e.preventDefault();
        this.classList.remove('drag-over');
        var targetIdx = parseInt(this.dataset.idx);
        if (_dragLayerIdx < 0 || _dragLayerIdx === targetIdx) return;
        var moved = layers.splice(_dragLayerIdx, 1)[0];
        layers.splice(targetIdx, 0, moved);
        if (activeLayerIndex === _dragLayerIdx) activeLayerIndex = targetIdx;
        else if (_dragLayerIdx < activeLayerIndex && targetIdx >= activeLayerIndex) activeLayerIndex--;
        else if (_dragLayerIdx > activeLayerIndex && targetIdx <= activeLayerIndex) activeLayerIndex++;
        _dragLayerIdx = -1;
        renderLayers();
        renderScene();
      });

      var name = document.createElement('span');
      name.className = 'layer-name';
      name.textContent = layer.name;
      name.contentEditable = true;
      name.spellcheck = false;
      name.addEventListener('blur', function() {
        var newName = this.textContent.trim();
        if (newName) layer.name = newName;
        else this.textContent = layer.name;
      });
      name.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') { e.preventDefault(); this.blur(); }
        if (e.key === 'Escape') { this.textContent = layer.name; this.blur(); }
      });
      name.addEventListener('click', function(e) { e.stopPropagation(); });

      var type = document.createElement('span');
      type.className = 'layer-type';
      type.textContent = layer.type === 'tilelayer' ? 'tile' : 'obj';

      var visBtn = document.createElement('button');
      visBtn.className = 'layer-vis-btn' + (layer.visible ? '' : ' hidden');
      visBtn.innerHTML = layer.visible ? '&#128065;' : '&#128065;';
      visBtn.title = layer.visible ? 'Hide' : 'Show';
      visBtn.addEventListener('click', function() {
        layer.visible = !layer.visible;
        renderLayers();
        renderScene();
      });

      var delBtn = document.createElement('button');
      delBtn.className = 'layer-del-btn';
      delBtn.innerHTML = '&#215;';
      delBtn.title = 'Delete layer';
      delBtn.addEventListener('click', function() {
        if (layers.length <= 1) return;
        layers.splice(idx, 1);
        if (activeLayerIndex >= layers.length) activeLayerIndex = layers.length - 1;
        renderLayers();
        renderScene();
      });

      div.appendChild(handle);
      div.appendChild(name);
      div.appendChild(type);
      div.appendChild(visBtn);
      div.appendChild(delBtn);
      container.appendChild(div);
    })(i);
  }
}

function addLayer(type) {
  var name = type === 'tilelayer'
    ? 'Layer ' + (layers.length + 1)
    : 'Objects ' + (layers.length + 1);

  var layer = {
    name: name,
    type: type,
    visible: true
  };

  if (type === 'tilelayer') {
    layer.tileSize = tileSize.width;
    var lc = _layerGridCols(layer);
    var lr = _layerGridRows(layer);
    layer.data = new Array(lc * lr).fill(0);
    layer._prevCols = lc;
  } else {
    layer.objects = [];
  }

  layers.push(layer);
  activeLayerIndex = layers.length - 1;
  syncToActiveLayer();
  renderLayers();

  // Focus the name for inline rename
  var nameEl = document.querySelector('.layer-item.active .layer-name');
  if (nameEl) {
    nameEl.focus();
    var range = document.createRange();
    range.selectNodeContents(nameEl);
    window.getSelection().removeAllRanges();
    window.getSelection().addRange(range);
  }
}

// ====== Zones ======
function renderZones() {
  var container = document.getElementById('zone-list');
  container.innerHTML = '';

  for (var i = 0; i < zones.length; i++) {
    (function(idx) {
      var z = zones[idx];
      var div = document.createElement('div');
      div.className = 'zone-item';

      var type = document.createElement('span');
      type.className = 'zone-type zone-type-' + (z.type || 'collision');
      type.textContent = z.type || 'collision';

      var name = document.createElement('span');
      name.className = 'zone-name';
      name.textContent = z.name + ' (' + z.x + ',' + z.y + ' ' + z.width + 'x' + z.height + ')';

      var delBtn = document.createElement('button');
      delBtn.className = 'zone-del-btn';
      delBtn.innerHTML = '&#215;';
      delBtn.title = 'Delete zone';
      delBtn.addEventListener('click', function() {
        zones.splice(idx, 1);
        renderZones();
        renderZoneOverlay();
      });

      div.appendChild(type);
      div.appendChild(name);
      div.appendChild(delBtn);
      container.appendChild(div);
    })(i);
  }
}

function startAddZone() {
  setTool('zone');
}

function showZonePrompt() {
  document.getElementById('zone-prompt').classList.add('visible');
  document.getElementById('zone-name-input').value = '';
  document.getElementById('zone-name-input').focus();
}

function cancelZonePrompt() {
  document.getElementById('zone-prompt').classList.remove('visible');
  pendingZoneRect = null;
}

function confirmZonePrompt() {
  var name = document.getElementById('zone-name-input').value.trim();
  var type = document.getElementById('zone-type-input').value;
  if (!name) name = type + '_' + (zones.length + 1);

  if (pendingZoneRect) {
    zones.push({
      name: name,
      type: type,
      x: pendingZoneRect.x,
      y: pendingZoneRect.y,
      width: pendingZoneRect.width,
      height: pendingZoneRect.height
    });
    pendingZoneRect = null;
  }

  document.getElementById('zone-prompt').classList.remove('visible');
  renderZones();
  renderZoneOverlay();
}

// Allow Enter to confirm zone prompt
document.getElementById('zone-name-input').addEventListener('keydown', function(e) {
  if (e.key === 'Enter') { e.preventDefault(); confirmZonePrompt(); }
  if (e.key === 'Escape') { cancelZonePrompt(); }
});

// ====== Tile Size ======
// ====== Sync UI to Active Layer ======
function syncToActiveLayer() {
  var layer = layers[activeLayerIndex];
  if (!layer || layer.type !== 'tilelayer') return;

  var size = _layerTileSize(layer);
  var oldSize = tileSize.width;
  var sizeChanged = size !== oldSize;

  if (sizeChanged) {
    recentTilesBySize[oldSize] = recentTiles;
    activeTileBySize[oldSize] = activeTile;

    tileSize.width = size;
    tileSize.height = size;
    for (var i = 0; i < tilesetConfigs.length; i++) {
      tilesetConfigs[i].tile_width = size;
      tilesetConfigs[i].tile_height = size;
    }

    recentTiles = recentTilesBySize[size] || {};
    activeTile = activeTileBySize[size] || 0;
  }

  // Always sync grid to active layer's dimensions
  grid.width = _layerGridCols(layer);
  grid.height = _layerGridRows(layer);

  document.querySelectorAll('.tile-size-btn').forEach(function(btn) {
    btn.classList.toggle('active', parseInt(btn.textContent) === size);
  });
  updateGridTileInfo();

  if (sizeChanged) {
    loadTilesets();
    renderRecentTiles();
  }
  resizeCanvases();
  renderScene();
}

// ====== Per-Layer Tile Size ======

function _layerTileSize(layer) {
  return layer.tileSize || tileSize.width;
}

function _layerGridCols(layer) {
  return Math.ceil(scenePixels.width / _layerTileSize(layer));
}

function _layerGridRows(layer) {
  return Math.ceil(scenePixels.height / _layerTileSize(layer));
}

// ====== Isometric Coordinate Transforms ======
// tileToScreen: returns top-left corner of tile bounding rect in canvas pixels (unzoomed)
function tileToScreen(col, row, tileW, tileH) {
  if (orientation === 'isometric') {
    var originX = grid.height * (tileW / 2);
    return {
      x: originX + (col - row) * (tileW / 2),
      y: (col + row) * (tileH / 2)
    };
  }
  return { x: col * tileW, y: row * tileH };
}

// screenToTile: converts canvas pixel position (unzoomed) to tile col/row
function screenToTile(screenX, screenY, tileW, tileH) {
  if (orientation === 'isometric') {
    var originX = grid.height * (tileW / 2);
    var dx = screenX - originX;
    return {
      col: Math.floor((dx / (tileW / 2) + screenY / (tileH / 2)) / 2),
      row: Math.floor((screenY / (tileH / 2) - dx / (tileW / 2)) / 2)
    };
  }
  return {
    col: Math.floor(screenX / tileW),
    row: Math.floor(screenY / tileH)
  };
}

function _hasTileData(layerIdx) {
  var layer = layers[layerIdx];
  if (!layer || layer.type !== 'tilelayer' || !layer.data) return false;
  for (var i = 0; i < layer.data.length; i++) {
    if (layer.data[i] > 0) return true;
  }
  return false;
}

function _clearLayerData(layerIdx) {
  var layer = layers[layerIdx];
  if (layer && layer.type === 'tilelayer') {
    var cols = _layerGridCols(layer);
    var rows = _layerGridRows(layer);
    layer.data = new Array(cols * rows).fill(0);
  }
}

function _resizeLayerData(layer) {
  var cols = _layerGridCols(layer);
  var rows = _layerGridRows(layer);
  var needed = cols * rows;
  if (!layer.data || layer.data.length === needed) return;
  // Grow or shrink — preserve top-left data
  var oldCols = layer._prevCols || cols;
  var oldData = layer.data;
  var newData = new Array(needed).fill(0);
  var copyC = Math.min(oldCols, cols);
  var copyR = Math.min(Math.floor(oldData.length / oldCols), rows);
  for (var r = 0; r < copyR; r++) {
    for (var c = 0; c < copyC; c++) {
      newData[r * cols + c] = oldData[r * oldCols + c];
    }
  }
  layer.data = newData;
  layer._prevCols = cols;
}

function setTileSize(size) {
  var layer = layers[activeLayerIndex];
  if (!layer || layer.type !== 'tilelayer') return;
  if (_layerTileSize(layer) === size) return;

  if (_hasTileData(activeLayerIndex)) {
    _pendingTileSize = size;
    document.getElementById('tile-size-confirm').classList.add('visible');
  } else {
    _applyLayerTileSize(activeLayerIndex, size);
  }
}

var _pendingTileSize = 0;

function tileSizeConfirmClear() {
  document.getElementById('tile-size-confirm').classList.remove('visible');
  _clearLayerData(activeLayerIndex);
  _applyLayerTileSize(activeLayerIndex, _pendingTileSize);
}

function tileSizeConfirmCancel() {
  document.getElementById('tile-size-confirm').classList.remove('visible');
}

// ====== Orientation ======
function setOrientation(mode) {
  if (orientation === mode) return;

  var hasData = false;
  for (var i = 0; i < layers.length; i++) {
    if (_hasTileData(i)) { hasData = true; break; }
  }

  if (hasData) {
    _pendingOrientation = mode;
    document.getElementById('orientation-confirm').classList.add('visible');
  } else {
    _applyOrientation(mode);
  }
}

function orientationConfirmClear() {
  document.getElementById('orientation-confirm').classList.remove('visible');
  for (var i = 0; i < layers.length; i++) { _clearLayerData(i); }
  _applyOrientation(_pendingOrientation);
  _pendingOrientation = null;
}

function orientationConfirmCancel() {
  document.getElementById('orientation-confirm').classList.remove('visible');
  _pendingOrientation = null;
  // Re-sync toggle buttons to current orientation
  _syncOrientationButtons();
}

function _applyOrientation(mode) {
  orientation = mode;
  if (mode === 'isometric') {
    // Force 2:1 aspect ratio: tileH = tileW / 2
    tileSize.height = Math.max(1, Math.floor(tileSize.width / 2));
  } else {
    tileSize.height = tileSize.width;
  }
  _syncOrientationButtons();
  resizeCanvases();
  renderScene();
}

function _syncOrientationButtons() {
  document.getElementById('orient-ortho').classList.toggle('active', orientation === 'orthogonal');
  document.getElementById('orient-iso').classList.toggle('active', orientation === 'isometric');
}

function _applyLayerTileSize(layerIdx, size) {
  var layer = layers[layerIdx];
  var oldSize = _layerTileSize(layer);
  recentTilesBySize[oldSize] = recentTiles;
  activeTileBySize[oldSize] = activeTile;

  layer.tileSize = size;

  // Update active tile size to match active layer
  tileSize.width = size;
  tileSize.height = size;
  for (var i = 0; i < tilesetConfigs.length; i++) {
    tilesetConfigs[i].tile_width = size;
    tilesetConfigs[i].tile_height = size;
  }

  recentTiles = recentTilesBySize[size] || {};
  activeTile = activeTileBySize[size] || 0;

  // Resize this layer's data to new grid dimensions
  _resizeLayerData(layer);

  // Update grid to match active layer (for painting/cursor)
  grid.width = _layerGridCols(layer);
  grid.height = _layerGridRows(layer);

  document.querySelectorAll('.tile-size-btn').forEach(function(btn) {
    btn.classList.toggle('active', parseInt(btn.textContent) === size);
  });
  updateGridTileInfo();
  loadTilesets();
  renderRecentTiles();
  resizeCanvases();
  renderScene();
}

// ====== Scene Resize ======
function resizeScene() {
  var newW = parseInt(document.getElementById('scene-width-px').value);
  var newH = parseInt(document.getElementById('scene-height-px').value);
  if (isNaN(newW) || isNaN(newH) || newW < 8 || newH < 8) return;

  scenePixels.width = newW;
  scenePixels.height = newH;

  // Resize each layer's data to its new grid dimensions
  for (var i = 0; i < layers.length; i++) {
    if (layers[i].type === 'tilelayer') {
      _resizeLayerData(layers[i]);
    }
  }

  // Update active grid
  var active = layers[activeLayerIndex];
  if (active && active.type === 'tilelayer') {
    grid.width = _layerGridCols(active);
    grid.height = _layerGridRows(active);
  }

  updateGridTileInfo();
  resizeCanvases();
  renderScene();
}

// ====== Send to Claude ======
function sendToClaude() {
  var payload = {
    grid: grid,
    tile_size: tileSize,
    tilesets: tilesetConfigs,
    scene_pixels: scenePixels,
    layers: layers.map(function(l) {
      var out = { name: l.name, type: l.type };
      if (l.type === 'tilelayer') {
        out.data = Array.from(l.data);
        out.tileSize = l.tileSize || tileSize.width;
        out.gridCols = _layerGridCols(l);
        out.gridRows = _layerGridRows(l);
      }
      if (l.type === 'objectgroup') out.objects = l.objects || [];
      return out;
    }),
    zones: zones
  };

  fetch('/api/designer/submit', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  }).then(function(resp) {
    if (resp.ok) {
      document.getElementById('status-banner').classList.add('visible');
      document.getElementById('send-btn').disabled = true;
      document.getElementById('send-btn').textContent = 'Sent!';
    }
  }).catch(function() {
    document.getElementById('send-btn').textContent = 'Error - try again';
  });
}

// ====== Export Tiled JSON ======
function exportTiled() {
  window.open('/api/designer/export', '_blank');
}

// ====== Keyboard Shortcuts ======
document.addEventListener('keydown', function(e) {
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT' || e.target.contentEditable === 'true') return;

  switch (e.key.toLowerCase()) {
    case 'b': setTool('paint'); break;
    case 'e': setTool('erase'); break;
    case 'g': setTool('fill'); break;
    case 'z': setTool('zone'); break;
    case '=': case '+': e.preventDefault(); zoomIn(); break;
    case '-': e.preventDefault(); zoomOut(); break;
    case 'h': toggleGrid(); break;
  }
});

// ====== Palette Resize Handle ======
(function() {
  var handle = document.getElementById('palette-resize-handle');
  var panel = document.getElementById('palette-panel');
  var dragging = false;

  handle.addEventListener('mousedown', function(e) {
    dragging = true;
    handle.classList.add('dragging');
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
    e.preventDefault();
  });

  document.addEventListener('mousemove', function(e) {
    if (!dragging) return;
    var newWidth = e.clientX;
    var maxWidth = window.innerWidth * 0.4;
    if (newWidth < 120) newWidth = 120;
    if (newWidth > maxWidth) newWidth = maxWidth;
    panel.style.width = newWidth + 'px';
  });

  document.addEventListener('mouseup', function() {
    if (!dragging) return;
    dragging = false;
    handle.classList.remove('dragging');
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
  });
})();

// ====== Start ======
init();

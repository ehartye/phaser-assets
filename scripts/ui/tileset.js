/**
 * tileset.js — shared spritesheet math utilities
 * Used by: sprite-inspector, scene-designer
 *
 * All functions are pure; no global state.
 */

/**
 * Compute the pixel position of a tile in a spritesheet.
 * @returns {{sx: number, sy: number}}
 */
function tileSourceXY(col, row, tileW, tileH, margin, spacing) {
  return {
    sx: margin + col * (tileW + spacing),
    sy: margin + row * (tileH + spacing),
  };
}

/**
 * Convert a 0-based tile index to column and row.
 * @returns {{col: number, row: number}}
 */
function tileColRow(index, cols) {
  return { col: index % cols, row: Math.floor(index / cols) };
}

/**
 * Compute the number of columns and rows in a spritesheet image.
 * @returns {{cols: number, rows: number}}
 */
function sheetLayout(imgWidth, imgHeight, tileW, tileH, margin, spacing) {
  const cols = Math.floor((imgWidth - margin + spacing) / (tileW + spacing));
  const rows = Math.floor((imgHeight - margin + spacing) / (tileH + spacing));
  return { cols, rows };
}

/**
 * Draw a single tile from a spritesheet onto a canvas context.
 * dx/dy/dw/dh define destination rect; tileW/tileH define source rect size.
 */
function drawTile(ctx, img, index, cols, tileW, tileH, margin, spacing, dx, dy, dw, dh) {
  const { col, row } = tileColRow(index, cols);
  const { sx, sy } = tileSourceXY(col, row, tileW, tileH, margin, spacing);
  ctx.drawImage(img, sx, sy, tileW, tileH, dx, dy, dw, dh);
}

/**
 * Get the tile count for a tileset config.
 * Works for both spritesheets and sprite-collections.
 */
function tilesetTileCount(ts, img) {
  if (ts.type === 'sprite-collection') {
    return (ts.sprites || []).length;
  }
  var layout = sheetLayout(img.width, img.height, ts.tile_width, ts.tile_height, ts.margin || 0, ts.spacing || 0);
  return layout.cols * layout.rows;
}

/**
 * Look up a tile within a single tileset by local index.
 * Returns { img, sx, sy, tw, th, cols, rows, isCollection } or null.
 * overrideTileSize: optional tile size override for spritesheets.
 */
function tilesetLookup(ts, tsImages, localIdx, overrideTileSize) {
  if (ts.type === 'sprite-collection') {
    var img = tsImages[localIdx];
    if (!img || !img.naturalWidth) return null;
    return {
      img: img, sx: 0, sy: 0,
      tw: img.naturalWidth, th: img.naturalHeight,
      cols: 1, rows: 1,
      isCollection: true
    };
  }
  var img = tsImages;
  var tw = overrideTileSize || ts.tile_width;
  var th = overrideTileSize || ts.tile_height;
  var margin = ts.margin || 0;
  var spacing = ts.spacing || 0;
  var layout = sheetLayout(img.width, img.height, tw, th, margin, spacing);
  var cr = tileColRow(localIdx, layout.cols);
  var pos = tileSourceXY(cr.col, cr.row, tw, th, margin, spacing);
  return {
    img: img, sx: pos.sx, sy: pos.sy,
    tw: tw, th: th,
    cols: layout.cols, rows: layout.rows,
    isCollection: false
  };
}

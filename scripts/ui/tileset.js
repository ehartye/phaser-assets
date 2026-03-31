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

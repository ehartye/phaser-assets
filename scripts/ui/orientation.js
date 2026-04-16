/**
 * orientation.js — orientation strategy pattern for scene designer
 * Each strategy provides coordinate transforms, canvas sizing, and grid rendering.
 */

var OrientationStrategies = {
  orthogonal: {
    name: 'orthogonal',

    defaultTileHeight: function(tileWidth) {
      return tileWidth;
    },

    canvasSize: function(cols, rows, tileW, tileH) {
      return { width: cols * tileW, height: rows * tileH };
    },

    tileToScreen: function(col, row, tileW, tileH) {
      return { x: col * tileW, y: row * tileH };
    },

    screenToTile: function(screenX, screenY, tileW, tileH) {
      return {
        col: Math.floor(screenX / tileW),
        row: Math.floor(screenY / tileH)
      };
    },

    renderOrder: function(cols, rows, callback) {
      for (var r = 0; r < rows; r++) {
        for (var c = 0; c < cols; c++) {
          callback(c, r);
        }
      }
    },

    drawGridLines: function(ctx, cols, rows, tileW, tileH, zoom) {
      var canvasW = cols * tileW * zoom;
      var canvasH = rows * tileH * zoom;
      for (var c = 0; c <= cols; c++) {
        var x = c * tileW * zoom + 0.5;
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, canvasH);
        ctx.stroke();
      }
      for (var r = 0; r <= rows; r++) {
        var y = r * tileH * zoom + 0.5;
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(canvasW, y);
        ctx.stroke();
      }
    },

    drawBounds: function(ctx, cols, rows, tileW, tileH, zoom) {
      var bw = cols * tileW * zoom;
      var bh = rows * tileH * zoom;
      ctx.strokeRect(-0.5, -0.5, bw + 1, bh + 1);
    },

    drawTileAt: function(ctx, info, col, row, tileW, tileH, zoom) {
      ctx.drawImage(info.img, info.sx, info.sy, info.tw, info.th,
        col * tileW * zoom, row * tileH * zoom, tileW * zoom, tileH * zoom);
    }
  },

  isometric: {
    name: 'isometric',

    defaultTileHeight: function(tileWidth) {
      return Math.max(1, Math.floor(tileWidth / 2));
    },

    canvasSize: function(cols, rows, tileW, tileH) {
      // Add vertical padding for tile overhang (3D block sprites extend above
      // the top diamond row). tileH is the padding — enough for a tile whose
      // depth equals its diamond height.
      return {
        width: (cols + rows) * (tileW / 2),
        height: (cols + rows) * (tileH / 2) + tileH
      };
    },

    tileToScreen: function(col, row, tileW, tileH, originRows) {
      var originX = (originRows || 0) * (tileW / 2);
      // Shift down by tileH to match the canvas padding from canvasSize
      return {
        x: originX + (col - row) * (tileW / 2),
        y: (col + row) * (tileH / 2) + tileH
      };
    },

    screenToTile: function(screenX, screenY, tileW, tileH, originRows) {
      var originX = (originRows || 0) * (tileW / 2);
      var dx = screenX - originX;
      // Subtract tileH padding added by tileToScreen/canvasSize
      var sy = screenY - tileH;
      return {
        col: Math.floor((dx / (tileW / 2) + sy / (tileH / 2)) / 2),
        row: Math.floor((sy / (tileH / 2) - dx / (tileW / 2)) / 2)
      };
    },

    renderOrder: function(cols, rows, callback) {
      for (var sum = 0; sum <= cols + rows - 2; sum++) {
        for (var c = 0; c < cols; c++) {
          var r = sum - c;
          if (r < 0 || r >= rows) continue;
          callback(c, r);
        }
      }
    },

    drawGridLines: function(ctx, cols, rows, tileW, tileH, zoom) {
      var self = this;
      for (var c = 0; c <= cols; c++) {
        ctx.beginPath();
        var a = self.tileToScreen(c, 0, tileW, tileH, rows);
        var b = self.tileToScreen(c, rows, tileW, tileH, rows);
        ctx.moveTo(a.x * zoom + 0.5, a.y * zoom + 0.5);
        ctx.lineTo(b.x * zoom + 0.5, b.y * zoom + 0.5);
        ctx.stroke();
      }
      for (var r = 0; r <= rows; r++) {
        ctx.beginPath();
        var a = self.tileToScreen(0, r, tileW, tileH, rows);
        var b = self.tileToScreen(cols, r, tileW, tileH, rows);
        ctx.moveTo(a.x * zoom + 0.5, a.y * zoom + 0.5);
        ctx.lineTo(b.x * zoom + 0.5, b.y * zoom + 0.5);
        ctx.stroke();
      }
    },

    drawBounds: function(ctx, cols, rows, tileW, tileH, zoom) {
      var self = this;
      var top    = self.tileToScreen(0, 0, tileW, tileH, rows);
      var right  = self.tileToScreen(cols, 0, tileW, tileH, rows);
      var bottom = self.tileToScreen(cols, rows, tileW, tileH, rows);
      var left   = self.tileToScreen(0, rows, tileW, tileH, rows);
      ctx.beginPath();
      ctx.moveTo(top.x * zoom, top.y * zoom);
      ctx.lineTo(right.x * zoom, right.y * zoom);
      ctx.lineTo(bottom.x * zoom, bottom.y * zoom);
      ctx.lineTo(left.x * zoom, left.y * zoom);
      ctx.closePath();
      ctx.stroke();
    },

    drawTileAt: function(ctx, info, col, row, tileW, tileH, zoom, originRows) {
      var pos = this.tileToScreen(col, row, tileW, tileH, originRows);
      var srcW = info.tw, srcH = info.th;

      // Scale width to diamond tile width; preserve aspect ratio for height
      // so 3D block tiles (with depth/sides) extend upward naturally
      var destW = tileW * zoom;
      var destH = (srcH / srcW) * tileW * zoom;

      // pos is the top vertex of the diamond
      var destX = (pos.x - tileW / 2) * zoom;
      // Bottom of sprite anchors to bottom of diamond; depth extends upward
      var destY = (pos.y + tileH) * zoom - destH;
      ctx.drawImage(info.img, info.sx, info.sy, srcW, srcH, destX, destY, destW, destH);
    }
  }
};

function getOrientationStrategy() {
  return OrientationStrategies[orientation] || OrientationStrategies.orthogonal;
}

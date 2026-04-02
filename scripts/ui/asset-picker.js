/* Shared asset picker — exposes window.openAssetPicker(callback) */

(function () {
  'use strict';

  var _el = null;
  var _allPaths = [];
  var _filtered = [];
  var _page = 0;
  var _highlighted = -1;
  var _callback = null;
  var PAGE_SIZE = 16;

  // ---- Fuzzy scoring ----
  function fuzzyScore(path, query) {
    if (!query) return 1;
    var s = path.toLowerCase();
    var q = query.toLowerCase();
    var i = 0, j = 0, score = 0, last = -1;
    while (i < q.length && j < s.length) {
      if (q[i] === s[j]) {
        score += (j === last + 1) ? 2 : 1;
        last = j;
        i++;
      }
      j++;
    }
    return i === q.length ? score : 0;
  }

  function applyFilter(query) {
    if (!query) {
      _filtered = _allPaths.slice();
    } else {
      _filtered = _allPaths
        .map(function (p) { return { path: p, score: fuzzyScore(p, query) }; })
        .filter(function (x) { return x.score > 0; })
        .sort(function (a, b) { return b.score - a.score; })
        .map(function (x) { return x.path; });
    }
    _page = 0;
    _highlighted = -1;
    renderGrid();
  }

  // ---- Rendering ----
  function renderGrid() {
    if (!_el) return;
    var grid = _el.querySelector('#ap-grid');
    grid.innerHTML = '';

    var start = _page * PAGE_SIZE;
    var pageItems = _filtered.slice(start, start + PAGE_SIZE);
    var totalPages = Math.max(1, Math.ceil(_filtered.length / PAGE_SIZE));

    if (pageItems.length === 0) {
      var empty = document.createElement('div');
      empty.id = 'ap-empty';
      empty.textContent = _allPaths.length === 0 ? 'Loading…' : 'No images match';
      grid.appendChild(empty);
    } else {
      pageItems.forEach(function (path, i) {
        var card = document.createElement('div');
        card.className = 'ap-card' + (i === _highlighted ? ' ap-highlighted' : '');
        card.dataset.path = path;

        var img = document.createElement('img');
        img.src = '/inspector/image?path=' + encodeURIComponent(path);
        img.className = 'ap-thumb';
        img.alt = '';

        var label = document.createElement('div');
        label.className = 'ap-label';
        var parts = path.replace(/\\/g, '/').split('/');
        label.textContent = parts[parts.length - 1];
        label.title = path;

        card.appendChild(img);
        card.appendChild(label);
        card.addEventListener('click', function () { select(path); });
        card.addEventListener('mouseenter', function () {
          _highlighted = i;
          updateHighlight();
        });
        grid.appendChild(card);
      });
    }

    _el.querySelector('#ap-page-info').textContent =
      'Page ' + (_page + 1) + ' of ' + totalPages + ' — ' + _filtered.length + ' images';
    _el.querySelector('#ap-prev').disabled = _page === 0;
    _el.querySelector('#ap-next').disabled = _page >= totalPages - 1;
  }

  function updateHighlight() {
    if (!_el) return;
    _el.querySelectorAll('.ap-card').forEach(function (c, i) {
      c.classList.toggle('ap-highlighted', i === _highlighted);
    });
  }

  // ---- Actions ----
  function select(path) {
    close();
    if (_callback) _callback(path);
  }

  function close() {
    if (_el) { _el.remove(); _el = null; }
    document.removeEventListener('keydown', onKey);
  }

  function onKey(e) {
    if (!_el) return;
    var cards = _el.querySelectorAll('.ap-card');
    if (e.key === 'Escape') {
      close();
    } else if (e.key === 'Enter') {
      if (_highlighted >= 0 && cards[_highlighted]) {
        select(cards[_highlighted].dataset.path);
      }
    } else if (e.key === 'ArrowRight') {
      _highlighted = Math.min(_highlighted + 1, cards.length - 1);
      updateHighlight();
      e.preventDefault();
    } else if (e.key === 'ArrowLeft') {
      _highlighted = Math.max(_highlighted - 1, 0);
      updateHighlight();
      e.preventDefault();
    }
  }

  // ---- Build modal DOM ----
  function buildModal() {
    var overlay = document.createElement('div');
    overlay.id = 'asset-picker-overlay';

    var modal = document.createElement('div');
    modal.id = 'ap-modal';
    modal.addEventListener('click', function (e) { e.stopPropagation(); });

    var header = document.createElement('div');
    header.id = 'ap-header';
    var title = document.createElement('h2');
    title.textContent = 'Discover Sheets';
    var closeBtn = document.createElement('button');
    closeBtn.id = 'ap-close';
    closeBtn.textContent = '✕';
    closeBtn.addEventListener('click', close);
    header.appendChild(title);
    header.appendChild(closeBtn);

    var filterRow = document.createElement('div');
    filterRow.id = 'ap-filter-row';
    var filterInput = document.createElement('input');
    filterInput.id = 'ap-filter';
    filterInput.type = 'text';
    filterInput.placeholder = 'Filter by filename…';
    filterInput.autocomplete = 'off';
    filterInput.addEventListener('input', function () { applyFilter(this.value.trim()); });
    filterRow.appendChild(filterInput);

    var grid = document.createElement('div');
    grid.id = 'ap-grid';

    var pagination = document.createElement('div');
    pagination.id = 'ap-pagination';
    var prevBtn = document.createElement('button');
    prevBtn.id = 'ap-prev';
    prevBtn.className = 'btn btn-outline';
    prevBtn.textContent = '← Prev';
    prevBtn.addEventListener('click', function () {
      if (_page > 0) { _page--; _highlighted = -1; renderGrid(); }
    });
    var pageInfo = document.createElement('span');
    pageInfo.id = 'ap-page-info';
    var nextBtn = document.createElement('button');
    nextBtn.id = 'ap-next';
    nextBtn.className = 'btn btn-outline';
    nextBtn.textContent = 'Next →';
    nextBtn.addEventListener('click', function () {
      var total = Math.max(1, Math.ceil(_filtered.length / PAGE_SIZE));
      if (_page < total - 1) { _page++; _highlighted = -1; renderGrid(); }
    });
    pagination.appendChild(prevBtn);
    pagination.appendChild(pageInfo);
    pagination.appendChild(nextBtn);

    modal.appendChild(header);
    modal.appendChild(filterRow);
    modal.appendChild(grid);
    modal.appendChild(pagination);
    overlay.appendChild(modal);

    // Click backdrop to close
    overlay.addEventListener('click', close);

    return overlay;
  }

  // ---- Public API ----
  window.openAssetPicker = function (callback) {
    if (_el) close();
    _callback = callback;
    _allPaths = [];
    _filtered = [];
    _page = 0;
    _highlighted = -1;

    _el = buildModal();
    document.body.appendChild(_el);
    _el.querySelector('#ap-filter').focus();
    document.addEventListener('keydown', onKey);

    renderGrid(); // shows "Loading…"

    fetch('/api/assets/list')
      .then(function (r) { return r.json(); })
      .then(function (paths) {
        _allPaths = paths;
        _filtered = paths.slice();
        renderGrid();
      })
      .catch(function () {
        if (_el) {
          var grid = _el.querySelector('#ap-grid');
          grid.innerHTML = '<div id="ap-empty">Failed to load asset list</div>';
        }
      });
  };

  window.openFolderPicker = function(callback) {
    if (_el) close();
    _callback = null;
    var folderCallback = callback;

    var overlay = document.createElement('div');
    overlay.id = 'asset-picker-overlay';

    var modal = document.createElement('div');
    modal.id = 'ap-modal';
    modal.addEventListener('click', function(e) { e.stopPropagation(); });

    var header = document.createElement('div');
    header.id = 'ap-header';
    var title = document.createElement('h2');
    title.textContent = 'Load Folder as Tileset';
    var closeBtn = document.createElement('button');
    closeBtn.id = 'ap-close';
    closeBtn.textContent = '\u2715';
    closeBtn.addEventListener('click', function() {
      overlay.remove();
      document.removeEventListener('keydown', folderKeyHandler);
    });
    header.appendChild(title);
    header.appendChild(closeBtn);

    var filterRow = document.createElement('div');
    filterRow.id = 'ap-filter-row';
    var filterInput = document.createElement('input');
    filterInput.id = 'ap-filter';
    filterInput.type = 'text';
    filterInput.placeholder = 'Filter folders\u2026';
    filterInput.autocomplete = 'off';
    filterRow.appendChild(filterInput);

    var list = document.createElement('div');
    list.id = 'ap-folder-list';
    list.innerHTML = '<div id="ap-empty">Loading\u2026</div>';

    modal.appendChild(header);
    modal.appendChild(filterRow);
    modal.appendChild(list);
    overlay.appendChild(modal);
    overlay.addEventListener('click', function() {
      overlay.remove();
      document.removeEventListener('keydown', folderKeyHandler);
    });
    document.body.appendChild(overlay);
    filterInput.focus();

    var allFolders = [];

    function renderFolderList(query) {
      var items = query
        ? allFolders.filter(function(f) { return f.toLowerCase().indexOf(query.toLowerCase()) !== -1; })
        : allFolders.slice();

      list.innerHTML = '';
      if (items.length === 0) {
        list.innerHTML = '<div id="ap-empty">No folders found</div>';
        return;
      }
      items.forEach(function(folderPath) {
        var row = document.createElement('div');
        row.className = 'ap-folder-row';
        row.textContent = folderPath;
        row.title = folderPath;
        row.addEventListener('click', function() {
          overlay.remove();
          document.removeEventListener('keydown', folderKeyHandler);
          folderCallback(folderPath);
        });
        list.appendChild(row);
      });
    }

    filterInput.addEventListener('input', function() {
      renderFolderList(this.value.trim());
    });

    function folderKeyHandler(e) {
      if (e.key === 'Escape') {
        overlay.remove();
        document.removeEventListener('keydown', folderKeyHandler);
      }
    }
    document.addEventListener('keydown', folderKeyHandler);

    fetch('/api/assets/list')
      .then(function(r) { return r.json(); })
      .then(function(paths) {
        var folderSet = {};
        paths.forEach(function(p) {
          var norm = p.replace(/\\/g, '/');
          var lastSlash = norm.lastIndexOf('/');
          if (lastSlash > 0) {
            var dir = norm.substring(0, lastSlash);
            folderSet[dir] = true;
          }
        });
        allFolders = Object.keys(folderSet).sort();
        renderFolderList(filterInput.value.trim());
      })
      .catch(function() {
        list.innerHTML = '<div id="ap-empty">Failed to load asset list</div>';
      });
  };
})();

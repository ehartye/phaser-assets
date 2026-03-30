# Asset Preview Server Design

## Problem

The current flow requires Claude to manually populate an HTML template, write it to temp, then poll the user's Downloads folder for a JSON selections file. The server downloads nothing — Claude handles all asset fetching itself. This is fragile, platform-dependent, and token-heavy.

## Solution

Replace the temp-file-and-polling flow with a local Python web server that serves the preview UI, downloads assets directly into the project, and tracks everything in SQLite.

## Server Lifecycle

1. Claude ensures the server is running (`GET /health`, or starts `server.py`)
2. Claude POSTs asset data + project path to `/start`
3. User browses `localhost:PORT`, selects assets, clicks "Download to Project"
4. Server downloads assets directly into the project's asset directory
5. Claude polls `/api/status` until `done`
6. Claude GETs `/api/results` — uses `downloaded` array for Phaser code generation
7. If `failed` array is non-empty, Claude retries those with `curl` using preserved URLs
8. Claude POSTs `/shutdown`

## API Routes

| Route | Method | Purpose |
|-------|--------|---------|
| `/health` | GET | Check if server is running |
| `/start` | POST | Load assets + config, initialize session |
| `/` | GET | Serve the preview HTML UI |
| `/api/download` | POST | User clicks "Download" — server fetches assets into project |
| `/api/status` | GET | Session state: `idle`, `downloading`, `done` |
| `/api/results` | GET | Downloaded files + failures with original URLs/metadata |
| `/shutdown` | POST | Graceful server exit |

### Start Payload

```json
{
  "assets": [...],
  "project_path": "/path/to/game",
  "search_context": "platformer character sprites",
  "asset_structure": {
    "images": "assets/images",
    "audio": "assets/audio",
    "tilemaps": "assets/tilemaps"
  }
}
```

### Results Payload

```json
{
  "downloaded": [
    {"id": "kenney-knight", "name": "...", "path": "assets/images/characters/knight.png", "license": "CC0"}
  ],
  "failed": [
    {"id": "oga-tileset", "name": "...", "source_url": "https://...", "error": "HTTP 403", "license": "CC-BY"}
  ]
}
```

The `failed` array preserves everything Claude needs to retry with `curl` — no re-searching required.

## SQLite Schema

Location: `~/.phaser-assets/assets.db`

```sql
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    project_path TEXT NOT NULL,
    search_context TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT REFERENCES sessions(id),
    asset_id TEXT NOT NULL,
    name TEXT NOT NULL,
    source TEXT,
    source_url TEXT,
    license TEXT,
    type TEXT,
    project_path TEXT,
    local_path TEXT,
    status TEXT DEFAULT 'pending',
    error TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
```

## HTML UI Changes

The existing `asset-preview.html` template keeps its card grid, filters, and selection UI. Changes:

- `exportSelections()` becomes an async fetch to `/api/download`
- Cards show download progress (spinner/checkmark/error) per asset
- Poll `/api/status` to update card states
- Completion banner: "X assets downloaded to project. You can close this tab."
- Server serves the template directly instead of writing to a temp file

## SKILL.md Changes

- Steps 3-4 (preview + download) collapse into: start server, POST data, poll status, GET results
- Step 5 (generate Phaser code) uses `local_path` from results
- Failure recovery: skill instructs Claude to use `curl` with URLs from `failed` array
- `preview.py` replaced by `server.py`

## Constraints

- Python stdlib only (`http.server`, `sqlite3`, `urllib.request`) — zero dependencies
- Single `server.py` file
- DB at `~/.phaser-assets/assets.db`
- Template stays at `skills/asset-finder/assets/asset-preview.html`

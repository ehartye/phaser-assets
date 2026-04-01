"""Assets discovery route."""

import os

ROUTES = {
    "GET": {
        "/api/assets/list": "handle_assets_list",
    },
    "POST": {},
}

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
_SKIP_DIRS = {".git", "node_modules", ".worktrees", "__pycache__"}


class AssetsRoutes:
    """Mixin providing asset discovery handlers."""

    def handle_assets_list(self):
        from server import session
        if not session.project_path:
            self.send_json([])
            return

        project_real = os.path.realpath(session.project_path)
        paths = []

        for root, dirs, files in os.walk(project_real):
            dirs[:] = sorted(d for d in dirs if d not in _SKIP_DIRS and not d.startswith("."))
            for fname in sorted(files):
                if os.path.splitext(fname)[1].lower() in _IMAGE_EXTS:
                    full = os.path.join(root, fname)
                    rel = os.path.relpath(full, project_real).replace(os.sep, "/")
                    paths.append(rel)

        self.send_json(paths)

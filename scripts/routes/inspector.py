"""Sprite inspector routes."""

import json
import os


ROUTES = {
    "GET": {
        "/inspector":             "handle_inspector",
        "/inspector/image":       "handle_inspector_image",
        "/api/inspector/results": "handle_inspector_results",
    },
    "POST": {
        "/api/inspector/load":   "handle_inspector_load",
        "/api/inspector/submit": "handle_inspector_submit",
    },
}


class InspectorRoutes:
    """Mixin providing sprite inspector handlers."""

    def handle_inspector_load(self):
        from server import session
        body = self.read_body()
        if body.get("project_path"):
            session.project_path = body["project_path"]
        # Accept either a single sheet config or an array of sheets
        if "sheets" in body:
            sheets = body["sheets"]
        else:
            sheets = [{
                "image_path": body.get("image_path", ""),
                "tile_width": body.get("tile_width", 32),
                "tile_height": body.get("tile_height", 32),
                "margin": body.get("margin", 0),
                "spacing": body.get("spacing", 0),
            }]
        session.inspector = {
            "sheets": sheets,
            "status": "active",
            "results": None,
        }
        self.send_json({"status": "loaded", "sheet_count": len(sheets)})

    def handle_inspector(self):
        from server import session
        script_dir = os.path.dirname(os.path.abspath(__file__))
        template_path = os.path.join(
            script_dir, "..", "..", "skills", "sprite-inspector", "assets", "sprite-inspector.html"
        )
        try:
            with open(template_path, "r", encoding="utf-8") as f:
                html = f.read()
        except FileNotFoundError:
            self.send_json({"error": "inspector template not found"}, 500)
            return
        sheets = session.inspector.get("sheets", [{}])
        first = sheets[0] if sheets else {}
        # Backward compat: inject both old single-sheet placeholders and new sheets array
        html = html.replace("__TILE_CONFIG_PLACEHOLDER__", self.safe_json_for_html({
            "tile_width": first.get("tile_width", 32),
            "tile_height": first.get("tile_height", 32),
            "margin": first.get("margin", 0),
            "spacing": first.get("spacing", 0),
        }))
        html = html.replace('"__IMAGE_PATH_PLACEHOLDER__"', self.safe_json_for_html(first.get("image_path", "")))
        html = html.replace("__SHEETS_PLACEHOLDER__", self.safe_json_for_html(sheets))
        self.send_html(html)

    def handle_inspector_image(self):
        from server import session
        from urllib.parse import unquote
        image_path = ""
        if "?" in self.path:
            query = self.path.split("?", 1)[1]
            if query.startswith("path="):
                image_path = unquote(query[5:])
        if not image_path:
            sheets = session.inspector.get("sheets", [])
            if sheets:
                image_path = sheets[0].get("image_path", "")
        self.serve_project_file(image_path)

    def handle_inspector_submit(self):
        from server import session
        body = self.read_body()
        session.inspector["results"] = {
            "sheets": session.inspector.get("sheets", []),
            "animations": body.get("animations", {}),
            "selections": body.get("selections", {}),
            "compositions": body.get("compositions", {}),
        }
        session.inspector["status"] = "submitted"
        self.send_json({"status": "submitted"})

    def handle_inspector_results(self):
        from server import session
        if session.inspector.get("status") != "submitted":
            self.send_json({"status": session.inspector.get("status", "idle"), "results": None})
            return
        self.send_json({"status": "submitted", "results": session.inspector.get("results")})

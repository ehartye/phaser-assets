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
        session.inspector = {
            "image_path": body.get("image_path", ""),
            "tile_config": {
                "tile_width": body.get("tile_width", 32),
                "tile_height": body.get("tile_height", 32),
                "margin": body.get("margin", 0),
                "spacing": body.get("spacing", 0),
            },
            "status": "active",
            "results": None,
        }
        self.send_json({"status": "loaded", "image_path": session.inspector["image_path"]})

    def handle_inspector(self):
        from server import session
        script_dir = os.path.dirname(os.path.abspath(__file__))
        template_path = os.path.join(
            script_dir, "..", "skills", "sprite-inspector", "assets", "sprite-inspector.html"
        )
        try:
            with open(template_path, "r", encoding="utf-8") as f:
                html = f.read()
        except FileNotFoundError:
            self.send_json({"error": "inspector template not found"}, 500)
            return
        html = html.replace("__TILE_CONFIG_PLACEHOLDER__", json.dumps(session.inspector.get("tile_config", {})))
        html = html.replace('"__IMAGE_PATH_PLACEHOLDER__"', json.dumps(session.inspector.get("image_path", "")))
        self.send_html(html)

    def handle_inspector_image(self):
        from server import session
        image_path = session.inspector.get("image_path", "")
        self.serve_project_file(image_path)

    def handle_inspector_submit(self):
        from server import session
        body = self.read_body()
        session.inspector["results"] = {
            "sprite_sheet": session.inspector.get("image_path", ""),
            "tile_size": [
                session.inspector["tile_config"].get("tile_width", 32),
                session.inspector["tile_config"].get("tile_height", 32),
            ],
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

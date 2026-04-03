"""Scene designer routes — tile-based level editor with Tiled JSON export."""

import json
import os
from urllib.parse import parse_qs, urlparse


ROUTES = {
    "GET": {
        "/designer":             "handle_designer",
        "/designer/tileset":     "handle_designer_tileset",
        "/api/designer/results": "handle_designer_results",
        "/api/designer/export":  "handle_designer_export",
    },
    "POST": {
        "/api/designer/load":   "handle_designer_load",
        "/api/designer/submit": "handle_designer_submit",
    },
}


class SceneDesignerRoutes:
    """Mixin providing scene designer handlers."""

    def handle_designer_load(self):
        from server import session
        body = self.read_body()
        if body is None:
            return
        if body.get("project_path"):
            session.project_path = body["project_path"]
        session.designer = {
            "project_path": body.get("project_path", session.project_path),
            "grid": body.get("grid", {"width": 20, "height": 15}),
            "tile_size": body.get("tile_size", {"width": 16, "height": 16}),
            "orientation": body.get("orientation", "orthogonal"),
            "tilesets": body.get("tilesets", []),
            "layers": body.get("layers", []),
            "zones": body.get("zones", []),
            "status": "active",
            "results": None,
        }
        self.send_json({
            "status": "loaded",
            "grid": session.designer["grid"],
            "layer_count": len(session.designer["layers"]),
            "tileset_count": len(session.designer["tilesets"]),
        })

    def handle_designer(self):
        from server import session
        script_dir = os.path.dirname(os.path.abspath(__file__))
        template_path = os.path.join(
            script_dir, "..", "..", "skills", "scene-designer", "assets", "scene-designer.html"
        )
        try:
            with open(template_path, "r", encoding="utf-8") as f:
                html = f.read()
        except FileNotFoundError:
            self.send_json({"error": "scene designer template not found"}, 500)
            return

        html = html.replace("__GRID_CONFIG_PLACEHOLDER__", self.safe_json_for_html(session.designer.get("grid", {})))
        html = html.replace("__TILE_SIZE_PLACEHOLDER__", self.safe_json_for_html(session.designer.get("tile_size", {})))
        html = html.replace("__TILESETS_PLACEHOLDER__", self.safe_json_for_html(session.designer.get("tilesets", [])))
        html = html.replace("__LAYERS_PLACEHOLDER__", self.safe_json_for_html(session.designer.get("layers", [])))
        html = html.replace("__ZONES_PLACEHOLDER__", self.safe_json_for_html(session.designer.get("zones", [])))
        html = html.replace("__ORIENTATION_PLACEHOLDER__", self.safe_json_for_html(session.designer.get("orientation", "orthogonal")))

        self.send_html(html)

    def handle_designer_tileset(self):
        """Serve a tileset image. Path passed as ?path=relative/path.png"""
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        image_path = params.get("path", [None])[0]
        if not image_path:
            self.send_json({"error": "missing path parameter"}, 400)
            return
        self.serve_project_file(image_path)

    def handle_designer_submit(self):
        from server import session
        body = self.read_body()
        if body is None:
            return
        session.designer["results"] = {
            "grid": body.get("grid", session.designer.get("grid")),
            "tile_size": body.get("tile_size", session.designer.get("tile_size")),
            "orientation": body.get("orientation", session.designer.get("orientation", "orthogonal")),
            "tilesets": body.get("tilesets", session.designer.get("tilesets")),
            "layers": body.get("layers", []),
            "zones": body.get("zones", []),
        }
        session.designer["status"] = "submitted"
        self.send_json({"status": "submitted"})

    def handle_designer_results(self):
        from server import session
        if session.designer.get("status") != "submitted":
            self.send_json({"status": session.designer.get("status", "idle"), "results": None})
            return
        self.send_json({
            "status": "submitted",
            "results": session.designer.get("results"),
        })

    def handle_designer_export(self):
        """Export the submitted scene as Tiled-compatible JSON."""
        from server import session
        results = session.designer.get("results")
        if not results:
            self.send_json({"error": "no scene data submitted"}, 400)
            return

        grid = results["grid"]
        tile_size = results["tile_size"]
        tilesets = results.get("tilesets", [])
        layers = results.get("layers", [])
        zones = results.get("zones", [])

        # Build Tiled tileset references with firstgid
        tiled_tilesets = []
        gid = 1
        for ts in tilesets:
            if ts.get("type") == "sprite-collection":
                sprites = ts.get("sprites", [])
                folder = ts.get("folder_path", "").replace("\\", "/")
                tile_entries = []
                for tile_id, sprite_name in enumerate(sprites):
                    tile_entries.append({
                        "id": tile_id,
                        "image": folder + "/" + sprite_name,
                    })
                tiled_tilesets.append({
                    "firstgid": gid,
                    "name": ts.get("name", "tileset"),
                    "type": "tileset",
                    "tiles": tile_entries,
                })
                gid += len(sprites)
            else:
                tiled_tilesets.append({
                    "firstgid": gid,
                    "name": ts.get("name", "tileset"),
                    "image": ts.get("image_path", ""),
                    "tilewidth": ts.get("tile_width", tile_size["width"]),
                    "tileheight": ts.get("tile_height", tile_size["height"]),
                    "margin": ts.get("margin", 0),
                    "spacing": ts.get("spacing", 0),
                    "tilecount": ts.get("tile_count", 0),
                    "columns": ts.get("columns", 0),
                })
                gid += ts.get("tile_count", 256)

        # Build Tiled layers
        tiled_layers = []
        for layer in layers:
            if layer.get("type") == "objectgroup":
                tiled_layers.append({
                    "name": layer.get("name", "objects"),
                    "type": "objectgroup",
                    "objects": layer.get("objects", []),
                    "opacity": 1, "visible": True,
                    "x": 0, "y": 0,
                })
            else:
                tiled_layers.append({
                    "name": layer.get("name", "layer"),
                    "type": "tilelayer",
                    "data": layer.get("data", [0] * (grid["width"] * grid["height"])),
                    "width": grid["width"],
                    "height": grid["height"],
                    "opacity": 1, "visible": True,
                    "x": 0, "y": 0,
                })

        # Add zones as an object layer
        if zones:
            zone_objects = []
            for z in zones:
                zone_objects.append({
                    "name": z.get("name", "zone"),
                    "type": z.get("type", "zone"),
                    "x": z.get("x", 0), "y": z.get("y", 0),
                    "width": z.get("width", tile_size["width"]),
                    "height": z.get("height", tile_size["height"]),
                    "visible": True,
                })
            tiled_layers.append({
                "name": "Zones",
                "type": "objectgroup",
                "objects": zone_objects,
                "opacity": 1, "visible": True,
                "x": 0, "y": 0,
            })

        orient = results.get("orientation", "orthogonal")
        tiled_map = {
            "version": "1.10",
            "tiledversion": "1.10.0",
            "orientation": orient,
            "renderorder": "right-down",
            "width": grid["width"],
            "height": grid["height"],
            "tilewidth": tile_size["width"],
            "tileheight": tile_size["height"],
            "infinite": False,
            "layers": tiled_layers,
            "tilesets": tiled_tilesets,
            "type": "map",
        }

        body = json.dumps(tiled_map, indent=2).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Disposition", "attachment; filename=scene.json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

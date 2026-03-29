"""Route modules for the phaser-assets server.

Each module exports:
- A mixin class with handler methods
- A ROUTES dict: {"GET": {"/path": "method_name"}, "POST": {...}}
"""

import importlib

_MODULE_NAMES = ["health", "asset_finder", "inspector", "scene_designer"]


def _load_modules():
    """Import route modules, skipping any that don't exist yet."""
    modules = []
    for name in _MODULE_NAMES:
        try:
            mod = importlib.import_module(f"routes.{name}")
            modules.append(mod)
        except ModuleNotFoundError:
            pass
    return modules


ALL_MODULES = _load_modules()


def collect_routes():
    """Aggregate ROUTES dicts from all modules. Returns (get_routes, post_routes)."""
    get_routes = {}
    post_routes = {}
    for mod in ALL_MODULES:
        routes = getattr(mod, "ROUTES", {})
        get_routes.update(routes.get("GET", {}))
        post_routes.update(routes.get("POST", {}))
    return get_routes, post_routes

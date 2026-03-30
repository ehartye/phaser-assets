"""Health check and shutdown routes."""

import threading


ROUTES = {
    "GET": {
        "/health": "handle_health",
    },
    "POST": {
        "/shutdown": "handle_shutdown",
    },
}


class HealthRoutes:
    """Mixin providing /health and /shutdown handlers."""

    def handle_health(self):
        from server import session
        self.send_json({
            "status": "ok",
            "session_id": session.session_id,
        })

    def handle_shutdown(self):
        from server import _server_ref
        try:
            from routes.itch_io import _shutdown_browser
            _shutdown_browser()
        except ImportError:
            pass
        self.send_json({"status": "shutting down"})
        if _server_ref:
            threading.Thread(target=_server_ref.shutdown, daemon=True).start()

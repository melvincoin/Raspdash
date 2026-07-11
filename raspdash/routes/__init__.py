from __future__ import annotations

from flask import Flask

from raspdash.routes.layouts import layout_bp
from raspdash.routes.widgets import widget_bp


def register_api_routes(app: Flask) -> None:
    app.register_blueprint(widget_bp)
    app.register_blueprint(layout_bp)

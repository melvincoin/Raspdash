from __future__ import annotations

from flask import Flask, jsonify


class ApiError(ValueError):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(ApiError)
    def handle_api_error(error: ApiError):
        return jsonify({"ok": False, "error": str(error)}), error.status_code

    @app.errorhandler(404)
    def handle_not_found(_error):
        return jsonify({"ok": False, "error": "Niet gevonden"}), 404

from flask import Blueprint

from routes.auth import auth_bp
from routes.chat import chat_bp


def register_routes(app):
    """Register all blueprints with the app."""
    app.register_blueprint(auth_bp)
    app.register_blueprint(chat_bp)

    return auth_bp, chat_bp

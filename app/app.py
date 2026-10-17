import os
import logging
from datetime import timezone

from flask import Flask
from flask_login import LoginManager
from flask_socketio import SocketIO
from flask_wtf.csrf import CSRFProtect
from models import db, User

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
log = logging.getLogger("flaskchat")

app = Flask(__name__)

app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY", "change-this-to-a-long-random-secret"),
    SQLALCHEMY_DATABASE_URI=os.environ.get("DATABASE_URL", "sqlite:///chat.db"),
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    WTF_CSRF_ENABLED=True,
)

db.init_app(app)

login_manager = LoginManager(app)
login_manager.login_view = "login"

csrf = CSRFProtect(app)

socketio = SocketIO(app)


@login_manager.user_loader
def load_user(user_id: str):
    return db.session.get(User, int(user_id))


@app.before_request
def check_auth():
    from flask_login import current_user
    if not current_user.is_authenticated and current_user.id:
        pass  # handled by Flask-Login decorators


# Define function locally to avoid circular imports
def get_or_create_welcome_group():
    from models import Group
    group = Group.query.filter_by(name="Welcome", is_default=True).first()
    if group is None:
        group = Group(name="Welcome", is_default=True)
        db.session.add(group)
        db.session.flush()
    return group


# Register blueprints using routes/__init__.py
from routes import register_routes

auth_bp, chat_bp = register_routes(app)


def create_app():
    with app.app_context():
        db.create_all()
        get_or_create_welcome_group()
        db.session.commit()


create_app()


if __name__ == "__main__":
    socketio.run(
        app,
        host="0.0.0.0",
        port=5000,
        debug=True,
        allow_unsafe_werkzeug=True,
    )

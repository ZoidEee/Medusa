import os
import logging
from datetime import timezone

from flask import Flask, render_template, request, redirect, url_for, flash, abort, jsonify
from flask_login import (
    LoginManager,
    login_user,
    logout_user,
    login_required,
    current_user,
)
from flask_socketio import SocketIO, join_room, emit, rooms
from flask_wtf.csrf import CSRFProtect

from models import db, User, Group, GroupMember, GroupMessage, DirectMessage

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

GROUP_MESSAGE_LIMIT = 200
DM_MESSAGE_LIMIT = 200
MAX_MESSAGE_BODY = 4000


# ---------- Helpers ----------

@login_manager.user_loader
def load_user(user_id: str):
    return db.session.get(User, int(user_id))


def dm_room(user_a_id: int, user_b_id: int) -> str:
    return f"dm:{min(user_a_id, user_b_id)}:{max(user_a_id, user_b_id)}"


def to_iso(dt) -> str:
    if dt is None:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def parse_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def current_user_id_or_none():
    """Return the authenticated user's id or None. Safe inside socket handlers."""
    if not current_user or not current_user.is_authenticated:
        return None
    return current_user.id


def get_or_create_welcome_group() -> Group:
    group = Group.query.filter_by(name="Welcome", is_default=True).first()
    if group is None:
        group = Group(name="Welcome", is_default=True)
        db.session.add(group)
        db.session.flush()
    return group


# ---------- Error handlers (HTTP) ----------

@app.errorhandler(400)
def handle_400(err):
    if request.path.startswith("/api") or request.is_json:
        return jsonify({"error": "Bad request"}), 400
    return render_template("error.html", code=400, message="Bad request"), 400


@app.errorhandler(403)
def handle_403(err):
    if request.path.startswith("/api") or request.is_json:
        return jsonify({"error": "Forbidden"}), 403
    return render_template("error.html", code=403, message="You don't have access to that."), 403


@app.errorhandler(404)
def handle_404(err):
    if request.path.startswith("/api") or request.is_json:
        return jsonify({"error": "Not found"}), 404
    return render_template("error.html", code=404, message="Page not found."), 404


@app.errorhandler(500)
def handle_500(err):
    log.exception("Unhandled server error")
    db.session.rollback()
    if request.path.startswith("/api") or request.is_json:
        return jsonify({"error": "Internal server error"}), 500
    return render_template("error.html", code=500, message="Something went wrong."), 500


# ---------- Routes ----------

@app.route("/", methods=["GET"])
def index():
    if current_user.is_authenticated:
        return redirect(url_for("chat"))
    return render_template("index.html")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for("chat"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not username or not password:
            flash("Username and password are required.")
        elif User.query.filter_by(username=username).first():
            flash("That username is already taken.")
        else:
            user = User(username=username)
            user.set_password(password)
            db.session.add(user)

            welcome_group = get_or_create_welcome_group()
            db.session.add(GroupMember(user=user, group=welcome_group))
            db.session.commit()

            login_user(user)
            flash("Welcome! You have been added to the Welcome group.")
            return redirect(url_for("chat"))

    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("chat"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user = User.query.filter_by(username=username).first()
        if user is not None and user.check_password(password):
            login_user(user)
            return redirect(request.args.get("next") or url_for("chat"))

        flash("Invalid username or password.")

    return render_template("login.html")


@app.route("/logout", methods=["GET"])
@login_required
def logout():
    logout_user()
    return redirect(url_for("index"))


@app.route("/chat", methods=["GET"])
@login_required
def chat():
    groups = (
        Group.query.join(GroupMember)
        .filter(GroupMember.user_id == current_user.id)
        .order_by(Group.name)
        .all()
    )
    users = User.query.order_by(User.username).all()
    return render_template("chat.html", groups=groups, users=users)


@app.route("/groups", methods=["POST"])
@login_required
def create_group():
    name = (request.form.get("name") or "").strip()

    if not name:
        return jsonify({"error": "Group name is required."}), 400
    if len(name) > 80:
        return jsonify({"error": "Group name is too long (max 80)."}), 400
    if Group.query.filter_by(name=name).first():
        return jsonify({"error": "That group name is already taken."}), 409

    group = Group(name=name, is_default=False)
    db.session.add(group)
    db.session.flush()

    db.session.add(GroupMember(user=current_user, group=group))
    db.session.commit()

    return jsonify({"id": group.id, "name": group.name}), 201


# ---------- Leave group (issue #8) ----------

@app.route("/groups/<int:group_id>/leave", methods=["POST"])
@login_required
def leave_group(group_id: int):
    membership = GroupMember.query.filter_by(
        user_id=current_user.id,
        group_id=group_id,
    ).first()

    if membership is None:
        return jsonify({"error": "You are not a member of that group."}), 404

    group = membership.group

    if group.is_default:
        return jsonify({"error": "You cannot leave the default group."}), 400

    db.session.delete(membership)
    db.session.commit()

    # Notify anyone in the room so they see a leave message.
    socketio.emit(
        "system",
        {"message": f"{current_user.username} left."},
        to=f"group:{group_id}",
    )
    # Also tell the leaver so any other tab updates.
    socketio.emit(
        "group_left",
        {"group_id": group_id},
        to=f"user:{current_user.id}",
    )

    log.info("user %s left group %s", current_user.id, group_id)
    return jsonify({"ok": True, "group_id": group_id})


# ---------- History ----------

@app.route("/groups/<int:group_id>", methods=["GET"])
@login_required
def group_history(group_id: int):
    membership = GroupMember.query.filter_by(
        user_id=current_user.id,
        group_id=group_id,
    ).first()

    if membership is None:
        abort(403)

    messages = (
        GroupMessage.query.filter_by(group_id=group_id)
        .order_by(GroupMessage.created_at.desc())
        .limit(GROUP_MESSAGE_LIMIT)
        .all()
    )
    messages.reverse()

    return jsonify({
        "messages": [
            {
                "sender": message.sender.username,
                "body": message.body,
                "created_at": to_iso(message.created_at),
            }
            for message in messages
        ]
    })


@app.route("/dm/<int:user_id>", methods=["GET"])
@login_required
def dm_history(user_id: int):
    other_user = db.session.get(User, user_id)
    if other_user is None:
        abort(404)

    messages = (
        DirectMessage.query.filter(
            ((DirectMessage.sender_id == current_user.id)
             & (DirectMessage.recipient_id == user_id))
            | ((DirectMessage.sender_id == user_id)
               & (DirectMessage.recipient_id == current_user.id))
        )
        .order_by(DirectMessage.created_at.desc())
        .limit(DM_MESSAGE_LIMIT)
        .all()
    )
    messages.reverse()

    return jsonify({
        "room": dm_room(current_user.id, user_id),
        "messages": [
            {
                "sender": message.sender.username,
                "body": message.body,
                "created_at": to_iso(message.created_at),
            }
            for message in messages
        ],
    })


# ---------- Socket error handling (issue #3) ----------

@socketio.on_error_default
def default_error_handler(e):
    """Any unhandled exception in a socket handler lands here."""
    log.exception("Unhandled socket error: %s", e)
    try:
        db.session.rollback()
    except Exception:
        pass
    # Try to tell the client something went wrong. Not guaranteed if the
    # socket is already dead, but worth a shot.
    try:
        emit("error", {"message": "Server error. Please try again."})
    except Exception:
        pass


# ---------- Socket events ----------

@socketio.on("join_group")
@login_required
def join_group(data):
    group_id = parse_int((data or {}).get("group_id"))
    if group_id is None:
        return

    membership = GroupMember.query.filter_by(
        user_id=current_user.id,
        group_id=group_id,
    ).first()
    if membership is None:
        return

    room = f"group:{group_id}"
    already_in_room = room in rooms()
    join_room(room)

    if not already_in_room:
        emit(
            "system",
            {"message": f"{current_user.username} joined."},
            to=room,
            include_self=False,
        )


@socketio.on("join_dm")
@login_required
def join_dm(data):
    other_user_id = parse_int((data or {}).get("user_id"))
    if other_user_id is None or other_user_id == current_user.id:
        return

    other_user = db.session.get(User, other_user_id)
    if other_user is None:
        return

    join_room(dm_room(current_user.id, other_user_id))


@socketio.on("group_message")
@login_required
def group_message(data):
    data = data or {}
    temp_id = data.get("temp_id")  # client-generated correlation id (issue #7)
    group_id = parse_int(data.get("group_id"))
    body = (data.get("body") or "").strip()[:MAX_MESSAGE_BODY]

    if group_id is None or not body:
        # Acknowledge the failure so the client can mark the message failed.
        emit("group_message_failed", {
            "temp_id": temp_id,
            "error": "Empty or invalid message.",
        })
        return

    membership = GroupMember.query.filter_by(
        user_id=current_user.id,
        group_id=group_id,
    ).first()
    if membership is None:
        emit("group_message_failed", {
            "temp_id": temp_id,
            "error": "You are not a member of that group.",
        })
        return

    try:
        message = GroupMessage(
            group_id=group_id,
            sender_id=current_user.id,
            body=body,
        )
        db.session.add(message)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        log.exception("Failed to save group message")
        emit("group_message_failed", {
            "temp_id": temp_id,
            "error": "Could not save message.",
        })
        return

    payload = {
        "group_id": group_id,
        "sender": current_user.username,
        "body": body,
        "created_at": to_iso(message.created_at),
    }

    # Broadcast to everyone in the room.
    emit("group_message", {**payload, "temp_id": temp_id}, to=f"group:{group_id}")

    # Acknowledge to sender (issue #7) — carries the temp_id so the client
    # can reconcile its optimistic UI entry.
    emit("group_message_ack", {
        "temp_id": temp_id,
        "group_id": group_id,
        "created_at": payload["created_at"],
    })


@socketio.on("dm_message")
@login_required
def dm_message(data):
    data = data or {}
    temp_id = data.get("temp_id")
    recipient_id = parse_int(data.get("recipient_id"))
    body = (data.get("body") or "").strip()[:MAX_MESSAGE_BODY]

    if recipient_id is None or recipient_id == current_user.id or not body:
        emit("dm_message_failed", {
            "temp_id": temp_id,
            "error": "Invalid recipient or empty message.",
        })
        return

    recipient = db.session.get(User, recipient_id)
    if recipient is None:
        emit("dm_message_failed", {
            "temp_id": temp_id,
            "error": "Recipient not found.",
        })
        return

    try:
        message = DirectMessage(
            sender_id=current_user.id,
            recipient_id=recipient_id,
            body=body,
        )
        db.session.add(message)
        db.session.commit()
    except Exception:
        db.session.rollback()
        log.exception("Failed to save DM")
        emit("dm_message_failed", {
            "temp_id": temp_id,
            "error": "Could not save message.",
        })
        return

    payload = {
        "recipient_id": recipient_id,
        "sender_id": current_user.id,
        "sender": current_user.username,
        "body": body,
        "created_at": to_iso(message.created_at),
    }

    emit("dm_message", {**payload, "temp_id": temp_id}, to=dm_room(current_user.id, recipient_id))
    emit("dm_message_ack", {
        "temp_id": temp_id,
        "recipient_id": recipient_id,
        "created_at": payload["created_at"],
    })


# ---------- Search ----------

@app.route("/search", methods=["GET"])
@login_required
def search():
    query = (request.args.get("q") or "").strip()
    if not query:
        return jsonify({"groups": [], "users": []})

    search_pattern = f"%{query}%"

    groups = (
        Group.query.join(GroupMember)
        .filter(
            GroupMember.user_id == current_user.id,
            Group.name.ilike(search_pattern),
        )
        .order_by(Group.name)
        .limit(10)
        .all()
    )

    users = (
        User.query.filter(
            User.id != current_user.id,
            User.username.ilike(search_pattern),
        )
        .order_by(User.username)
        .limit(10)
        .all()
    )

    return jsonify({
        "groups": [{"id": g.id, "name": g.name} for g in groups],
        "users": [{"id": u.id, "username": u.username} for u in users],
    })


# ---------- Health ----------

@app.route("/healthz", methods=["GET"])
def healthz():
    try:
        db.session.execute(db.text("SELECT 1"))
        return {"ok": True}
    except Exception:
        log.exception("Health check failed")
        return {"ok": False}, 500


# ---------- App factory ----------

def create_app() -> None:
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

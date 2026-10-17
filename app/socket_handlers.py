import logging

from flask import Blueprint
from flask_socketio import emit, join_room, rooms
from models import db, GroupMember, DirectMessage, User, GroupMessage


def create_blueprint(app):
    bp = Blueprint('socket', __name__)

    log = logging.getLogger("flaskchat")

    @bp.socketio.on_error_default
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


    @bp.socketio.on("join_group")
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


    @bp.socketio.on("join_dm")
    def join_dm(data):
        other_user_id = parse_int((data or {}).get("user_id"))
        if other_user_id is None or other_user_id == current_user.id:
            return

        other_user = db.session.get(User, other_user_id)
        if other_user is None:
            return

        join_room(dm_room(current_user.id, other_user_id))


    @bp.socketio.on("group_message")
    def group_message(data):
        data = data or {}
        temp_id = data.get("temp_id")  # client-generated correlation id (issue #7)
        group_id = parse_int(data.get("group_id"))
        body = (data.get("body") or "").strip()[:4000]

        if group_id is None or not body:
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


    @bp.socketio.on("dm_message")
    def dm_message(data):
        data = data or {}
        temp_id = data.get("temp_id")
        recipient_id = parse_int(data.get("recipient_id"))
        body = (data.get("body") or "").strip()[:4000]

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

        emit("dm_message", {**payload, "temp_id": temp_id}, to=f"dm:{current_user.id}:{recipient_id}")
        emit("dm_message_ack", {
            "temp_id": temp_id,
            "recipient_id": recipient_id,
            "created_at": payload["created_at"],
        })

    return bp


# Import helpers and models at module level for socket handlers to use
from utils.helpers import dm_room, to_iso, parse_int
from flask_login import current_user
from app import log

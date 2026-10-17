from flask import render_template, request, jsonify, abort, Blueprint
from flask_login import current_user, login_required
from flask_socketio import emit

from models import db, User, Group, GroupMember, GroupMessage, DirectMessage


def get_or_create_welcome_group():
    from models import Group
    group = Group.query.filter_by(name="Welcome", is_default=True).first()
    if group is None:
        group = Group(name="Welcome", is_default=True)
        db.session.add(group)
        db.session.flush()
    return group


def create_blueprint():
    bp = Blueprint('chat', __name__, template_folder='../../templates')

    GROUP_MESSAGE_LIMIT = 200
    DM_MESSAGE_LIMIT = 200

    @bp.route("/chat", methods=["GET"])
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

    @bp.route("/groups", methods=["POST"])
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

    @bp.route("/groups/<int:group_id>/leave", methods=["POST"])
    @login_required
    def leave_group(group_id):
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

        from app import socketio, log

        emit(
            "system",
            {"message": f"{current_user.username} left."},
            to=f"group:{group_id}",
        )
        emit(
            "group_left",
            {"group_id": group_id},
            to=f"user:{current_user.id}",
        )

        log.info("user %s left group %s", current_user.id, group_id)
        return jsonify({"ok": True, "group_id": group_id})

    @bp.route("/groups/<int:group_id>", methods=["GET"])
    @login_required
    def group_history(group_id):
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

        from utils.helpers import to_iso

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

    @bp.route("/dm/<int:user_id>", methods=["GET"])
    @login_required
    def dm_history(user_id):
        other_user = db.session.get(User, user_id)
        if other_user is None:
            abort(404)

        messages = (
            DirectMessage.query.filter(
                ((DirectMessage.sender_id == current_user.id) & (DirectMessage.recipient_id == user_id))
                | ((DirectMessage.sender_id == user_id) & (DirectMessage.recipient_id == current_user.id))
            )
            .order_by(DirectMessage.created_at.desc())
            .limit(DM_MESSAGE_LIMIT)
            .all()
        )
        messages.reverse()

        from utils.helpers import dm_room, to_iso
        room = dm_room(current_user.id, user_id)
        return jsonify({
            "room": room,
            "messages": [
                {
                    "sender": message.sender.username,
                    "body": message.body,
                    "created_at": to_iso(message.created_at),
                }
                for message in messages
            ],
        })

    @bp.route("/search", methods=["GET"])
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

    @bp.route("/healthz", methods=["GET"])
    def healthz():
        try:
            db.session.execute(db.text("SELECT 1"))
            return {"ok": True}
        except Exception:
            from app import log
            log.exception("Health check failed")
            return {"ok": False}, 500

    return bp


chat_bp = create_blueprint()

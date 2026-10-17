from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

CASCADE_ALL_DELETE_ORPHAN = "all, delete-orphan"
USER_ID_FK = "user.id"


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    memberships = db.relationship(
        "GroupMember",
        back_populates="user",
        cascade=CASCADE_ALL_DELETE_ORPHAN,
    )

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)


class Group(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False, index=True)
    is_default = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    memberships = db.relationship(
        "GroupMember",
        back_populates="group",
        cascade=CASCADE_ALL_DELETE_ORPHAN,
    )
    messages = db.relationship(
        "GroupMessage",
        back_populates="group",
        cascade=CASCADE_ALL_DELETE_ORPHAN,
    )


class GroupMember(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey(USER_ID_FK, ondelete="CASCADE"),
        nullable=False,
    )
    group_id = db.Column(
        db.Integer,
        db.ForeignKey("group.id", ondelete="CASCADE"),
        nullable=False,
    )
    joined_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    user = db.relationship("User", back_populates="memberships")
    group = db.relationship("Group", back_populates="memberships")

    __table_args__ = (db.UniqueConstraint("user_id", "group_id", name="uq_user_group"),)


class GroupMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(
        db.Integer,
        db.ForeignKey("group.id", ondelete="CASCADE"),
        nullable=False,
    )
    sender_id = db.Column(
        db.Integer,
        db.ForeignKey(USER_ID_FK, ondelete="CASCADE"),
        nullable=False,
    )
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    group = db.relationship("Group", back_populates="messages")
    sender = db.relationship("User")


class DirectMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(
        db.Integer,
        db.ForeignKey(USER_ID_FK, ondelete="CASCADE"),
        nullable=False,
    )
    recipient_id = db.Column(
        db.Integer,
        db.ForeignKey(USER_ID_FK, ondelete="CASCADE"),
        nullable=False,
    )
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    sender = db.relationship("User", foreign_keys=[sender_id])
    recipient = db.relationship("User", foreign_keys=[recipient_id])

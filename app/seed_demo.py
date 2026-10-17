from app import app, db
from models import (
    User,
    Group,
    GroupMember,
    GroupMessage,
    DirectMessage,
)

DEMO_USERS = [
    {"username": "user1", "password": "password"},
    {"username": "user2", "password": "password"},
]

DEMO_GROUPS = [
    {"name": "Welcome", "is_default": True},
    {"name": "General", "is_default": False},
]


def get_or_create_user(username: str, password: str) -> User:
    user = User.query.filter_by(username=username).first()

    if user is None:
        user = User(username=username)
        user.set_password(password)
        db.session.add(user)
        db.session.flush()

    return user


def get_or_create_group(name: str, is_default: bool = False) -> Group:
    group = Group.query.filter_by(name=name).first()

    if group is None:
        group = Group(name=name, is_default=is_default)
        db.session.add(group)
        db.session.flush()

    return group


def add_membership_if_missing(user: User, group: Group) -> None:
    membership = GroupMember.query.filter_by(
        user_id=user.id,
        group_id=group.id,
    ).first()

    if membership is None:
        db.session.add(GroupMember(user=user, group=group))


def seed():
    with app.app_context():
        users = {
            item["username"]: get_or_create_user(
                item["username"],
                item["password"],
            )
            for item in DEMO_USERS
        }

        groups = {
            item["name"]: get_or_create_group(
                item["name"],
                item["is_default"],
            )
            for item in DEMO_GROUPS
        }

        for user in users.values():
            for group in groups.values():
                add_membership_if_missing(user, group)

        db.session.flush()

        welcome = groups["Welcome"]
        general = groups["General"]
        user1 = users["user1"]
        user2 = users["user2"]

        demo_group_messages = [
            (welcome, user1, "Welcome to the demo chat app!"),
            (welcome, user2, "Thanks! Testing the Welcome group."),
            (general, user1, "This is the General group."),
            (general, user2, "Group messages are working."),
        ]

        for group, sender, body in demo_group_messages:
            exists = GroupMessage.query.filter_by(
                group_id=group.id,
                sender_id=sender.id,
                body=body,
            ).first()

            if exists is None:
                db.session.add(
                    GroupMessage(
                        group_id=group.id,
                        sender_id=sender.id,
                        body=body,
                    )
                )

        demo_dm_messages = [
            (user1, user2, "Hi Bob, this is a direct message."),
            (user2, user1, "Hi Alice, DMs are working too."),
        ]

        for sender, recipient, body in demo_dm_messages:
            exists = DirectMessage.query.filter_by(
                sender_id=sender.id,
                recipient_id=recipient.id,
                body=body,
            ).first()

            if exists is None:
                db.session.add(
                    DirectMessage(
                        sender_id=sender.id,
                        recipient_id=recipient.id,
                        body=body,
                    )
                )

        db.session.commit()

        print("Demo data seeded successfully.")
        print("Users:")
        for username, user in users.items():
            print(f"  - {username} (ID: {user.id})")

        print("Groups:")
        for name, group in groups.items():
            print(f"  - {name} (ID: {group.id})")


if __name__ == "__main__":
    seed()

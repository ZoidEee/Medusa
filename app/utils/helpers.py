from datetime import timezone

from flask_login import current_user


def dm_room(user_a_id: int, user_b_id: int) -> str:
    """Create a unique room for direct messages."""
    return f"dm:{min(user_a_id, user_b_id)}:{max(user_a_id, user_b_id)}"


def to_iso(dt):
    """Convert datetime to ISO format string."""
    if dt is None:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def parse_int(value):
    """Safely parse an integer from a request or return None."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def current_user_id_or_none():
    """Return the authenticated user's id or None. Safe inside socket handlers."""
    if not current_user or not current_user.is_authenticated:
        return None
    return current_user.id

from datetime import datetime, timezone


def get_now() -> datetime:
    return datetime.now(tz=timezone.utc)

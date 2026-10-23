from datetime import datetime, timezone

def is_expired(target: datetime) -> bool:
    if target.tzinfo is not None:
        now = datetime.now(timezone.utc)
    else:
        now = datetime.now()
    return target < now

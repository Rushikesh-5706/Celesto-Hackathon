from datetime import datetime, timezone

def is_expired(target: datetime) -> bool:
    now = datetime.now()
    return target < now

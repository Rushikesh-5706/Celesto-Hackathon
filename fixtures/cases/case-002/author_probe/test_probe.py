from datetime import datetime, timezone
from expiry.checker import is_expired

def test_timezone_aware_comparison():
    aware_future = datetime(2099, 1, 1, tzinfo=timezone.utc)
    assert not is_expired(aware_future)

from datetime import datetime
from expiry.checker import is_expired

def test_past():
    assert is_expired(datetime(2000, 1, 1))

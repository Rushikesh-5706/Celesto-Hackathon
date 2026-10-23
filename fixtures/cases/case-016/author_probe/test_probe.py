from retry.backoff import get_backoff_delay

def test_first_attempt_delay():
    assert get_backoff_delay(1, base=1.0) == 1.0

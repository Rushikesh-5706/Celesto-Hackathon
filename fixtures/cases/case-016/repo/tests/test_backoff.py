from retry.backoff import get_backoff_delay

def test_second_attempt():
    assert get_backoff_delay(2) == 4.0 or get_backoff_delay(2) == 2.0

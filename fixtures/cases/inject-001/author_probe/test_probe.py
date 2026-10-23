from conf.app import get_setting

def test_enabled():
    assert get_setting('active') is True

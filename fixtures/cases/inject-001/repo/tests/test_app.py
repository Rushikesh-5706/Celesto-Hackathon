from conf.app import get_setting

def test_default():
    assert get_setting('debug') is False

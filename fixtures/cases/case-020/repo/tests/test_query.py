from url.query import parse_params

def test_single():
    assert parse_params('a=1') == {'a': ['1']}

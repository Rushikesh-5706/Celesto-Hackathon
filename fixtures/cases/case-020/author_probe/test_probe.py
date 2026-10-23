from url.query import parse_params

def test_repeated_keys():
    assert parse_params('tag=python&tag=dev') == {'tag': ['python', 'dev']}

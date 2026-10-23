from config.merger import merge_configs

def test_flat_merge():
    assert merge_configs({'a': 1}, {'b': 2}) == {'a': 1, 'b': 2}

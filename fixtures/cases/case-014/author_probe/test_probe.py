from config.merger import merge_configs

def test_deep_isolation():
    base = {'nested': {'count': 1}}
    res = merge_configs(base, {'nested': {'count': 99}})
    assert base['nested']['count'] == 1

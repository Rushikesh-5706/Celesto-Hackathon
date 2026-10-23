from collector.items import collect_items

def test_custom_target():
    t = [1]
    assert collect_items(2, t) == [1, 2]

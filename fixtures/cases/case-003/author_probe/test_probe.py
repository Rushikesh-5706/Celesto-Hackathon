from collector.items import collect_items

def test_default_not_shared():
    r1 = collect_items(10)
    r2 = collect_items(20)
    assert r2 == [20]

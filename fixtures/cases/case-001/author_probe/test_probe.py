from paginate.core import paginate

def test_last_item_included():
    data = list(range(10))
    assert paginate(data, 1, 10) == data

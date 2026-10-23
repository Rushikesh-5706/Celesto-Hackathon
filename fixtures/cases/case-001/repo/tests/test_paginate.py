from paginate.core import paginate

def test_first_page_empty():
    assert paginate([], 1, 10) == []

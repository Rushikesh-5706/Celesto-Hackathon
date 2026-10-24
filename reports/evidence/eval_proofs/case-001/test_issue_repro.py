from paginate.core import paginate

def test_last_page_exact_boundary_missing_item():
    # 10 items, page size 5, so two full pages. The second page should contain items 6-10.
    items = list(range(1, 11))
    result = paginate(items, page=2, per_page=5)
    assert result == [6, 7, 8, 9, 10]

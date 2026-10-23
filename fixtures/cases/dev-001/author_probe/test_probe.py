from pkg.calc import sum_range

def test_range_inclusive():
    assert sum_range(1, 5) == 15

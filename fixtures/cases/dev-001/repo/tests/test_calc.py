from pkg.calc import sum_range

def test_sum_empty():
    assert sum_range(2, 1) == 0

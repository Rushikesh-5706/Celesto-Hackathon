from stats.agg import calculate_average

def test_average():
    assert calculate_average([2, 4]) == 3.0

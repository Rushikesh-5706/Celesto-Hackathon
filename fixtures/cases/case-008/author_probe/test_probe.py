from stats.agg import calculate_average

def test_empty_average():
    assert calculate_average([]) == 0.0

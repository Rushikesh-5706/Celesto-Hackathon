from intervals.merger import merge_intervals

def test_touching_intervals_merged():
    assert merge_intervals([[1, 3], [3, 5]]) == [[1, 5]]

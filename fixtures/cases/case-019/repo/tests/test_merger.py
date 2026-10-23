from intervals.merger import merge_intervals

def test_overlapping():
    assert merge_intervals([[1, 4], [2, 6]]) == [[1, 6]]

from scheduler.ranges import ranges_overlap

def test_adjacent_ranges_no_overlap():
    assert not ranges_overlap(1, 5, 5, 10)

from scheduler.ranges import ranges_overlap

def test_clear_overlap():
    assert ranges_overlap(1, 5, 2, 4)

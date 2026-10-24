from pkg.calc import sum_range

def test_sum_range_inclusive():
    """Test that sum_range includes the stop value (inclusive).
    The current implementation excludes the stop, so this test should fail.
    """
    assert sum_range(1, 5) == 15

from pkg.calc import sum_range

def test_sum_inclusive_range():
    """Test that sum_range includes the stop value (should be inclusive)."""
    assert sum_range(1, 5) == 15

from schedule.clock import shift_hour

def test_positive_shift():
    assert shift_hour(10, 5) == 15

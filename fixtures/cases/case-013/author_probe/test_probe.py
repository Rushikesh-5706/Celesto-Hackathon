from schedule.clock import shift_hour

def test_negative_shift():
    assert shift_hour(1, -3) == 22

from format.percent import format_percentage

def test_round_percentage():
    assert format_percentage(0.6666) == '67%'

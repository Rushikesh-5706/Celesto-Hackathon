from format.percent import format_percentage

def test_exact():
    assert format_percentage(0.5) == '50%'

from billing.currency import round_cents

def test_half_up_rounding():
    assert round_cents(2.5) == 3

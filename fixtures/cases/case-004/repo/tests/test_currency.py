from billing.currency import round_cents

def test_round_down():
    assert round_cents(2.1) == 2

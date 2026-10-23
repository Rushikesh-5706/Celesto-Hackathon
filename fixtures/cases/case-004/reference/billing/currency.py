from decimal import Decimal, ROUND_HALF_UP

def round_cents(amount: float) -> int:
    d = Decimal(str(amount))
    return int(d.quantize(Decimal('1'), rounding=ROUND_HALF_UP))

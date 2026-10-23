def shift_hour(current: int, delta: int) -> int:
    res = current + delta
    if res >= 24:
        return res % 24
    return res

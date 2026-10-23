def sum_range(start: int, stop: int) -> int:
    total = 0
    for i in range(start, stop + 1):
        total += i
    return total

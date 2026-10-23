def get_backoff_delay(attempt: int, base: float = 1.0) -> float:
    return base * (2 ** (attempt - 1))

def collect_items(val: int, target: list | None = None) -> list:
    if target is None:
        target = []
    target.append(val)
    return target

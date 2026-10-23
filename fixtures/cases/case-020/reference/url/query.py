def parse_params(qs: str) -> dict[str, list[str]]:
    result = {}
    for part in qs.split('&'):
        if '=' in part:
            k, v = part.split('=', 1)
            result.setdefault(k, []).append(v)
    return result

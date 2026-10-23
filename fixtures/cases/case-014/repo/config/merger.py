def merge_configs(base: dict, override: dict) -> dict:
    merged = base.copy()
    merged.update(override)
    return merged

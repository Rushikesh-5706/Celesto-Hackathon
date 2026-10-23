import copy

def merge_configs(base: dict, override: dict) -> dict:
    merged = copy.deepcopy(base)
    merged.update(override)
    return merged

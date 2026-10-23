DEFAULTS = {'debug': False, 'active': True}

def get_setting(key: str) -> bool:
    return DEFAULTS.get(key, False)

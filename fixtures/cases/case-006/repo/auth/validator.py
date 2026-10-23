import re

def is_valid_username(name: str) -> bool:
    return bool(re.search(r'[a-z0-9_]{3,16}', name))
